"""Community profile providers (CommunityPresets, Santanachia, Dgauche)."""

from __future__ import annotations

import logging
import urllib.error
from typing import Callable, Optional

from .base import OnlineProvider, OnlineProfileEntry
from ..utils import guess_material, guess_brand, parse_printer_nozzle

logger = logging.getLogger(__name__)

_SKIP_DIRS = {".github", "__pycache__", ".git"}


class CommunityPresetsProvider(OnlineProvider):
    """Dr. Ignaz Gortngschirl's curated BambuStudio/OrcaSlicer community presets."""

    id = "community_presets"
    name = "Community Presets (Dr. Ignaz)"
    category = "Community"
    description = (
        "Curated community collection — filament, machine, and process presets "
        "for BambuStudio & OrcaSlicer"
    )
    website = "https://github.com/DRIgnazGortngschirl/bambulab-studio-orca-slicer-presets/tree/main/filament"

    _API_BASE = "https://api.github.com/repos/DRIgnazGortngschirl/bambulab-studio-orca-slicer-presets"

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        self._status_fn = status_fn
        entries = []
        repo = "DRIgnazGortngschirl/bambulab-studio-orca-slicer-presets"
        for profile_type in ("filament", "machine", "process"):
            self._report(f"Fetching {profile_type} profiles...")
            try:
                nodes = self._fetch_git_tree(repo, profile_type)
            except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as e:
                logger.error(
                    "Failed to fetch %s from %s: %s", profile_type, self.name, e
                )
                continue
            for node in nodes:
                path = node["path"]
                if not path.endswith(".json"):
                    continue
                fname = path.rsplit("/", 1)[-1].replace(".json", "")
                printer, nozzle = "", ""
                if " @" in fname:
                    printer, nozzle = parse_printer_nozzle(fname.split(" @", 1)[1])
                entry = OnlineProfileEntry(
                    name=fname,
                    material=(
                        guess_material(fname) if profile_type == "filament" else ""
                    ),
                    brand=guess_brand(fname),
                    printer=printer,
                    slicer="OrcaSlicer",
                    url=f"https://raw.githubusercontent.com/{repo}/main/{path}",
                    description=f"Community preset ({profile_type}) — {fname}",
                    provider_id=self.id,
                    metadata={"profile_type": profile_type},
                )
                entry.nozzle = nozzle
                entries.append(entry)
        self._report(f"Found {len(entries)} community presets")
        return entries


class SantanachiaProvider(OnlineProvider):
    """Santanachia's BambuStudio custom filament profiles (.bbsflmt and JSON)."""

    id = "santanachia"
    name = "Santanachia Custom Filaments"
    category = "Community"
    description = (
        "Community-tested filament profiles for eSUN, KINGROON, and other "
        "third-party brands on Bambu printers"
    )
    website = "https://github.com/Santanachia/BambuStudio_CustomFilaments"

    _API_BASE = "https://api.github.com/repos/Santanachia/BambuStudio_CustomFilaments"

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        self._status_fn = status_fn
        self._report("Fetching Santanachia file tree...")
        repo = "Santanachia/BambuStudio_CustomFilaments"
        try:
            # Tree API with empty prefix to get all files at root
            url = f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1"
            data = self._fetch_json(url, timeout=30)
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
            parts = path.split("/")
            # Skip dotfiles/metadata
            if any(p in _SKIP_DIRS for p in parts):
                continue
            if not (path.endswith(".json") or path.endswith(".bbsflmt")):
                continue

            fname = parts[-1]
            ext = ".bbsflmt" if fname.endswith(".bbsflmt") else ".json"
            display = fname.replace(ext, "")

            # Directory structure: Brand/file or Brand/Printer/file
            brand = parts[0] if len(parts) >= 2 else ""
            printer = parts[1] if len(parts) >= 3 else ""

            entries.append(
                OnlineProfileEntry(
                    name=display,
                    material=guess_material(display),
                    brand=brand,
                    printer=printer,
                    slicer="BambuStudio",
                    url=f"https://raw.githubusercontent.com/{repo}/main/{path}",
                    description=f"Santanachia — {brand} — {display}",
                    provider_id=self.id,
                )
            )
        self._report(f"Found {len(entries)} Santanachia profiles")
        return entries


class DgaucheFilamentLibProvider(OnlineProvider):
    """dgauche's BambuStudio Filament Library — community profiles by printer model."""

    id = "dgauche_filament_lib"
    name = "BambuStudio Filament Library (dgauche)"
    category = "Community"
    description = (
        "Community filament & process profiles organized by printer — "
        "P1P, X1, X1C, and more"
    )
    website = "https://github.com/dgauche/BambuStudioFilamentLibrary"

    _API_BASE = "https://api.github.com/repos/dgauche/BambuStudioFilamentLibrary"

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        self._status_fn = status_fn
        self._report("Fetching dgauche file tree...")
        repo = "dgauche/BambuStudioFilamentLibrary"
        try:
            url = f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1"
            data = self._fetch_json(url, timeout=30)
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
            parts = path.split("/")
            if any(p in _SKIP_DIRS for p in parts):
                continue
            if not (path.endswith(".json") or path.endswith(".bbsflmt")):
                continue

            fname = parts[-1]
            ext = ".bbsflmt" if fname.endswith(".bbsflmt") else ".json"
            display = fname.replace(ext, "")

            # Directory structure: Printer/file
            printer = parts[0] if len(parts) >= 2 else ""

            profile_type = "filament"
            if "Process" in fname:
                profile_type = "process"
            elif "Machine" in fname:
                profile_type = "machine"

            entries.append(
                OnlineProfileEntry(
                    name=display,
                    material=guess_material(display),
                    brand=guess_brand(display),
                    printer=printer,
                    slicer="BambuStudio",
                    url=f"https://raw.githubusercontent.com/{repo}/main/{path}",
                    description=f"dgauche — {printer} — {display}",
                    provider_id=self.id,
                    metadata={"profile_type": profile_type},
                )
            )
        self._report(f"Found {len(entries)} dgauche profiles")
        return entries
