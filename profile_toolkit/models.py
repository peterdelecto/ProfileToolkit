# Core data models

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from copy import deepcopy
from datetime import datetime
from typing import Optional


class UnsupportedFormatError(ValueError):
    """Raised when a file extension is not a recognized profile format."""


class BundleDetectedError(ValueError):
    """Raised when a file is a Prusa bundle requiring the wizard flow."""


from .constants import (
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
    FILAMENT_LAYOUT,
    MAX_INHERITANCE_DEPTH,
)

logger = logging.getLogger(__name__)


def _decode_json_bytes(raw: bytes) -> Optional[str]:
    """Decode raw bytes to JSON text, trying zlib decompression then encoding chains.

    Returns the decoded text string ready for json.loads(), or None if all attempts fail.
    """
    text = None
    _MAX_DECOMPRESS = 50 * 1024 * 1024  # 50 MB
    if len(raw) >= 2 and raw[0:1] != b"{" and raw[0:1] != b"[":
        for wbits in (15, -15, 15 + 32):  # zlib, raw deflate, gzip
            try:
                dobj = zlib.decompressobj(wbits)
                decompressed = dobj.decompress(raw, max_length=_MAX_DECOMPRESS)
                if dobj.unconsumed_tail:
                    raise ValueError("Decompressed data exceeds 50 MB limit")
                candidate = decompressed.decode("utf-8").strip()
                if candidate and candidate[0] in ("{", "["):
                    text = candidate
                    break
            except (zlib.error, UnicodeDecodeError, ValueError) as exc:
                logger.debug("zlib probe wbits=%d failed: %s", wbits, exc)
                continue
    if text is None:
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                candidate = raw.decode(enc).strip()
                if candidate and candidate[0] in ("{", "["):
                    text = candidate
                    break
            except (UnicodeDecodeError, UnicodeError):
                continue
    return text


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

    @property
    def collisions(self) -> int:
        """Return the number of name collisions detected during indexing."""
        return self._collisions

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
        logger.debug(
            "PresetIndex: %s — %d new presets indexed, %d name collisions (last-write-wins)",
            label,
            added,
            self._collisions,
        )

    def _scan_dir(self, directory: str) -> None:
        """Recursively scan for .json preset files."""
        for root, dirs, files in os.walk(directory):
            for fname in files:
                if not fname.endswith(".json"):
                    continue
                fp = os.path.join(root, fname)
                try:
                    data = self._read_json_file(fp)
                    if data is None:
                        continue
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

    @staticmethod
    def _read_json_file(fp: str):
        """Read a JSON file, handling zlib-compressed and multi-encoding files."""
        with open(fp, "rb") as f:
            raw = f.read()
        text = _decode_json_bytes(raw)
        if text is None:
            return None
        return json.loads(text)

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
                logger.warning(
                    "Circular inheritance detected: %s → %s",
                    " → ".join(chain),
                    current_name,
                )
                break
            visited.add(current_name)
            parent_data = self._by_name.get(current_name)
            if parent_data is None:
                # Try fuzzy match: strip @suffix
                base = re.sub(r"\s*@.*$", "", current_name)
                parent_data = self._by_name.get(base)
            if parent_data is None:
                break
            chain.append(current_name)
            current_name = parent_data.get("inherits", "")
            depth += 1

        if depth >= max_depth and current_name:
            logger.warning(
                "Max inheritance depth %d reached for '%s' — possible circular inheritance",
                max_depth,
                profile.data.get("name", ""),
            )

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
                base = re.sub(r"\s*@.*$", "", ancestor_name)
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
        base = re.sub(r"\s*@.*$", "", name)
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

    def __init__(
        self,
        data: dict,
        source_path: str,
        source_type: str,
        type_hint: Optional[str] = None,
        origin: str = "",
    ) -> None:
        """Initialize a Profile object."""
        if not data:
            logger.warning("Profile created with empty data dict: %s", source_path)

        self.data = data
        self.source_path = source_path
        self.source_type = source_type
        self.type_hint = (
            type_hint  # From directory structure ("filament", "process", etc.)
        )
        self.origin = origin or self._detect_origin(source_path)
        self.modified = False
        self.changelog = []  # List of (timestamp, action, details, snapshot) tuples
        self._missing_conversion_keys: set[str] = (
            set()
        )  # Keys expected by target slicer after conversion
        # Populated by PresetIndex.resolve():
        self.resolved_data = None  # Full merged data (parent + overrides)
        self.inherited_keys = set()  # Keys that came from parent (not overridden)
        self.inheritance_chain = []  # List of ancestor names

        # Sanitize name on import to strip unsafe filesystem characters
        if self.data.get("name"):
            self.data["name"] = Profile.sanitize_name(self.data["name"])

    @staticmethod
    def sanitize_name(name: str) -> str:
        """Remove characters that are incompatible with slicer profile names.
        Strips filesystem-unsafe and JSON-unsafe characters, collapses whitespace.
        Preserves Unicode (CJK, accented characters, etc.)."""
        cleaned = Profile._UNSAFE_NAME_CHARS.sub("_", name)
        # Strip control characters but preserve all Unicode (CJK, accented, etc.)
        cleaned = re.sub(r"[\x00-\x1f]", "", cleaned)
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
        if "_full_data" in snapshot:
            self.data = deepcopy(snapshot["_full_data"])
            self.modified = snapshot.get("_modified", False)
        else:
            # Legacy per-key restore for inline rename snapshots etc.
            for k, v in snapshot.items():
                if k == "_modified":
                    self.modified = v
                else:
                    self.data[k] = deepcopy(v)
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
        return (
            name_val
            if name_val
            else os.path.splitext(os.path.basename(self.source_path))[0]
        )

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
            except (json.JSONDecodeError, ValueError, TypeError):
                compat_printers = [compat_printers] if compat_printers else []
        return compat_printers if isinstance(compat_printers, list) else []

    @property
    def is_factory_preset(self) -> bool:
        """True if this profile came from a slicer's system/vendor directory."""
        p = self.source_path.lower()
        return any(
            seg in p for seg in ("/system/", "/vendor/", "\\system\\", "\\vendor\\")
        )

    @property
    def inherits(self) -> str:
        """Return the profile name this profile inherits from, or empty string."""
        return self.data.get("inherits", "")

    @property
    def is_locked(self) -> bool:
        """Check if profile is printer-specific (bound to certain printer models)."""
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
                clean = re.sub(
                    r"\s+\d+\.\d+\s*nozzle$", "", printer_name, flags=re.IGNORECASE
                ).strip()
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
                match = re.search(r"(\d+\.\d+)\s*nozzle", printer_name, re.IGNORECASE)
                if match:
                    sizes.add(match.group(1) + "mm")
            if sizes:
                return ", ".join(sorted(sizes))

        name = self.data.get("name", "")
        match = re.search(r"(\d+\.\d+)\s*nozzle", name, re.IGNORECASE)
        if match:
            return match.group(1) + "mm"

        printer_settings_id = self.data.get("printer_settings_id", "")
        if isinstance(printer_settings_id, list):
            printer_settings_id = printer_settings_id[0] if printer_settings_id else ""
        if printer_settings_id:
            match = re.search(
                r"(\d+\.\d+)\s*nozzle", printer_settings_id, re.IGNORECASE
            )
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
                return "Made Universal"
            elif self.is_locked:
                return "Printer-Specific"
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

    def make_universal(self) -> None:
        """Remove printer-specific restrictions from a profile.

        Sets compatible_printers=[] which BambuStudio treats as "all printers"
        when on flattened user profiles — the profile appears in the Custom list
        for every printer. This matches known-working user profiles.
        """
        self._flatten_into_data()
        # Snapshot full data so restore can undo flattening + modifications
        snapshot = {"_full_data": deepcopy(self.data), "_modified": self.modified}

        old_printers = self.data.get("compatible_printers", [])
        old_psid = self.data.get("printer_settings_id", "")
        self.data["compatible_printers"] = []
        if "compatible_printers_condition" in self.data:
            self.data["compatible_printers_condition"] = ""
        if "printer_settings_id" in self.data:
            self.data["printer_settings_id"] = ""
        self.modified = True

        detail_parts = []
        if old_printers:
            detail_parts.append(
                f"Removed printer restriction: {', '.join(old_printers)}"
            )
        if old_psid:
            detail_parts.append(f"Cleared printer assignment: {old_psid}")
        self.log_change("Made Universal", "; ".join(detail_parts), snapshot=snapshot)

    def retarget(self, printers: list) -> None:
        """Retarget profile to a different set of printers."""
        if not printers:
            return
        printers = [str(p).strip() for p in printers if p and str(p).strip()]
        if not printers:
            return
        self._flatten_into_data()
        # Snapshot full data so restore can undo flattening + modifications
        snapshot = {"_full_data": deepcopy(self.data), "_modified": self.modified}

        old_printers = self.data.get("compatible_printers", [])
        self.data["compatible_printers"] = printers
        if "compatible_printers_condition" in self.data:
            self.data["compatible_printers_condition"] = ""
        if "printer_settings_id" in self.data:
            self.data["printer_settings_id"] = ""
        self.modified = True
        self.log_change(
            "Retargeted",
            f"{', '.join(old_printers) or 'Universal'} → {', '.join(printers)}",
            snapshot=snapshot,
        )

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
            # Overlay user edits so they take precedence over inherited values
            for k, v in self.data.items():
                if k != "inherits":
                    export[k] = v
            return json.dumps(export, indent=indent, ensure_ascii=False)
        return json.dumps(self.data, indent=indent, ensure_ascii=False)

    # Bambu → Prusa key mapping for parameters that differ only in name
    _BAMBU_TO_PRUSA = {
        "nozzle_temperature": "temperature",
        "nozzle_temperature_initial_layer": "first_layer_temperature",
        "close_fan_the_first_x_layers": "disable_fan_first_layers",
        "fan_min_speed": "min_fan_speed",
        "fan_max_speed": "max_fan_speed",
        "slow_down_min_speed": "min_print_speed",
        "filament_flow_ratio": "extrusion_multiplier",
        "filament_retraction_length": "filament_retract_length",
        "filament_retraction_speed": "filament_retract_speed",
        "filament_deretraction_speed": "filament_deretract_speed",
        "filament_max_volumetric_speed": "filament_max_volumetric_speed",
        "filament_start_gcode": "start_filament_gcode",
        "filament_end_gcode": "end_filament_gcode",
    }

    # Prusa → Bambu key mapping (reverse of _BAMBU_TO_PRUSA)
    _PRUSA_TO_BAMBU = {
        v: k for k, v in _BAMBU_TO_PRUSA.items() if v != k
    }  # skip identity mappings

    # Bed temperature: Prusa has 2 keys, Bambu has 6 plate types × 2 layers
    _PRUSA_BED_TO_BAMBU = {
        "bed_temperature": [
            "hot_plate_temp",
            "cool_plate_temp",
            "textured_plate_temp",
            "eng_plate_temp",
            "textured_cool_plate_temp",
            "supertack_plate_temp",
        ],
        "first_layer_bed_temperature": [
            "hot_plate_temp_initial_layer",
            "cool_plate_temp_initial_layer",
            "textured_plate_temp_initial_layer",
            "eng_plate_temp_initial_layer",
            "textured_cool_plate_temp_initial_layer",
            "supertack_plate_temp_initial_layer",
        ],
    }

    def convert_to(self, target: str) -> tuple["Profile", list[str], list[str]]:
        """Convert this profile to a different slicer format.

        Args:
            target: "PrusaSlicer", "OrcaSlicer", or "BambuStudio"

        Returns:
            (new_profile, dropped_keys, missing_keys)
            - dropped_keys: source-specific params removed (no target equivalent)
            - missing_keys: target-specific params not in source (need filling)
        """
        from .constants import FILAMENT_LAYOUT, _IDENTITY_KEYS

        # Flatten: merge resolved_data + data so we're self-contained
        if self.resolved_data:
            flat = dict(self.resolved_data)
            flat.update(self.data)
        else:
            flat = dict(self.data)

        # Remove identity/meta keys except name
        for k in list(flat):
            if k in _IDENTITY_KEYS and k != "name":
                del flat[k]

        source = self.origin or ""
        source_is_prusa = "prusa" in source.lower()
        target_is_prusa = "prusa" in target.lower()
        source_is_bambu_orca = "bambu" in source.lower() or "orca" in source.lower()
        target_is_bambu_orca = "bambu" in target.lower() or "orca" in target.lower()

        dropped: list[str] = []
        converted = {}

        # Collect slicer-tagged key sets from layout
        prusa_tagged = set()
        bambu_tagged = set()
        for tab_sections in FILAMENT_LAYOUT.values():
            for params in tab_sections.values():
                for entry in params:
                    if len(entry) >= 3:
                        if entry[2] == "Prusa":
                            prusa_tagged.add(entry[0])
                        elif entry[2] == "Bambu":
                            bambu_tagged.add(entry[0])

        if source_is_bambu_orca and target_is_prusa:
            # Bambu/Orca → Prusa
            for k, v in flat.items():
                if k in self._BAMBU_TO_PRUSA:
                    converted[self._BAMBU_TO_PRUSA[k]] = v
                elif k in bambu_tagged and k not in self._BAMBU_TO_PRUSA:
                    # Bambu-only key with no Prusa equivalent — check bed temps
                    if any(k in plates for plates in self._PRUSA_BED_TO_BAMBU.values()):
                        continue  # handled below
                    dropped.append(k)
                else:
                    converted[k] = v
            # Collapse Bambu plate temps → Prusa bed temps
            for prusa_key, bambu_plates in self._PRUSA_BED_TO_BAMBU.items():
                if prusa_key not in converted:
                    for plate in bambu_plates:
                        if plate in flat:
                            converted[prusa_key] = flat[plate]
                            break

        elif source_is_prusa and target_is_bambu_orca:
            # Prusa → Bambu/Orca
            for k, v in flat.items():
                if k in self._PRUSA_TO_BAMBU:
                    converted[self._PRUSA_TO_BAMBU[k]] = v
                elif k in prusa_tagged and k not in self._PRUSA_TO_BAMBU:
                    # Prusa-only key — check bed temps
                    if k in self._PRUSA_BED_TO_BAMBU:
                        # Expand to all plate types
                        for plate in self._PRUSA_BED_TO_BAMBU[k]:
                            converted[plate] = v
                    else:
                        dropped.append(k)
                else:
                    converted[k] = v

        elif source_is_bambu_orca and target_is_bambu_orca:
            # Bambu ↔ Orca: same keys, just change origin
            converted = flat
        else:
            # Unknown conversion path — copy as-is
            converted = flat

        # Determine missing keys: target-slicer-specific params not in converted data
        if target_is_prusa:
            target_specific = prusa_tagged
        elif target_is_bambu_orca:
            target_specific = bambu_tagged
        else:
            target_specific = set()

        # Also include keys that have mappings pointing to target
        mapped_target_keys = set()
        if target_is_prusa:
            mapped_target_keys = set(self._BAMBU_TO_PRUSA.values())
        elif target_is_bambu_orca:
            mapped_target_keys = set(self._PRUSA_TO_BAMBU.values())

        expected = target_specific | mapped_target_keys
        missing = sorted(k for k in expected if k not in converted)

        # Build new profile
        new_profile = Profile(
            data=converted,
            source_path=self.source_path,
            source_type=self.source_type,
            type_hint=self.type_hint,
            origin=target,
        )
        new_profile._missing_conversion_keys = set(missing)
        new_profile.modified = True
        new_profile.log_change(
            "convert",
            f"Converted from {source or 'unknown'} to {target}. "
            f"{len(dropped)} dropped, {len(missing)} missing.",
        )

        return new_profile, sorted(dropped), missing

    def to_prusa_ini(self) -> str:
        """Export profile as a PrusaSlicer-compatible INI string."""
        data = dict(self.resolved_data or {})
        data.update(self.data)

        # Collect all Prusa-tagged keys from the layout
        prusa_keys = set()
        for tab_sections in FILAMENT_LAYOUT.values():
            for params in tab_sections.values():
                for entry in params:
                    if len(entry) >= 3 and entry[2] == "Prusa":
                        prusa_keys.add(entry[0])

        out = {}
        # 1) Direct Prusa keys present in data
        for k in prusa_keys:
            if k in data:
                out[k] = data[k]
        # 2) Bambu→Prusa translations (only if Prusa key not already set)
        for bambu_key, prusa_key in self._BAMBU_TO_PRUSA.items():
            if prusa_key not in out and bambu_key in data:
                out[prusa_key] = data[bambu_key]
        # 3) Bed temperature: pick hot_plate first, then any *_plate_temp
        if "bed_temperature" not in out:
            for candidate in (
                "hot_plate_temp",
                "cool_plate_temp",
                "textured_plate_temp",
                "eng_plate_temp",
                "textured_cool_plate_temp",
                "supertack_plate_temp",
            ):
                if candidate in data:
                    out["bed_temperature"] = data[candidate]
                    break
        if "first_layer_bed_temperature" not in out:
            for candidate in (
                "hot_plate_temp_initial_layer",
                "cool_plate_temp_initial_layer",
                "textured_plate_temp_initial_layer",
                "eng_plate_temp_initial_layer",
                "textured_cool_plate_temp_initial_layer",
                "supertack_plate_temp_initial_layer",
            ):
                if candidate in data:
                    out["first_layer_bed_temperature"] = data[candidate]
                    break

        # Format as INI
        section_name = re.sub(r"\s*@\s*\S+.*$", "", self.name).strip() or "Unnamed"
        lines = [f"# generated by Profile Toolkit", f"[filament:{section_name}]"]
        for k in sorted(out):
            v = out[k]
            if isinstance(v, list):
                v = ";".join(str(x) for x in v)
            elif isinstance(v, bool):
                v = "1" if v else "0"
            lines.append(f"{k} = {v}")
        return "\n".join(lines) + "\n"

    def to_ini(self, flatten: bool = True) -> str:
        """Export to PrusaSlicer-compatible INI format."""
        source = self.data
        if flatten and self.resolved_data:
            source = dict(self.resolved_data)
            for k, v in self.data.items():
                if k != "inherits":
                    source[k] = v
        section_name = re.sub(r"\s*@\s*\S+.*$", "", self.name).strip() or "Unnamed"
        lines = [f"[filament:{section_name}]"]
        for k, v in sorted(source.items()):
            if k == "inherits" and flatten:
                continue
            if isinstance(v, bool):
                v = "1" if v else "0"
            elif isinstance(v, dict):
                v = json.dumps(v)
            elif isinstance(v, list):
                v = ";".join(str(x) for x in v)
            lines.append(f"{k} = {v}")
        return "\n".join(lines) + "\n"

    def suggested_filename(self, fmt: str = "json") -> str:
        """Generate a safe filename for export."""
        name = re.sub(r"\s*@\s*\S+.*$", "", self.name)
        name = re.sub(r"[^\w\s\-.]", "", name)
        name = re.sub(r"\s+", "_", name.strip())
        ext = fmt if fmt in ("json", "ini") else "json"
        return f"{name or 'profile'}.{ext}"


class ProfileEngine:
    """
    Static methods for loading and parsing profiles from various file formats.
    Supports JSON, 3MF archives, and embedded configuration formats.
    """

    @staticmethod
    def load_json(path: str, type_hint: str = None) -> list:
        """Load profiles from a JSON file.

        BambuStudio stores some .json preset files as raw zlib-compressed
        data (no text encoding — the first bytes are a zlib header, not
        '{' or '[').  We detect this by reading the first two bytes and
        attempting zlib decompression before falling back to plain-text
        encoding attempts.
        """
        raw = None
        with open(path, "rb") as f:
            raw = f.read()

        text = _decode_json_bytes(raw)

        # If all decoding failed, check if it's actually a zip/bbsflmt archive
        if text is None and len(raw) >= 4 and raw[:4] == b"PK\x03\x04":
            return ProfileEngine.extract_from_3mf(path)

        if text is None:
            raise ValueError(
                f"Cannot decode {os.path.basename(path)} "
                f"(file may be compressed in an unsupported format)"
            )

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {os.path.basename(path)}: {e}") from e

        def _is_profile(d: dict) -> bool:
            """Check if a dict looks like a slicer profile."""
            keys = set(d.keys())
            if keys & _PROFILE_SIGNAL_KEYS:
                return True
            # Also accept dicts with explicit type/name/inherits fields
            if any(d.get(k) for k in ("type", "name", "inherits", "setting_id")):
                return True
            return False

        if isinstance(data, dict):
            if not _is_profile(data):
                raise ValueError(
                    f"{os.path.basename(path)} is not a recognized slicer profile "
                    f"(no filament, process, or printer fields found)"
                )
            return [Profile(data, path, "json", type_hint)]
        elif isinstance(data, list):
            profiles = [
                Profile(d, path, "json", type_hint)
                for d in data
                if isinstance(d, dict) and _is_profile(d)
            ]
            if not profiles and data:
                raise ValueError(
                    f"{os.path.basename(path)} contains JSON but no recognized "
                    f"slicer profiles"
                )
            return profiles
        return []

    @staticmethod
    def extract_from_3mf(path: str) -> list:
        """Extract profiles from a 3MF archive file."""
        profiles = []
        errors = []
        if not zipfile.is_zipfile(path):
            raise ValueError(f"{os.path.basename(path)} is not a valid archive")

        _MAX_ENTRY_SIZE = 50 * 1024 * 1024  # 50 MB

        with zipfile.ZipFile(path, "r") as zf:
            for info in zf.infolist():
                name = info.filename
                if info.file_size > _MAX_ENTRY_SIZE:
                    logger.warning(
                        "3MF: skipping %s — file_size %d exceeds 50 MB limit",
                        name,
                        info.file_size,
                    )
                    continue

                if name.endswith(".json"):
                    try:
                        with zf.open(name) as entry_f:
                            raw = entry_f.read(_MAX_ENTRY_SIZE + 1)
                            if len(raw) > _MAX_ENTRY_SIZE:
                                logger.warning(
                                    "Skipping oversized entry: %s (%d bytes)",
                                    name,
                                    len(raw),
                                )
                                continue
                        text = _decode_json_bytes(raw)
                        if text is None:
                            errors.append(f"{name}: could not decode")
                            continue
                        data = json.loads(text)
                        if isinstance(data, dict) and (
                            "name" in data
                            or "type" in data
                            or "filament_type" in data
                            or "layer_height" in data
                        ):
                            profiles.append(Profile(data, path, "3mf"))
                    except (
                        json.JSONDecodeError,
                        UnicodeDecodeError,
                        KeyError,
                        ValueError,
                    ) as e:
                        errors.append(f"{name}: {e}")

                if name.startswith("Metadata/") and any(
                    name.endswith(ext) for ext in (".config", ".xml", ".ini")
                ):
                    try:
                        with zf.open(name) as entry_f:
                            raw = entry_f.read(_MAX_ENTRY_SIZE + 1)
                            if len(raw) > _MAX_ENTRY_SIZE:
                                logger.warning(
                                    "Skipping oversized entry: %s (%d bytes)",
                                    name,
                                    len(raw),
                                )
                                continue
                        text = _decode_json_bytes(raw)
                        if text is None:
                            errors.append(f"{name}: could not decode")
                            continue
                        profiles.extend(ProfileEngine._parse_config(text, path))
                    except (
                        UnicodeDecodeError,
                        KeyError,
                        ValueError,
                        ET.ParseError,
                    ) as e:
                        errors.append(f"{name}: {e}")

                if name.startswith("Metadata/") and name.endswith(".txt"):
                    try:
                        with zf.open(name) as entry_f:
                            raw = entry_f.read(_MAX_ENTRY_SIZE + 1)
                            if len(raw) > _MAX_ENTRY_SIZE:
                                logger.warning(
                                    "Skipping oversized entry: %s (%d bytes)",
                                    name,
                                    len(raw),
                                )
                                continue
                        text = _decode_json_bytes(raw)
                        if text is None:
                            errors.append(f"{name}: could not decode")
                            continue
                        if any(
                            k in text
                            for k in (
                                "filament_type",
                                "layer_height",
                                "nozzle_temperature",
                                "compatible_printers",
                            )
                        ):
                            profiles.extend(ProfileEngine._parse_config(text, path))
                    except (UnicodeDecodeError, KeyError, ValueError) as e:
                        errors.append(f"{name}: {e}")

        if errors:
            if not profiles:
                logger.warning(
                    "3MF extraction failed — no profiles extracted. Errors: %s",
                    "; ".join(errors),
                )
            else:
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
            items = (
                [data]
                if isinstance(data, dict)
                else (
                    [d for d in data if isinstance(d, dict)]
                    if isinstance(data, list)
                    else []
                )
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
                        elif len(item.keys() & _FILAMENT_SIGNAL_KEYS) > len(
                            item.keys() & _PROCESS_SIGNAL_KEYS
                        ):
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
                            sid = item.get("filament_settings_id") or item.get(
                                "setting_id"
                            )
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
        if len(content) > 10_000_000:  # 10 MB limit for XML metadata
            logger.warning("XML content too large, skipping: %d bytes", len(content))
            return []
        profiles = []
        parser = ET.XMLParser()
        parser.entity = {}  # Disable entity expansion
        try:
            root = ET.fromstring(content, parser=parser)
        except ET.ParseError:
            return []
        for elem in root.iter():
            tag_lower = elem.tag.lower().split("}")[-1]

            if tag_lower in ("filament", "print", "process"):
                data = ProfileEngine._extract_xml_profile(elem)
                if data and ProfileEngine._is_profile_data(data):
                    if "type" not in data:
                        data["type"] = (
                            "filament"
                            if ("filament_type" in data or tag_lower == "filament")
                            else "process"
                        )
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
            m = re.match(r"^\[(\w+)(?::(.+))?\]$", line)
            if m:
                if current and current_name and ProfileEngine._is_profile_data(current):
                    current["name"] = current_name
                    profiles.append(Profile(current, source_path, "3mf"))
                current = {"type": m.group(1)}
                current_name = m.group(2) or m.group(1)
                continue
            kv = re.match(r"^(\S+)\s*=\s*(.*)$", line)
            if kv:
                current[kv.group(1)] = ProfileEngine._parse_config_value(
                    kv.group(2).strip()
                )
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
                kv = re.match(r"^(\S+)\s*=\s*(.*)$", line)
                if kv:
                    data[kv.group(1)] = ProfileEngine._parse_config_value(
                        kv.group(2).strip()
                    )
            if data and ProfileEngine._is_profile_data(data):
                if "name" not in data:
                    data["name"] = (
                        f"Extracted profile from {os.path.basename(source_path)}"
                    )
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
        if (
            " " not in raw_string
            and not raw_string.startswith("#")
            and raw_string.count(".") <= 1
        ):
            if re.match(r"^-?\d+\.?\d*$", raw_string):
                try:
                    return float(raw_string) if "." in raw_string else int(raw_string)
                except ValueError:
                    pass
        if raw_string.startswith(("[", "{")):
            try:
                return json.loads(raw_string)
            except (json.JSONDecodeError, ValueError) as e:
                logger.debug("Failed to parse JSON value '%s': %s", raw_string, e)
        return raw_string

    @staticmethod
    def load_ini(path: str, type_hint: str = None) -> list:
        """Load a PrusaSlicer-style .ini profile (flat key=value, one profile per file)."""
        raw_bytes = open(path, "rb").read()
        content = None
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                content = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if content is None:
            content = raw_bytes.decode("utf-8", errors="replace")
        data = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^(\S+)\s*=\s*(.*)", line)
            if m:
                key = m.group(1)
                raw = m.group(2).strip()
                if raw == "nil":
                    continue  # PrusaSlicer nil = unset, skip
                # Preserve % suffix — PrusaSlicer uses it for relative values
                data[key] = ProfileEngine._parse_config_value(raw)
        if not data:
            return []
        # Derive name from filename if not in data
        if "name" not in data:
            data["name"] = os.path.splitext(os.path.basename(path))[0]
        return [Profile(data, path, "ini", type_hint=type_hint, origin="PrusaSlicer")]

    # ── Prusa Bundle (.ini with [vendor] + multiple [type:name] sections) ──

    @staticmethod
    def parse_prusa_bundle(path: str, only: str | None = None) -> dict:
        """Parse a PrusaSlicer factory bundle .ini into structured sections.

        Args:
            path: Path to the bundle .ini file
            only: If set, only parse this section type (e.g. "filaments")
                  to skip irrelevant sections and speed up parsing.

        Returns dict with keys:
            'vendor': dict of vendor metadata
            'printer_models': {model_id: {name, variants, default_materials, ...}}
            'filaments': {section_name: {key: value, ...}}  (includes abstract *name* entries)
            'prints': {section_name: {key: value, ...}}
            'printers': {section_name: {key: value, ...}}
        """
        sections: dict[str, dict] = {
            "vendor": {},
            "printer_models": {},
            "filaments": {},
            "prints": {},
            "printers": {},
        }

        # Map section type from header to bucket key
        _TYPE_TO_BUCKET = {
            "vendor": "vendor",
            "printer_model": "printer_models",
            "filament": "filaments",
            "print": "prints",
            "printer": "printers",
        }

        # Which bucket keys to actually populate
        if only:
            _active_buckets = {only, "vendor"}
        else:
            _active_buckets = None

        current_bucket = None
        current_name = None
        skip_section = False

        KV_RE = re.compile(r"^(\S+)\s*=\s*(.*)")

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                # Fast path: skip non-header lines in irrelevant sections
                if line[0] != "[":
                    if skip_section or current_bucket is None:
                        continue
                    stripped = line.strip()
                    if not stripped or stripped[0] in ("#", ";"):
                        continue
                    kv = KV_RE.match(stripped)
                    if kv:
                        key = kv.group(1)
                        raw = kv.group(2).strip()
                        if raw == "nil":
                            continue
                        # Preserve % suffix — PrusaSlicer uses it for relative values
                        # (e.g. fill_density = 20% vs 20)
                        val = ProfileEngine._parse_config_value(raw)
                        target = (
                            current_bucket
                            if current_name == "__self__"
                            else current_bucket[current_name]
                        )
                        target[key] = val
                    continue

                # Line starts with '[' — parse section header
                stripped = line.strip()
                # Extract type and name from [type:name]
                close = stripped.find("]")
                if close < 0:
                    continue
                inner = stripped[1:close]
                colon = inner.find(":")
                if colon >= 0:
                    sec_type = inner[:colon]
                    sec_name = inner[colon + 1 :].strip()
                else:
                    sec_type = inner
                    sec_name = ""

                bucket_key = _TYPE_TO_BUCKET.get(sec_type)
                if bucket_key is None:
                    skip_section = True
                    continue
                if _active_buckets and bucket_key not in _active_buckets:
                    skip_section = True
                    continue
                skip_section = False
                current_bucket = sections[bucket_key]
                if sec_type == "vendor":
                    current_name = "__self__"
                else:
                    current_name = sec_name
                    current_bucket[current_name] = {}

        return sections

    @staticmethod
    def is_prusa_bundle(path: str) -> bool:
        """Quick check: does this .ini file look like a PrusaSlicer factory bundle?"""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(4096)
            return "[vendor]" in head and "[printer_model:" in head
        except OSError:
            return False

    @staticmethod
    def resolve_bundle_filament(
        name: str,
        all_filaments: dict,
        _seen: set | None = None,
        _depth: int = 0,
    ) -> dict:
        """Resolve a filament section by flattening its inheritance chain.

        Handles multi-parent inheritance (inherits = parent1; parent2)
        with left-to-right merge, child overrides last. Cycle-safe.
        """
        if _depth > 20 or name in (_seen or set()) or name not in all_filaments:
            return {}
        if _seen is None:
            _seen = set()
        _seen.add(name)

        section = all_filaments[name]
        inherits_raw = section.get("inherits", "")
        if not inherits_raw:
            return dict(section)

        # Parse parent list: "parent1; parent2" or "parent1"
        parents = [p.strip() for p in str(inherits_raw).split(";") if p.strip()]

        # Merge parents left-to-right
        merged = {}
        for parent_name in parents:
            parent_data = ProfileEngine.resolve_bundle_filament(
                parent_name, all_filaments, set(_seen), _depth + 1
            )
            merged.update(parent_data)

        # Child overrides
        merged.update(section)
        return merged

    @staticmethod
    def load_bundle_filaments(
        path: str, selected_names: list[str], sections: dict | None = None
    ) -> list:
        """Load specific filament profiles from a Prusa bundle, fully resolved.

        Args:
            path: Path to the .ini bundle file
            selected_names: List of filament section names to resolve and return
            sections: Pre-parsed sections dict (avoids re-parsing the bundle)
        """
        if sections is None:
            sections = ProfileEngine.parse_prusa_bundle(path)
        all_filaments = sections["filaments"]
        profiles = []
        for name in selected_names:
            if name not in all_filaments:
                continue
            data = ProfileEngine.resolve_bundle_filament(name, all_filaments)
            data.pop("inherits", None)
            data.pop("compatible_printers_condition", None)
            if "name" not in data:
                data["name"] = name
            profiles.append(
                Profile(data, path, "ini", type_hint="filament", origin="PrusaSlicer")
            )
        return profiles

    @staticmethod
    def get_bundle_printer_families(sections: dict) -> dict[str, str]:
        """Extract printer families from bundle's printer_model sections.
        Returns {family_id: display_name} e.g. {'COREONE': 'Prusa CORE One'}"""
        families = {}
        for model_id, data in sections.get("printer_models", {}).items():
            families[model_id] = data.get("name", model_id)
        return families

    @staticmethod
    def get_bundle_filaments_by_family(sections: dict) -> dict[str, list[str]]:
        """Group concrete filament names by printer family from @ suffix.

        Maps @SUFFIX to the best-matching printer_model ID. Suffixes that
        don't match any model go under '__other__'. Profiles without @ go
        under '__generic__'.
        """
        model_ids = set(sections.get("printer_models", {}).keys())
        groups: dict[str, list[str]] = {"__generic__": []}

        def _best_model(suffix: str) -> str:
            """Find the printer_model ID that best matches a @ suffix."""
            # Try exact first word match: "COREONE HF0.4" -> "COREONE"
            base = suffix.split()[0] if suffix else ""
            if base in model_ids:
                return base
            # Try the full suffix as-is
            if suffix in model_ids:
                return suffix
            return "__other__"

        for name in sections.get("filaments", {}):
            if name.startswith("*") and name.endswith("*"):
                continue
            if "@" in name:
                suffix = name.split("@", 1)[1].strip()
                family = _best_model(suffix)
                groups.setdefault(family, []).append(name)
            else:
                groups["__generic__"].append(name)
        return groups

    @staticmethod
    def load_file(path: str, type_hint: str = None) -> list:
        """Load profiles from a file (auto-detect format by extension)."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".json":
            return ProfileEngine.load_json(path, type_hint)
        elif ext in (".3mf", ".bbsflmt"):
            return ProfileEngine.extract_from_3mf(path)
        elif ext == ".ini":
            # Check for bundle format first
            if ProfileEngine.is_prusa_bundle(path):
                raise BundleDetectedError(path)
            return ProfileEngine.load_ini(path, type_hint)
        raise UnsupportedFormatError(f"Unsupported: {ext}")


class SlicerDetector:
    """
    Detect installed slicer applications and locate their configuration directories.
    Provides utilities for discovering preset files.
    """

    # Platform-specific paths to slicer config directories
    PATHS = {
        "BambuStudio": {
            "Darwin": "~/Library/Application Support/BambuStudio",
            "Windows": "%APPDATA%/BambuStudio",
            "Linux": "~/.config/BambuStudio",
        },
        "OrcaSlicer": {
            "Darwin": "~/Library/Application Support/OrcaSlicer",
            "Windows": "%APPDATA%/OrcaSlicer",
            "Linux": "~/.config/OrcaSlicer",
        },
        "PrusaSlicer": {
            "Darwin": "~/Library/Application Support/PrusaSlicer",
            "Windows": "%APPDATA%/PrusaSlicer",
            "Linux": "~/.config/PrusaSlicer",
        },
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

        # Orca/Bambu layout: user/<uid>/<type>/*.json
        user_dir = os.path.join(slicer_path, "user")
        if os.path.isdir(user_dir):
            for uid in os.listdir(user_dir):
                uid_path = os.path.join(user_dir, uid)
                if not os.path.isdir(uid_path):
                    continue
                for profile_type in presets:
                    type_dir = os.path.join(uid_path, profile_type)
                    if os.path.isdir(type_dir):
                        presets[profile_type].extend(
                            os.path.join(type_dir, f)
                            for f in os.listdir(type_dir)
                            if f.endswith(".json")
                        )

        # PrusaSlicer layout: <type>/*.ini  (filament/, print/, printer/)
        _PRUSA_TYPE_MAP = {
            "filament": "filament",
            "print": "process",
            "printer": "machine",
        }
        for prusa_dir, mapped_type in _PRUSA_TYPE_MAP.items():
            type_dir = os.path.join(slicer_path, prusa_dir)
            if os.path.isdir(type_dir):
                presets[mapped_type].extend(
                    os.path.join(type_dir, f)
                    for f in os.listdir(type_dir)
                    if f.endswith(".ini")
                )

        return presets

    @staticmethod
    def get_export_dir(slicer_path: str) -> str:
        """Get the export directory for user profiles.

        Prefers the most recently modified user subdirectory to target the
        active account when multiple user directories exist.
        """
        user_dir = os.path.join(slicer_path, "user")
        if os.path.isdir(user_dir):
            candidates = []
            for e in os.listdir(user_dir):
                entry_path = os.path.join(user_dir, e)
                if os.path.isdir(entry_path):
                    candidates.append(entry_path)
            if candidates:
                return max(candidates, key=os.path.getmtime)
        return slicer_path
