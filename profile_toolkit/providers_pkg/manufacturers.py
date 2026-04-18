"""Manufacturer profile providers (Polymaker, ColorFabb, Prusa)."""

from __future__ import annotations

import logging
import os
import urllib.error
from typing import Callable, Optional

from .base import OnlineProvider, OnlineProfileEntry
from ..utils import guess_material, guess_brand, parse_printer_nozzle

logger = logging.getLogger(__name__)


class PolymakerProvider(OnlineProvider):
    """Official Polymaker filament presets from GitHub.

    Repo structure: preset/Material/Brand/Model/Slicer/Preset.json
    """

    id = "polymaker"
    name = "Polymaker"
    category = "Manufacturer"
    description = "Official Polymaker filament presets — PLA, PETG, ABS, TPU, and specialty blends"
    website = "https://github.com/Polymaker3D/Polymaker-Preset/tree/main/preset"

    _API_BASE = "https://api.github.com/repos/Polymaker3D/Polymaker-Preset"

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        self._status_fn = status_fn
        self._report("Fetching Polymaker file tree...")
        repo = "Polymaker3D/Polymaker-Preset"
        try:
            url = f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1"
            data = self._fetch_json(url, timeout=30, max_size=50 * 1024 * 1024)
            if not isinstance(data, dict) or "tree" not in data:
                raise RuntimeError("Unexpected git tree response")
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []

        entries = []
        prefix = "preset/"
        for node in data["tree"]:
            if node.get("type") != "blob":
                continue
            path = node.get("path", "")
            if not path.startswith(prefix) or not path.endswith(".json"):
                continue
            # Structure: preset/Material/Brand/Model/Slicer/file.json
            parts = path[len(prefix) :].split("/")
            if len(parts) < 5:
                continue
            material_dir = parts[0]
            mfr_brand = parts[1]
            model = parts[2]
            slicer = parts[3]
            fname = parts[-1].replace(".json", "")

            # Expand BBL machine aliases
            if mfr_brand.upper() == "BBL":
                printer, nozzle = parse_printer_nozzle(f"BBL {model}")
            else:
                printer = f"{mfr_brand} {model}" if model else mfr_brand
                nozzle = ""

            entry = OnlineProfileEntry(
                name=fname,
                material=guess_material(material_dir) or guess_material(fname),
                brand="Polymaker",
                printer=printer,
                slicer=slicer,
                url=f"https://raw.githubusercontent.com/{repo}/main/{path}",
                description=f"Polymaker official — {fname}",
                provider_id=self.id,
            )
            entry.nozzle = nozzle
            entries.append(entry)
        self._report(f"Found {len(entries)} Polymaker profiles")
        return entries


class ColorFabbProvider(OnlineProvider):
    """colorFabb's official profiles for multiple slicers."""

    id = "colorfabb"
    name = "colorFabb"
    category = "Manufacturer"
    description = "Official colorFabb profiles — HT, nGen, PETG, woodFill, and more"
    website = "https://github.com/colorfabb/printer-profiles"

    _API_BASE = "https://api.github.com/repos/colorfabb/printer-profiles"

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        """Fetch all profiles from colorFabb GitHub using tree API."""
        self._status_fn = status_fn
        self._report("Fetching colorFabb file tree...")
        repo = "colorfabb/printer-profiles"
        try:
            url = f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1"
            data = self._fetch_json(url, timeout=30, max_size=50 * 1024 * 1024)
            if not isinstance(data, dict) or "tree" not in data:
                raise RuntimeError("Unexpected git tree response")
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []

        entries = []
        for node in data["tree"]:
            if node.get("type") != "blob":
                continue
            path = node.get("path", "")
            if not path.endswith(".json"):
                continue
            parts = path.split("/")
            if len(parts) < 3:
                continue
            slicer = parts[0]  # BambuStudio, OrcaSlicer, etc.
            profile_type = parts[1]  # filament, process
            if profile_type != "filament":
                continue
            fname = parts[-1].replace(".json", "")
            printer, nozzle = "", ""
            if " @" in fname:
                printer, nozzle = parse_printer_nozzle(fname.split(" @", 1)[1])
            entry = OnlineProfileEntry(
                name=fname,
                material=guess_material(fname),
                brand="colorFabb",
                printer=printer,
                slicer=slicer,
                url=f"https://raw.githubusercontent.com/{repo}/main/{path}",
                description=f"colorFabb official — {fname}",
                provider_id=self.id,
                metadata={"profile_type": profile_type},
            )
            entry.nozzle = nozzle
            entries.append(entry)
        self._report(f"Found {len(entries)} colorFabb profiles")
        return entries


class PrusaResearchProvider(OnlineProvider):
    """Official Prusament and generic filament presets from PrusaSlicer's factory bundle.

    Downloads the monolithic PrusaResearch.ini bundle from GitHub, parses it
    with ProfileEngine.parse_prusa_bundle(), and exposes each concrete filament
    section as an individual profile entry.  Inheritance is fully resolved at
    download time so imported profiles are self-contained.
    """

    id = "prusaresearch"
    name = "Prusa"
    category = "Manufacturer"
    description = (
        "Official Prusament & generic presets from Prusa's factory bundle (200+)"
    )
    website = "https://github.com/prusa3d/PrusaSlicer/tree/master/resources/profiles"

    _BUNDLE_URL = (
        "https://raw.githubusercontent.com/prusa3d/PrusaSlicer/"
        "master/resources/profiles/PrusaResearch.ini"
    )

    def __init__(self) -> None:
        super().__init__()
        self._bundle_lock = __import__("threading").Lock()
        self._cached_raw: bytes | None = None
        self._cached_sections: dict | None = None

    def clear_cache(self) -> None:
        with self._bundle_lock:
            self._cached_raw = None
            self._cached_sections = None

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

    @staticmethod
    def _parse_printer_nozzle(raw: str) -> tuple[str, str]:
        """Parse printer alias and nozzle — delegates to shared parser."""
        return parse_printer_nozzle(raw)

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
        words = name.split()
        return words[0] if words else ""

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
            printer, nozzle = (
                self._parse_printer_nozzle(raw_printer) if raw_printer else ("", "")
            )
            entry = OnlineProfileEntry(
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
            entry.nozzle = nozzle
            entries.append(entry)
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
            printer, nozzle = (
                self._parse_printer_nozzle(raw_printer) if raw_printer else ("", "")
            )
            entry = OnlineProfileEntry(
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
            entry.nozzle = nozzle
            entries.append(entry)
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

        from pathlib import Path

        safe = Path(
            name.replace(" ", "_").replace("/", "-").replace("\\", "-")[:200]
        ).name
        return content, f"{safe}.ini"
