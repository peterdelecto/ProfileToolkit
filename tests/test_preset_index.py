"""Tests for PresetIndex — indexing, collision tracking, inheritance resolution."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from profile_toolkit.models import PresetIndex, Profile


def _make_json_file(directory: str, name: str, data: dict) -> str:
    fp = os.path.join(directory, name)
    with open(fp, "w") as f:
        json.dump(data, f)
    return fp


def _make_profile(data: dict, source_path: str = "/tmp/test.json") -> Profile:
    return Profile(data=data, source_path=source_path, source_type="json")


class TestPresetIndexBuild:
    """build() scans directories and indexes presets by name."""

    def test_indexes_json_files(self):
        idx = PresetIndex()
        with tempfile.TemporaryDirectory() as root:
            sys_dir = os.path.join(root, "system")
            os.makedirs(sys_dir)
            _make_json_file(sys_dir, "pla.json", {"name": "PLA Generic", "temp": 210})
            _make_json_file(sys_dir, "petg.json", {"name": "PETG Generic", "temp": 230})
            idx.build(root, "BambuStudio")
        assert idx._by_name.get("PLA Generic") is not None
        assert idx._by_name.get("PETG Generic") is not None

    def test_skips_nameless_files(self):
        idx = PresetIndex()
        with tempfile.TemporaryDirectory() as root:
            sys_dir = os.path.join(root, "system")
            os.makedirs(sys_dir)
            _make_json_file(sys_dir, "noname.json", {"temp": 200})
            idx.build(root, "BambuStudio")
        assert len(idx._by_name) == 0

    def test_user_overrides_system(self):
        """User presets take priority over system presets (last-write-wins)."""
        idx = PresetIndex()
        with tempfile.TemporaryDirectory() as root:
            sys_dir = os.path.join(root, "system")
            usr_dir = os.path.join(root, "user", "uid1")
            os.makedirs(sys_dir)
            os.makedirs(usr_dir)
            _make_json_file(sys_dir, "pla.json", {"name": "PLA", "temp": 200})
            _make_json_file(usr_dir, "pla.json", {"name": "PLA", "temp": 215})
            idx.build(root, "BambuStudio")
        assert idx._by_name["PLA"]["temp"] == 215

    def test_collision_count(self):
        idx = PresetIndex()
        with tempfile.TemporaryDirectory() as root:
            sys_dir = os.path.join(root, "system")
            usr_dir = os.path.join(root, "user", "uid1")
            os.makedirs(sys_dir)
            os.makedirs(usr_dir)
            _make_json_file(sys_dir, "pla.json", {"name": "PLA", "temp": 200})
            _make_json_file(usr_dir, "pla.json", {"name": "PLA", "temp": 215})
            idx.build(root, "BambuStudio")
        assert idx.collisions == 1

    def test_handles_json_arrays(self):
        """Files containing a JSON array of presets should index each."""
        idx = PresetIndex()
        with tempfile.TemporaryDirectory() as root:
            sys_dir = os.path.join(root, "system")
            os.makedirs(sys_dir)
            _make_json_file(sys_dir, "bundle.json", [
                {"name": "ABS Basic", "temp": 240},
                {"name": "ABS High", "temp": 260},
            ])
            idx.build(root, "BambuStudio")
        assert "ABS Basic" in idx._by_name
        assert "ABS High" in idx._by_name


class TestPresetIndexResolve:
    """Inheritance chain resolution."""

    def _build_index_with_chain(self):
        """Create an index with grandparent → parent → child chain."""
        idx = PresetIndex()
        with tempfile.TemporaryDirectory() as root:
            sys_dir = os.path.join(root, "system")
            os.makedirs(sys_dir)
            _make_json_file(sys_dir, "gp.json", {
                "name": "Grandparent", "temp": 200, "speed": 50, "flow": 0.98,
            })
            _make_json_file(sys_dir, "parent.json", {
                "name": "Parent", "inherits": "Grandparent", "temp": 210,
            })
            idx.build(root, "BambuStudio")
        return idx

    def test_single_parent(self):
        idx = self._build_index_with_chain()
        child = _make_profile({"name": "Child", "inherits": "Parent", "speed": 60})
        idx.resolve(child)
        assert child.resolved_data is not None
        # Child overrides speed, inherits temp from Parent, flow from Grandparent
        assert child.resolved_data["temp"] == 210
        assert "flow" in child.inherited_keys

    def test_no_parent(self):
        idx = PresetIndex()
        profile = _make_profile({"name": "Standalone", "temp": 200})
        idx.resolve(profile)
        assert profile.resolved_data is None
        assert profile.inherited_keys == set()

    def test_missing_parent(self):
        idx = PresetIndex()
        profile = _make_profile({"name": "Orphan", "inherits": "DoesNotExist"})
        idx.resolve(profile)
        assert profile.resolved_data is None
        assert "Orphan" in idx.unresolved_profiles

    def test_circular_inheritance(self):
        """Circular references should be detected, not loop forever."""
        idx = PresetIndex()
        with tempfile.TemporaryDirectory() as root:
            sys_dir = os.path.join(root, "system")
            os.makedirs(sys_dir)
            _make_json_file(sys_dir, "a.json", {"name": "A", "inherits": "B", "temp": 200})
            _make_json_file(sys_dir, "b.json", {"name": "B", "inherits": "A", "temp": 210})
            idx.build(root, "BambuStudio")
        profile = _make_profile({"name": "C", "inherits": "A"})
        idx.resolve(profile)
        # Should not hang — just resolves what it can
        assert isinstance(profile.inheritance_chain, list)

    def test_resolve_caching(self):
        """Second resolve for same name uses cache."""
        idx = self._build_index_with_chain()
        p1 = _make_profile({"name": "Cached", "inherits": "Parent"})
        p2 = _make_profile({"name": "Cached", "inherits": "Parent"})
        idx.resolve(p1)
        idx.resolve(p2)
        assert p1.resolved_data == p2.resolved_data
        assert p1.inherited_keys == p2.inherited_keys


class TestPresetIndexCollectPrinters:
    """compatible_printers parsing."""

    def test_json_array_string(self):
        idx = PresetIndex()
        with tempfile.TemporaryDirectory() as root:
            sys_dir = os.path.join(root, "system")
            os.makedirs(sys_dir)
            _make_json_file(sys_dir, "pla.json", {
                "name": "PLA",
                "compatible_printers": '["Bambu Lab X1C", "Bambu Lab P1S"]',
            })
            idx.build(root, "BambuStudio")
        assert "Bambu Lab X1C" in idx.known_printers
        assert "Bambu Lab P1S" in idx.known_printers

    def test_semicolon_separated(self):
        idx = PresetIndex()
        with tempfile.TemporaryDirectory() as root:
            sys_dir = os.path.join(root, "system")
            os.makedirs(sys_dir)
            _make_json_file(sys_dir, "pla.json", {
                "name": "PLA",
                "compatible_printers": "Prusa MK4;Prusa MINI+",
            })
            idx.build(root, "BambuStudio")
        assert "Prusa MK4" in idx.known_printers
        assert "Prusa MINI+" in idx.known_printers

    def test_list_format(self):
        idx = PresetIndex()
        with tempfile.TemporaryDirectory() as root:
            sys_dir = os.path.join(root, "system")
            os.makedirs(sys_dir)
            _make_json_file(sys_dir, "pla.json", {
                "name": "PLA",
                "compatible_printers": ["Bambu Lab A1"],
            })
            idx.build(root, "BambuStudio")
        assert "Bambu Lab A1" in idx.known_printers
