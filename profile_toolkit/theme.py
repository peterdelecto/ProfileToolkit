# Theme color tokens


class Theme:
    """Color tokens for the lime + purple dark palette.

    Backgrounds carry a blue-gray undertone. Primary accent is lime (#C6FF00)
    for actions, purple (#BA68C8) for secondary/decorative. Plain attribute bag
    so callers just do theme.bg, theme.fg, etc.
    """

    def __init__(self) -> None:
        # Backgrounds
        self.bg = "#2D2D31"  # Window background
        self.bg2 = "#34343A"  # Panels / sidebar
        self.bg3 = "#3A3A41"  # Input fields / raised surfaces
        self.bg4 = "#3E3E45"  # Buttons default
        self.border = "#4A4A51"  # Borders / separators

        # Text
        self.fg = "#EFEFF0"  # Primary text (11.9:1 on bg)
        self.fg2 = "#E5E5E6"  # Secondary text (10.9:1 on bg)
        self.fg3 = "#B3B3B5"  # Muted / tertiary (6.6:1 on bg)
        self.fg_disabled = "#9A9A9C"  # Disabled controls (4.5:1 AA on bg)

        # Primary accent (lime)
        self.accent = "#C6FF00"  # Primary lime — main action color
        self.accent_hover = "#D4FF33"  # Hover / highlight (subtle lift)
        self.accent_dark = "#9ACD32"  # Muted / subdued lime
        self.accent_fg = "#1A1A1A"  # Dark text ON lime backgrounds (12.5:1)

        # Secondary accent (purple)
        self.secondary = "#BA68C8"  # Purple — secondary/decorative accent
        self.secondary_bright = "#CE93D8"  # Lighter purple for text on dark bg
        self.secondary_dark = "#8E44AD"  # Darker purple variant
        self.secondary_fg = "#1A1A1A"  # Dark text ON purple backgrounds

        # Status
        self.success = "#4DD0E1"  # Success / info (cyan, 7.3:1 on bg)
        self.converted = "#4B9FE8"  # Info / converted (blue, 4.9:1 on bg)
        self.warning = "#FFCD05"  # Warning (yellow, high visibility)
        self.error = "#FF7070"  # Error / printer-specific (warm red, 4.8:1 on bg)

        # Interactive surfaces (desaturated #BA68C8 mixed toward bg)
        self.icon_hover_bg = "#62436A"  # Hover (1.65:1 vs bg, 7.2:1 fg)
        self.icon_active_bg = "#81508B"  # Active (2.26:1 vs bg, 5.3:1 fg)
        self.icon_active_bg_strong = (
            "#8B4F96"  # Strong/selected (2.5:1 vs bg, 4.8:1 fg)
        )

        # Derived / UI elements
        self.sel = "#8B4F96"  # Selected row bg (WCAG AA 4.8:1 vs fg #EFEFF0)
        self.btn_bg = "#3E3E45"  # Default button (same as bg4)
        self.btn_fg = "#EFEFF0"  # Default button text
        self.section_bg = "#303036"  # Section header bg
        self.param_bg = "#34343A"  # Parameter content area (same as bg2)
        self.edit_bg = "#3A3A41"  # Editable value fields (same as bg3)
        self.placeholder_fg = "#A0A0A6"  # Placeholder / hint text (4.5:1 AA on bg)
        self.convert_all_bg = "#34343A"  # "Convert All" button
        self.warning_bg = "#3A2200"  # Warning banner background (dark amber)

        # Slicer badge colors (canonical source — use these instead of hardcoding)
        self.badge_prusa = "#FF7B15"  # PrusaSlicer orange
        self.badge_bambu = "#028A0F"  # BambuStudio green
        self.badge_orca = "#2196F3"  # OrcaSlicer blue
        self.badge_fg = "#FFFFFF"  # Badge text (white on colored bg)

        # --- Win95 Bevels (adapted to blue-gray) ---
        self.bevel_light = "#EFEFF0"  # Raised edge highlight
        self.bevel_shadow = "#4A4A51"  # Sunken edge shadow

        # --- Compare view diff backgrounds ---
        self.compare_changed_bg = "#453040"  # Plum tint for changed rows (10.2:1 vs fg)
        self.compare_missing_bg = "#502838"  # Red-plum for missing rows (10.8:1 vs fg)

        # --- Semantic color roles ---
        # Action:  accent (lime)    = interactive / clickable / editable
        # State:   inherited        = value comes from parent profile
        #          modified         = user has changed this value
        #          info             = informational (below range, Profile B)
        #          warning (yellow) = needs review (above range, diffs exist)
        #          error (red)      = blocked / missing / validation failure
        # Identity: secondary (purple) = branding, selected, decorative
        self.inherited = self.secondary_bright  # #CE93D8 — purple-bright
        self.modified = self.converted  # #4B9FE8 — blue
        self.info = self.success  # #4DD0E1 — cyan

        # --- Popup-specific semantic colors ---
        self.recommended = "#4DB6AC"  # Teal — "Recommended for" labels (5.5:1 on bg3)
        self.note = "#FF8C42"  # Orange — advisory notes in popups (4.5:1 AA on bg4)

        # --- Legacy aliases (TODO: remove in v2) ---
        self.accent2 = self.secondary  # Backwards compat (was accent_hover)
        self.locked = self.error  # Backwards compat
