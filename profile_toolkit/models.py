# Core data models

from __future__ import annotations

import json
import hashlib
import io
import logging
import os
import platform
import re
import xml.etree.ElementTree as ET
import zipfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Optional

from .constants import (
    _ALL_PROCESS_KEYS,
    _ALL_FILAMENT_KEYS,
    _IDENTITY_KEYS,
    _FILAMENT_SIGNAL_KEYS,
    _PROCESS_SIGNAL_KEYS,
    _PROFILE_SIGNAL_KEYS,
    _KNOWN_VENDORS,
    _FILAMENT_TYPES,
    _NOZZLE_SIZES,
    _ALL_BBL_PRINTERS,
    _KNOWN_PRINTERS,
    _PLATFORM,
    MAX_INHERITANCE_DEPTH,
)

logger = logging.getLogger(__name__)


class PresetIndex:
    """
    Indexes all presets (system + user) from a slicer directory so we can
    resolve inheritance chains.  Call build() once per slicer path, then
    resolve(profile) to fill in inherited parameters.
    """

    # Typical slicer directory layouts
    SYSTEM_SUBDIRS = {
        "BambuStudio": ["system"],
        "OrcaSlicer": ["system"],
        "PrusaSlicer": ["vendor"],
    }

    def __init__(self) -> None:
        """Initialize an empty preset index."""
        self._by_name = {}  # name → dict of raw JSON data
        self.known_printers = set()  # all printer names seen in compatible_printers
        self._collisions = 0

    def build(self, slicer_path: str, slicer_name: str = "") -> None:
        """Scan a slicer directory and index all presets by name."""
        before = len(self._by_name)
        self._collisions = 0

        # Index user presets
        user_dir = os.path.join(slicer_path, "user")
        if os.path.isdir(user_dir):
            self._scan_dir(user_dir)

        # Index system presets
        for subdir in self.SYSTEM_SUBDIRS.get(slicer_name, ["system", "vendor"]):
            sys_dir = os.path.join(slicer_path, subdir)
            if os.path.isdir(sys_dir):
                self._scan_dir(sys_dir)

        added = len(self._by_name) - before
        label = slicer_name or slicer_path
        logger.debug("PresetIndex: %s — %d new presets indexed, %d name collisions (last-write-wins)", label, added, self._collisions)

    def _scan_dir(self, directory: str) -> None:
        """Recursively scan for .json preset files."""
        for root, dirs, files in os.walk(directory):
            for fname in files:
                if not fname.endswith(".json"):
                    continue
                fp = os.path.join(root, fname)
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "name" in data:
                        if data["name"] in self._by_name:
                            self._collisions += 1
                        self._by_name[data["name"]] = data
                        self._collect_printers(data)
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and "name" in item:
                                if item["name"] in self._by_name:
                                    self._collisions += 1
                                self._by_name[item["name"]] = item
                                self._collect_printers(item)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.debug("Skipping malformed preset file: %s — %s", fp, e)
                except OSError as exc:
                    logger.warning("Could not read %s: %s", fp, exc)

    def _collect_printers(self, data: dict) -> None:
        """Extract printer names from compatible_printers into known_printers."""
        cp = data.get("compatible_printers")
        if isinstance(cp, str):
            try:
                cp = json.loads(cp)
            except (json.JSONDecodeError, ValueError):
                cp = [cp] if cp else []
        if isinstance(cp, list):
            for name in cp:
                if isinstance(name, str) and name.strip():
                    self.known_printers.add(name.strip())

    def add_profiles(self, profiles: list) -> None:
        """Add loaded Profile objects to the index (for cross-referencing)."""
        for profile in profiles:
            if profile.name and profile.name not in self._by_name:
                self._by_name[profile.name] = profile.data
            self._collect_printers(profile.data)

    def resolve(self, profile: Profile, max_depth: int = MAX_INHERITANCE_DEPTH) -> None:
        """
        Resolve a profile's inheritance chain.
        Sets profile.resolved_data (full merged dict) and
        profile.inherited_keys (set of keys that came from parents).
        """
        merged = {}
        inherited_keys = set()
        chain = []

        # Walk up the inheritance chain
        current_name = profile.inherits
        depth = 0
        visited = {profile.data.get("name", "")}  # Detect circular references
        while current_name and depth < max_depth:
            if current_name in visited:
                logger.warning("Circular inheritance detected: %s → %s",
                              " → ".join(chain), current_name)
                break
            visited.add(current_name)
            parent_data = self._by_name.get(current_name)
            if parent_data is None:
                # Try fuzzy match: strip @suffix
                base = re.sub(r'\s*@.*$', '', current_name)
                parent_data = self._by_name.get(base)
            if parent_data is None:
                break
            chain.append(current_name)
            current_name = parent_data.get("inherits", "")
            depth += 1

        if depth >= max_depth and current_name:
            logger.warning("Max inheritance depth %d reached for '%s' — possible circular inheritance",
                          max_depth, profile.data.get("name", ""))

        # If no parents were found, inheritance is unresolved — leave
        # resolved_data as None so the UI can show an appropriate warning.
        if not chain:
            profile.resolved_data = None
            profile.inherited_keys = set()
            profile.inheritance_chain = []
            return

        # Merge from deepest ancestor → nearest parent → profile itself
        for ancestor_name in reversed(chain):
            ancestor = self._by_name.get(ancestor_name)
            if ancestor is None:
                base = re.sub(r'\s*@.*$', '', ancestor_name)
                ancestor = self._by_name.get(base, {})
            for k, v in ancestor.items():
                if k not in _IDENTITY_KEYS:
                    merged[k] = v
                    inherited_keys.add(k)

        for k, v in profile.data.items():
            if k not in _IDENTITY_KEYS:
                merged[k] = v
                inherited_keys.discard(k)  # It's an override, not inherited

        profile.resolved_data = merged
        profile.inherited_keys = inherited_keys
        profile.inheritance_chain = chain

    @property
    def preset_count(self) -> int:
        """Return the count of indexed presets."""
        return len(self._by_name)

    def has_preset(self, name: str) -> bool:
        """Check if a preset exists by name (with fuzzy @suffix matching)."""
        if name in self._by_name:
            return True
        base = re.sub(r'\s*@.*$', '', name)
        return base in self._by_name


class Profile:
    """
    Represents a slicer profile (printer, process, or filament).
    Tracks data, source, modification state, and inheritance chain.
    """

    # Characters that are unsafe in slicer profile names:
    # filesystem-unsafe: / \ : * ? " < > |
    # JSON/slicer-unsafe: { } (used as template markers in some slicers)
    _UNSAFE_NAME_CHARS = re.compile(r'[\\/:*?"<>|{}]')

    def __init__(self, data: dict, source_path: str, source_type: str,
                 type_hint: str = None, origin: str = "") -> None:
        """Initialize a Profile object."""
        if not data:
            logger.warning("Profile created with empty data dict: %s", source_path)

        self.data = data
        self.source_path = source_path
        self.source_type = source_type
        self.type_hint = type_hint  # From directory structure ("filament", "process", etc.)
        self.origin = origin or self._detect_origin(source_path)
        self.modified = False
        self.changelog = []  # List of (timestamp, action, details, snapshot) tuples
        # Populated by PresetIndex.resolve():
        self.resolved_data = None   # Full merged data (parent + overrides)
        self.inherited_keys = set() # Keys that came from parent (not overridden)
        self.inheritance_chain = [] # List of ancestor names

    @staticmethod
    def sanitize_name(name: str) -> str:
        """Remove characters that are incompatible with slicer profile names.
        Strips filesystem-unsafe and JSON-unsafe characters, collapses whitespace.
        Also removes non-ASCII characters for Windows filesystem compatibility."""
        cleaned = Profile._UNSAFE_NAME_CHARS.sub("", name)
        cleaned = cleaned.encode('ascii', 'replace').decode('ascii')
        cleaned = " ".join(cleaned.split())  # Collapse whitespace
        return cleaned.strip()

    def log_change(self, action: str, details: str = "", snapshot: dict = None) -> None:
        """Append an entry to this profile's changelog.
        If snapshot is provided, the change can be undone by restoring it."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.changelog.append((ts, action, details, snapshot))

    def restore_snapshot(self, changelog_index: int) -> bool:
        """Undo a changelog entry by restoring its snapshot.
        Removes the entry and all entries after it.
        Returns True if successful, False otherwise."""
        if changelog_index < 0 or changelog_index >= len(self.changelog):
            return False
        entry = self.changelog[changelog_index]
        if len(entry) < 4 or entry[3] is None:
            return False
        snapshot = entry[3]
        # Restore snapshotted fields
        for k, v in snapshot.items():
            if k == "_modified":
                self.modified = v
            else:
                self.data[k] = deepcopy(v)
        # Remove this entry and everything after it
        self.changelog = self.changelog[:changelog_index]
        return True

    @staticmethod
    def _detect_origin(path: str) -> str:
        """Guess slicer origin from the file path."""
        path_lower = path.lower()
        if "bambustudio" in path_lower or "bambu" in path_lower:
            return "BambuStudio"
        if "orcaslicer" in path_lower or "orca" in path_lower:
            return "OrcaSlicer"
        if "prusaslicer" in path_lower or "prusa" in path_lower:
            return "PrusaSlicer"
        return ""

    @property
    def name(self) -> str:
        """Return the profile name, falling back to filename if not set."""
        name_val = self.data.get("name", "")
        return name_val if name_val else os.path.splitext(os.path.basename(self.source_path))[0]

    @property
    def profile_type(self) -> str:
        """Detect profile type: 'filament', 'process', 'printer', or 'unknown'."""
        # 1. Explicit type field
        type_str = self.data.get("type", "").lower()
        if type_str in ("filament",):
            return "filament"
        elif type_str in ("process", "print"):
            return "process"
        elif type_str in ("machine", "printer"):
            return "printer"

        # 2. Directory-based hint (from slicer import)
        if self.type_hint:
            hint = self.type_hint.lower()
            if hint in ("filament",):
                return "filament"
            elif hint in ("process", "print"):
                return "process"
            elif hint in ("machine", "printer"):
                return "printer"

        # 3. Heuristic: guess from keys present
        keys = set(self.data.keys())
        filament_signals = keys & _FILAMENT_SIGNAL_KEYS
        process_signals = keys & _PROCESS_SIGNAL_KEYS

        if len(filament_signals) > len(process_signals):
            return "filament"
        if len(process_signals) > 0:
            return "process"
        return "unknown"

    @property
    def compatible_printers(self) -> list:
        """Return list of compatible printer names.
        Handles JSON string encoding and empty string edge case."""
        compat_printers = self.data.get("compatible_printers", [])
        if isinstance(compat_printers, str):
            if compat_printers == "":
                return []
            try:
                compat_printers = json.loads(compat_printers)
            except Exception:
                compat_printers = [compat_printers] if compat_printers else []
        return compat_printers if isinstance(compat_printers, list) else []

    @property
    def inherits(self) -> str:
        """Return the profile name this profile inherits from, or empty string."""
        return self.data.get("inherits", "")

    @property
    def is_locked(self) -> bool:
        """Check if profile is locked to specific printer(s)."""
        if self.modified:
            return False
        cp = self.compatible_printers
        if cp:
            # If compatible_printers contains the full BBL set (or more),
            # the profile is universal.
            if set(_ALL_BBL_PRINTERS).issubset(set(cp)):
                return False
            return True
        # Also locked if printer_settings_id is set
        printer_settings_id = self.data.get("printer_settings_id", "")
        if isinstance(printer_settings_id, list):
            printer_settings_id = printer_settings_id[0] if printer_settings_id else ""
        return bool(printer_settings_id)

    @property
    def source_label(self) -> str:
        """Return a human-readable source label."""
        filename = os.path.basename(self.source_path)
        if self.source_type == "3mf":
            return f"Extracted from {filename}"
        return filename

    @property
    def printer_group(self) -> str:
        """Extract a human-readable printer name for grouping.
        Uses compatible_printers first, then printer_settings_id,
        then the @... suffix in the profile name."""
        # 1. compatible_printers list
        cp = self.compatible_printers
        if cp:
            names = set()
            for printer_name in cp:
                clean = re.sub(r'\s+\d+\.\d+\s*nozzle$', '', printer_name, flags=re.IGNORECASE).strip()
                names.add(clean)
            return ", ".join(sorted(names)) if names else "Universal"

        printer_settings_id = self.data.get("printer_settings_id", "")
        if isinstance(printer_settings_id, list):
            printer_settings_id = printer_settings_id[0] if printer_settings_id else ""
        if printer_settings_id:
            return printer_settings_id

        name = self.data.get("name", "")
        if "@" in name:
            return name.split("@", 1)[1].strip()

        return "Universal"

    @property
    def manufacturer_group(self) -> str:
        """Return manufacturer/vendor grouping."""
        vendor = self.data.get("filament_vendor", "")
        if isinstance(vendor, list):
            vendor = vendor[0] if vendor else ""
        if vendor:
            return vendor

        name = self.data.get("name", "")
        base = name.split("@")[0].strip() if "@" in name else name
        base_lower = base.lower()
        for v in sorted(_KNOWN_VENDORS, key=len, reverse=True):
            if base_lower.startswith(v.lower()):
                return v

        inherits = self.data.get("inherits", "")
        if inherits:
            for v in sorted(_KNOWN_VENDORS, key=len, reverse=True):
                if inherits.lower().startswith(v.lower()):
                    return v

        if base.strip():
            first_word = base.split()[0]
            # Only use if it looks like a brand (starts uppercase, not a filament type)
            if first_word.upper() not in _FILAMENT_TYPES and len(first_word) > 1:
                return first_word
        return "Other"

    @property
    def material_group(self) -> str:
        """Return material type grouping."""
        filament_type_val = self.data.get("filament_type", "")
        if isinstance(filament_type_val, list):
            filament_type_val = filament_type_val[0] if filament_type_val else ""
        if filament_type_val:
            return filament_type_val

        if self.resolved_data:
            filament_type_val = self.resolved_data.get("filament_type", "")
            if isinstance(filament_type_val, list):
                filament_type_val = filament_type_val[0] if filament_type_val else ""
            if filament_type_val:
                return filament_type_val

        name = self.data.get("name", "")
        base = name.split("@")[0].strip() if "@" in name else name
        base_upper = base.upper()
        for mat in sorted(_FILAMENT_TYPES, key=len, reverse=True):
            if mat in base_upper:
                return mat
        return "Other"

    @property
    def nozzle_group(self) -> str:
        """Return nozzle size grouping."""
        compat_printers = self.compatible_printers
        if compat_printers:
            sizes = set()
            for printer_name in compat_printers:
                match = re.search(r'(\d+\.\d+)\s*nozzle', printer_name, re.IGNORECASE)
                if match:
                    sizes.add(match.group(1) + "mm")
            if sizes:
                return ", ".join(sorted(sizes))

        name = self.data.get("name", "")
        match = re.search(r'(\d+\.\d+)\s*nozzle', name, re.IGNORECASE)
        if match:
            return match.group(1) + "mm"

        printer_settings_id = self.data.get("printer_settings_id", "")
        if isinstance(printer_settings_id, list):
            printer_settings_id = printer_settings_id[0] if printer_settings_id else ""
        if printer_settings_id:
            match = re.search(r'(\d+\.\d+)\s*nozzle', printer_settings_id, re.IGNORECASE)
            if match:
                return match.group(1) + "mm"

        return "Unknown nozzle"

    def group_key(self, group_by: str) -> str:
        """Return the grouping key for a given group_by mode."""
        if group_by == "printer":
            return self.printer_group
        elif group_by == "manufacturer":
            return self.manufacturer_group
        elif group_by == "material":
            return self.material_group
        elif group_by == "nozzle":
            return self.nozzle_group
        elif group_by == "status":
            if self.modified:
                return "Unlocked"
            elif self.is_locked:
                return "Locked"
            else:
                return "Custom"
        return ""  # "none" — no grouping

    def _flatten_into_data(self) -> None:
        """Merge all inherited params into data and drop 'inherits' so the
        profile is fully self-contained.  This is a ONE-WAY operation — once
        flattened, the inheritance chain cannot be restored.  Ensures the
        profile displays correctly and exports with all parameters even when
        the parent profile is not available."""
        if self.resolved_data:
            for k, v in self.resolved_data.items():
                if k not in self.data:
                    self.data[k] = v
            self.data.pop("inherits", None)
            self.inherited_keys = set()
            self.resolved_data = None
            self.inheritance_chain = []

    def make_universal(self, all_printers: list = None) -> None:
        """Unlock profile from printer restrictions."""
        self._flatten_into_data()
        # Snapshot the fields we're about to modify so the change can be undone
        snapshot = {}
        for k in ("compatible_printers", "compatible_printers_condition",
                   "printer_settings_id"):
            if k in self.data:
                snapshot[k] = deepcopy(self.data[k])
        snapshot["_modified"] = self.modified

        old_printers = self.data.get("compatible_printers", [])
        old_psid = self.data.get("printer_settings_id", "")
        # BambuStudio treats compatible_printers=[] on flattened user profiles
        # as "all printers" — the profile appears in the Custom list for every
        # printer.  This matches known-working user profiles.
        self.data["compatible_printers"] = []
        if "compatible_printers_condition" in self.data:
            self.data["compatible_printers_condition"] = ""
        if "printer_settings_id" in self.data:
            self.data["printer_settings_id"] = ""
        self.modified = True

        detail_parts = []
        if old_printers:
            detail_parts.append(f"Removed printer lock: {', '.join(old_printers)}")
        if old_psid:
            detail_parts.append(f"Cleared printer binding: {old_psid}")
        self.log_change("Unlocked", "; ".join(detail_parts), snapshot=snapshot)

    def retarget(self, printers: list) -> None:
        """Retarget profile to a different set of printers."""
        self._flatten_into_data()
        snapshot = {}
        for k in ("compatible_printers", "compatible_printers_condition",
                   "printer_settings_id"):
            if k in self.data:
                snapshot[k] = deepcopy(self.data[k])
        snapshot["_modified"] = self.modified

        old_printers = self.data.get("compatible_printers", [])
        self.data["compatible_printers"] = printers
        if "compatible_printers_condition" in self.data:
            self.data["compatible_printers_condition"] = ""
        if "printer_settings_id" in self.data:
            self.data["printer_settings_id"] = ""
        self.modified = True
        self.log_change("Retargeted",
                        f"{', '.join(old_printers) or 'Universal'} → {', '.join(printers)}",
                        snapshot=snapshot)

    def to_json(self, indent: int = 4, flatten: bool = True) -> str:
        """Export to JSON. If flatten=True and resolved_data exists,
        exports the full flattened profile (no inheritance dependency)."""
        if flatten and self.resolved_data:
            export = {}
            for k in _IDENTITY_KEYS:
                if k == "inherits":
                    continue
                if k in self.data:
                    export[k] = self.data[k]
            export.update(self.resolved_data)
            return json.dumps(export, indent=indent, ensure_ascii=False)
        return json.dumps(self.data, indent=indent, ensure_ascii=False)

    def suggested_filename(self) -> str:
        """Generate a safe filename for export."""
        name = re.sub(r'\s*@\s*\S+.*$', '', self.name)
        name = re.sub(r'[^\w\s\-.]', '', name)
        name = re.sub(r'\s+', '_', name.strip())
        return f"{name or 'profile'}.json"


class ProfileEngine:
    """
    Static methods for loading and parsing profiles from various file formats.
    Supports JSON, 3MF archives, and embedded configuration formats.
    """

    @staticmethod
    def load_json(path: str, type_hint: str = None) -> list:
        """Load profiles from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return [Profile(data, path, "json", type_hint)]
        elif isinstance(data, list):
            return [Profile(d, path, "json", type_hint) for d in data if isinstance(d, dict)]
        return []

    @staticmethod
    def extract_from_3mf(path: str) -> list:
        """Extract profiles from a 3MF archive file."""
        profiles = []
        errors = []
        if not zipfile.is_zipfile(path):
            raise ValueError(f"{os.path.basename(path)} is not a valid archive")

        with zipfile.ZipFile(path, "r") as zf:
            for name in zf.namelist():
                if name.endswith(".json"):
                    try:
                        data = json.loads(zf.read(name).decode("utf-8"))
                        if isinstance(data, dict) and ("name" in data or "type" in data
                                                        or "filament_type" in data or "layer_height" in data):
                            profiles.append(Profile(data, path, "3mf"))
                    except Exception as e:
                        errors.append(f"{name}: {e}")

                if name.startswith("Metadata/") and any(
                        name.endswith(ext) for ext in (".config", ".xml", ".ini")):
                    try:
                        content = zf.read(name).decode("utf-8")
                        profiles.extend(ProfileEngine._parse_config(content, path))
                    except Exception as e:
                        errors.append(f"{name}: {e}")

                if name.startswith("Metadata/") and name.endswith(".txt"):
                    try:
                        content = zf.read(name).decode("utf-8")
                        if any(k in content for k in ("filament_type", "layer_height",
                                                       "nozzle_temperature", "compatible_printers")):
                            profiles.extend(ProfileEngine._parse_config(content, path))
                    except Exception as e:
                        errors.append(f"{name}: {e}")

        if errors:
            logger.warning("3MF extraction warnings: %s", "; ".join(errors))

        # Deduplicate by name
        seen = set()
        unique = []
        for profile in profiles:
            if profile.name not in seen:
                seen.add(profile.name)
                unique.append(profile)
        return unique

    @staticmethod
    def _parse_config_json(content: str, source_path: str) -> list:
        """Parse JSON-format config content (BambuStudio .config style)."""
        profiles = []
        try:
            data = json.loads(content)
            items = [data] if isinstance(data, dict) else (
                [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []
            )
            for item in items:
                if ProfileEngine._is_profile_data(item):
                    # Infer type from keys/fields if not set
                    if "type" not in item:
                        # Use name hint: filament_settings_* → filament,
                        # project_settings / process_settings → process
                        item_name = item.get("name", "")
                        if "filament_settings" in item_name.lower():
                            item["type"] = "filament"
                        elif "project_settings" in item_name.lower():
                            item["type"] = "process"
                        elif len(item.keys() & _FILAMENT_SIGNAL_KEYS) > len(item.keys() & _PROCESS_SIGNAL_KEYS):
                            item["type"] = "filament"
                        else:
                            item["type"] = "process"
                    # Derive a descriptive name
                    raw_name = item.get("name", "")
                    basename = os.path.splitext(os.path.basename(source_path))[0]
                    # "project_settings" is generic — replace with source filename
                    if not raw_name or raw_name in ("project_settings", ""):
                        if item.get("type") == "process":
                            item["name"] = f"Project Settings ({basename})"
                        else:
                            sid = item.get("filament_settings_id") or item.get("setting_id")
                            if isinstance(sid, list):
                                sid = sid[0] if sid else None
                            if sid and sid != "nil":
                                item["name"] = sid
                            else:
                                item["name"] = f"Extracted profile ({basename})"
                    profiles.append(Profile(item, source_path, "3mf"))
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug("Failed to parse JSON config: %s", e)
        return profiles

    @staticmethod
    def _parse_config_xml(content: str, source_path: str) -> list:
        """Parse XML-format config content. Raises ET.ParseError if not valid XML."""
        profiles = []
        root = ET.fromstring(content)
        for elem in root.iter():
            tag_lower = elem.tag.lower().split("}")[-1]

            if tag_lower in ("filament", "print", "process"):
                data = ProfileEngine._extract_xml_profile(elem)
                if data and ProfileEngine._is_profile_data(data):
                    if "type" not in data:
                        data["type"] = "filament" if (
                            "filament_type" in data or tag_lower == "filament"
                        ) else "process"
                    if "name" not in data:
                        ft = data.get("filament_type", "Unknown")
                        if isinstance(ft, list):
                            ft = ft[0] if ft else "Unknown"
                        data["name"] = f"Extracted {ft} profile"
                    profiles.append(Profile(data, source_path, "3mf"))

            elif tag_lower == "plate":
                pass

            elif tag_lower in ("settings", "object_settings"):
                data = ProfileEngine._extract_xml_profile(elem)
                if data and ProfileEngine._is_profile_data(data):
                    profiles.append(Profile(data, source_path, "3mf"))

        return profiles

    @staticmethod
    def _parse_config_ini(content: str, source_path: str) -> list:
        """Parse INI-style [section:name] key=value config content."""
        profiles = []
        current = {}
        current_name = None
        for line in content.splitlines():
            line = line.strip()
            m = re.match(r'^\[(\w+)(?::(.+))?\]$', line)
            if m:
                if current and current_name and ProfileEngine._is_profile_data(current):
                    current["name"] = current_name
                    profiles.append(Profile(current, source_path, "3mf"))
                current = {"type": m.group(1)}
                current_name = m.group(2) or m.group(1)
                continue
            kv = re.match(r'^(\S+)\s*=\s*(.+)$', line)
            if kv:
                current[kv.group(1)] = ProfileEngine._parse_config_value(kv.group(2).strip())
        if current and current_name and ProfileEngine._is_profile_data(current):
            current["name"] = current_name
            profiles.append(Profile(current, source_path, "3mf"))
        return profiles

    @staticmethod
    def _parse_config(content: str, source_path: str) -> list:
        """Parse config content from .3mf metadata files.
        Tries JSON first, then XML, then INI, then flat key=value."""
        stripped = content.strip()

        if stripped.startswith("{") or stripped.startswith("["):
            return ProfileEngine._parse_config_json(content, source_path)

        try:
            profiles = ProfileEngine._parse_config_xml(content, source_path)
        except ET.ParseError:
            profiles = ProfileEngine._parse_config_ini(content, source_path)

        if not profiles and "=" in content and not stripped.startswith("<"):
            data = {}
            for line in content.splitlines():
                line = line.strip()
                kv = re.match(r'^(\S+)\s*=\s*(.+)$', line)
                if kv:
                    data[kv.group(1)] = ProfileEngine._parse_config_value(kv.group(2).strip())
            if data and ProfileEngine._is_profile_data(data):
                if "name" not in data:
                    data["name"] = f"Extracted profile from {os.path.basename(source_path)}"
                profiles.append(Profile(data, source_path, "3mf"))

        return profiles

    @staticmethod
    def _extract_xml_profile(elem) -> dict:
        """Extract key-value pairs from an XML element."""
        data = {}
        for child in elem:
            tag = child.tag.lower().split("}")[-1]
            if tag == "metadata":
                k = child.get("key", "")
                v = child.get("value", child.text or "")
                if k:
                    data[k] = ProfileEngine._parse_config_value(v)
            elif tag == "setting":
                k = child.get("key", child.get("id", ""))
                v = child.get("value", child.text or "")
                if k:
                    data[k] = ProfileEngine._parse_config_value(v)
        for k, v in elem.attrib.items():
            if k in ("id", "idx"):
                continue
            if k not in data:
                data[k] = ProfileEngine._parse_config_value(v)
        return data

    @staticmethod
    def _is_profile_data(data: dict) -> bool:
        """Check if a dict looks like actual profile data (not just plate metadata)."""
        return bool(data.keys() & _PROFILE_SIGNAL_KEYS)

    @staticmethod
    def _parse_config_value(raw_string: str):
        """Parse a config value to Python type (bool, int, float, JSON, or str)."""
        if not isinstance(raw_string, str):
            return raw_string
        s_lower = raw_string.lower()
        if s_lower in ("true", "false"):
            return s_lower == "true"
        if " " not in raw_string and not raw_string.startswith("#") and raw_string.count(".") <= 1:
            if re.match(r'^-?\d+\.?\d*$', raw_string):
                try:
                    result = float(raw_string) if "." in raw_string else int(raw_string)
                    logger.debug("Converted string '%s' to %s", raw_string, type(result).__name__)
                    return result
                except ValueError:
                    pass
        if raw_string.startswith(("[", "{")):
            try:
                return json.loads(raw_string)
            except Exception as e:
                logger.debug("Failed to parse JSON value '%s': %s", raw_string, e)
        return raw_string

    @staticmethod
    def load_file(path: str, type_hint: str = None) -> list:
        """Load profiles from a file (auto-detect format by extension)."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".json":
            return ProfileEngine.load_json(path, type_hint)
        elif ext in (".3mf", ".bbsflmt"):
            return ProfileEngine.extract_from_3mf(path)
        raise ValueError(f"Unsupported: {ext}")


class SlicerDetector:
    """
    Detect installed slicer applications and locate their configuration directories.
    Provides utilities for discovering preset files.
    """

    # Platform-specific paths to slicer config directories
    PATHS = {
        "BambuStudio": {"Darwin": "~/Library/Application Support/BambuStudio",
                        "Windows": "%APPDATA%/BambuStudio",
                        "Linux": "~/.config/BambuStudio"},
        "OrcaSlicer":  {"Darwin": "~/Library/Application Support/OrcaSlicer",
                        "Windows": "%APPDATA%/OrcaSlicer",
                        "Linux": "~/.config/OrcaSlicer"},
        "PrusaSlicer": {"Darwin": "~/Library/Application Support/PrusaSlicer",
                        "Windows": "%APPDATA%/PrusaSlicer",
                        "Linux": "~/.config/PrusaSlicer"},
    }

    @staticmethod
    def find_all() -> dict:
        """Find all installed slicers and return dict of {slicer_name: path}."""
        found = {}
        system = _PLATFORM  # Use _PLATFORM from constants
        for slicer, paths in SlicerDetector.PATHS.items():
            path_template = paths.get(system, "")
            if not path_template:
                continue
            expanded_path = os.path.expandvars(os.path.expanduser(path_template))
            if os.path.isdir(expanded_path):
                found[slicer] = expanded_path
        return found

    @staticmethod
    def find_user_presets(slicer_path: str) -> dict:
        """Returns dict of {profile_type: [file_paths]} with type info preserved."""
        presets = {"filament": [], "process": [], "machine": []}
        user_dir = os.path.join(slicer_path, "user")
        if not os.path.isdir(user_dir):
            return presets
        for uid in os.listdir(user_dir):
            uid_path = os.path.join(user_dir, uid)
            if not os.path.isdir(uid_path):
                continue
            for profile_type in presets:
                type_dir = os.path.join(uid_path, profile_type)
                if os.path.isdir(type_dir):
                    presets[profile_type].extend(
                        os.path.join(type_dir, f) for f in os.listdir(type_dir) if f.endswith(".json")
                    )
        return presets

    @staticmethod
    def get_export_dir(slicer_path: str) -> str:
        """Get the export directory for user profiles."""
        user_dir = os.path.join(slicer_path, "user")
        if os.path.isdir(user_dir):
            for e in os.listdir(user_dir):
                entry_path = os.path.join(user_dir, e)
                if os.path.isdir(entry_path):
                    return entry_path
        return slicer_path
