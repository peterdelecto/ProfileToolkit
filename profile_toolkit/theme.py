# Lime + Purple dark palette
# Backgrounds carry a blue-gray undertone (from the original Orca-derived base)
# Accent: lime (#C6FF00) for primary actions, purple (#BA68C8) for secondary/decorative
# See ORCA_COLOR_SCHEME.md for original base rationale; colors updated for lime+purple scheme


class Theme:
    """Color tokens — plain attribute bag so callers just do theme.bg, theme.fg, etc."""

    def __init__(self) -> None:
        # ── Backgrounds (blue-gray undertone, unchanged from Orca base) ──
        self.bg = "#2D2D31"        # Window background
        self.bg2 = "#34343A"       # Panels / sidebar
        self.bg3 = "#3A3A41"       # Input fields / raised surfaces
        self.bg4 = "#3E3E45"       # Buttons default
        self.border = "#4A4A51"    # Borders / separators

        # ── Text ──
        self.fg = "#EFEFF0"        # Primary text (11.9:1 on bg)
        self.fg2 = "#E5E5E6"       # Secondary text (10.9:1 on bg)
        self.fg3 = "#B3B3B5"       # Muted / tertiary (6.6:1 on bg)
        self.fg_disabled = "#818183"  # Disabled controls (3.5:1 on bg, AA Large)

        # ── Primary accent (lime) ──
        self.accent = "#C6FF00"        # Primary lime — main action color
        self.accent_hover = "#D4FF33"  # Hover / highlight (subtle lift)
        self.accent_dark = "#9ACD32"   # Muted / subdued lime
        self.accent_fg = "#1A1A1A"     # Dark text ON lime backgrounds (12.5:1)

        # ── Secondary accent (purple) ──
        self.secondary = "#BA68C8"       # Purple — secondary/decorative accent
        self.secondary_bright = "#CE93D8" # Lighter purple for text on dark bg
        self.secondary_dark = "#8E44AD"  # Darker purple variant
        self.secondary_fg = "#1A1A1A"    # Dark text ON purple backgrounds

        # ── Status ──
        self.success = "#4DD0E1"    # Success / info (cyan, 7.3:1 on bg)
        self.converted = "#4B9FE8"  # Info / converted (blue, 4.9:1 on bg)
        self.warning = "#FFCD05"    # Warning (yellow, high visibility)
        self.error = "#EF5350"      # Error / locked (warm red, 4.5:1 on bg)

        # ── Icon-safe active backgrounds (purple-tinted) ──
        self.icon_active_bg = "#2D1F3D"         # Subtle active state (dark purple tint)
        self.icon_active_bg_strong = "#362B50"   # Strong active/selected (dark purple)
        self.icon_hover_bg = "#2F2440"           # Icon hover state

        # ── Derived / UI elements ──
        self.sel = "#362B50"            # Selected row bg (matches icon_active_bg_strong)
        self.btn_bg = "#3E3E45"         # Default button (same as bg4)
        self.btn_fg = "#EFEFF0"         # Default button text
        self.section_bg = "#303036"     # Section header bg
        self.param_bg = "#34343A"       # Parameter content area (same as bg2)
        self.edit_bg = "#3A3A41"        # Editable value fields (same as bg3)
        self.placeholder_fg = "#909096"  # Placeholder / hint text (3.6:1 AA Large)
        self.convert_all_bg = "#34343A"  # "Convert All" button
        self.warning_bg = "#3A2200"      # Warning banner background (dark amber)

        # ── Win95 Bevels (adapted to blue-gray) ──
        self.bevel_light = "#EFEFF0"   # Raised edge highlight
        self.bevel_shadow = "#4A4A51"  # Sunken edge shadow

        # ── Compare view diff backgrounds ──
        self.compare_changed_bg = "#453040"   # Plum tint for changed rows (10.2:1 vs fg)
        self.compare_missing_bg = "#502838"   # Red-plum for missing rows (10.8:1 vs fg)

        # ── Legacy aliases ──
        self.accent2 = self.secondary    # Backwards compat (was accent_hover)
        self.locked = self.error          # Backwards compat
