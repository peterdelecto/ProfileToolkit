import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest.mock as mock

# Build a tkinter mock that satisfies both `import tkinter as tk` and
# `from tkinter import ttk, filedialog, messagebox`.
tk_mock = mock.MagicMock()
tk_mock.__name__ = "tkinter"
tk_mock.__package__ = "tkinter"
tk_mock.__path__ = []
tk_mock.__spec__ = None

ttk_mock = mock.MagicMock()
ttk_mock.__name__ = "tkinter.ttk"
ttk_mock.__package__ = "tkinter"

filedialog_mock = mock.MagicMock()
filedialog_mock.__name__ = "tkinter.filedialog"
filedialog_mock.__package__ = "tkinter"

messagebox_mock = mock.MagicMock()
messagebox_mock.__name__ = "tkinter.messagebox"
messagebox_mock.__package__ = "tkinter"

tk_mock.ttk = ttk_mock
tk_mock.filedialog = filedialog_mock
tk_mock.messagebox = messagebox_mock

# Make tk.Frame and tk.Toplevel real (stub) classes so that subclasses like
# ProfileDetailPanel are real Python types and can be instantiated with object.__new__().
class _FakeTkBase:
    def __init__(self, *args, **kwargs):
        pass
    def winfo_toplevel(self):
        return self
    def bind(self, *args, **kwargs):
        pass

tk_mock.Frame = _FakeTkBase
tk_mock.Toplevel = _FakeTkBase
tk_mock.Tk = _FakeTkBase

sys.modules["tkinter"] = tk_mock
sys.modules["tkinter.ttk"] = ttk_mock
sys.modules["tkinter.filedialog"] = filedialog_mock
sys.modules["tkinter.messagebox"] = messagebox_mock

# Import from the refactored package
from profile_toolkit.models import Profile, ProfileEngine
from profile_toolkit.panels import ProfileDetailPanel
from profile_toolkit.constants import _ENUM_LABEL_TO_JSON


def make_profile(data=None):
    return Profile(data or {"name": "test", "layer_height": 0.2}, "/tmp/test.json", "json")


def _make_panel(profile=None):
    """Create a ProfileDetailPanel instance bypassing tkinter __init__."""
    panel = object.__new__(ProfileDetailPanel)
    panel._undo_stack = []
    panel._pre_edit_modified = None
    panel.current_profile = profile
    panel._edit_vars = {}
    panel._current_tab = None
    panel._param_order = []
    panel._switch_tab = lambda tab: None  # no-op; would require a display
    return panel


def test_undo_no_phantom_entry():
    """Clicking a field and then committing an unchanged value must not add an undo entry."""
    p = make_profile({"name": "test", "layer_height": 0.2})
    panel = _make_panel(profile=p)

    # Simulate what _commit_single does for an unchanged value
    key = "layer_height"
    original = 0.2
    var = mock.MagicMock()
    var.get.return_value = "0.2"         # user typed same value back
    panel._edit_vars[key] = (var, original, "entry")

    panel._commit_single(key)

    assert len(panel._undo_stack) == 0, (
        f"Undo stack should be empty after a no-change commit; got {panel._undo_stack}"
    )
    assert panel._pre_edit_modified is None


def test_undo_does_not_clear_conversion_modified():
    """Undoing parameter edit must not clear modified=True set by a conversion."""
    p = make_profile({"name": "test", "layer_height": 0.2})
    p.modified = True   # set by make_universal() / retarget() — not by a param edit

    panel = _make_panel(profile=p)

    # Simulate one real edit: push an undo entry + take pre_edit snapshot
    panel._pre_edit_modified = True        # was already modified before edit
    panel._undo_stack.append(("layer_height", 0.2))
    p.data["layer_height"] = 0.3
    p.modified = True

    # Now undo — should restore modified to pre_edit_modified (True), not False
    panel._on_undo()

    assert p.modified is True, (
        "After undoing a param edit on an already-converted profile, "
        "modified must remain True"
    )
    assert panel._pre_edit_modified is None   # sentinel cleaned up
    assert len(panel._undo_stack) == 0


def test_parse_edit_list_length_preserved():
    """Entering 2 values for a 4-element list should pad to 4."""
    original = [0.2, 0.2, 0.2, 0.2]
    result = ProfileDetailPanel._parse_edit("0.1, 0.3", original)
    assert len(result) == 4, f"Expected 4, got {len(result)}: {result}"
    assert result[0] == 0.1
    assert result[1] == 0.3
    assert result[2] == 0.3
    assert result[3] == 0.3


def test_pv_preserves_hex_color():
    assert ProfileEngine._parse_config_value("#FF0000") == "#FF0000"


def test_pv_preserves_version_string():
    assert ProfileEngine._parse_config_value("1.0.3") == "1.0.3"


def test_pv_preserves_gcode_string():
    gcode = "G28 X0"
    assert ProfileEngine._parse_config_value(gcode) == gcode


def test_format_value_humanizes_known_enum_label():
    """_format_value with a known enum key should return the human label, not the JSON value."""
    # seam_position: "nearest" → "Nearest" in ENUM_VALUES
    result = ProfileDetailPanel._format_value("nearest", key="seam_position")
    assert result == "Nearest", f"Expected 'Nearest', got {result!r}"


def test_enum_label_to_json_round_trip():
    """_ENUM_LABEL_TO_JSON must map human label back to raw JSON value for known enums."""
    label_to_json = _ENUM_LABEL_TO_JSON
    # wall_generator: "arachne" → "Arachne" forward, "Arachne" → "arachne" reverse
    assert "wall_generator" in label_to_json, "wall_generator must have reverse lookup"
    assert label_to_json["wall_generator"].get("Arachne") == "arachne", (
        "Reverse lookup 'Arachne' → 'arachne' must be correct"
    )
    assert label_to_json["wall_generator"].get("Classic") == "classic"
    # seam_position
    assert label_to_json["seam_position"].get("Nearest") == "nearest"
    assert label_to_json["seam_position"].get("Aligned") == "aligned"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
