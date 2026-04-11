"""Database/library profile providers (SimplyPrint, OrcaSlicer, Bambu)."""

from __future__ import annotations

import logging
import urllib.error
from typing import Callable, Optional

from .base import OnlineProvider, OnlineProfileEntry
from ..utils import guess_material, guess_brand

logger = logging.getLogger(__name__)


class SimplyPrintDBProvider(OnlineProvider):
    """SimplyPrint open slicer-profiles-db on GitHub.

    Uses the generated profiles/ directory which aggregates overlays and other
    data sources into hundreds of ready-to-use filament profiles.
    """

    id = "simplyprint"
    name = "SimplyPrint Slicer DB"
    category = "Community"
    description = "Open slicer profile database — crowd-sourced filament settings from many brands and materials"
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

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        """Fetch profile listings from the generated profiles directory."""
        self._status_fn = status_fn
        entries = []
        self._report("Connecting to GitHub (SimplyPrint DB)...")
        try:
            url = f"{self._API_BASE}/contents/profiles/bambustudio/BBL/filament"
            items = self._fetch_json(url)
            self._report("Parsing profile listings...")
            if not isinstance(items, list):
                raise RuntimeError(
                    "Unexpected response from GitHub API (may be rate-limited)"
                )
            for item in items:
                if item.get("type") == "file" and item["name"].endswith(".json"):
                    url = item.get("download_url", "")
                    if not url:
                        continue
                    raw_name = item["name"].replace(".json", "")
                    display_name, printer = self._parse_profile_name(raw_name)
                    entries.append(
                        OnlineProfileEntry(
                            name=raw_name,
                            material=guess_material(raw_name),
                            brand=guess_brand(raw_name),
                            printer=printer,
                            slicer="BambuStudio",
                            url=url,
                            description=f"SimplyPrint DB — {display_name}",
                            provider_id=self.id,
                        )
                    )
            self._report(f"Found {len(entries)} SimplyPrint profiles")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []
        return entries


class OrcaSlicerLibraryProvider(OnlineProvider):
    """OrcaSlicer's built-in filament library from GitHub.

    Verified: 700+ JSON filament presets with direct download_url fields.
    """

    id = "orcalibrary"
    name = "OrcaSlicer Built-in Library"
    category = "Community"
    description = "Built-in OrcaSlicer filament library — 700+ presets covering most popular brands and materials"
    website = "https://github.com/SoftFever/OrcaSlicer"

    _API_BASE = "https://api.github.com/repos/SoftFever/OrcaSlicer"

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
        """Fetch catalog from OrcaSlicer GitHub repository."""
        self._status_fn = status_fn
        entries = []
        self._report("Connecting to GitHub (OrcaSlicer)...")
        try:
            url = f"{self._API_BASE}/contents/resources/profiles/OrcaFilamentLibrary/filament"
            items = self._fetch_json(url)
            self._report("Parsing profile listings...")
            if not isinstance(items, list):
                raise RuntimeError(
                    "Unexpected response from GitHub API (may be rate-limited)"
                )
            for item in items:
                if item.get("type") == "file" and item["name"].endswith(".json"):
                    url = item.get("download_url", "")
                    if not url:
                        continue
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
                            url=url,
                            description="OrcaSlicer built-in filament preset",
                            provider_id=self.id,
                        )
                    )
            self._report(f"Found {len(entries)} OrcaSlicer profiles")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []
        return entries


class BambuStudioOfficialProvider(OnlineProvider):
    """BambuStudio's official built-in BBL filament profiles from GitHub."""

    id = "bambustudio_official"
    name = "BambuStudio Official (BBL)"
    category = "Manufacturer"
    description = "Default Bambu Lab filament presets shipped with BambuStudio — clean baselines for all BBL materials (200+)"
    website = "https://github.com/bambulab/BambuStudio"

    _API_BASE = "https://api.github.com/repos/bambulab/BambuStudio"

    def _fetch_catalog_online(
        self, status_fn: Optional[Callable[[str], None]] = None
    ) -> list[OnlineProfileEntry]:
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
                                if sub.get("type") == "file" and sub["name"].endswith(
                                    ".json"
                                ):
                                    sub_url = sub.get("download_url", "")
                                    if not sub_url:
                                        continue
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
                                            url=sub_url,
                                            description="BambuStudio official filament preset",
                                            provider_id=self.id,
                                        )
                                    )
                    except (urllib.error.URLError, urllib.error.HTTPError) as e:
                        logger.error(
                            "Failed to fetch catalog from %s: %s", self.name, e
                        )
                elif item.get("type") == "file" and item["name"].endswith(".json"):
                    item_url = item.get("download_url", "")
                    if not item_url:
                        continue
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
                            url=item_url,
                            description="BambuStudio official filament preset",
                            provider_id=self.id,
                        )
                    )
            self._report(f"Found {len(entries)} BambuStudio official profiles")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            logger.error("Failed to fetch catalog from %s: %s", self.name, e)
            return []
        return entries
