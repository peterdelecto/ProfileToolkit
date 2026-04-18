"""Tests for constants.py — layout integrity, recommendation consistency, enum sanity."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from profile_toolkit.constants import (
    ENUM_VALUES,
    FILAMENT_LAYOUT,
    ORCA_ONLY_TABS,
    RECOMMENDATIONS,
    SLICER_COLORS,
    SLICER_SHORT_LABELS,
    _ALL_FILAMENT_KEYS,
)


# ---------- FILAMENT_LAYOUT integrity ----------


class TestFilamentLayoutNoDuplicateKeys:
    """Every json_key must appear exactly once across the entire layout."""

    def test_no_duplicate_keys(self):
        seen = {}
        for tab, sections in FILAMENT_LAYOUT.items():
            for section, params in sections.items():
                for entry in params:
                    key = entry[0]
                    loc = f"{tab} > {section}"
                    assert key not in seen, (
                        f"Duplicate key '{key}': first in '{seen[key]}', again in '{loc}'"
                    )
                    seen[key] = loc


class TestFilamentLayoutEntryFormat:
    """Each entry is a 2- or 3-tuple: (json_key, label[, slicer_tag])."""

    def test_entry_tuples_valid(self):
        for tab, sections in FILAMENT_LAYOUT.items():
            for section, params in sections.items():
                for entry in params:
                    assert isinstance(entry, tuple), f"Non-tuple in {tab} > {section}: {entry}"
                    assert len(entry) in (2, 3), f"Bad length in {tab} > {section}: {entry}"
                    assert isinstance(entry[0], str) and entry[0], f"Empty key in {tab} > {section}"
                    assert isinstance(entry[1], str) and entry[1], f"Empty label in {tab} > {section}"

    def test_slicer_tags_valid(self):
        valid_tags = {"Prusa", "Bambu", "Orca"}
        for tab, sections in FILAMENT_LAYOUT.items():
            for section, params in sections.items():
                for entry in params:
                    if len(entry) == 3:
                        assert entry[2] in valid_tags, (
                            f"Unknown slicer tag '{entry[2]}' in {tab} > {section} > {entry[0]}"
                        )


class TestFilamentLayoutSections:
    """Tabs and sections are non-empty and ordered."""

    def test_no_empty_tabs(self):
        for tab, sections in FILAMENT_LAYOUT.items():
            assert sections, f"Tab '{tab}' has no sections"

    def test_no_empty_sections(self):
        for tab, sections in FILAMENT_LAYOUT.items():
            for section, params in sections.items():
                assert params, f"Section '{tab} > {section}' has no parameters"

    def test_all_filament_keys_matches_layout(self):
        """_ALL_FILAMENT_KEYS must match what we extract from FILAMENT_LAYOUT."""
        extracted = set()
        for sections in FILAMENT_LAYOUT.values():
            for params in sections.values():
                for entry in params:
                    extracted.add(entry[0])
        assert extracted == _ALL_FILAMENT_KEYS


class TestFilamentLayoutTabOrder:
    """Tab ordering must match BambuStudio UI exactly (immutable contract)."""

    EXPECTED_TAB_ORDER = [
        "Filament",
        "Cooling",
        "Setting Overrides",
        "Advanced",
        "Multimaterial",
        "Dependencies",
        "Notes",
    ]

    def test_tab_order(self):
        actual = list(FILAMENT_LAYOUT.keys())
        assert actual == self.EXPECTED_TAB_ORDER, (
            f"Tab order mismatch.\nExpected: {self.EXPECTED_TAB_ORDER}\nActual: {actual}"
        )


class TestOrcaOnlyTabs:
    """ORCA_ONLY_TABS must be a subset of FILAMENT_LAYOUT keys."""

    def test_subset_of_layout(self):
        assert ORCA_ONLY_TABS <= set(FILAMENT_LAYOUT.keys())


# ---------- RECOMMENDATIONS integrity ----------


class TestRecommendationsStructure:
    """Each recommendation entry has required fields."""

    def test_required_fields(self):
        for key, rec in RECOMMENDATIONS.items():
            assert "info" in rec, f"Recommendation '{key}' missing 'info'"
            assert isinstance(rec["info"], str), f"Recommendation '{key}' info not a string"

    def test_ranges_have_min_max(self):
        for key, rec in RECOMMENDATIONS.items():
            if "ranges" not in rec:
                continue
            for material, rng in rec["ranges"].items():
                assert "min" in rng, f"'{key}' range for '{material}' missing 'min'"
                assert "max" in rng, f"'{key}' range for '{material}' missing 'max'"
                assert rng["min"] <= rng["max"], (
                    f"'{key}' range for '{material}': min ({rng['min']}) > max ({rng['max']})"
                )

    def test_sources_have_label_and_url(self):
        for key, rec in RECOMMENDATIONS.items():
            for src in rec.get("sources", []):
                assert "label" in src, f"'{key}' source missing 'label'"
                assert "url" in src, f"'{key}' source missing 'url'"
                assert src["url"].startswith("http"), f"'{key}' source bad url: {src['url']}"
            # Also check per-material sources
            for material, rng in rec.get("ranges", {}).items():
                for src in rng.get("sources", []):
                    assert "label" in src, f"'{key}/{material}' source missing 'label'"
                    assert "url" in src, f"'{key}/{material}' source missing 'url'"


# ---------- ENUM_VALUES integrity ----------


class TestEnumValues:
    """Each enum mapping has at least two options and valid structure."""

    def test_entries_are_tuples(self):
        for key, options in ENUM_VALUES.items():
            assert isinstance(options, list), f"ENUM_VALUES['{key}'] not a list"
            for opt in options:
                assert isinstance(opt, tuple) and len(opt) == 2, (
                    f"ENUM_VALUES['{key}'] bad entry: {opt}"
                )
                assert isinstance(opt[0], str) and isinstance(opt[1], str), (
                    f"ENUM_VALUES['{key}'] non-string in: {opt}"
                )

    def test_no_duplicate_json_values(self):
        for key, options in ENUM_VALUES.items():
            json_vals = [opt[0] for opt in options]
            assert len(json_vals) == len(set(json_vals)), (
                f"ENUM_VALUES['{key}'] has duplicate json values"
            )


# ---------- SLICER_COLORS / SLICER_SHORT_LABELS ----------


class TestSlicerMeta:
    def test_colors_and_labels_same_keys(self):
        assert set(SLICER_COLORS.keys()) == set(SLICER_SHORT_LABELS.keys())

    def test_colors_are_hex(self):
        import re
        for slicer, color in SLICER_COLORS.items():
            assert re.match(r"^#[0-9A-Fa-f]{6}$", color), (
                f"SLICER_COLORS['{slicer}'] invalid hex: {color}"
            )
