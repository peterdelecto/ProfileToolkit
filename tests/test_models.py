"""Tests for profile_toolkit.models — Profile, ProfileEngine, _decode_json_bytes."""

import json
import os
import tempfile
import zlib

from profile_toolkit.models import Profile, ProfileEngine, _decode_json_bytes


def make_profile(data=None):
    return Profile(
        data or {"name": "test", "layer_height": 0.2},
        os.path.join(tempfile.gettempdir(), "test.json"),
        "json",
    )


# --- _decode_json_bytes ---


class TestDecodeJsonBytes:
    def test_plain_utf8(self):
        assert _decode_json_bytes(b'{"key": "value"}') == '{"key": "value"}'

    def test_utf8_bom(self):
        data = b'\xef\xbb\xbf{"key": "value"}'
        result = _decode_json_bytes(data)
        assert result is not None
        assert "key" in result

    def test_garbage_returns_none(self):
        assert _decode_json_bytes(b"\x00\x01\x02\x03") is None

    def test_zlib_compressed(self):
        original = b'{"compressed": true}'
        compressed = zlib.compress(original)
        result = _decode_json_bytes(compressed)
        assert result is not None
        assert "compressed" in result

    def test_latin1_fallback(self):
        # Latin-1 encoded JSON with non-ASCII char
        data = '{"name": "Résine"}'.encode("latin-1")
        result = _decode_json_bytes(data)
        assert result is not None
        assert "Résine" in result

    def test_json_array(self):
        assert _decode_json_bytes(b"[1, 2, 3]") == "[1, 2, 3]"

    def test_empty_bytes(self):
        assert _decode_json_bytes(b"") is None


# --- Profile ---


class TestProfileInit:
    def test_basic_creation(self):
        p = make_profile({"name": "Test", "layer_height": 0.2})
        assert p.data["name"] == "Test"
        assert p.modified is False
        assert p.changelog == []

    def test_sanitizes_name(self):
        p = make_profile({"name": "bad/name:here", "layer_height": 0.2})
        assert "/" not in p.data["name"]
        assert ":" not in p.data["name"]

    def test_log_change(self):
        p = make_profile()
        p.log_change("edit", "changed layer height")
        assert len(p.changelog) == 1
        assert p.changelog[0][1] == "edit"

    def test_restore_snapshot(self):
        p = make_profile({"name": "test", "layer_height": 0.2})
        snapshot = {
            "_full_data": {"name": "test", "layer_height": 0.15},
            "_modified": False,
        }
        p.log_change("edit", "changed lh", snapshot=snapshot)
        p.data["layer_height"] = 0.3
        p.modified = True
        assert p.restore_snapshot(0) is True
        assert p.data["layer_height"] == 0.15
        assert p.modified is False

    def test_restore_invalid_index(self):
        p = make_profile()
        assert p.restore_snapshot(5) is False
        assert p.restore_snapshot(-1) is False

    def test_restore_no_snapshot(self):
        p = make_profile()
        p.log_change("edit", "no snapshot")
        assert p.restore_snapshot(0) is False


class TestProfileSanitizeName:
    def test_strips_unsafe_chars(self):
        assert Profile.sanitize_name('test/file:name*"bad') == "test_file_name__bad"

    def test_preserves_unicode(self):
        assert Profile.sanitize_name("日本語プロファイル") == "日本語プロファイル"

    def test_collapses_whitespace(self):
        assert Profile.sanitize_name("too   many   spaces") == "too many spaces"

    def test_strips_control_chars(self):
        assert Profile.sanitize_name("test\x00\x01name") == "testname"

    def test_strips_braces(self):
        assert Profile.sanitize_name("template{var}") == "template_var_"

    def test_empty_string(self):
        assert Profile.sanitize_name("") == ""

    def test_only_unsafe(self):
        result = Profile.sanitize_name('/:*?"<>|')
        assert all(c not in result for c in '/:*?"<>|')


# --- ProfileEngine ---


class TestProfileEngineLoadJson:
    def test_load_single_profile(self):
        data = {"name": "Test PLA", "filament_type": "PLA", "layer_height": 0.2}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            profiles = ProfileEngine.load_json(path)
            assert len(profiles) == 1
            assert profiles[0].data["filament_type"] == "PLA"
        finally:
            os.unlink(path)

    def test_load_array_of_profiles(self):
        data = [
            {"name": "PLA", "filament_type": "PLA"},
            {"name": "PETG", "filament_type": "PETG"},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            profiles = ProfileEngine.load_json(path)
            assert len(profiles) == 2
            names = {p.data["name"] for p in profiles}
            assert names == {"PLA", "PETG"}
        finally:
            os.unlink(path)

    def test_load_deduplicates_by_name(self):
        data = [
            {"name": "Dupe", "filament_type": "PLA"},
            {"name": "Dupe", "filament_type": "PETG"},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            profiles = ProfileEngine.load_json(path)
            assert len(profiles) == 1
        finally:
            os.unlink(path)

    def test_load_zlib_compressed(self):
        data = {"name": "Compressed", "filament_type": "ABS"}
        compressed = zlib.compress(json.dumps(data).encode("utf-8"))
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(compressed)
            path = f.name
        try:
            profiles = ProfileEngine.load_json(path)
            assert len(profiles) == 1
            assert profiles[0].data["name"] == "Compressed"
        finally:
            os.unlink(path)

    def test_load_invalid_json_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{not valid json")
            path = f.name
        try:
            import pytest

            with pytest.raises(ValueError, match="Invalid JSON"):
                ProfileEngine.load_json(path)
        finally:
            os.unlink(path)

    def test_load_non_profile_raises(self):
        data = {"unrelated": "data", "no_profile_keys": True}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            import pytest

            with pytest.raises(ValueError, match="not a recognized slicer profile"):
                ProfileEngine.load_json(path)
        finally:
            os.unlink(path)

    def test_load_empty_array(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([], f)
            path = f.name
        try:
            profiles = ProfileEngine.load_json(path)
            assert profiles == []
        finally:
            os.unlink(path)


class TestProfileEngineLoadIni:
    def test_load_basic_ini(self):
        content = "name = Test Profile\nlayer_height = 0.2\nfilament_type = PLA\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            profiles = ProfileEngine.load_ini(path)
            assert len(profiles) == 1
            assert profiles[0].data["name"] == "Test Profile"
            assert profiles[0].data["layer_height"] == 0.2
        finally:
            os.unlink(path)

    def test_skips_nil_values(self):
        content = "name = Test\nlayer_height = nil\nfilament_type = PLA\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            profiles = ProfileEngine.load_ini(path)
            assert "layer_height" not in profiles[0].data
        finally:
            os.unlink(path)

    def test_skips_comments(self):
        content = "# This is a comment\nname = Test\nfilament_type = PLA\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            profiles = ProfileEngine.load_ini(path)
            assert len(profiles) == 1
        finally:
            os.unlink(path)

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write("")
            path = f.name
        try:
            profiles = ProfileEngine.load_ini(path)
            assert profiles == []
        finally:
            os.unlink(path)

    def test_derives_name_from_filename(self):
        content = "layer_height = 0.2\nfilament_type = PLA\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ini", delete=False, prefix="MyProfile_"
        ) as f:
            f.write(content)
            path = f.name
        try:
            profiles = ProfileEngine.load_ini(path)
            assert profiles[0].data["name"]  # should have a name derived from filename
        finally:
            os.unlink(path)


class TestProfileEngineParseConfigValue:
    def test_bool_true(self):
        assert ProfileEngine._parse_config_value("true") is True

    def test_bool_false(self):
        assert ProfileEngine._parse_config_value("false") is False

    def test_integer(self):
        assert ProfileEngine._parse_config_value("42") == 42

    def test_float(self):
        assert ProfileEngine._parse_config_value("3.14") == 3.14

    def test_negative_int(self):
        assert ProfileEngine._parse_config_value("-5") == -5

    def test_hex_color_preserved(self):
        assert ProfileEngine._parse_config_value("#FF0000") == "#FF0000"

    def test_version_string_preserved(self):
        assert ProfileEngine._parse_config_value("1.0.3") == "1.0.3"

    def test_gcode_preserved(self):
        assert ProfileEngine._parse_config_value("G28 X0") == "G28 X0"

    def test_json_array(self):
        result = ProfileEngine._parse_config_value("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_json_object(self):
        result = ProfileEngine._parse_config_value('{"a": 1}')
        assert result == {"a": 1}

    def test_non_string_passthrough(self):
        assert ProfileEngine._parse_config_value(42) == 42


class TestProfileEngine3mf:
    def test_extract_from_3mf_with_json(self):
        """Create a minimal 3MF zip with a JSON profile inside."""
        import zipfile

        data = {"name": "3MF Profile", "filament_type": "PLA", "layer_height": 0.2}
        with tempfile.NamedTemporaryFile(suffix=".3mf", delete=False) as f:
            path = f.name
        try:
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("profile.json", json.dumps(data))
            profiles = ProfileEngine.extract_from_3mf(path)
            assert len(profiles) == 1
            assert profiles[0].data["name"] == "3MF Profile"
        finally:
            os.unlink(path)

    def test_extract_deduplicates(self):
        import zipfile

        data = {"name": "Dupe", "filament_type": "PLA"}
        with tempfile.NamedTemporaryFile(suffix=".3mf", delete=False) as f:
            path = f.name
        try:
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("a.json", json.dumps(data))
                zf.writestr("b.json", json.dumps(data))
            profiles = ProfileEngine.extract_from_3mf(path)
            assert len(profiles) == 1
        finally:
            os.unlink(path)

    def test_not_a_zip_raises(self):
        import pytest

        with tempfile.NamedTemporaryFile(mode="w", suffix=".3mf", delete=False) as f:
            f.write("not a zip")
            path = f.name
        try:
            with pytest.raises(ValueError, match="not a valid archive"):
                ProfileEngine.extract_from_3mf(path)
        finally:
            os.unlink(path)
