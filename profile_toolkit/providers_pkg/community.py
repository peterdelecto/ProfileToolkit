"""Community profile providers (CommunityPresets, Santanachia, Dgauche)."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Callable, Optional

from .base import OnlineProvider, OnlineProfileEntry
from ..utils import guess_material, guess_brand

logger = logging.getLogger(__name__)


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

    def _fetch_catalog_online(self, status_fn: Optional[Callable[[str], None]] = None) -> list[OnlineProfileEntry]:
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

    def _fetch_catalog_online(self, status_fn: Optional[Callable[[str], None]] = None) -> list[OnlineProfileEntry]:
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

    def _fetch_catalog_online(self, status_fn: Optional[Callable[[str], None]] = None) -> list[OnlineProfileEntry]:
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
