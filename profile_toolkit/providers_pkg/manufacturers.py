"""Manufacturer profile providers (Polymaker, ColorFabb, Prusa)."""

from __future__ import annotations

import logging
import os
import re
import urllib.error
import urllib.request
from typing import Callable, Optional

from .base import OnlineProvider, OnlineProfileEntry
from ..utils import guess_material, guess_brand

logger = logging.getLogger(__name__)


class PolymakerProvider(OnlineProvider):
    """Polymaker's official preset library — scraped from their legacy wiki."""

    id = "polymaker"
    name = "Polymaker"
    category = "Manufacturer"
    description = "Official Polymaker filament presets — PLA, PETG, ABS, TPU, and specialty blends (30+)"
    website = "https://wiki.polymaker.com/polymaker-products/printer-profiles"

    _WIKI_URL = "https://wiki.polymaker.com/polymaker-products/printer-profiles/legacy-profiles-by-material"
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
        except (IndexError, ValueError):
            return "Unknown Profile"

    def _ensure_alt_media(self, url: str) -> str:
        """Append ?alt=media to Gitbook URLs for raw file download."""
        if "alt=media" not in url:
            sep = "&" if "?" in url else "?"
            url = url + sep + "alt=media"
        return url

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        """Scrape Polymaker wiki for .bbsflmt download links."""
        self._status_fn = status_fn
        entries = []
        self._report("Connecting to Polymaker wiki...")
        try:
            html = self._fetch_url(self._WIKI_URL).decode("utf-8", errors="replace")
            self._report("Scanning for profile downloads...")
            try:
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
            except Exception as parse_err:
                logger.error("Polymaker wiki HTML parsing failed: %s", parse_err)
                return []
            self._report(f"Found {len(entries)} Polymaker profiles")
            if not entries:
                raise RuntimeError(
                    "No profiles found on Polymaker wiki — page may have changed"
                )
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []
        return entries


class ColorFabbProvider(OnlineProvider):
    """colorFabb's official profiles for BambuStudio and OrcaSlicer."""

    id = "colorfabb"
    name = "colorFabb"
    category = "Manufacturer"
    description = "Official colorFabb profiles for BambuStudio & OrcaSlicer — HT, nGen, PETG, woodFill, and more (~96)"
    website = "https://github.com/colorfabb/printer-profiles"

    _API_BASE = "https://api.github.com/repos/colorfabb/printer-profiles"

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        """Fetch profiles from colorFabb GitHub repository."""
        self._status_fn = status_fn
        entries = []
        for slicer, slicer_label in [
            ("BambuStudio", "BambuStudio"),
            ("OrcaSlicer", "OrcaSlicer"),
        ]:
            for ptype in ("filament", "process"):
                self._report(f"Fetching {slicer_label} {ptype} profiles...")
                try:
                    url = f"{self._API_BASE}/contents/{slicer}/{ptype}"
                    items = self._fetch_json(url)
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        if item.get("type") == "file" and item["name"].endswith(
                            ".json"
                        ):
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


class PrusaResearchProvider(OnlineProvider):
    """Official Prusament and generic filament presets from PrusaSlicer's factory bundle.

    Downloads the monolithic PrusaResearch.ini bundle from GitHub, parses it
    with ProfileEngine.parse_prusa_bundle(), and exposes each concrete filament
    section as an individual profile entry.  Inheritance is fully resolved at
    download time so imported profiles are self-contained.
    """

    id = "prusaresearch"
    name = "Prusa (Experimental)"
    category = "Manufacturer"
    description = (
        "Official Prusament & generic presets from Prusa's factory bundle (200+)"
    )
    website = "https://github.com/prusa3d/PrusaSlicer"

    _BUNDLE_URL = (
        "https://raw.githubusercontent.com/prusa3d/PrusaSlicer/"
        "master/resources/profiles/PrusaResearch.ini"
    )

    def __init__(self) -> None:
        super().__init__()
        self._bundle_lock = __import__("threading").Lock()
        self._cached_raw: bytes | None = None
        self._cached_sections: dict | None = None

    def _fetch_bundle_raw(
        self, cancel_check: Callable[[], bool] | None = None
    ) -> bytes:
        """Download the raw bundle bytes, caching the result."""
        if self._cached_raw is not None:
            return self._cached_raw
        with self._bundle_lock:
            if self._cached_raw is not None:
                return self._cached_raw
            self._report("Downloading PrusaResearch bundle...")
            self._cached_raw = self._fetch_url(
                self._BUNDLE_URL, timeout=30, cancel_check=cancel_check
            )
        return self._cached_raw

    def _scan_filament_names(self, raw: bytes) -> list[str]:
        """Extract filament section names from raw bundle without full parse."""
        names = []
        prefix = b"[filament:"
        for line in raw.split(b"\n"):
            if line.startswith(prefix):
                close = line.find(b"]", len(prefix))
                if close > 0:
                    name = (
                        line[len(prefix) : close]
                        .decode("utf-8", errors="replace")
                        .strip()
                    )
                    # Skip abstract sections like *common*
                    if not (name.startswith("*") and name.endswith("*")):
                        names.append(name)
        return sorted(names)

    def _get_parsed_sections(
        self, cancel_check: Callable[[], bool] | None = None
    ) -> dict:
        """Full parse of bundle (for download/import). Cached after first call."""
        if self._cached_sections is not None:
            return self._cached_sections
        raw = self._fetch_bundle_raw(cancel_check=cancel_check)
        import tempfile as _tmp

        fd, tmp_path = _tmp.mkstemp(suffix=".ini")
        fd_closed = False
        try:
            os.write(fd, raw)
            os.close(fd)
            fd_closed = True
            from ..models import ProfileEngine

            self._cached_sections = ProfileEngine.parse_prusa_bundle(
                tmp_path, only="filaments"
            )
        except Exception:
            logger.exception("Failed to parse Prusa bundle")
            raise
        finally:
            if not fd_closed:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return self._cached_sections or {}

    _PRINTER_ALIASES = {
        "PG": "Planetary Gear",
        "COREONE": "Core One",
        "XL": "XL",
        "HT90": "HT90",
        "MINI": "Mini",
        "MINI+": "Mini+",
        "MK2S": "MK2S",
        "MK2.5": "MK2.5",
        "MK2.5S": "MK2.5S",
        "MK3": "MK3",
        "MK3S": "MK3S",
        "MK3S+": "MK3S+",
        "MK3.5": "MK3.5",
        "MK3.5S": "MK3.5S",
        "MK4": "MK4",
        "MK4S": "MK4S",
    }

    def _expand_printer(self, raw: str) -> str:
        """Expand printer alias from section name, e.g. 'PG 0.8' → 'MK4/XL 0.8'."""
        parts = raw.split(None, 1)
        if not parts:
            return raw
        alias = parts[0].upper().replace("@", "")
        expanded = self._PRINTER_ALIASES.get(alias, parts[0])
        nozzle = parts[1] if len(parts) > 1 else ""
        return f"{expanded} {nozzle}".strip()

    def _extract_brand(self, name: str) -> str:
        """Extract brand from filament section name."""
        brand = guess_brand(name)
        if brand:
            return brand
        if "Prusament" in name:
            return "Prusament"
        if name.lower().startswith("generic"):
            return "Generic"
        # First word as fallback
        return name.split()[0] if name.split() else ""

    def _catalog_from_bundle(self) -> list[OnlineProfileEntry]:
        """Build catalog from bundled .ini files with Prusa-specific parsing."""
        bdir = self._bundled_dir()
        if not bdir:
            return []
        entries: list[OnlineProfileEntry] = []
        files = sorted(bdir.iterdir())
        total = len(files)
        for i, fp in enumerate(files, 1):
            if fp.suffix.lower() != ".ini":
                continue
            if i % 200 == 0:
                self._report(f"Loading bundled Prusa: {i}/{total}...")
            # Reconstruct section name from filename
            name = fp.stem.replace("_", " ")
            material = guess_material(name) or "Unknown"
            brand = self._extract_brand(name)
            raw_printer = name.split("@", 1)[1].strip() if "@" in name else ""
            printer = self._expand_printer(raw_printer) if raw_printer else ""
            entries.append(
                OnlineProfileEntry(
                    name=name,
                    material=material,
                    brand=brand,
                    printer=printer,
                    slicer="PrusaSlicer",
                    url="",
                    description=f"PrusaSlicer factory preset — {name}",
                    provider_id=self.id,
                    metadata={"bundled": True, "local_path": str(fp)},
                )
            )
        self._report(f"Found {len(entries)} bundled Prusa profiles")
        return entries

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        self._status_fn = status_fn
        cancel_check = self._cancel_check
        try:
            raw = self._fetch_bundle_raw(cancel_check=cancel_check)
        except InterruptedError:
            return []
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            OSError,
            ValueError,
        ) as e:
            logger.error("Failed to fetch Prusa bundle: %s", e)
            return []

        self._report("Scanning filament profiles...")
        names = self._scan_filament_names(raw)

        entries: list[OnlineProfileEntry] = []
        total = len(names)
        for i, name in enumerate(names):
            if cancel_check and cancel_check():
                return []
            if i % 200 == 0:
                self._report(f"Building catalog: {i}/{total} profiles...")
            material = guess_material(name) or "Unknown"
            brand = self._extract_brand(name)
            raw_printer = name.split("@", 1)[1].strip() if "@" in name else ""
            printer = self._expand_printer(raw_printer) if raw_printer else ""
            entries.append(
                OnlineProfileEntry(
                    name=name,
                    material=material,
                    brand=brand,
                    printer=printer,
                    slicer="PrusaSlicer",
                    url="",
                    description=f"PrusaSlicer factory preset — {name}",
                    provider_id=self.id,
                    metadata={"bundle_name": name},
                )
            )
        self._report(f"Found {len(entries)} Prusa filament profiles")
        return entries

    def download_profile(self, entry: OnlineProfileEntry) -> tuple[bytes, str]:
        """Return a flat .ini for the profile — from bundle or resolved online."""
        # Bundled files are already resolved flat .ini — just read them
        result = self._download_from_bundle(entry)
        if result:
            return result

        # Online path: download bundle, parse, resolve inheritance
        sections = self._get_parsed_sections(cancel_check=self._cancel_check)
        all_filaments = sections.get("filaments", {})
        name = entry.metadata.get("bundle_name", entry.name)

        from ..models import ProfileEngine

        data = ProfileEngine.resolve_bundle_filament(name, all_filaments)
        data.pop("inherits", None)
        data.pop("compatible_printers_condition", None)
        if "name" not in data:
            data["name"] = name

        lines: list[str] = []
        for k, v in sorted(data.items()):
            if isinstance(v, list):
                v = ";".join(str(x) for x in v)
            lines.append(f"{k} = {v}")
        content = "\n".join(lines).encode("utf-8")

        from pathlib import Path as _P

        safe = _P(
            name.replace(" ", "_").replace("/", "-").replace("\\", "-")[:200]
        ).name
        return content, f"{safe}.ini"
