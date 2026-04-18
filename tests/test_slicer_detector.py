"""Tests for SlicerDetector — path discovery, preset scanning, export dir logic."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from profile_toolkit.models import SlicerDetector


class TestSlicerDetectorPaths:
    """PATHS dict covers all expected slicers and platforms."""

    def test_all_slicers_present(self):
        assert set(SlicerDetector.PATHS.keys()) == {"BambuStudio", "OrcaSlicer", "PrusaSlicer"}

    def test_all_platforms_covered(self):
        for slicer, paths in SlicerDetector.PATHS.items():
            assert set(paths.keys()) == {"Darwin", "Windows", "Linux"}, (
                f"{slicer} missing platforms: {set(paths.keys())}"
            )


class TestFindAll:
    """find_all returns only existing directories."""

    def test_returns_dict(self):
        result = SlicerDetector.find_all()
        assert isinstance(result, dict)

    def test_values_are_existing_dirs(self):
        for slicer, path in SlicerDetector.find_all().items():
            assert os.path.isdir(path), f"{slicer} path doesn't exist: {path}"


class TestFindUserPresets:
    """find_user_presets discovers JSON and INI files in expected layouts."""

    def test_orca_bambu_layout(self):
        """Orca/Bambu: user/<uid>/filament/*.json"""
        with tempfile.TemporaryDirectory() as root:
            uid_dir = os.path.join(root, "user", "12345", "filament")
            os.makedirs(uid_dir)
            for name in ["PLA.json", "PETG.json"]:
                with open(os.path.join(uid_dir, name), "w") as f:
                    json.dump({"name": name}, f)
            # Also create a non-json file that should be ignored
            with open(os.path.join(uid_dir, "notes.txt"), "w") as f:
                f.write("ignore me")

            result = SlicerDetector.find_user_presets(root)
            assert len(result["filament"]) == 2
            assert len(result["process"]) == 0
            assert len(result["machine"]) == 0

    def test_prusa_layout(self):
        """PrusaSlicer: filament/*.ini, print/*.ini, printer/*.ini"""
        with tempfile.TemporaryDirectory() as root:
            for subdir, profile_type in [("filament", "filament"), ("print", "process"), ("printer", "machine")]:
                d = os.path.join(root, subdir)
                os.makedirs(d)
                with open(os.path.join(d, "default.ini"), "w") as f:
                    f.write("[settings]\n")

            result = SlicerDetector.find_user_presets(root)
            assert len(result["filament"]) == 1
            assert len(result["process"]) == 1
            assert len(result["machine"]) == 1

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as root:
            result = SlicerDetector.find_user_presets(root)
            assert result == {"filament": [], "process": [], "machine": []}

    def test_ignores_non_json_in_orca_layout(self):
        with tempfile.TemporaryDirectory() as root:
            uid_dir = os.path.join(root, "user", "abc", "filament")
            os.makedirs(uid_dir)
            with open(os.path.join(uid_dir, "readme.txt"), "w") as f:
                f.write("not a profile")
            result = SlicerDetector.find_user_presets(root)
            assert result["filament"] == []

    def test_multiple_uids(self):
        """Multiple user directories should all be scanned."""
        with tempfile.TemporaryDirectory() as root:
            for uid in ["user1", "user2"]:
                d = os.path.join(root, "user", uid, "filament")
                os.makedirs(d)
                with open(os.path.join(d, f"{uid}_PLA.json"), "w") as f:
                    json.dump({"name": f"{uid}_PLA"}, f)
            result = SlicerDetector.find_user_presets(root)
            assert len(result["filament"]) == 2


class TestGetExportDir:
    """get_export_dir picks the most recently modified user subdir."""

    def test_picks_newest_uid(self):
        with tempfile.TemporaryDirectory() as root:
            old = os.path.join(root, "user", "old_uid")
            new = os.path.join(root, "user", "new_uid")
            os.makedirs(old)
            os.makedirs(new)
            # Touch old first, then new
            os.utime(old, (1000, 1000))
            os.utime(new, (2000, 2000))
            result = SlicerDetector.get_export_dir(root)
            assert result == new

    def test_no_user_dir_falls_back(self):
        with tempfile.TemporaryDirectory() as root:
            result = SlicerDetector.get_export_dir(root)
            assert result == root

    def test_empty_user_dir_falls_back(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "user"))
            result = SlicerDetector.get_export_dir(root)
            assert result == root
