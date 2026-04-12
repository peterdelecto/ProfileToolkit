"""Tests for ProfileDetailPanel (undo, parse, format)."""

import os
import tempfile
import unittest.mock as mock

from profile_toolkit.models import Profile
from profile_toolkit.panels import ProfileDetailPanel
from profile_toolkit.constants import _ENUM_LABEL_TO_JSON


def make_profile(data=None):
    return Profile(
        data or {"name": "test", "layer_height": 0.2},
        os.path.join(tempfile.gettempdir(), "test.json"),
        "json",
    )


def _make_panel(profile=None):
    """Create a ProfileDetailPanel instance bypassing tkinter __init__."""
    panel = object.__new__(ProfileDetailPanel)
    panel._undo_stack = []
    panel._pre_edit_modified = None
    panel.current_profile = profile
    panel._edit_vars = {}
    panel._current_tab = None
    panel._param_order = []
    panel._switch_tab = lambda tab: None
    return panel


def test_undo_no_phantom_entry():
    """Clicking a field and then committing an unchanged value must not add an undo entry."""
    p = make_profile({"name": "test", "layer_height": 0.2})
    panel = _make_panel(profile=p)

    key = "layer_height"
    original = 0.2
    var = mock.MagicMock()
    var.get.return_value = "0.2"
    panel._edit_vars[key] = (var, original, "entry")

    panel._commit_single(key)

    assert (
        len(panel._undo_stack) == 0
    ), f"Undo stack should be empty after a no-change commit; got {panel._undo_stack}"
    assert panel._pre_edit_modified is None


def test_undo_does_not_clear_conversion_modified():
    """Undoing parameter edit must not clear modified=True set by a conversion."""
    p = make_profile({"name": "test", "layer_height": 0.2})
    p.modified = True

    panel = _make_panel(profile=p)

    panel._pre_edit_modified = True
    panel._undo_stack.append(("layer_height", 0.2))
    p.data["layer_height"] = 0.3
    p.modified = True

    panel._on_undo()

    assert p.modified is True, (
        "After undoing a param edit on an already-converted profile, "
        "modified must remain True"
    )
    assert panel._pre_edit_modified is None
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


def test_format_value_humanizes_known_enum_label():
    """_format_value with a known enum key should return the human label."""
    result = ProfileDetailPanel._format_value("nearest", key="seam_position")
    assert result == "Nearest", f"Expected 'Nearest', got {result!r}"


def test_enum_label_to_json_round_trip():
    """_ENUM_LABEL_TO_JSON must map human label back to raw JSON value."""
    label_to_json = _ENUM_LABEL_TO_JSON
    assert label_to_json["wall_generator"].get("Arachne") == "arachne"
    assert label_to_json["wall_generator"].get("Classic") == "classic"
    assert label_to_json["seam_position"].get("Nearest") == "nearest"
    assert label_to_json["seam_position"].get("Aligned") == "aligned"
