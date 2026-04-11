"""Base classes for online profile providers."""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from ..constants import HTTP_USER_AGENT, _KNOWN_VENDORS
from ..utils import guess_material, guess_brand

logger = logging.getLogger(__name__)

# SSL warning shown once per session to avoid log spam
_SSL_WARNED = False


class OnlineProfileEntry:
    """A single profile available from an online source."""

    def __init__(
        self,
        name: str,
        material: str = "",
        brand: str = "",
        printer: str = "",
        slicer: str = "",
        url: str = "",
        description: str = "",
        provider_id: str = "",
        metadata: Optional[dict] = None,
    ) -> None:
        """Initialize an online profile entry.

        Args:
            name: Profile name.
            material: PLA, PETG, ABS, etc.
            brand: Polymaker, eSUN, etc.
            printer: Target printer (e.g. "Bambu Lab X1C").
            slicer: BambuStudio, OrcaSlicer, PrusaSlicer.
            url: Download URL.
            description: Human-readable description.
            provider_id: Which provider this came from.
            metadata: Provider-specific extra data.
        """
        self.name = name
        self.material = material
        self.brand = brand
        self.printer = printer
        self.slicer = slicer
        self.url = url
        self.description = description
        self.provider_id = provider_id
        self.metadata = metadata or {}
        self.selected = False


class OnlineProvider:
    """Base class for online profile sources."""

    id: str = ""
    name: str = ""
    category: str = ""  # "Manufacturer", "Community", "Database"
    description: str = ""
    website: str = ""  # URL to source website/repo for user reference

    _ssl_ctx: Optional[ssl.SSLContext] = None  # lazily created SSL context
    _ssl_lock = __import__("threading").Lock()
    _ssl_degraded_flag: bool = (
        False  # class-level: set True when SSL verification disabled
    )

    def __init__(self) -> None:
        self._status_fn: Optional[Callable[[str], None]] = None
        self._cancel_check: Optional[Callable[[], bool]] = None
        self._ssl_degraded: bool = False

    # ------------------------------------------------------------------
    # Bundled-profile support
    # ------------------------------------------------------------------

    def _bundled_dir(self) -> Optional[Path]:
        """Return the bundled_profiles/{id} directory if it exists and has files."""
        base = getattr(
            sys, "_MEIPASS", str(Path(__file__).resolve().parent.parent.parent)
        )
        bdir = Path(base) / "bundled_profiles" / self.id
        if bdir.is_dir() and any(bdir.iterdir()):
            return bdir
        return None

    def _catalog_from_bundle(self) -> list[OnlineProfileEntry]:
        """Build a catalog from locally bundled profile files."""
        bdir = self._bundled_dir()
        if not bdir:
            return []
        entries: list[OnlineProfileEntry] = []
        files = sorted(bdir.iterdir())
        for i, fp in enumerate(files, 1):
            if fp.suffix.lower() not in (".json", ".bbsflmt", ".ini"):
                continue
            name = fp.stem.replace("_", " ")
            self._report(f"Loading bundled {self.name}: {i}/{len(files)}")
            entries.append(
                OnlineProfileEntry(
                    name=name,
                    material=guess_material(name),
                    brand=guess_brand(name),
                    url="",
                    provider_id=self.id,
                    metadata={"bundled": True, "local_path": str(fp)},
                )
            )
        return entries

    def _download_from_bundle(
        self, entry: OnlineProfileEntry
    ) -> Optional[tuple[bytes, str]]:
        """Read profile bytes from a bundled file, or return None to fall back online."""
        if entry.metadata.get("bundled") and entry.metadata.get("local_path"):
            local_path = Path(entry.metadata["local_path"])
            if local_path.is_file():
                return local_path.read_bytes(), local_path.name
        return None

    # ------------------------------------------------------------------
    # Freshness check
    # ------------------------------------------------------------------

    _manifest_cache: Optional[dict] = None  # class-level cache, read once
    _manifest_lock = __import__("threading").Lock()

    @classmethod
    def _load_manifest(cls) -> dict:
        """Read bundled_profiles/manifest.json (cached across all providers)."""
        if cls._manifest_cache is not None:
            return cls._manifest_cache
        with cls._manifest_lock:
            if cls._manifest_cache is not None:
                return cls._manifest_cache
            base = getattr(
                sys, "_MEIPASS", str(Path(__file__).resolve().parent.parent.parent)
            )
            manifest_path = Path(base) / "bundled_profiles" / "manifest.json"
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    cls._manifest_cache = json.load(f)
            except (OSError, json.JSONDecodeError, ValueError):
                cls._manifest_cache = {}
            return cls._manifest_cache

    def check_for_updates(self) -> bool:
        """Return True if remote HEAD differs from bundled commit_sha. Never raises."""
        try:
            api_base = getattr(self, "_API_BASE", "")
            if not api_base:
                return False
            # Parse owner/repo from _API_BASE (https://api.github.com/repos/owner/repo)
            parts = api_base.rstrip("/").split("/")
            if len(parts) < 2:
                return False
            owner_repo = f"{parts[-2]}/{parts[-1]}"
            manifest = self._load_manifest()
            bundled_sha = (
                manifest.get("providers", {}).get(self.id, {}).get("commit_sha", "")
            )
            if not bundled_sha:
                return False
            url = (
                f"https://api.github.com/repos/{owner_repo}/commits?sha=main&per_page=1"
            )
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": HTTP_USER_AGENT,
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            ctx = self._get_ssl_ctx()
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data and isinstance(data, list):
                remote_sha = data[0].get("sha", "")
                return remote_sha != bundled_sha
        except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
            pass
        return False

    # ------------------------------------------------------------------
    # Public API — tries bundle first, falls back to online
    # ------------------------------------------------------------------

    def fetch_catalog(
        self,
        status_fn: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> list[OnlineProfileEntry]:
        """Return catalog from bundle if available, otherwise fetch online."""
        self._status_fn = status_fn
        self._cancel_check = cancel_check
        bundled = self._bundled_dir()
        if bundled:
            self._report(f"Loading {self.name} from bundled profiles...")
            return self._catalog_from_bundle()
        return self._fetch_catalog_online(status_fn)

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        """Fetch catalog from the network. Override in subclass."""
        return []

    _MAX_PROFILE_SIZE = 10 * 1024 * 1024  # 10MB — reject obviously oversized payloads

    def download_profile(self, entry: OnlineProfileEntry) -> tuple[bytes, str]:
        """Download profile from bundle or network.

        Note: No checksum verification — see issue #85.
        """
        result = self._download_from_bundle(entry)
        if result:
            data, filename = result
        else:
            data = self._fetch_url(entry.url)
            filename = self._suggest_filename(entry)
        if len(data) > self._MAX_PROFILE_SIZE:
            raise ValueError(
                f"Profile too large ({len(data)} bytes) — rejected for safety"
            )
        return data, filename

    def _suggest_filename(self, entry: OnlineProfileEntry) -> str:
        """Generate a safe filename from the entry."""
        url_path = entry.url.split("?")[0].split("#")[0]
        ext = ".bbsflmt" if url_path.endswith(".bbsflmt") else ".json"
        safe_name = Path(
            entry.name.replace(" ", "_").replace("/", "-").replace("\\", "-")
        ).name
        safe_name = safe_name.lstrip(".").replace("\x00", "")[:200]
        return safe_name + ext

    def _report(self, msg: str) -> None:
        """Report progress if callback is set."""
        if self._status_fn:
            self._status_fn(msg)

    @classmethod
    def _get_ssl_ctx(cls) -> ssl.SSLContext:
        """Get SSL context with fallback to unverified if certs missing.

        Warning: Callers should check logs for SSL warnings indicating
        unverified connections that may be vulnerable to MITM attacks.
        """
        if cls._ssl_ctx is not None:
            return cls._ssl_ctx

        with cls._ssl_lock:
            # Double-check after acquiring lock
            if cls._ssl_ctx is not None:
                return cls._ssl_ctx
            return cls._init_ssl_ctx()

    @classmethod
    def _init_ssl_ctx(cls) -> ssl.SSLContext:
        global _SSL_WARNED
        try:
            ctx = ssl.create_default_context()
            stats = ctx.cert_store_stats()
            if stats.get("x509_ca", 0) > 0:
                cls._ssl_ctx = ctx
                return ctx
        except (ssl.SSLError, OSError):
            pass

        try:
            import certifi

            ctx = ssl.create_default_context(cafile=certifi.where())
            cls._ssl_ctx = ctx
            return ctx
        except (ImportError, ssl.SSLError, OSError):
            pass

        if not _SSL_WARNED:
            logger.warning(
                "SSL certificate verification disabled — downloads are vulnerable to MITM attacks. "
                "Install the 'certifi' package to fix this."
            )
            _SSL_WARNED = True

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        cls._ssl_ctx = ctx
        cls._ssl_degraded_flag = True
        return ctx

    def _fetch_url(
        self,
        url: str,
        timeout: int = 15,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> bytes:
        """Fetch URL and return bytes (max 50MB).

        Reads in 64KB chunks to release the GIL regularly and allow
        cancellation checks between chunks.
        """
        import time

        _MAX = 50 * 1024 * 1024
        _CHUNK = 64 * 1024
        # Encode spaces and special chars in URL path (GitHub download_urls
        # often contain unencoded spaces and '+' characters)
        url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*,;=-._~%")
        req = urllib.request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})
        ctx = self._get_ssl_ctx()
        if self.__class__._ssl_degraded_flag:
            self._ssl_degraded = True
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            total = int(resp.headers.get("Content-Length", 0) or 0)
            chunks: list[bytes] = []
            received = 0
            while True:
                if cancel_check and cancel_check():
                    raise InterruptedError("Download cancelled")
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                chunks.append(chunk)
                received += len(chunk)
                if received > _MAX:
                    raise ValueError(f"Response too large (>{_MAX} bytes)")
                # Report download progress if total size is known
                if total > 0 and received % (256 * 1024) < _CHUNK:
                    pct = min(99, int(received * 100 / total))
                    self._report(f"Downloading... {pct}% ({received // 1024}KB)")
                # Yield GIL so main thread can process events
                time.sleep(0)
            return b"".join(chunks)

    def _fetch_json(self, url: str, timeout: int = 15) -> dict | list:
        """Fetch URL and parse as JSON (max 10MB)."""
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": HTTP_USER_AGENT,
                "Accept": "application/vnd.github.v3+json",
            },
        )
        ctx = self._get_ssl_ctx()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read(self._MAX_PROFILE_SIZE + 1)
                if len(raw) > self._MAX_PROFILE_SIZE:
                    raise ValueError(f"JSON response too large ({len(raw)} bytes)")
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                logger.warning("GitHub API rate limit reached")
                raise RuntimeError("GitHub API rate limit reached. Try again later.")
            raise
