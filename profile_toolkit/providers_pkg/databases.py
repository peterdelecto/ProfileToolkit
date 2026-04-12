"""Database/library profile providers (SimplyPrint, OrcaSlicer, Bambu)."""

from __future__ import annotations

import logging
import urllib.error
from typing import Callable, Optional

from .base import OnlineProvider, OnlineProfileEntry
from ..utils import guess_material, guess_brand, parse_printer_nozzle

logger = logging.getLogger(__name__)


def _make_entry(
    fname: str,
    url: str,
    slicer: str,
    provider_id: str,
    description: str,
    default_brand: str = "",
) -> OnlineProfileEntry:
    """Build an OnlineProfileEntry from a filename, parsing @BBL machine/nozzle."""
    printer, nozzle = "", ""
    if " @" in fname:
        display = fname.split(" @", 1)[0]
        printer, nozzle = parse_printer_nozzle(fname.split(" @", 1)[1])
    else:
        display = fname
    entry = OnlineProfileEntry(
        name=fname,
        material=guess_material(fname),
        brand=guess_brand(fname) or default_brand,
        printer=printer,
        slicer=slicer,
        url=url,
        description=f"{description} — {display}",
        provider_id=provider_id,
    )
    entry.nozzle = nozzle
    return entry


class SimplyPrintDBProvider(OnlineProvider):
    """SimplyPrint open slicer-profiles-db on GitHub.

    Uses git tree API to get the full file listing across all manufacturers.
    """

    id = "simplyprint"
    name = "SimplyPrint Slicer DB"
    category = "Community"
    description = "Open slicer profile database — crowd-sourced filament settings across many manufacturers"
    website = "https://github.com/SimplyPrint/slicer-profiles-db/tree/main/profiles"

    _API_BASE = "https://api.github.com/repos/SimplyPrint/slicer-profiles-db"

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        self._status_fn = status_fn
        self._report("Fetching SimplyPrint file tree...")
        repo = "SimplyPrint/slicer-profiles-db"
        try:
            url = f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1"
            data = self._fetch_json(url, timeout=30, max_size=50 * 1024 * 1024)
            if not isinstance(data, dict) or "tree" not in data:
                raise RuntimeError("Unexpected git tree response")
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []

        entries = []
        prefix = "profiles/"
        for node in data["tree"]:
            if node.get("type") != "blob":
                continue
            path = node.get("path", "")
            if not path.startswith(prefix) or not path.endswith(".json"):
                continue
            # Only include filament profiles
            if "/filament/" not in path:
                continue
            # Structure: profiles/bambustudio/MFR/filament/name.json
            parts = path[len(prefix) :].split("/")
            slicer = parts[0] if parts else "BambuStudio"
            manufacturer = parts[1] if len(parts) > 1 else ""
            fname = path.rsplit("/", 1)[-1].replace(".json", "")
            dl_url = f"https://raw.githubusercontent.com/{repo}/main/{path}"
            entry = _make_entry(fname, dl_url, slicer, self.id, "SimplyPrint DB")
            if not entry.brand and manufacturer:
                entry.brand = manufacturer
            entries.append(entry)
        self._report(f"Found {len(entries)} SimplyPrint profiles")
        return entries


class OrcaSlicerLibraryProvider(OnlineProvider):
    """OrcaSlicer's built-in filament profiles from GitHub.

    Uses git tree API across all manufacturer subdirectories under
    resources/profiles/*/filament/ for the complete listing (5000+).
    """

    id = "orcalibrary"
    name = "OrcaSlicer Built-in Library"
    category = "Community"
    description = (
        "Built-in OrcaSlicer filament library — 5000+ presets across 40+ manufacturers"
    )
    website = "https://github.com/OrcaSlicer/OrcaSlicer/tree/main/resources/profiles"

    _API_BASE = "https://api.github.com/repos/OrcaSlicer/OrcaSlicer"

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        self._status_fn = status_fn
        self._report("Fetching OrcaSlicer file tree...")
        repo = "OrcaSlicer/OrcaSlicer"
        try:
            # Get full tree — profiles are under resources/profiles/*/filament/
            url = f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1"
            data = self._fetch_json(url, timeout=30, max_size=50 * 1024 * 1024)
            if not isinstance(data, dict) or "tree" not in data:
                raise RuntimeError("Unexpected git tree response")
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []

        entries = []
        prefix = "resources/profiles/"
        for node in data["tree"]:
            if node.get("type") != "blob":
                continue
            path = node.get("path", "")
            if not path.startswith(prefix) or "/filament/" not in path:
                continue
            if not path.endswith(".json"):
                continue
            fname = path.rsplit("/", 1)[-1].replace(".json", "")
            # Extract manufacturer from path: resources/profiles/MFR/filament/...
            parts = path[len(prefix) :].split("/")
            manufacturer = parts[0] if parts else ""
            fetch_url = f"https://raw.githubusercontent.com/{repo}/main/{path}"
            entry = _make_entry(
                fname, fetch_url, "OrcaSlicer", self.id, "OrcaSlicer preset"
            )
            # Use manufacturer dir as brand if guess_brand didn't find one
            if not entry.brand and manufacturer:
                entry.brand = manufacturer
            entries.append(entry)
        self._report(f"Found {len(entries)} OrcaSlicer profiles")
        return entries


class BambuStudioOfficialProvider(OnlineProvider):
    """BambuStudio's official built-in BBL filament profiles from GitHub.

    Uses git tree API for complete listing (master branch).
    """

    _DEFAULT_BRANCH = "master"

    id = "bambustudio_official"
    name = "BambuStudio Official (BBL)"
    category = "Manufacturer"
    description = "Default Bambu Lab filament presets shipped with BambuStudio"
    website = "https://github.com/bambulab/BambuStudio/tree/master/resources/profiles"

    _API_BASE = "https://api.github.com/repos/bambulab/BambuStudio"

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        self._status_fn = status_fn
        self._report("Fetching BambuStudio file tree...")
        try:
            nodes = self._fetch_git_tree(
                "bambulab/BambuStudio",
                "resources/profiles/BBL/filament",
                branch="master",
            )
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []

        entries = []
        for node in nodes:
            path = node["path"]
            if not path.endswith(".json"):
                continue
            fname = path.rsplit("/", 1)[-1].replace(".json", "")
            url = (
                f"https://raw.githubusercontent.com/bambulab/BambuStudio/master/{path}"
            )
            entries.append(
                _make_entry(
                    fname,
                    url,
                    "BambuStudio",
                    self.id,
                    "BambuStudio official",
                    default_brand="Bambu",
                )
            )
        self._report(f"Found {len(entries)} BambuStudio official profiles")
        return entries
