# Online profile providers (Polymaker, SimplyPrint, etc.)

from __future__ import annotations

import json
import logging
import re
import ssl
import urllib.error
import urllib.request
from typing import Callable, Optional

from .constants import HTTP_USER_AGENT, _KNOWN_VENDORS
from .utils import guess_material, guess_brand

logger = logging.getLogger(__name__)

# Module-level flag to ensure SSL warning appears only once (Fix #81)
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
    _status_fn: Optional[Callable[[str], None]] = None

    _ssl_ctx: Optional[ssl.SSLContext] = None  # lazily created SSL context

    def fetch_catalog(self, status_fn: Optional[Callable[[str], None]] = None) -> list[OnlineProfileEntry]:
        """Return list of OnlineProfileEntry. Override in subclass.

        Args:
            status_fn: Optional callback for progress updates.

        Returns:
            List of OnlineProfileEntry objects.
        """
        return []

    def download_profile(self, entry: OnlineProfileEntry) -> tuple[bytes, str]:
        """Download profile and return (raw_bytes, suggested_filename).

        Note: No integrity verification (checksum) is performed on downloaded profiles.
        Consider adding SHA256 verification if providers offer checksums (Fix #85).

        Args:
            entry: The profile entry to download.

        Returns:
            Tuple of (raw bytes, suggested filename).
        """
        data = self._fetch_url(entry.url)
        filename = self._suggest_filename(entry)
        return data, filename

    def _suggest_filename(self, entry: OnlineProfileEntry) -> str:
        """Generate a safe filename from the entry."""
        ext = ".bbsflmt" if entry.url.endswith(".bbsflmt") else ".json"
        filename = entry.name.replace(" ", "_").replace("/", "-").replace("\\", "-").replace("..", "")
        return filename + ext

    def _report(self, msg: str) -> None:
        """Report progress if callback is set."""
        if self._status_fn:
            self._status_fn(msg)

    @classmethod
    def _get_ssl_ctx(cls) -> ssl.SSLContext:
        """Get SSL context with fallback to unverified if certs missing."""
        global _SSL_WARNED

        if cls._ssl_ctx is not None:
            return cls._ssl_ctx

        try:
            ctx = ssl.create_default_context()
            stats = ctx.cert_store_stats()
            if stats.get("x509_ca", 0) > 0:
                cls._ssl_ctx = ctx
                return ctx
        except Exception:
            pass

        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
            cls._ssl_ctx = ctx
            return ctx
        except Exception:
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
        return ctx

    def _fetch_url(self, url: str, timeout: int = 15) -> bytes:
        """Fetch URL and return bytes."""
        req = urllib.request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})
        ctx = self._get_ssl_ctx()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read()

    def _fetch_json(self, url: str, timeout: int = 15) -> dict | list:
        """Fetch URL and parse as JSON."""
        req = urllib.request.Request(
            url,
            headers={"User-Agent": HTTP_USER_AGENT, "Accept": "application/vnd.github.v3+json"},
        )
        ctx = self._get_ssl_ctx()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))


class PolymakerProvider(OnlineProvider):
    """Polymaker's official preset library — scraped from their legacy wiki."""

    id = "polymaker"
    name = "Polymaker"
    category = "Manufacturer"
    description = "Official Polymaker filament presets — PLA, PETG, ABS, TPU, and specialty blends (30+)"
    website = "https://wiki.polymaker.com/polymaker-products/printer-profiles"

    _WIKI_URL = (
        "https://wiki.polymaker.com/polymaker-products/printer-profiles/legacy-profiles-by-material"
    )
    _BBSFLMT_RE = re.compile(
        r"(https://3491278982-files\.gitbook\.io/~/files/v0/b/gitbook-x-prod\.appspot\.com"
        r"/o/spaces%2FCp7LK0pgIUpVwJdO2wqk%2Fuploads%2F[^\"'<>\s]+\.bbsflmt[^\"'<>\s]*)"
    )

    def _parse_name_from_url(self, url: str) -> str:
        """Extract profile name from Gitbook URL."""
        try:
            part = url.split("%2F")[-1]
            fname = part.split(".bbsflmt")[0]
            fname = urllib.request.url2pathname(fname.replace("+", " "))
            if fname.startswith("Polymaker "):
                fname = fname[len("Polymaker ") :]
            return fname
        except Exception:
            return "Unknown Profile"

    def _ensure_alt_media(self, url: str) -> str:
        """Append ?alt=media to Gitbook URLs for raw file download."""
        if "alt=media" not in url:
            sep = "&" if "?" in url else "?"
            url = url + sep + "alt=media"
        return url

    def fetch_catalog(self, status_fn: Optional[Callable[[str], None]] = None) -> list[OnlineProfileEntry]:
        """Scrape Polymaker wiki for .bbsflmt download links."""
        self._status_fn = status_fn
        entries = []
        self._report("Connecting to Polymaker wiki...")
        try:
            html = self._fetch_url(self._WIKI_URL).decode("utf-8", errors="replace")
            self._report("Scanning for profile downloads...")
            seen = set()
            for match in self._BBSFLMT_RE.finditer(html):
                raw_url = match.group(1)
                upload_id = (
                    raw_url.split("uploads%2F")[-1].split("%2F")[0]
                    if "uploads%2F" in raw_url
                    else raw_url
                )
                if upload_id in seen:
                    continue
                seen.add(upload_id)
                url = self._ensure_alt_media(raw_url)
                name = self._parse_name_from_url(raw_url)
                entries.append(
                    OnlineProfileEntry(
                        name=name,
                        material=guess_material(name),
                        brand="Polymaker",
                        printer="",
                        slicer="BambuStudio",
                        url=url,
                        description=f"Polymaker official — {name}",
                        provider_id=self.id,
                    )
                )
            self._report(f"Found {len(entries)} Polymaker profiles")
            if not entries:
                raise RuntimeError("No profiles found on Polymaker wiki — page may have changed")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []
        return entries

    def _suggest_filename(self, entry: OnlineProfileEntry) -> str:
        filename = entry.name.replace(" ", "_").replace("/", "-").replace("\\", "-").replace("..", "")
        return filename + ".bbsflmt"


class SimplyPrintDBProvider(OnlineProvider):
    """SimplyPrint open slicer-profiles-db on GitHub.

    Uses the generated profiles/ directory which aggregates overlays and other
    data sources into hundreds of ready-to-use filament profiles.
    """

    id = "simplyprint"
    name = "SimplyPrint Slicer DB"
    category = "Database"
    description = (
        "Open slicer profile database — crowd-sourced filament settings from many brands and materials"
    )
    website = "https://github.com/SimplyPrint/slicer-profiles-db"

    _API_BASE = "https://api.github.com/repos/SimplyPrint/slicer-profiles-db"

    def _parse_profile_name(self, fname: str) -> tuple[str, str]:
        """Parse 'Bambu PLA Basic @BBL P1S 0.4 nozzle' style names."""
        printer = ""
        if " @" in fname:
            parts = fname.split(" @", 1)
            fname_clean = parts[0]
            printer = parts[1].strip()
        else:
            fname_clean = fname
        return fname_clean, printer

    def fetch_catalog(self, status_fn: Optional[Callable[[str], None]] = None) -> list[OnlineProfileEntry]:
        """Fetch profile listings from the generated profiles directory."""
        self._status_fn = status_fn
        entries = []
        self._report("Connecting to GitHub (SimplyPrint DB)...")
        try:
            url = f"{self._API_BASE}/contents/profiles/bambustudio/BBL/filament"
            items = self._fetch_json(url)
            self._report("Parsing profile listings...")
            if not isinstance(items, list):
                raise RuntimeError("Unexpected response from GitHub API (may be rate-limited)")
            for item in items:
                if item.get("type") == "file" and item["name"].endswith(".json"):
                    raw_name = item["name"].replace(".json", "")
                    display_name, printer = self._parse_profile_name(raw_name)
                    entries.append(
                        OnlineProfileEntry(
                            name=raw_name,
                            material=guess_material(raw_name),
                            brand=guess_brand(raw_name),
                            printer=printer,
                            slicer="BambuStudio",
                            url=item.get("download_url", ""),
                            description=f"SimplyPrint DB — {display_name}",
                            provider_id=self.id,
                        )
                    )
            self._report(f"Found {len(entries)} SimplyPrint profiles")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []
        return entries

    def _suggest_filename(self, entry: OnlineProfileEntry) -> str:
        filename = entry.name.replace(" ", "_").replace("/", "-").replace("\\", "-").replace("..", "")
        return filename + ".json"


class OrcaSlicerLibraryProvider(OnlineProvider):
    """OrcaSlicer's built-in filament library from GitHub.

    Verified: 700+ JSON filament presets with direct download_url fields.
    """

    id = "orcalibrary"
    name = "OrcaSlicer Built-in Library"
    category = "Database"
    description = (
        "Built-in OrcaSlicer filament library — 700+ presets covering most popular brands and materials"
    )
    website = "https://github.com/SoftFever/OrcaSlicer"

    _API_BASE = "https://api.github.com/repos/SoftFever/OrcaSlicer"

    def fetch_catalog(self, status_fn: Optional[Callable[[str], None]] = None) -> list[OnlineProfileEntry]:
        """Fetch catalog from OrcaSlicer GitHub repository."""
        self._status_fn = status_fn
        entries = []
        self._report("Connecting to GitHub (OrcaSlicer)...")
        try:
            url = f"{self._API_BASE}/contents/resources/profiles/OrcaFilamentLibrary/filament"
            items = self._fetch_json(url)
            self._report("Parsing profile listings...")
            if not isinstance(items, list):
                raise RuntimeError("Unexpected response from GitHub API (may be rate-limited)")
            for item in items:
                if item.get("type") == "file" and item["name"].endswith(".json"):
                    fname = item["name"].replace(".json", "")
                    printer = ""
                    if " @" in fname:
                        printer = fname.split(" @", 1)[1].strip()
                    entries.append(
                        OnlineProfileEntry(
                            name=fname,
                            material=guess_material(fname),
                            brand=guess_brand(fname),
                            printer=printer,
                            slicer="OrcaSlicer",
                            url=item.get("download_url", ""),
                            description="OrcaSlicer built-in filament preset",
                            provider_id=self.id,
                        )
                    )
            self._report(f"Found {len(entries)} OrcaSlicer profiles")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []
        return entries

    def _suggest_filename(self, entry: OnlineProfileEntry) -> str:
        filename = entry.name.replace(" ", "_").replace("/", "-").replace("\\", "-").replace("..", "")
        return filename + ".json"


class ColorFabbProvider(OnlineProvider):
    """colorFabb's official profiles for BambuStudio and OrcaSlicer."""

    id = "colorfabb"
    name = "colorFabb"
    category = "Manufacturer"
    description = (
        "Official colorFabb profiles for BambuStudio & OrcaSlicer — HT, nGen, PETG, woodFill, and more (~96)"
    )
    website = "https://github.com/colorfabb/printer-profiles"

    _API_BASE = "https://api.github.com/repos/colorfabb/printer-profiles"

    def fetch_catalog(self, status_fn: Optional[Callable[[str], None]] = None) -> list[OnlineProfileEntry]:
        """Fetch profiles from colorFabb GitHub repository."""
        self._status_fn = status_fn
        entries = []
        for slicer, slicer_label in [("BambuStudio", "BambuStudio"), ("OrcaSlicer", "OrcaSlicer")]:
            for ptype in ("filament", "process"):
                self._report(f"Fetching {slicer_label} {ptype} profiles...")
                try:
                    url = f"{self._API_BASE}/contents/{slicer}/{ptype}"
                    items = self._fetch_json(url)
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        if item.get("type") == "file" and item["name"].endswith(".json"):
                            fname = item["name"].replace(".json", "")
                            printer = ""
                            if " @" in fname:
                                printer = fname.split(" @", 1)[1].strip()
                            entries.append(
                                OnlineProfileEntry(
                                    name=fname,
                                    material=guess_material(fname),
                                    brand="colorFabb",
                                    printer=printer,
                                    slicer=slicer_label,
                                    url=item.get("download_url", ""),
                                    description=f"colorFabb official — {fname}",
                                    provider_id=self.id,
                                )
                            )
                except (urllib.error.URLError, urllib.error.HTTPError) as e:
                    logger.error("Failed to fetch catalog from %s: %s", self.name, e)
        self._report(f"Found {len(entries)} colorFabb profiles")
        if not entries:
            raise RuntimeError("No profiles found — colorFabb repo may have changed")
        return entries

    def _suggest_filename(self, entry: OnlineProfileEntry) -> str:
        filename = entry.name.replace(" ", "_").replace("/", "-").replace("\\", "-").replace("..", "")
        return filename + ".json"


class BambuStudioOfficialProvider(OnlineProvider):
    """BambuStudio's official built-in BBL filament profiles from GitHub."""

    id = "bambustudio_official"
    name = "BambuStudio Official (BBL)"
    category = "Database"
    description = (
        "Default Bambu Lab filament presets shipped with BambuStudio — clean baselines for all BBL materials (200+)"
    )
    website = "https://github.com/bambulab/BambuStudio"

    _API_BASE = "https://api.github.com/repos/bambulab/BambuStudio"

    def fetch_catalog(self, status_fn: Optional[Callable[[str], None]] = None) -> list[OnlineProfileEntry]:
        """Fetch official BambuStudio profiles from GitHub."""
        self._status_fn = status_fn
        entries = []
        self._report("Connecting to GitHub (BambuStudio official)...")
        try:
            url = f"{self._API_BASE}/contents/resources/profiles/BBL/filament"
            items = self._fetch_json(url)
            if not isinstance(items, list):
                raise RuntimeError("Unexpected response from GitHub API")
            self._report(f"Found {len(items)} items, scanning...")
            for item in items:
                if item.get("type") == "dir":
                    self._report(f"Scanning {item['name']}...")
                    try:
                        sub_items = self._fetch_json(item["url"])
                        if isinstance(sub_items, list):
                            for sub in sub_items:
                                if sub.get("type") == "file" and sub["name"].endswith(".json"):
                                    fname = sub["name"].replace(".json", "")
                                    printer = ""
                                    if " @" in fname:
                                        printer = fname.split(" @", 1)[1].strip()
                                    entries.append(
                                        OnlineProfileEntry(
                                            name=fname,
                                            material=guess_material(fname),
                                            brand=guess_brand(fname) or "Bambu",
                                            printer=printer,
                                            slicer="BambuStudio",
                                            url=sub.get("download_url", ""),
                                            description="BambuStudio official filament preset",
                                            provider_id=self.id,
                                        )
                                    )
                    except (urllib.error.URLError, urllib.error.HTTPError) as e:
                        logger.error("Failed to fetch catalog from %s: %s", self.name, e)
                elif item.get("type") == "file" and item["name"].endswith(".json"):
                    fname = item["name"].replace(".json", "")
                    printer = ""
                    if " @" in fname:
                        printer = fname.split(" @", 1)[1].strip()
                    entries.append(
                        OnlineProfileEntry(
                            name=fname,
                            material=guess_material(fname),
                            brand=guess_brand(fname) or "Bambu",
                            printer=printer,
                            slicer="BambuStudio",
                            url=item.get("download_url", ""),
                            description="BambuStudio official filament preset",
                            provider_id=self.id,
                        )
                    )
            self._report(f"Found {len(entries)} BambuStudio official profiles")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []
        return entries

    def _suggest_filename(self, entry: OnlineProfileEntry) -> str:
        filename = entry.name.replace(" ", "_").replace("/", "-").replace("\\", "-").replace("..", "")
        return filename + ".json"


class CommunityPresetsProvider(OnlineProvider):
    """DR. Ignaz Gortngschirl's curated BambuStudio/OrcaSlicer community presets."""

    id = "community_presets"
    name = "Community Presets (DR. Ignaz)"
    category = "Community"
    description = (
        "Curated community collection — filament, machine, and process presets for BambuStudio & OrcaSlicer (~140)"
    )
    website = "https://github.com/DRIgnazGortngschirl/bambulab-studio-orca-slicer-presets"

    _API_BASE = "https://api.github.com/repos/DRIgnazGortngschirl/bambulab-studio-orca-slicer-presets"

    def fetch_catalog(self, status_fn: Optional[Callable[[str], None]] = None) -> list[OnlineProfileEntry]:
        """Fetch community presets from GitHub."""
        self._status_fn = status_fn
        entries = []
        for ptype in ("filament", "machine", "process"):
            self._report(f"Fetching {ptype} profiles...")
            try:
                url = f"{self._API_BASE}/contents/{ptype}"
                items = self._fetch_json(url)
                if not isinstance(items, list):
                    continue
                for item in items:
                    if item.get("type") == "file" and item["name"].endswith(".json"):
                        fname = item["name"].replace(".json", "")
                        printer = ""
                        if " @" in fname:
                            printer = fname.split(" @", 1)[1].strip()
                        entries.append(
                            OnlineProfileEntry(
                                name=fname,
                                material=guess_material(fname) if ptype == "filament" else "",
                                brand=guess_brand(fname),
                                printer=printer,
                                slicer="OrcaSlicer",
                                url=item.get("download_url", ""),
                                description=f"Community preset ({ptype}) — {fname}",
                                provider_id=self.id,
                                metadata={"profile_type": ptype},
                            )
                        )
            except (urllib.error.URLError, urllib.error.HTTPError) as e:
                logger.error("Failed to fetch catalog from %s: %s", self.name, e)
        self._report(f"Found {len(entries)} community presets")
        if not entries:
            raise RuntimeError("No profiles found — community presets repo may have changed")
        return entries

    def _suggest_filename(self, entry: OnlineProfileEntry) -> str:
        filename = entry.name.replace(" ", "_").replace("/", "-").replace("\\", "-").replace("..", "")
        return filename + ".json"


class SantanachiaProvider(OnlineProvider):
    """Santanachia's BambuStudio custom filament profiles (.bbsflmt and JSON)."""

    id = "santanachia"
    name = "Santanachia Custom Filaments"
    category = "Community"
    description = (
        "Community-tested filament profiles for eSUN, KINGROON, and other third-party brands on Bambu printers"
    )
    website = "https://github.com/Santanachia/BambuStudio_CustomFilaments"

    _API_BASE = "https://api.github.com/repos/Santanachia/BambuStudio_CustomFilaments"

    def fetch_catalog(self, status_fn: Optional[Callable[[str], None]] = None) -> list[OnlineProfileEntry]:
        """Fetch Santanachia custom filament profiles from GitHub."""
        self._status_fn = status_fn
        entries = []
        self._report("Connecting to GitHub (Santanachia)...")
        try:
            top = self._fetch_json(f"{self._API_BASE}/contents")
            if not isinstance(top, list):
                raise RuntimeError("Unexpected response from GitHub API")
            dirs = [item for item in top if item.get("type") == "dir" and item["name"] not in (".github", "__pycache__")]
            for d in dirs:
                brand_name = d["name"]
                self._report(f"Scanning {brand_name}...")
                try:
                    items = self._fetch_json(d["url"])
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        if item.get("type") == "file":
                            fname = item["name"]
                            if fname.endswith(".json"):
                                display = fname.replace(".json", "")
                                entries.append(
                                    OnlineProfileEntry(
                                        name=display,
                                        material=guess_material(display),
                                        brand=brand_name,
                                        printer="",
                                        slicer="BambuStudio",
                                        url=item.get("download_url", ""),
                                        description=f"Santanachia — {brand_name} — {display}",
                                        provider_id=self.id,
                                    )
                                )
                            elif fname.endswith(".bbsflmt"):
                                display = fname.replace(".bbsflmt", "")
                                entries.append(
                                    OnlineProfileEntry(
                                        name=display,
                                        material=guess_material(display),
                                        brand=brand_name,
                                        printer="",
                                        slicer="BambuStudio",
                                        url=item.get("download_url", ""),
                                        description=f"Santanachia — {brand_name} — {display}",
                                        provider_id=self.id,
                                    )
                                )
                        elif item.get("type") == "dir":
                            sub_name = item["name"]
                            try:
                                sub_items = self._fetch_json(item["url"])
                                if isinstance(sub_items, list):
                                    for si in sub_items:
                                        if si.get("type") == "file" and (
                                            si["name"].endswith(".json")
                                            or si["name"].endswith(".bbsflmt")
                                        ):
                                            ext = (
                                                ".json" if si["name"].endswith(".json") else ".bbsflmt"
                                            )
                                            display = si["name"].replace(ext, "")
                                            entries.append(
                                                OnlineProfileEntry(
                                                    name=display,
                                                    material=guess_material(display),
                                                    brand=brand_name,
                                                    printer=sub_name,
                                                    slicer="BambuStudio",
                                                    url=si.get("download_url", ""),
                                                    description=f"Santanachia — {brand_name}/{sub_name} — {display}",
                                                    provider_id=self.id,
                                                )
                                            )
                            except (urllib.error.URLError, urllib.error.HTTPError) as e:
                                logger.error("Failed to fetch catalog from %s: %s", self.name, e)
                except (urllib.error.URLError, urllib.error.HTTPError) as e:
                    logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            self._report(f"Found {len(entries)} Santanachia profiles")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []
        return entries

    def _suggest_filename(self, entry: OnlineProfileEntry) -> str:
        ext = ".bbsflmt" if ".bbsflmt" in entry.description else ".json"
        filename = entry.name.replace(" ", "_").replace("/", "-").replace("\\", "-").replace("..", "")
        return filename + ext


class DgaucheFilamentLibProvider(OnlineProvider):
    """dgauche's BambuStudio Filament Library — community profiles by printer model."""

    id = "dgauche_filament_lib"
    name = "BambuStudio Filament Library (dgauche)"
    category = "Community"
    description = (
        "Community filament & process profiles organized by printer — P1P, X1, X1C, and Creality K1 (~50+)"
    )
    website = "https://github.com/dgauche/BambuStudioFilamentLibrary"

    _API_BASE = "https://api.github.com/repos/dgauche/BambuStudioFilamentLibrary"

    def fetch_catalog(self, status_fn: Optional[Callable[[str], None]] = None) -> list[OnlineProfileEntry]:
        """Fetch dgauche filament library profiles from GitHub."""
        self._status_fn = status_fn
        entries = []
        self._report("Connecting to GitHub (dgauche FilamentLibrary)...")
        try:
            top = self._fetch_json(f"{self._API_BASE}/contents")
            if not isinstance(top, list):
                raise RuntimeError("Unexpected response from GitHub API")
            dirs = [
                item
                for item in top
                if item.get("type") == "dir" and item["name"] not in (".github", "__pycache__")
            ]
            for d in dirs:
                printer_name = d["name"]
                self._report(f"Scanning {printer_name}...")
                try:
                    items = self._fetch_json(d["url"])
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        if item.get("type") != "file":
                            continue
                        fname = item["name"]
                        if not (fname.endswith(".json") or fname.endswith(".bbsflmt")):
                            continue
                        ext = ".bbsflmt" if fname.endswith(".bbsflmt") else ".json"
                        display = fname.replace(ext, "")
                        ptype = "filament"
                        if "Process" in fname:
                            ptype = "process"
                        elif "Machine" in fname:
                            ptype = "machine"
                        entries.append(
                            OnlineProfileEntry(
                                name=display,
                                material=guess_material(display),
                                brand=guess_brand(display),
                                printer=printer_name,
                                slicer="BambuStudio",
                                url=item.get("download_url", ""),
                                description=f"dgauche — {printer_name} — {display}",
                                provider_id=self.id,
                                metadata={"profile_type": ptype},
                            )
                        )
                except (urllib.error.URLError, urllib.error.HTTPError) as e:
                    logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            self._report(f"Found {len(entries)} dgauche profiles")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []
        return entries

    def _suggest_filename(self, entry: OnlineProfileEntry) -> str:
        ext = ".bbsflmt" if entry.url.endswith(".bbsflmt") else ".json"
        filename = entry.name.replace(" ", "_").replace("/", "-").replace("\\", "-").replace("..", "")
        return filename + ext


# Provider registry — only sources with verified direct-download URLs.
# Sources removed (URLs were HTML pages, not downloadable profiles):
#   eSUN, 3DJake, Coex3D, QIDI, MakerWorld, Printables, 3DFilamentProfiles
ALL_PROVIDERS: list[OnlineProvider] = [
    PolymakerProvider(),
    ColorFabbProvider(),
    SimplyPrintDBProvider(),
    OrcaSlicerLibraryProvider(),
    BambuStudioOfficialProvider(),
    CommunityPresetsProvider(),
    SantanachiaProvider(),
    DgaucheFilamentLibProvider(),
]

PROVIDER_CATEGORIES: list[str] = ["Manufacturer", "Database", "Community"]
