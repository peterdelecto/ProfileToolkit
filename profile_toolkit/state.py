# Profile state persistence (changelog, modified flags, online import prefs)

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from typing import TYPE_CHECKING

from .constants import _PLATFORM

if TYPE_CHECKING:
    from .models import Profile

logger = logging.getLogger(__name__)


def _config_base_dir() -> str:
    """Platform-aware base directory for app config/state files."""
    if _PLATFORM == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif _PLATFORM == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/.config")

    new_path = os.path.join(base, "ProfileToolkit")
    old_path = os.path.join(base, "PrintProfileConverter")

    # Migrate legacy directory if new one doesn't exist yet
    if os.path.isdir(old_path) and not os.path.isdir(new_path):
        try:
            import shutil

            shutil.move(old_path, new_path)
            logger.info("Migrated config dir: %s -> %s", old_path, new_path)
        except OSError as exc:
            logger.warning("Could not migrate config dir: %s", exc)
            return old_path

    # Prefer new path; fall back to old if new doesn't exist but old does
    if os.path.isdir(new_path):
        return new_path
    if os.path.isdir(old_path):
        return old_path
    return new_path


def online_import_prefs_path() -> str:
    """Path to online_import_prefs.json, platform-aware."""
    return os.path.join(_config_base_dir(), "online_import_prefs.json")


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
    """Persist online import preferences to disk."""
    path = online_import_prefs_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(prefs, f, indent=2)
            os.replace(tmp, path)
        except Exception:
            os.unlink(tmp)
            raise
    except OSError as exc:
        logger.warning("Could not save online import prefs: %s", exc)


def state_dir() -> str:
    """Path to profile_state directory, platform-aware."""
    return os.path.join(_config_base_dir(), "profile_state")


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
        if len(entry) < 3:
            continue
        ts, action, details, *rest = entry
        snapshot = rest[0] if rest else None
        # Validate snapshot is JSON-serializable before including
        if snapshot is not None:
            try:
                json.dumps(snapshot)
            except (TypeError, ValueError):
                logger.debug(
                    "Stripping non-serializable snapshot for action '%s'", action
                )
                snapshot = None
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
        "saved_at": time.time(),
    }
    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(state_path), suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, state_path)
        except (OSError, TypeError):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as exc:
        logger.warning("Could not save state for profile '%s': %s", profile.name, exc)
    except TypeError as exc:
        logger.warning(
            "Could not serialize state for profile '%s': %s", profile.name, exc
        )


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
            logger.warning("Couldn't restore state for '%s': %s", profile.name, e)
            continue
        if state.get("source_path") != profile.source_path:
            continue
        if state.get("modified", False):
            profile.modified = True
        saved_log = state.get("changelog", [])
        if saved_log:
            restored_entries = []
            for entry in saved_log:
                restored_entries.append(
                    (
                        entry.get("ts", ""),
                        entry.get("action", ""),
                        entry.get("details", ""),
                        entry.get("snapshot"),
                    )
                )
            # Merge: keep existing in-memory entries, prepend restored ones (deduplicated)
            existing = {
                (ts, action, details) for ts, action, details, *_ in profile.changelog
            }
            deduped = [
                e for e in restored_entries if (e[0], e[1], e[2]) not in existing
            ]
            profile.changelog = deduped + profile.changelog
            if profile.modified:
                reapply_unlock_state(profile, state)


def reapply_unlock_state(profile: Profile, state: dict) -> None:
    """Walk the changelog backwards and re-apply the most recent unlock/retarget."""
    saved_at = state.get("saved_at")
    if saved_at and profile.source_path and os.path.exists(profile.source_path):
        try:
            file_mtime = os.path.getmtime(profile.source_path)
            if file_mtime > saved_at:
                logger.warning(
                    "Profile '%s' on disk is newer than saved state "
                    "(file modified %.0fs after state was saved). "
                    "State will be applied but may be stale.",
                    profile.name,
                    file_mtime - saved_at,
                )
        except OSError:
            logger.debug("Could not stat source file for '%s'", profile.name)
    saved_log = state.get("changelog", [])
    if not isinstance(saved_log, list):
        return
    try:
        for entry in reversed(saved_log):
            if not isinstance(entry, dict):
                continue
            action = entry.get("action", "")
            if action in ("Made Universal", "Retargeted"):
                saved_cp = state.get("compatible_printers")
                if isinstance(saved_cp, list):
                    profile.data["compatible_printers"] = saved_cp
                elif saved_cp is not None:
                    profile.data["compatible_printers"] = [str(saved_cp)]
                else:
                    profile.data["compatible_printers"] = []
                if "compatible_printers_condition" in profile.data:
                    profile.data["compatible_printers_condition"] = ""
                if "printer_settings_id" in profile.data:
                    profile.data["printer_settings_id"] = ""
                return
    except (TypeError, KeyError, AttributeError):
        logger.debug(
            "Could not reapply unlock state for '%s'", profile.name, exc_info=True
        )


def cleanup_stale_state(max_age_days: int = 90) -> int:
    """Remove state files whose source profiles no longer exist on disk.

    Returns count of files removed.
    """
    sdir = state_dir()
    if not os.path.isdir(sdir):
        return 0
    removed = 0
    cutoff = time.time() - (max_age_days * 86400)
    for fname in os.listdir(sdir):
        if not fname.endswith(".json"):
            continue
        fp = os.path.join(sdir, fname)
        try:
            with open(fp, "r", encoding="utf-8") as f:
                state = json.load(f)
            src = state.get("source_path", "")
            if src and not os.path.exists(src) and os.path.getmtime(fp) < cutoff:
                os.unlink(fp)
                removed += 1
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            logger.debug("Skipping stale state file '%s': %s", fname, exc)
            continue
    if removed:
        logger.info("Cleaned up %d stale state files", removed)
    return removed
