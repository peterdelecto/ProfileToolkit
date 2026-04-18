"""Base classes for online profile providers."""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from ..constants import HTTP_USER_AGENT
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
        self.nozzle = "0.4"  # standard nozzle default
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

    @property
    def source_hint(self) -> str:
        """Short domain hint for UI display, e.g. 'github.com/prusa3d'."""
        if not self.website:
            return ""
        from urllib.parse import urlparse

        parsed = urlparse(self.website)
        host = parsed.netloc or ""
        path_parts = [p for p in parsed.path.split("/") if p]
        if host.endswith("github.com") and path_parts:
            return f"github.com/{path_parts[0]}"
        return host

    _ssl_ctx: Optional[ssl.SSLContext] = None  # lazily created SSL context
    _ssl_lock = threading.Lock()
    _ssl_degraded_flag: bool = (
        False  # class-level: set True when SSL verification disabled
    )

    _DEFAULT_BRANCH: str = "main"  # override to "master" for repos using it

    _CATALOG_CACHE_TTL = 24 * 3600  # 24 hours

    def __init__(self) -> None:
        self._status_fn: Optional[Callable[[str], None]] = None
        self._cancel_check: Optional[Callable[[], bool]] = None
        self._ssl_degraded: bool = False

    def clear_cache(self) -> None:
        """Clear any cached data so the next fetch is fresh. Override in subclass."""
        cache_path = self._catalog_cache_path()
        if cache_path.exists():
            cache_path.unlink(missing_ok=True)

    @classmethod
    def _cache_dir(cls) -> Path:
        """Return writable cache directory for catalog data."""
        if sys.platform == "darwin":
            d = Path.home() / "Library" / "Caches" / "ProfileToolkit"
        elif sys.platform == "win32":
            d = (
                Path(os.environ.get("LOCALAPPDATA", Path.home()))
                / "ProfileToolkit"
                / "cache"
            )
        else:
            d = Path.home() / ".cache" / "ProfileToolkit"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _catalog_cache_path(self) -> Path:
        return self._cache_dir() / f"catalog_{self.id}.json"

    def _save_catalog_cache(self, entries: list[OnlineProfileEntry]) -> None:
        """Save catalog to disk cache."""
        data = {
            "timestamp": time.time(),
            "entries": [
                {
                    "name": e.name,
                    "material": e.material,
                    "brand": e.brand,
                    "printer": e.printer,
                    "nozzle": e.nozzle,
                    "slicer": e.slicer,
                    "url": e.url,
                    "description": e.description,
                    "provider_id": e.provider_id,
                    "metadata": e.metadata,
                }
                for e in entries
            ],
        }
        try:
            self._catalog_cache_path().write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            logger.debug("Cache write failed", exc_info=True)

    def _load_catalog_cache(self) -> Optional[list[OnlineProfileEntry]]:
        """Load catalog from disk cache if fresh enough."""
        path = self._catalog_cache_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - data.get("timestamp", 0)
            if age > self._CATALOG_CACHE_TTL:
                return None
            entries = []
            for d in data.get("entries", []):
                e = OnlineProfileEntry(
                    name=d["name"],
                    material=d.get("material", ""),
                    brand=d.get("brand", ""),
                    printer=d.get("printer", ""),
                    slicer=d.get("slicer", ""),
                    url=d.get("url", ""),
                    description=d.get("description", ""),
                    provider_id=d.get("provider_id", ""),
                    metadata=d.get("metadata", {}),
                )
                e.nozzle = d.get("nozzle", "") or "0.4"
                entries.append(e)
            return entries
        except (OSError, json.JSONDecodeError, KeyError):
            logger.debug("Cache read failed", exc_info=True)
            return None

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
            if not local_path.is_absolute() or ".." in local_path.parts:
                logger.warning("Suspicious cache path rejected: %s", local_path)
                return None
            if local_path.is_file():
                return local_path.read_bytes(), local_path.name
        return None

    # ------------------------------------------------------------------
    # Freshness check
    # ------------------------------------------------------------------

    _manifest_cache: Optional[dict] = None  # class-level cache, read once
    _manifest_lock = threading.Lock()

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
                logger.debug("Manifest read failed", exc_info=True)
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
            url = f"https://api.github.com/repos/{owner_repo}/commits?sha={self._DEFAULT_BRANCH}&per_page=1"
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
            logger.debug("Update check failed", exc_info=True)
        return False

    # ------------------------------------------------------------------
    # Public API — tries online first, falls back to bundle
    # ------------------------------------------------------------------

    def fetch_catalog(
        self,
        status_fn: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> list[OnlineProfileEntry]:
        """Return catalog: cache → online → bundled fallback."""
        self._status_fn = status_fn
        self._cancel_check = cancel_check
        try:
            # 1. Check disk cache (fast, <24h old)
            cached = self._load_catalog_cache()
            if cached:
                self._report(f"Loaded {len(cached)} {self.name} profiles from cache")
                return cached
            # 2. Try online (fresh)
            try:
                catalog = self._fetch_catalog_online(status_fn)
                if catalog:
                    self._save_catalog_cache(catalog)
                    return catalog
            except (
                OSError,
                urllib.error.URLError,
                json.JSONDecodeError,
                ValueError,
                KeyError,
            ) as e:
                logger.warning("Online fetch failed for %s: %s", self.name, e)
            # 3. Fall back to bundled profiles (offline)
            bundled = self._bundled_dir()
            if bundled:
                self._report(f"Loading {self.name} from bundled profiles (offline)...")
                return self._catalog_from_bundle()
            return []
        finally:
            self._status_fn = None
            self._cancel_check = None

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        """Fetch catalog from the network. Override in subclass."""
        return []

    _MAX_PROFILE_SIZE = 10 * 1024 * 1024  # 10MB — reject obviously oversized payloads

    def download_profile(self, entry: OnlineProfileEntry) -> tuple[bytes, str]:
        """Download profile from bundle or network."""
        result = self._download_from_bundle(entry)
        if result:
            data, filename = result
        else:
            data = self._fetch_url(entry.url, max_size=self._MAX_PROFILE_SIZE)
            filename = self._suggest_filename(entry)
            # Validate network-downloaded content is well-formed
            self._validate_profile_content(data, filename)
        if len(data) > self._MAX_PROFILE_SIZE:
            raise ValueError(
                f"Profile too large ({len(data)} bytes) — rejected for safety"
            )
        return data, filename

    def _validate_profile_content(self, data: bytes, filename: str) -> None:
        """Validate that profile content is well-formed."""
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"Profile is not valid UTF-8 text: {filename}")
        lower = filename.lower()
        if lower.endswith(".json") or lower.endswith(".bbsflmt"):
            try:
                json.loads(text)
            except json.JSONDecodeError as e:
                raise ValueError(f"Profile is not valid JSON: {filename}: {e}") from e

    def _suggest_filename(self, entry: OnlineProfileEntry) -> str:
        """Generate a safe filename from the entry."""
        url_path = entry.url.split("?")[0].split("#")[0]
        if url_path.endswith(".bbsflmt"):
            ext = ".bbsflmt"
        elif url_path.endswith(".ini"):
            ext = ".ini"
        else:
            ext = ".json"
        # Sanitize: replace spaces, path seps, and Windows-illegal characters
        safe_name = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", entry.name.replace(" ", "_"))
        safe_name = Path(safe_name).name.lstrip(".")[:200]
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

    @classmethod
    def ssl_is_degraded(cls) -> bool:
        """Return True if SSL verification is disabled (MITM vulnerability)."""
        with cls._ssl_lock:
            return cls._ssl_degraded_flag

    def _fetch_url(
        self,
        url: str,
        timeout: int = 15,
        cancel_check: Optional[Callable[[], bool]] = None,
        max_size: int = 0,
    ) -> bytes:
        """Fetch URL and return bytes.

        Reads in 64KB chunks to release the GIL regularly and allow
        cancellation checks between chunks.
        """
        _MAX = max_size or (50 * 1024 * 1024)
        _CHUNK = 64 * 1024
        # Encode spaces and special chars in URL path (GitHub download_urls
        # often contain unencoded spaces and '+' characters)
        url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*,;=-._~%")
        req = urllib.request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})
        ctx = self._get_ssl_ctx()
        if self.__class__.ssl_is_degraded():
            self._ssl_degraded = True
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            total = int(resp.headers.get("Content-Length", 0) or 0)
            if total > _MAX:
                raise ValueError(f"Response too large ({total} bytes, limit {_MAX})")
            chunks: list[bytes] = []
            received = 0
            chunk_count = 0
            while True:
                if cancel_check and cancel_check():
                    raise InterruptedError("Download cancelled")
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                chunks.append(chunk)
                received += len(chunk)
                chunk_count += 1
                if received > _MAX:
                    raise ValueError(f"Response too large (>{_MAX} bytes)")
                # Report download progress if total size is known
                if total > 0 and received % (256 * 1024) < _CHUNK:
                    pct = min(99, int(received * 100 / total))
                    self._report(f"Downloading... {pct}% ({received // 1024}KB)")
                # Yield GIL every 64 chunks so main thread can process events
                if chunk_count % 64 == 0:
                    time.sleep(0)
            return b"".join(chunks)

    def _fetch_git_tree(
        self, owner_repo: str, path_prefix: str, branch: str = "main"
    ) -> list[dict]:
        """Fetch full recursive file tree from GitHub, filtered by path prefix.

        Uses /git/trees?recursive=1 which returns all files with no 1000-item cap.
        Returns list of {path, url} dicts for files matching path_prefix.
        """
        url = (
            f"https://api.github.com/repos/{owner_repo}/git/trees/{branch}?recursive=1"
        )
        data = self._fetch_json(url, timeout=30, max_size=50 * 1024 * 1024)
        if not isinstance(data, dict) or "tree" not in data:
            raise RuntimeError("Unexpected git tree response")
        if data.get("truncated"):
            logger.warning(
                "Git tree truncated for %s/%s — some profiles may be missing",
                owner_repo,
                path_prefix,
            )
        prefix = path_prefix.rstrip("/") + "/"
        return [
            node
            for node in data["tree"]
            if node.get("type") == "blob" and node.get("path", "").startswith(prefix)
        ]

    def _fetch_json(
        self, url: str, timeout: int = 15, max_size: int = 0, retries: int = 1
    ) -> dict | list:
        """Fetch URL and parse as JSON. Retries once on transient errors."""
        if retries < 0:
            retries = 0
        limit = max_size or self._MAX_PROFILE_SIZE
        req_headers = {
            "User-Agent": HTTP_USER_AGENT,
            "Accept": "application/vnd.github.v3+json",
        }
        ctx = self._get_ssl_ctx()
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(url, headers=req_headers)
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                    raw = resp.read(limit + 1)
                    if len(raw) > limit:
                        raise ValueError(f"JSON response too large ({len(raw)} bytes)")
                    return json.loads(raw.decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):
                    logger.warning("GitHub API rate limit reached")
                    raise RuntimeError(
                        "GitHub API rate limit reached. Try again later."
                    )
                if e.code >= 500 and attempt < retries:
                    delay = 2 * (2**attempt)  # exponential backoff: 2s, 4s, 8s...
                    time.sleep(delay)
                    last_err = e
                    continue
                raise
            except (urllib.error.URLError, OSError) as e:
                if attempt < retries:
                    time.sleep(2)
                    last_err = e
                    continue
                raise
        raise last_err  # type: ignore[misc]
