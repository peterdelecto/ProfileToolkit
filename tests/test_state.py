"""Tests for profile_toolkit.state — persistence, cleanup."""

import json
import os
import tempfile
import time
import unittest.mock as mock

from profile_toolkit.models import Profile
from profile_toolkit.state import (
    profile_state_key,
    save_profile_state,
    restore_profile_state,
    load_online_prefs,
    save_online_prefs,
    cleanup_stale_state,
)


def _make_profile(name="Test", path=None, modified=False):
    p = Profile(
        {"name": name, "filament_type": "PLA"},
        path or os.path.join(tempfile.gettempdir(), f"{name}.json"),
        "json",
    )
    p.modified = modified
    return p


class TestProfileStateKey:
    def test_deterministic(self):
        p = _make_profile("Test", "/tmp/test.json")
        k1 = profile_state_key(p)
        k2 = profile_state_key(p)
        assert k1 == k2

    def test_different_paths_differ(self):
        p1 = _make_profile("Test", "/tmp/a.json")
        p2 = _make_profile("Test", "/tmp/b.json")
        assert profile_state_key(p1) != profile_state_key(p2)

    def test_sanitizes_name(self):
        p = _make_profile("bad/name:here")
        key = profile_state_key(p)
        assert "/" not in key
        assert ":" not in key


class TestSaveRestoreState:
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("profile_toolkit.state.state_dir", return_value=tmpdir):
                p = _make_profile("RoundTrip", os.path.join(tmpdir, "rt.json"))
                p.modified = True
                p.log_change("edit", "set layer height")

                save_profile_state(p)

                # Create a fresh profile with same path
                p2 = _make_profile("RoundTrip", os.path.join(tmpdir, "rt.json"))
                assert p2.modified is False
                assert len(p2.changelog) == 0

                restore_profile_state([p2])

                assert p2.modified is True
                assert len(p2.changelog) == 1
                assert p2.changelog[0][1] == "edit"

    def test_skips_no_source_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("profile_toolkit.state.state_dir", return_value=tmpdir):
                p = _make_profile("NoPath")
                p.source_path = ""
                save_profile_state(p)
                # Should not create any file
                assert len(os.listdir(tmpdir)) == 0

    def test_snapshot_non_serializable_stripped(self):
        """Non-JSON-serializable snapshots should be stripped, not crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("profile_toolkit.state.state_dir", return_value=tmpdir):
                p = _make_profile("Snap", os.path.join(tmpdir, "snap.json"))
                p.log_change("edit", "bad snapshot", snapshot={"func": lambda: None})

                save_profile_state(p)

                # Should have saved without the snapshot
                state_files = [f for f in os.listdir(tmpdir) if f.endswith(".json")]
                assert len(state_files) == 1
                with open(os.path.join(tmpdir, state_files[0])) as f:
                    state = json.load(f)
                assert state["changelog"][0]["snapshot"] is None


class TestOnlinePrefs:
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prefs_path = os.path.join(tmpdir, "online_import_prefs.json")
            with mock.patch(
                "profile_toolkit.state.online_import_prefs_path",
                return_value=prefs_path,
            ):
                save_online_prefs({"last_provider": "Polymaker", "count": 5})
                result = load_online_prefs()
                assert result["last_provider"] == "Polymaker"
                assert result["count"] == 5

    def test_missing_file_returns_empty(self):
        with mock.patch(
            "profile_toolkit.state.online_import_prefs_path",
            return_value="/nonexistent/path/prefs.json",
        ):
            assert load_online_prefs() == {}


class TestCleanupStaleState:
    def test_removes_stale_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("profile_toolkit.state.state_dir", return_value=tmpdir):
                # Create a state file pointing to a non-existent source
                state = {
                    "source_path": "/nonexistent/profile.json",
                    "name": "Gone",
                    "modified": False,
                    "changelog": [],
                }
                state_file = os.path.join(tmpdir, "gone_abc123.json")
                with open(state_file, "w") as f:
                    json.dump(state, f)
                # Backdate the file so it's older than max_age
                old_time = time.time() - (91 * 86400)
                os.utime(state_file, (old_time, old_time))

                removed = cleanup_stale_state(max_age_days=90)
                assert removed == 1
                assert not os.path.exists(state_file)

    def test_keeps_recent_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("profile_toolkit.state.state_dir", return_value=tmpdir):
                state = {
                    "source_path": "/nonexistent/profile.json",
                    "name": "Recent",
                    "modified": False,
                    "changelog": [],
                }
                state_file = os.path.join(tmpdir, "recent_abc123.json")
                with open(state_file, "w") as f:
                    json.dump(state, f)
                # File is fresh — should not be removed
                removed = cleanup_stale_state(max_age_days=90)
                assert removed == 0
                assert os.path.exists(state_file)

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("profile_toolkit.state.state_dir", return_value=tmpdir):
                assert cleanup_stale_state() == 0
