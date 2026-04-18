"""Tests for theme.py — WCAG AA contrast validation and token consistency."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from profile_toolkit.theme import Theme


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _relative_luminance(r: int, g: int, b: int) -> float:
    """WCAG 2.1 relative luminance."""
    def linearize(c):
        s = c / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def _contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = _relative_luminance(*_hex_to_rgb(hex1))
    l2 = _relative_luminance(*_hex_to_rgb(hex2))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# WCAG AA minimum for normal text
AA_MIN = 4.5


class TestTextOnBackgrounds:
    """Primary and secondary text must meet WCAG AA 4.5:1 on all backgrounds."""

    def setup_method(self):
        self.t = Theme()

    def test_fg_on_bg(self):
        ratio = _contrast_ratio(self.t.fg, self.t.bg)
        assert ratio >= AA_MIN, f"fg on bg: {ratio:.1f}:1 (need {AA_MIN})"

    def test_fg_on_bg2(self):
        ratio = _contrast_ratio(self.t.fg, self.t.bg2)
        assert ratio >= AA_MIN, f"fg on bg2: {ratio:.1f}:1"

    def test_fg_on_bg3(self):
        ratio = _contrast_ratio(self.t.fg, self.t.bg3)
        assert ratio >= AA_MIN, f"fg on bg3: {ratio:.1f}:1"

    def test_fg2_on_bg(self):
        ratio = _contrast_ratio(self.t.fg2, self.t.bg)
        assert ratio >= AA_MIN, f"fg2 on bg: {ratio:.1f}:1"

    def test_fg3_on_bg(self):
        ratio = _contrast_ratio(self.t.fg3, self.t.bg)
        assert ratio >= AA_MIN, f"fg3 on bg: {ratio:.1f}:1"

    def test_fg_disabled_on_bg(self):
        ratio = _contrast_ratio(self.t.fg_disabled, self.t.bg)
        assert ratio >= AA_MIN, f"fg_disabled on bg: {ratio:.1f}:1"

    def test_placeholder_on_bg3(self):
        ratio = _contrast_ratio(self.t.placeholder_fg, self.t.bg3)
        assert ratio >= AA_MIN, f"placeholder_fg on bg3 (edit fields): {ratio:.1f}:1"


class TestAccentContrast:
    """Accent text on accent backgrounds must meet AA."""

    def setup_method(self):
        self.t = Theme()

    def test_accent_fg_on_accent(self):
        ratio = _contrast_ratio(self.t.accent_fg, self.t.accent)
        assert ratio >= AA_MIN, f"accent_fg on accent: {ratio:.1f}:1"

    def test_secondary_fg_on_secondary(self):
        ratio = _contrast_ratio(self.t.secondary_fg, self.t.secondary)
        assert ratio >= AA_MIN, f"secondary_fg on secondary: {ratio:.1f}:1"

    def test_badge_fg_on_badge_colors(self):
        # Badges use bold text — AA Large (3:1) minimum
        AA_LARGE = 3.0
        t = self.t
        for name, bg in [
            ("prusa", t.badge_prusa),
            ("bambu", t.badge_bambu),
            ("orca", t.badge_orca),
        ]:
            ratio = _contrast_ratio(t.badge_fg, bg)
            assert ratio >= AA_LARGE, f"badge_fg on badge_{name}: {ratio:.1f}:1"


class TestStatusContrast:
    """Status colors must be readable on the main background."""

    def setup_method(self):
        self.t = Theme()

    def test_success_on_bg(self):
        ratio = _contrast_ratio(self.t.success, self.t.bg)
        assert ratio >= AA_MIN, f"success on bg: {ratio:.1f}:1"

    def test_warning_on_bg(self):
        ratio = _contrast_ratio(self.t.warning, self.t.bg)
        assert ratio >= AA_MIN, f"warning on bg: {ratio:.1f}:1"

    def test_error_on_bg(self):
        ratio = _contrast_ratio(self.t.error, self.t.bg)
        assert ratio >= AA_MIN, f"error on bg: {ratio:.1f}:1"

    def test_converted_on_bg(self):
        ratio = _contrast_ratio(self.t.converted, self.t.bg)
        assert ratio >= AA_MIN, f"converted on bg: {ratio:.1f}:1"


class TestSelectedRowContrast:
    """Text on selected/active surfaces must remain readable."""

    def setup_method(self):
        self.t = Theme()

    def test_fg_on_sel(self):
        ratio = _contrast_ratio(self.t.fg, self.t.sel)
        assert ratio >= AA_MIN, f"fg on sel: {ratio:.1f}:1"

    def test_fg_on_icon_active(self):
        ratio = _contrast_ratio(self.t.fg, self.t.icon_active_bg)
        assert ratio >= AA_MIN, f"fg on icon_active_bg: {ratio:.1f}:1"


class TestCompareViewContrast:
    """Diff highlight backgrounds must be readable with primary text."""

    def setup_method(self):
        self.t = Theme()

    def test_fg_on_compare_changed(self):
        ratio = _contrast_ratio(self.t.fg, self.t.compare_changed_bg)
        assert ratio >= AA_MIN, f"fg on compare_changed_bg: {ratio:.1f}:1"

    def test_fg_on_compare_missing(self):
        ratio = _contrast_ratio(self.t.fg, self.t.compare_missing_bg)
        assert ratio >= AA_MIN, f"fg on compare_missing_bg: {ratio:.1f}:1"


class TestAllColorsAreValidHex:
    """Every color token must be a valid 6-digit hex color."""

    def test_all_hex(self):
        import re
        t = Theme()
        for attr in dir(t):
            if attr.startswith("_"):
                continue
            val = getattr(t, attr)
            if isinstance(val, str) and val.startswith("#"):
                assert re.match(r"^#[0-9A-Fa-f]{6}$", val), (
                    f"theme.{attr} invalid hex: {val}"
                )
