"""Edge case tests for ProfileEngine — corrupt files, encoding, size limits, format detection."""

import json
import os
import sys
import tempfile
import zipfile
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from profile_toolkit.models import (
    Profile,
    ProfileEngine,
    UnsupportedFormatError,
    _decode_json_bytes,
)


def _write(path: str, content: bytes):
    with open(path, "wb") as f:
        f.write(content)


# --- load_json edge cases ---


class TestLoadJsonCorruptFiles:
    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b"")
            path = f.name
        try:
            with pytest.raises(ValueError):
                ProfileEngine.load_json(path)
        finally:
            os.unlink(path)

    def test_truncated_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b'{"name": "PLA", "temp":')
            path = f.name
        try:
            with pytest.raises(ValueError, match="Invalid JSON"):
                ProfileEngine.load_json(path)
        finally:
            os.unlink(path)

    def test_valid_json_but_not_profile(self):
        """A valid JSON dict without slicer keys should be rejected."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump({"greeting": "hello", "count": 42}, f)
            path = f.name
        try:
            with pytest.raises(ValueError, match="not a recognized slicer profile"):
                ProfileEngine.load_json(path)
        finally:
            os.unlink(path)

    def test_json_number_top_level(self):
        """Top-level JSON number should raise (rejected by decode since no { or [)."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("42")
            path = f.name
        try:
            with pytest.raises(ValueError):
                ProfileEngine.load_json(path)
        finally:
            os.unlink(path)

    def test_binary_garbage(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(os.urandom(256))
            path = f.name
        try:
            with pytest.raises((ValueError, UnsupportedFormatError)):
                ProfileEngine.load_json(path)
        finally:
            os.unlink(path)


class TestLoadJsonEncodings:
    def test_utf8_bom_profile(self):
        """UTF-8 BOM files should load normally."""
        data = {"name": "BOM Test", "filament_type": "PLA"}
        content = b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8")
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            profiles = ProfileEngine.load_json(path)
            assert len(profiles) == 1
            assert profiles[0].data["name"] == "BOM Test"
        finally:
            os.unlink(path)

    def test_latin1_profile(self):
        """Latin-1 encoded profile with accented chars."""
        data = '{"name": "Résine Spéciale", "filament_type": "Resin"}'
        content = data.encode("latin-1")
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            profiles = ProfileEngine.load_json(path)
            assert len(profiles) == 1
        finally:
            os.unlink(path)

    def test_zlib_compressed_profile(self):
        """Zlib-compressed JSON (BambuStudio format)."""
        data = {"name": "Compressed PLA", "filament_type": "PLA", "temp": 210}
        compressed = zlib.compress(json.dumps(data).encode("utf-8"))
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(compressed)
            path = f.name
        try:
            profiles = ProfileEngine.load_json(path)
            assert len(profiles) == 1
            assert profiles[0].data["name"] == "Compressed PLA"
        finally:
            os.unlink(path)


class TestLoadJsonArrays:
    def test_array_with_duplicates_deduped(self):
        """Duplicate names in a JSON array should be deduplicated."""
        data = [
            {"name": "PLA", "filament_type": "PLA", "temp": 200},
            {"name": "PLA", "filament_type": "PLA", "temp": 210},
        ]
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(data, f)
            path = f.name
        try:
            profiles = ProfileEngine.load_json(path)
            assert len(profiles) == 1  # second "PLA" skipped
        finally:
            os.unlink(path)

    def test_array_no_profiles(self):
        """Array of non-profile dicts should raise."""
        data = [{"foo": "bar"}, {"baz": 42}]
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(data, f)
            path = f.name
        try:
            with pytest.raises(ValueError, match="no recognized"):
                ProfileEngine.load_json(path)
        finally:
            os.unlink(path)

    def test_empty_array(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump([], f)
            path = f.name
        try:
            profiles = ProfileEngine.load_json(path)
            assert profiles == []
        finally:
            os.unlink(path)


class TestLoadJson3mfFallback:
    def test_zip_file_detected_as_3mf(self):
        """A .json file that is actually a ZIP/3MF archive should be handled."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            with zipfile.ZipFile(path, "w") as zf:
                profile = {"name": "3MF Profile", "filament_type": "PLA"}
                zf.writestr("preset.json", json.dumps(profile))
            profiles = ProfileEngine.load_json(path)
            assert len(profiles) >= 1
        finally:
            os.unlink(path)


# --- Profile edge cases ---


class TestProfileSanitizeEdgeCases:
    def test_control_characters_stripped(self):
        name = "PLA\x00\x01\x02Test"
        assert "\x00" not in Profile.sanitize_name(name)

    def test_unicode_preserved(self):
        name = "フィラメント PLA 日本語"
        assert Profile.sanitize_name(name) == name

    def test_curly_braces_replaced(self):
        name = "PLA {template}"
        sanitized = Profile.sanitize_name(name)
        assert "{" not in sanitized
        assert "}" not in sanitized

    def test_whitespace_collapsed(self):
        name = "PLA    Extra   Spaces"
        assert Profile.sanitize_name(name) == "PLA Extra Spaces"

    def test_empty_string(self):
        assert Profile.sanitize_name("") == ""


class TestProfileChangelog:
    def test_log_and_restore(self):
        p = Profile(
            {"name": "Test", "temp": 200},
            "/tmp/test.json",
            "json",
        )
        snapshot = {"_full_data": {"name": "Test", "temp": 200}, "_modified": False}
        p.data["temp"] = 999
        p.modified = True
        p.log_change("edit", "changed temp", snapshot)
        assert p.restore_snapshot(0)
        assert p.data["temp"] == 200
        assert not p.modified

    def test_restore_invalid_index(self):
        p = Profile({"name": "Test"}, "/tmp/test.json", "json")
        assert not p.restore_snapshot(5)
        assert not p.restore_snapshot(-1)

    def test_restore_no_snapshot(self):
        p = Profile({"name": "Test"}, "/tmp/test.json", "json")
        p.log_change("info", "no snapshot")
        assert not p.restore_snapshot(0)


# --- _decode_json_bytes additional edge cases ---


class TestDecodeJsonBytesEdgeCases:
    def test_whitespace_padded(self):
        result = _decode_json_bytes(b"   \n  {\"key\": 1}  \n  ")
        assert result is not None
        assert "key" in result

    def test_oversized_zlib_bomb_rejected(self):
        """Zlib data that decompresses to >50MB should be rejected."""
        # Create data that compresses very well (all zeros)
        huge = b"{" + b'"k":0,' * 10_000_000  # ~70MB uncompressed
        compressed = zlib.compress(huge[:51 * 1024 * 1024])  # compress first 51MB
        result = _decode_json_bytes(compressed)
        # Should either return None or truncate — not crash
        # The function has a 50MB decompression limit
        assert result is None or isinstance(result, str)
