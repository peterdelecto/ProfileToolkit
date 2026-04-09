# Profile state persistence (changelog, modified flags, online import prefs)

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .constants import _PLATFORM

if TYPE_CHECKING:
    from .models import Profile

logger = logging.getLogger(__name__)


def online_import_prefs_path() -> str:
    """Path to online_import_prefs.json, platform-aware."""
    if platform.system() == "Darwin":
        base = os.path.expanduser("~/Library/Application Support/PrintProfileConverter")
    elif platform.system() == "Windows":
        base = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")), "PrintProfileConverter"
        )
    else:
        base = os.path.expanduser("~/.config/PrintProfileConverter")
    return os.path.join(base, "online_import_prefs.json")


def load_online_prefs() -> dict:
    """Load online import prefs from disk, or empty dict on failure."""
    path = online_import_prefs_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        logger.debug("Couldn't load online prefs: %s", e)
        return {}


def save_online_prefs(prefs: dict) -> None:
    path = online_import_prefs_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
    except OSError as exc:
        logger.warning("Could not save online import prefs: %s", exc)


def state_dir() -> str:
    """Path to profile_state directory, platform-aware."""
    if platform.system() == "Darwin":
        base = os.path.expanduser("~/Library/Application Support/PrintProfileConverter")
    elif platform.system() == "Windows":
        base = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")), "PrintProfileConverter"
        )
    else:
        base = os.path.expanduser("~/.config/PrintProfileConverter")
    return os.path.join(base, "profile_state")


def profile_state_key(profile: Profile) -> str:
    """Sanitized name + short path hash, used as state filename."""
    path = profile.source_path or ""
    name = profile.name or "unknown"
    path_hash = hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
    safe_name = re.sub(r"[^\w\-.]", "_", name)[:60]
    return f"{safe_name}_{path_hash}"


def save_profile_state(profile: Profile) -> None:
    """Write changelog + modified flag to disk as JSON."""
    if not profile.source_path:
        return
    state_path = os.path.join(state_dir(), profile_state_key(profile) + ".json")
    changelog_data = []
    for entry in profile.changelog:
        ts, action, details = entry[0], entry[1], entry[2]
        snapshot = entry[3] if len(entry) > 3 else None
        changelog_data.append(
            {
                "ts": ts,
                "action": action,
                "details": details,
                "snapshot": snapshot,
            }
        )
    state = {
        "source_path": profile.source_path,
        "name": profile.name,
        "modified": profile.modified,
        "changelog": changelog_data,
        "compatible_printers": profile.data.get("compatible_printers"),
    }
    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.warning("Could not save state for profile '%s': %s", profile.name, exc)
    except TypeError as exc:
        logger.warning("Could not serialize state for profile '%s': %s", profile.name, exc)


def restore_profile_state(profiles: list[Profile]) -> None:
    """Load changelog + modified flags from disk onto the given profiles."""
    sdir = state_dir()
    if not os.path.isdir(sdir):
        return
    for profile in profiles:
        if not profile.source_path:
            continue
        state_path = os.path.join(sdir, profile_state_key(profile) + ".json")
        if not os.path.isfile(state_path):
            continue
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("Couldn't restore state for '%s': %s", profile.name, e)
            continue
        if state.get("source_path") != profile.source_path:
            continue
        if state.get("modified", False):
            profile.modified = True
        saved_log = state.get("changelog", [])
        if saved_log:
            profile.changelog = []
            for entry in saved_log:
                profile.changelog.append(
                    (
                        entry.get("ts", ""),
                        entry.get("action", ""),
                        entry.get("details", ""),
                        entry.get("snapshot"),
                    )
                )
            if profile.modified:
                reapply_unlock_state(profile, state)


def reapply_unlock_state(profile: Profile, state: dict) -> None:
    """Walk the changelog backwards and re-apply the most recent unlock/retarget."""
    saved_log = state.get("changelog", [])
    for entry in reversed(saved_log):
        action = entry.get("action", "")
        if action in ("Unlocked", "Retargeted"):
            saved_cp = state.get("compatible_printers")
            if saved_cp is not None:
                profile.data["compatible_printers"] = saved_cp
            else:
                profile.data["compatible_printers"] = []  # fallback for old state files
            if "compatible_printers_condition" in profile.data:
                profile.data["compatible_printers_condition"] = ""
            if "printer_settings_id" in profile.data:
                profile.data["printer_settings_id"] = ""
            return
