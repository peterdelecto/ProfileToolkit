# Convert detail panel — right-side conversion workspace
#
# Replaces ProfileDetailPanel in the PanedWindow when the Convert tab
# is active.  Shows the same FILAMENT_LAYOUT section structure with
# conversion-specific rendering: mapped values, editable missing params
# with knowledge tips, and "not applicable" dropped params.

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Optional

from .constants import (
    CONVERSION_DEFAULTS,
    FILAMENT_LAYOUT,
    SLICER_COLORS,
    SLICER_SHORT_LABELS,
    _ENTRY_CHARS,
    _LABEL_COL_WIDTH,
    _VAL_COL_WIDTH,
    NAME_TRUNCATE_SHORT,
    NAME_TRUNCATE_MEDIUM,
    NAME_TRUNCATE_LONG,
    UI_FONT,
)
from .theme import Theme
from .models import Profile
from .utils import detect_material, get_recommendation, user_error
from .widgets import ScrollableFrame, make_btn as _make_btn, InfoPopup as _InfoPopup

logger = logging.getLogger(__name__)

# Slicer names in a stable order for dropdown population
_SLICER_NAMES = list(SLICER_SHORT_LABELS.keys())

# _VAL_COL_WIDTH and _ENTRY_CHARS imported from constants


class ConvertDetailPanel(tk.Frame):
    """Right-side conversion workspace.

    Renders the selected profile's parameters in FILAMENT_LAYOUT section
    order, highlighting mapped / missing / dropped params for the chosen
    target slicer.  Editable inputs for missing params, knowledge tips,
    and a Convert button to commit the result.
    """

    def __init__(self, parent: tk.Widget, theme: Theme, app: Any) -> None:
        super().__init__(parent, bg=theme.bg)
        self.theme = theme
        self.app = app

        self._profile: Optional[Profile] = None
        self._target_slicer: Optional[str] = None
        self._converted: Optional[Profile] = None
        self._dropped: list[str] = []
        self._missing: list[str] = []
        self._warnings: list[str] = []
        self._filled: dict[str, Any] = {}  # preview edits, committed on Convert
        self._collapsed: set[str] = set()
        self._row_idx = 0  # alternating row counter

        self._build_ui()

    # --- Build static UI shell ---

    def _build_ui(self) -> None:
        theme = self.theme

        # --- Header ---
        self._header = tk.Frame(self, bg=theme.bg2)
        self._header.pack(fill="x")

        # Title row: slicer origin badge + profile name
        self._title_row = tk.Frame(self._header, bg=theme.bg2)
        self._title_row.pack(fill="x", padx=16, pady=(12, 4))

        self._lbl_badge = tk.Label(
            self._title_row,
            text="",
            bg=theme.secondary,
            fg=theme.accent_fg,
            font=(UI_FONT, 10, "bold"),
            padx=8,
            pady=1,
        )
        self._lbl_badge.pack(side="left")

        self._lbl_name = tk.Label(
            self._title_row,
            text="",
            bg=theme.bg2,
            fg=theme.fg,
            font=(UI_FONT, 14, "bold"),
        )
        self._lbl_name.pack(side="left", padx=(10, 0))

        self._badge_full = ""
        self._badge_abbr = ""

        def _resize_badge(e: tk.Event) -> None:
            if not self._badge_full:
                return
            row_w = e.width
            needed = (
                self._lbl_name.winfo_reqwidth() + self._lbl_badge.winfo_reqwidth() + 50
            )
            self._lbl_badge.configure(
                text=self._badge_abbr if row_w < needed else self._badge_full
            )

        self._title_row.bind("<Configure>", _resize_badge)

        # Controls row: From → To + Convert + Export
        ctrl_row = tk.Frame(self._header, bg=theme.bg2)
        ctrl_row.pack(fill="x", padx=16, pady=(2, 4))

        tk.Label(
            ctrl_row, text="From", bg=theme.bg2, fg=theme.fg3, font=(UI_FONT, 12)
        ).pack(side="left")
        self._from_var = tk.StringVar()
        self._from_combo = ttk.Combobox(
            ctrl_row,
            textvariable=self._from_var,
            state="readonly",
            width=14,
            font=(UI_FONT, 13),
            style="Param.TCombobox",
        )
        self._from_combo["values"] = _SLICER_NAMES
        self._from_combo.pack(side="left", padx=(6, 0))

        tk.Label(
            ctrl_row,
            text="\u2192",
            bg=theme.bg2,
            fg=theme.accent,
            font=(UI_FONT, 18, "bold"),
        ).pack(side="left", padx=10)

        tk.Label(
            ctrl_row, text="To", bg=theme.bg2, fg=theme.fg3, font=(UI_FONT, 12)
        ).pack(side="left")
        self._to_var = tk.StringVar()
        self._to_combo = ttk.Combobox(
            ctrl_row,
            textvariable=self._to_var,
            state="readonly",
            width=14,
            font=(UI_FONT, 13),
            style="Param.TCombobox",
        )
        self._to_combo["values"] = _SLICER_NAMES
        self._to_combo.pack(side="left", padx=(6, 0))
        self._to_combo.bind("<<ComboboxSelected>>", self._on_target_changed)

        spacer = tk.Frame(ctrl_row, bg=theme.bg2)
        spacer.pack(side="left", fill="x", expand=True)

        self._btn_convert = _make_btn(
            ctrl_row,
            "Convert Selected",
            self._do_convert,
            bg=theme.accent,
            fg=theme.accent_fg,
            font=(UI_FONT, 13, "bold"),
            padx=18,
            pady=5,
        )
        self._btn_convert.pack(side="right", padx=(6, 0))

        self._btn_export = _make_btn(
            ctrl_row,
            "Export",
            self._do_export,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 12),
            padx=14,
            pady=5,
        )
        self._btn_export.pack(side="right")

        # Separator
        tk.Frame(self._header, bg=theme.border, height=1).pack(fill="x")

        # --- Scrollable body ---
        self._scroll = ScrollableFrame(self, bg=theme.bg)
        self._scroll.pack(fill="both", expand=True)

        self._show_idle()

        # Keyboard shortcut — Ctrl/Cmd+Return to convert
        from .constants import _PLATFORM

        _mod = "Command" if _PLATFORM == "Darwin" else "Control"
        self.bind_all(
            f"<{_mod}-Return>",
            lambda e: (
                self._do_convert()
                if getattr(self.app, "_current_tab", "") == "convert"
                else None
            ),
        )

    # --- Public API ---

    def show_profile(self, profile: Profile) -> None:
        """Called by ProfileListPanel._on_select when in convert mode."""
        self._profile = profile
        self._filled.clear()

        # Update convert button with profile name
        name = profile.name or "Profile"
        short_name = (
            name[:NAME_TRUNCATE_SHORT] + "…"
            if len(name) > NAME_TRUNCATE_SHORT
            else name
        )
        self._btn_convert.configure(text=f"Convert \u201c{short_name}\u201d")

        # Update header
        self._lbl_name.configure(text=profile.name or "(unnamed)")
        origin = profile.origin or ""
        short = SLICER_SHORT_LABELS.get(origin, origin)
        if short:
            letter = short[0] if short else ""
            self._badge_full = f" {short} "
            self._badge_abbr = f" {letter} "
            color = SLICER_COLORS.get(origin, self.theme.secondary)
            self._lbl_badge.configure(text=self._badge_full, bg=color)
            self._lbl_badge.pack(side="left", padx=(8, 0))
        else:
            self._badge_full = ""
            self._badge_abbr = ""
            self._lbl_badge.pack_forget()

        # Auto-populate From and filter To combo (#9: exclude same slicer)
        if origin in _SLICER_NAMES:
            self._from_combo.current(_SLICER_NAMES.index(origin))
            targets = [s for s in _SLICER_NAMES if s != origin]
            self._to_combo["values"] = targets
        else:
            self._from_var.set("")
            self._to_combo["values"] = _SLICER_NAMES

        # Refresh preview if target already selected
        if self._target_slicer:
            self._preview_conversion()
        else:
            self._show_idle()

    def clear(self) -> None:
        """Reset to idle state."""
        self._profile = None
        self._target_slicer = None
        self._converted = None
        self._filled.clear()
        self._lbl_name.configure(text="")
        self._btn_convert.configure(text="Convert Selected")
        self._lbl_badge.pack_forget()
        self._from_var.set("")
        self._to_var.set("")
        self._show_idle()

    # --- Target change ---

    def _on_target_changed(self, event: Optional[tk.Event] = None) -> None:
        target = self._to_var.get()
        if target and target != self._target_slicer:
            # Warn before discarding filled values
            if self._filled:
                if not messagebox.askyesno(
                    "Unsaved Changes",
                    f"Discard {len(self._filled)} filled {'value' if len(self._filled) == 1 else 'values'}?",
                    parent=self,
                ):
                    # Restore combo to previous selection
                    if self._target_slicer:
                        self._to_var.set(self._target_slicer)
                    return
            self._target_slicer = target
            self._filled.clear()
            self._preview_conversion()

    # --- Conversion preview ---

    def _preview_conversion(self) -> None:
        if not self._profile or not self._target_slicer:
            self._show_idle()
            return
        # Handle conversion errors gracefully
        try:
            self._converted, dropped, missing, warnings = self._profile.convert_to(
                self._target_slicer
            )
        except Exception as exc:
            logger.exception("convert_to() failed: %s", exc)
            body = self._scroll.body
            for child in body.winfo_children():
                child.destroy()
            theme = self.theme
            tk.Label(
                body,
                text=user_error(
                    "Could not convert this profile.",
                    exc,
                    "The source may be missing required data.",
                ),
                bg=theme.bg,
                fg=theme.error,
                font=(UI_FONT, 14),
                wraplength=500,
            ).pack(pady=40, padx=20)
            return
        self._dropped = list(dropped)
        self._missing = list(missing)
        self._missing_set: set[str] = set(missing)
        self._warnings = list(warnings)
        # Re-apply any filled values that still exist in the target schema
        for k, v in list(self._filled.items()):
            if k in self._converted.data or k in self._missing_set:
                self._converted.data[k] = v
                if k in self._missing_set:
                    self._missing_set.discard(k)
                    self._missing = [m for m in self._missing if m != k]
            else:
                # Stale key from different conversion path — drop it
                del self._filled[k]
        self._rebuild()

    # --- Idle state ---

    def _show_idle(self) -> None:
        body = self._scroll.body
        for child in body.winfo_children():
            child.destroy()
        theme = self.theme
        msg = (
            "Select a profile and choose a target slicer above"
            if not self._profile
            else "Choose a target slicer above"
        )
        tk.Label(body, text=msg, bg=theme.bg, fg=theme.fg3, font=(UI_FONT, 14)).pack(
            pady=60
        )

    # --- Full rebuild ---

    def _rebuild(self, reset_scroll: bool = True) -> None:
        body = self._scroll.body
        for child in body.winfo_children():
            child.destroy()

        # Guard against None profile
        if not self._converted or not self._profile:
            self._show_idle()
            return

        theme = self.theme
        converted_data = self._converted.data
        dropped_set = set(self._dropped)
        missing_set = set(self._missing)
        material = detect_material(self._profile.data)

        # #3/#5/#16: Show conversion warnings as a banner
        if self._warnings:
            warn_outer = tk.Frame(body, bg=theme.compare_changed_bg)
            warn_outer.pack(fill="x", pady=(0, 6))
            tk.Frame(warn_outer, bg=theme.warning, width=4).place(
                x=0, y=0, relheight=1.0
            )
            # Cap warning banner height to avoid overflow with many warnings
            warn_frame = warn_outer
            if len(self._warnings) > 5:
                warn_frame = tk.Frame(warn_outer, bg=theme.compare_changed_bg)
                warn_frame.pack(fill="x")
                warn_outer.configure(height=150)
                warn_outer.pack_propagate(False)
            for w_msg in self._warnings:
                tk.Label(
                    warn_frame,
                    text=f"\u26a0  {w_msg}",
                    bg=theme.compare_changed_bg,
                    fg=theme.fg,
                    font=(UI_FONT, 13),
                    anchor="w",
                    wraplength=600,
                    justify="left",
                    padx=12,
                    pady=4,
                ).pack(anchor="w")

        self._row_idx = 0
        mapped_count = 0
        attention_count = 0
        dropped_count = 0

        # Walk FILAMENT_LAYOUT in section order
        layout = FILAMENT_LAYOUT
        for tab_name, sections in layout.items():
            for section_name, params in sections.items():
                # Determine which params are relevant for this conversion
                rows_info: list[tuple[str, str, str]] = []
                #  (key, label, kind)  where kind = "mapped" | "missing" | "dropped"
                section_attention = 0
                for entry in params:
                    key = entry[0]
                    label = entry[1]
                    if key in converted_data and key not in missing_set:
                        rows_info.append((key, label, "mapped"))
                        mapped_count += 1
                    elif key in missing_set:
                        rows_info.append((key, label, "missing"))
                        attention_count += 1
                        section_attention += 1
                    elif key in dropped_set:
                        rows_info.append((key, label, "dropped"))
                        dropped_count += 1
                    # else: param not in source or target — skip

                if not rows_info:
                    continue

                # Section header
                is_collapsed = section_name in self._collapsed
                self._render_section_header(
                    section_name, is_collapsed, section_attention
                )

                if is_collapsed:
                    continue

                # Render rows
                for key, label, kind in rows_info:
                    if kind == "mapped":
                        self._render_mapped_row(key, label, converted_data[key])
                    elif kind == "missing":
                        self._render_missing_row(key, label, material)
                    elif kind == "dropped":
                        self._render_dropped_row(key, label)

        if reset_scroll:
            self._scroll.canvas.yview_moveto(0)
        self._scroll.bind_scroll_recursive()

    # --- Section header ---

    def _render_section_header(
        self, name: str, collapsed: bool, attention: int
    ) -> None:
        theme = self.theme
        body = self._scroll.body

        hdr = tk.Frame(body, bg=theme.section_bg, cursor="pointinghand")
        hdr.pack(fill="x", pady=(10, 3))

        chevron = tk.Label(
            hdr,
            text="\u25b6" if collapsed else "\u25bc",
            bg=theme.section_bg,
            fg=theme.fg3,
            font=(UI_FONT, 10),
            padx=6,
        )
        chevron.pack(side="left")

        tk.Label(
            hdr,
            text=name,
            bg=theme.section_bg,
            fg=theme.fg2,
            font=(UI_FONT, 14, "bold"),
            pady=4,
        ).pack(side="left")

        # Attention badge
        if attention > 0:
            tk.Label(
                hdr,
                text=str(attention),
                bg=theme.bg3,
                fg=theme.warning,
                font=(UI_FONT, 10, "bold"),
                padx=6,
                pady=1,
            ).pack(side="left", padx=(8, 0))

        # Click to collapse/expand
        def _toggle(e: Optional[tk.Event] = None) -> None:
            if name in self._collapsed:
                self._collapsed.discard(name)
            else:
                self._collapsed.add(name)
            self._rebuild()

        for w in (hdr, chevron):
            w.bind("<Button-1>", _toggle)

    # --- Mapped row (editable on click) ---

    def _render_mapped_row(self, key: str, label: str, value: Any) -> None:
        theme = self.theme
        body = self._scroll.body
        edited = key in self._filled
        bg = theme.param_bg if self._row_idx % 2 == 0 else theme.bg
        self._row_idx += 1

        row = tk.Frame(body, bg=bg)
        row.pack(fill="x")
        row.columnconfigure(0, weight=1, minsize=_LABEL_COL_WIDTH)
        row.columnconfigure(1, minsize=_VAL_COL_WIDTH, weight=0)
        row.columnconfigure(2, minsize=24, weight=0)

        tk.Label(
            row,
            text=label,
            bg=bg,
            fg=theme.fg3,
            font=(UI_FONT, 14),
            anchor="w",
            pady=4,
        ).grid(row=0, column=0, sticky="ew", padx=(16, 12))

        display = self._filled[key] if edited else value
        val_str = self._format_value(display)
        val_frame = tk.Frame(row, bg=bg, width=_VAL_COL_WIDTH)
        val_frame.grid(row=0, column=1, sticky="w", padx=(0, 4), pady=4)
        val_frame.grid_propagate(False)
        val_frame.configure(height=28)

        val_lbl = tk.Label(
            val_frame,
            text=val_str,
            bg=bg,
            fg=theme.success if edited else theme.fg2,
            font=(UI_FONT, 14),
            anchor="w",
            cursor="pointinghand",
        )
        val_lbl.pack(side="left", fill="x", expand=True)

        def _start_edit(_e: tk.Event) -> None:
            val_lbl.pack_forget()
            entry = tk.Entry(
                val_frame,
                bg=theme.bg3,
                fg=theme.fg,
                font=(UI_FONT, 13),
                insertbackground=theme.fg,
                highlightbackground=theme.border,
                highlightcolor=theme.accent,
                highlightthickness=1,
                relief="flat",
                width=_ENTRY_CHARS,
            )
            entry.pack(side="left", fill="x", expand=True)
            entry.insert(0, str(display))
            entry.select_range(0, "end")
            entry.focus_set()
            entry.bind(
                "<Return>", lambda e, k=key, ent=entry: self._commit_entry(k, ent)
            )
            entry.bind(
                "<FocusOut>", lambda e, k=key, ent=entry: self._commit_entry(k, ent)
            )
            entry.bind("<Escape>", lambda e: self._cancel_and_rebuild())

        val_lbl.bind("<Button-1>", _start_edit)

        # Info popup icon (same as filament detail pane)
        self._render_info_icon(row, key, bg)

    # --- Missing row (editable, plum highlight) ---

    def _render_missing_row(self, key: str, label: str, material: str) -> None:
        theme = self.theme
        body = self._scroll.body
        already_filled = key in self._filled
        # Filled → normal alternating bg; unfilled → plum highlight
        bg = (
            (theme.param_bg if self._row_idx % 2 == 0 else theme.bg)
            if already_filled
            else theme.compare_changed_bg
        )
        self._row_idx += 1

        row = tk.Frame(body, bg=bg)
        row.pack(fill="x")
        row.columnconfigure(0, weight=1, minsize=_LABEL_COL_WIDTH)
        row.columnconfigure(1, minsize=_VAL_COL_WIDTH, weight=0)
        row.columnconfigure(2, minsize=24, weight=0)

        # Left border indicator for unfilled missing params
        if not already_filled:
            tk.Frame(row, bg=theme.warning, width=4).place(x=0, y=0, relheight=1.0)

        # Label with ⚠ icon (only when unfilled)
        lbl_frame = tk.Frame(row, bg=bg)
        lbl_frame.grid(row=0, column=0, sticky="ew", padx=(16, 12), pady=4)
        if not already_filled:
            tk.Label(
                lbl_frame,
                text="\u26a0",
                bg=bg,
                fg=theme.warning,
                font=(UI_FONT, 12, "bold"),
            ).pack(side="left", padx=(0, 6))
        tk.Label(
            lbl_frame,
            text=label,
            bg=bg,
            fg=theme.fg if already_filled else theme.fg2,
            font=(UI_FONT, 14),
            anchor="w",
        ).pack(side="left")

        # Value area
        val_frame = tk.Frame(row, bg=bg, width=_VAL_COL_WIDTH)
        val_frame.grid(row=0, column=1, sticky="w", padx=(0, 4), pady=4)
        val_frame.grid_propagate(False)
        val_frame.configure(height=28)

        if already_filled:
            # Show filled value (click to re-edit)
            val_lbl = tk.Label(
                val_frame,
                text=str(self._filled[key]),
                bg=bg,
                fg=theme.success,
                font=(UI_FONT, 14),
                cursor="pointinghand",
            )
            val_lbl.pack(side="left", fill="x", expand=True)

            def _re_edit(_e: tk.Event, k: str = key) -> None:
                # Remove from filled so it re-appears as editable
                self._filled.pop(k, None)
                self._rebuild()

            val_lbl.bind("<Button-1>", _re_edit)
        else:
            entry = tk.Entry(
                val_frame,
                bg=theme.bg3,
                fg=theme.fg,
                font=(UI_FONT, 13),
                insertbackground=theme.fg,
                highlightbackground=theme.warning,
                highlightcolor=theme.warning,
                highlightthickness=1,
                relief="flat",
                width=_ENTRY_CHARS,
            )
            entry.pack(side="left", fill="x", expand=True)

            # Pre-fill: RECOMMENDATIONS typical first, then CONVERSION_DEFAULTS
            rec = get_recommendation(key, material)
            conv_default = CONVERSION_DEFAULTS.get(key)
            prefill = None
            if rec and "typical" in rec:
                prefill = str(rec["typical"])
            elif conv_default and len(conv_default) > 0:
                prefill = str(conv_default[0])

            if prefill:
                entry.insert(0, prefill)
                entry.configure(fg=theme.fg3)
                # "(suggested)" hint next to pre-filled values
                tk.Label(
                    val_frame,
                    text="(recommended default)",
                    bg=bg,
                    fg=theme.fg3,
                    font=(UI_FONT, 11),
                ).pack(side="left", padx=(4, 0))
                entry.bind("<FocusIn>", lambda e, ent=entry: ent.configure(fg=theme.fg))

            entry.bind(
                "<Return>", lambda e, k=key, ent=entry: self._commit_entry(k, ent)
            )
            entry.bind(
                "<FocusOut>", lambda e, k=key, ent=entry: self._commit_entry(k, ent)
            )

        # Info popup icon (same as filament detail pane)
        self._render_info_icon(row, key, bg, material)

    # --- Dropped row ---

    def _render_dropped_row(self, key: str, label: str) -> None:
        theme = self.theme
        body = self._scroll.body
        bg = theme.param_bg if self._row_idx % 2 == 0 else theme.bg
        self._row_idx += 1

        row = tk.Frame(body, bg=bg)
        row.pack(fill="x")
        row.columnconfigure(0, weight=1, minsize=_LABEL_COL_WIDTH)
        row.columnconfigure(1, minsize=_VAL_COL_WIDTH, weight=0)
        row.columnconfigure(2, minsize=24, weight=0)

        tk.Label(
            row,
            text=label,
            bg=bg,
            fg=theme.fg3,
            font=(UI_FONT, 14, "italic"),
            anchor="w",
            pady=4,
        ).grid(row=0, column=0, sticky="ew", padx=(16, 12))

        tk.Label(
            row,
            text=(
                f"No equivalent in {self._target_slicer}"
                if self._target_slicer
                else "not applicable"
            ),
            bg=bg,
            fg=theme.fg3,
            font=(UI_FONT, 13, "italic"),
            anchor="w",
            pady=4,
        ).grid(row=0, column=1, sticky="w", padx=(0, 16))

    # --- Knowledge tip ---

    def _render_info_icon(
        self, row: tk.Frame, key: str, bg: str, material: str = "General"
    ) -> None:
        """Add ⓘ info popup icon in column 2, matching the filament detail pane."""
        theme = self.theme
        has_rec = get_recommendation(key, material) is not None
        if not has_rec:
            return
        info_frame = tk.Frame(row, bg=bg, width=24)
        info_frame.grid(row=0, column=2, sticky="e", padx=(0, 8))
        icon = tk.Label(
            info_frame,
            text="\u24d8",
            bg=bg,
            fg=theme.fg3,
            font=(UI_FONT, 12),
            cursor="pointinghand",
        )
        icon.pack()
        icon.bind("<Enter>", lambda e, w=icon: w.configure(fg=theme.accent))
        icon.bind("<Leave>", lambda e, w=icon: w.configure(fg=theme.fg3))
        _InfoPopup(icon, key, material, theme=theme)

    # --- Cancel edit ---

    def _cancel_and_rebuild(self) -> None:
        self._edit_cancelled = True
        self._rebuild()

    # --- Entry commit ---

    def _commit_entry(self, key: str, entry: tk.Entry) -> None:
        """Store the entered value in the preview dict and rebuild."""
        if getattr(self, "_edit_cancelled", False):
            self._edit_cancelled = False
            return
        val = entry.get().strip()
        if not val:
            # Cleared — remove from filled
            self._filled.pop(key, None)
            self._rebuild(reset_scroll=False)
            return

        # Skip phantom edits — don't store if value unchanged
        original = self._converted.data.get(key) if self._converted else None
        parsed_val: Any
        try:
            numeric = float(val)
            if "." not in val and numeric == int(numeric):
                parsed_val = int(numeric)
            else:
                parsed_val = numeric
        except ValueError:
            parsed_val = val

        # Basic temperature range validation — block obviously wrong values
        key_lower = key.lower()
        if isinstance(parsed_val, (int, float)):
            if "temp" in key_lower and not (-50 <= parsed_val <= 500):
                messagebox.showwarning(
                    "Value Out of Range",
                    f"Temperature {parsed_val}°C seems unusual (expected -50 to 500).",
                    parent=self,
                )
                self._rebuild(reset_scroll=False)
                return
            elif (
                "speed" in key_lower
                and "fan" in key_lower
                and not (0 <= parsed_val <= 100)
            ):
                messagebox.showwarning(
                    "Value Out of Range",
                    f"Fan speed {parsed_val}% seems unusual (expected 0–100).",
                    parent=self,
                )
                self._rebuild(reset_scroll=False)
                return

        if original is not None and parsed_val == original:
            # Value unchanged — don't mark as edited
            self._rebuild(reset_scroll=False)
            return

        self._filled[key] = parsed_val
        # Always rebuild to swap entry back to label and refresh badges
        self._rebuild(reset_scroll=False)

    # --- Convert action ---

    def _do_convert(self) -> None:
        if not self._profile or not self._target_slicer:
            messagebox.showwarning(
                "Missing Selection",
                "Select a profile and target slicer first.",
                parent=self,
            )
            return

        new_profile, _, _, _ = self._profile.convert_to(self._target_slicer)

        # Apply filled values
        for k, v in self._filled.items():
            new_profile.data[k] = v
            new_profile._missing_conversion_keys.discard(k)

        # Name already has old suffix stripped by convert_to; append new one
        short = SLICER_SHORT_LABELS.get(self._target_slicer, self._target_slicer)
        new_profile.data["name"] = f"{new_profile.name or 'Profile'} ({short})"

        # Add to profile list
        panel = self.app.filament_panel
        panel.profiles.append(new_profile)
        panel._refresh_list()

        # Select the new profile and switch to detail mode
        new_idx = len(panel.profiles) - 1
        iid = str(new_idx)
        if panel.tree.exists(iid):
            panel.tree.selection_set(iid)
            panel.tree.see(iid)

        self.app._switch_tab("filament")
        self.app._update_status(f"Converted to {short}: {new_profile.name}")

    def _do_export(self) -> None:
        """Export the converted profile directly."""
        if not self._converted:
            messagebox.showinfo(
                "Nothing to Export",
                "Convert a profile first, then export the result.",
                parent=self,
            )
            return
        # Export the converted profile, not the list selection
        if hasattr(self.app, "_export_profiles"):
            self.app._export_profiles([self._converted])
        elif hasattr(self.app, "_on_export"):
            self.app._on_export()

    # --- Helpers ---

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, list):
            unique = list(dict.fromkeys(str(x) for x in value))
            if len(unique) == 1:
                return unique[0]
            return ", ".join(unique)
        if isinstance(value, bool):
            return "Yes" if value else "No"
        s = str(value)
        # Truncate long gcode / multi-line values
        if "\n" in s:
            first = s.split("\n", 1)[0]
            return (
                first[:NAME_TRUNCATE_MEDIUM] + "..."
                if len(first) > NAME_TRUNCATE_MEDIUM
                else first + "..."
            )
        if len(s) > NAME_TRUNCATE_LONG:
            return s[: NAME_TRUNCATE_LONG - 3] + "..."
        return s
