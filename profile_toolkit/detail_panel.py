# Profile detail viewer/editor panel (extracted from panels.py)

from __future__ import annotations

import logging
import math
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Any, Callable, Optional

from .constants import (
    FILAMENT_LAYOUT,
    ORCA_ONLY_TABS,
    _IDENTITY_KEYS,
    _VALUE_TRUNCATE_LONG,
    _LABEL_COL_WIDTH,
    _VAL_COL_WIDTH,
    _ENTRY_CHARS,
    ENUM_VALUES,
    RECOMMENDATIONS,
    SLICER_COLORS,
    SLICER_SHORT_LABELS,
    _ENUM_LABEL_TO_JSON,
    UI_FONT,
    MONO_FONT,
    MONO_FONT_SIZE,
)
from .theme import Theme
from .models import Profile
from .utils import (
    bind_scroll,
    detect_material,
    get_recommendation,
    check_value_range,
    get_enum_human_label,
)
from .widgets import (
    Tooltip as _Tooltip,
    InfoPopup as _InfoPopup,
    ScrollableFrame,
    make_btn as _make_btn,
)

logger = logging.getLogger(__name__)


def _get_profile_list_panel_class():
    """Lazy import to avoid circular dependency with list_panel."""
    from .list_panel import ProfileListPanel

    return ProfileListPanel


def _find_ancestor(widget: tk.Widget, ancestor_type: type) -> Optional[Any]:
    """Walk up the widget tree to find the nearest ancestor of the given type.

    Fixes audit #37: Extract utility to replace repeated parent-tree-walk pattern.

    Args:
        widget: Starting widget to search from.
        ancestor_type: Class type to search for.

    Returns:
        The first ancestor of the given type, or None if not found.
    """
    parent = getattr(widget, "master", None)
    while parent:
        if isinstance(parent, ancestor_type):
            return parent
        parent = getattr(parent, "master", None)
    return None


class ProfileDetailPanel(tk.Frame):
    """Renders a profile's settings using BambuStudio's exact tab/section layout.

    This panel displays and edits profile parameters organized by tabs and sections.
    It supports inheritance resolution, smart recommendations, undo/redo, and inline
    parameter editing with type-aware validation.
    """

    def __init__(
        self, parent: tk.Widget, theme: Theme, icons: Any = None, icons_sm: Any = None
    ) -> None:
        """Initialize the detail panel.

        Args:
            parent: Parent widget.
            theme: Theme object with color scheme.
            icons: 24px IconSet, or None.
            icons_sm: 16px IconSet, or None.
        """
        super().__init__(parent, bg=theme.bg2)
        self.theme = theme
        self.icons = icons
        self.icons_sm = icons_sm
        self.current_profile = None
        self._tab_buttons = []
        self._current_tab = None
        self._edit_vars = {}
        self._undo_stack = []
        self._profile_undo_stacks = {}
        self._pre_edit_modified = None
        self._param_order = []
        self._header_frame = None
        self._name_row = None
        self._content_canvas = None
        self._content_frame = None
        self._content_sb = None
        self._canvas_window = None
        self._current_material = "General"
        self._indicator_frames = {}
        self._scroll_bound = False
        self._show_placeholder()

        # Note: Ctrl+Z / Cmd+Z is bound by App._bind_global_undo which
        # dispatches to the correct panel (ComparePanel or DetailPanel).

    def _show_placeholder(self, text: Optional[str] = None) -> None:
        for w in self.winfo_children():
            w.destroy()
        theme = self.theme
        if text:
            tk.Label(
                self, text=text, bg=theme.bg2, fg=theme.fg2, font=(UI_FONT, 13)
            ).pack(pady=40)
        else:
            # Empty state with centered message and actions
            container = tk.Frame(self, bg=theme.bg2)
            container.place(relx=0.5, rely=0.4, anchor="center")
            tk.Label(
                container, text="\u2699", bg=theme.bg2, fg=theme.fg3, font=(UI_FONT, 28)
            ).pack()
            tk.Label(
                container,
                text="No profile selected",
                bg=theme.bg2,
                fg=theme.fg2,
                font=(UI_FONT, 14),
            ).pack(pady=(4, 8))
            actions = tk.Frame(container, bg=theme.bg2)
            actions.pack()

            # Bind clicks — find the App instance (cache once, not per-click)
            def _find_app(widget: tk.Widget) -> Optional[Any]:
                """Walk up the widget tree to find the App root window."""
                w = widget
                while w:
                    from . import App

                    if isinstance(w, App):
                        return w
                    w = w.master
                return None

            app_ref = _find_app(self)

            def _safe_call(method_name: str) -> Callable:
                """Return a click handler that calls an App method if app_ref is valid."""

                def handler(event: tk.Event = None) -> None:
                    if app_ref is not None:
                        getattr(app_ref, method_name)()

                return handler

            json_lbl = tk.Label(
                actions,
                text="Import JSON",
                bg=theme.bg2,
                fg=theme.accent,
                font=(UI_FONT, 13, "bold"),
                cursor="pointinghand",
            )
            json_lbl.pack(side="left", padx=(0, 6))
            json_lbl.bind(
                "<Enter>", lambda e: json_lbl.configure(fg=theme.accent_hover)
            )
            json_lbl.bind("<Leave>", lambda e: json_lbl.configure(fg=theme.accent))
            json_lbl.bind("<Button-1>", _safe_call("_on_import_json"))
            tk.Label(
                actions, text="|", bg=theme.bg2, fg=theme.fg3, font=(UI_FONT, 13)
            ).pack(side="left", padx=(0, 6))
            mf_lbl = tk.Label(
                actions,
                text="Import from 3MF",
                bg=theme.bg2,
                fg=theme.accent,
                font=(UI_FONT, 13, "bold"),
                cursor="pointinghand",
            )
            mf_lbl.pack(side="left", padx=(0, 6))
            mf_lbl.bind("<Enter>", lambda e: mf_lbl.configure(fg=theme.accent_hover))
            mf_lbl.bind("<Leave>", lambda e: mf_lbl.configure(fg=theme.accent))
            mf_lbl.bind("<Button-1>", _safe_call("_on_extract_3mf"))
            tk.Label(
                actions, text="|", bg=theme.bg2, fg=theme.fg3, font=(UI_FONT, 13)
            ).pack(side="left", padx=(0, 6))
            lp_lbl = tk.Label(
                actions,
                text="Load Installed Profiles",
                bg=theme.bg2,
                fg=theme.accent,
                font=(UI_FONT, 13, "bold"),
                cursor="pointinghand",
            )
            lp_lbl.pack(side="left")
            lp_lbl.bind("<Enter>", lambda e: lp_lbl.configure(fg=theme.accent_hover))
            lp_lbl.bind("<Leave>", lambda e: lp_lbl.configure(fg=theme.accent))
            lp_lbl.bind("<Button-1>", _safe_call("_on_load_presets"))

    def _on_undo(self, event: Optional[tk.Event] = None) -> str:
        """Undo the last parameter edit."""
        if not self._undo_stack or not self.current_profile:
            return "break"
        entry = self._undo_stack.pop()
        key, old_value = entry[0], entry[1]
        was_in_data = entry[2] if len(entry) > 2 else True
        if was_in_data:
            self.current_profile.data[key] = old_value
        else:
            self.current_profile.data.pop(key, None)
        if (
            hasattr(self.current_profile, "resolved_data")
            and self.current_profile.resolved_data is not None
        ):
            if was_in_data:
                self.current_profile.resolved_data[key] = old_value
            else:
                self.current_profile.resolved_data.pop(key, None)
        if not self._undo_stack and self._pre_edit_modified is not None:
            self.current_profile.modified = self._pre_edit_modified
            self._pre_edit_modified = None
        # Find which tab the key belongs to
        target_tab = self._current_tab
        for tab_name, sections in FILAMENT_LAYOUT.items():
            for section_name, params in sections.items():
                if any(p[0] == key for p in params):
                    target_tab = tab_name
                    break
            else:
                continue
            break
        # Save scroll position
        canvas = getattr(self, "_content_canvas", None)
        scroll_y = canvas.yview()[0] if canvas else 0
        if target_tab:
            self._switch_tab(target_tab)
        # Restore scroll position (only if staying on same tab)
        if canvas and canvas.winfo_exists() and target_tab == self._current_tab:
            self.after_idle(lambda: canvas.yview_moveto(scroll_y))
        self._notify_list_refresh()
        return "break"

    def _notify_list_refresh(self) -> None:
        ProfileListPanel = _get_profile_list_panel_class()
        parent = _find_ancestor(self, ProfileListPanel)
        if parent:
            parent._refresh_list()

    # -- SECTION: Header Rendering --

    def _build_header(self, profile: Profile) -> tk.Frame:
        theme = self.theme

        # -- Header (compact: 3 rows max) --
        header_frame = tk.Frame(self, bg=theme.bg2)
        header_frame.pack(fill="x", padx=10, pady=(6, 0))

        # Row 1: profile name (left) + Save button (right)
        self._name_row = tk.Frame(header_frame, bg=theme.bg2)
        self._name_row.pack(fill="x")
        name_row = self._name_row

        ptype_upper = profile.profile_type.upper()
        self._name_label = tk.Label(
            name_row,
            text=f"{ptype_upper}  \u2022  {profile.name}",
            bg=theme.bg2,
            fg=theme.fg,
            font=(UI_FONT, 17, "bold"),
        )
        self._name_label.pack(side="left", anchor="w")

        # Slicer origin badge (dynamic: full label -> single letter when tight)
        if profile.origin and profile.origin in SLICER_COLORS:
            short = SLICER_SHORT_LABELS.get(profile.origin, profile.origin)
            letter = short[0] if short else ""
            badge_bg = SLICER_COLORS[profile.origin]
            slicer_badge = tk.Label(
                name_row,
                text=f" {short} ",
                bg=badge_bg,
                fg=theme.accent_fg,
                font=(UI_FONT, 11, "bold"),
                padx=4,
                pady=1,
            )
            slicer_badge.pack(side="left", padx=(8, 0))
            _Tooltip(
                slicer_badge, f"This profile uses {profile.origin} format", theme=theme
            )

            def _resize_badge(
                e: tk.Event, badge=slicer_badge, full=f" {short} ", abbr=f" {letter} "
            ) -> None:
                row_w = e.width
                needed = self._name_label.winfo_reqwidth() + badge.winfo_reqwidth() + 30
                badge.configure(text=abbr if row_w < needed else full)

            name_row.bind("<Configure>", _resize_badge)

        # "Fill Missing" button -- shown when profile has missing conversion keys
        if profile._missing_conversion_keys:
            n_missing = len(profile._missing_conversion_keys)
            fill_btn = _make_btn(
                name_row,
                f"\u24d8 Fill {n_missing} Missing",
                self._fill_all_missing,
                bg=theme.recommended,
                fg=theme.fg,
                font=(UI_FONT, 11, "bold"),
                padx=8,
                pady=2,
            )
            fill_btn.pack(side="right", pady=(4, 0), padx=(0, 4))
            _Tooltip(
                fill_btn,
                "Populate all missing conversion params with typical values",
                theme=theme,
            )

        # Clear Compare button -- resets comparison and lets user pick new profiles
        clear_icon = (
            self.icons_sm.clear
            if (self.icons_sm and hasattr(self.icons_sm, "clear"))
            else None
        )
        clear_btn = _make_btn(
            name_row,
            "Exit Compare",
            self._on_clear_compare,
            bg=theme.bg4,
            fg=theme.fg2,
            font=(UI_FONT, 12),
            padx=8,
            pady=2,
            image=clear_icon,
            compound="left",
        )
        clear_btn.pack(side="right", pady=(4, 0), padx=(0, 4))
        _Tooltip(clear_btn, "Return to single-profile view", theme=theme)

        # Smart Recommendations button
        rec_btn = _make_btn(
            name_row,
            "\u2699 Recommendations",
            self._open_recommendations,
            bg=theme.bg4,
            fg=theme.fg2,
            font=(UI_FONT, 12),
            padx=8,
            pady=2,
        )
        rec_btn.pack(side="right", pady=(4, 0), padx=(0, 4))
        self._name_label.bind("<Double-1>", lambda e: self._start_header_rename())
        _Tooltip(self._name_label, "Double-click to rename", theme=theme)

        # Row 2: status + inheritance + source -- one line, plain text
        row2 = tk.Frame(header_frame, bg=theme.bg2)
        row2.pack(fill="x", pady=(2, 0))

        # Status text (colored, no bg box)
        if profile.modified:
            status_text = "Unlocked"
            status_fg = theme.modified
        elif profile.is_locked:
            printers = profile.compatible_printers
            if printers:
                status_text = "Printer-Specific"
                status_fg = theme.locked
            else:
                # Bound to a printer profile via printer_settings_id
                psid = profile.data.get("printer_settings_id", "")
                if isinstance(psid, list):
                    psid = psid[0] if psid else ""
                if psid:
                    status_text = f"Specific to {psid}"
                    status_fg = theme.locked
                else:
                    status_text = "Custom"
                    status_fg = theme.fg
        else:
            status_text = "Custom"
            status_fg = theme.fg
        tk.Label(
            row2,
            text=status_text,
            bg=theme.bg2,
            fg=status_fg,
            font=(UI_FONT, 13, "bold"),
        ).pack(side="left")

        # Separator dot + inheritance + source
        info_parts = []
        if profile.inherits:
            inherit_str = f"inherits from {profile.inherits}"
            if not profile.resolved_data:
                inherit_str += " (not found)"
            info_parts.append(inherit_str)
        info_parts.append(profile.source_label)
        if info_parts:
            tk.Label(
                row2,
                text="  \u00b7  " + "  \u00b7  ".join(info_parts),
                bg=theme.bg2,
                fg=theme.fg2,
                font=(UI_FONT, 13),
            ).pack(side="left")

        # Undo / Changelog link -- always visible so users discover the feature
        hist_count = len(profile.changelog) if profile.changelog else 0
        hist_lbl = tk.Label(
            row2,
            text=f"  \u00b7  Undo / Changelog ({hist_count})",
            bg=theme.bg2,
            fg=theme.inherited,
            font=(UI_FONT, 13, "underline"),
            cursor="pointinghand",
        )
        hist_lbl.pack(side="left")
        hist_lbl.bind("<Button-1>", lambda e, p=profile: self._show_changelog(p))

        # Material badge + inherited count for legend
        inherited_count = len(self._inherited_keys)

        row3 = tk.Frame(header_frame, bg=theme.bg2)
        row3.pack(fill="x", pady=(1, 0))

        # Material badge (from Smart Recommendations)
        if self._current_material != "General":
            tk.Label(
                row3,
                text=f"Material: {self._current_material}",
                bg=theme.bg2,
                fg=theme.accent,
                font=(UI_FONT, 12, "bold"),
            ).pack(side="left")

        # Count how many params have recommendations (for legend decision)
        rec_param_count = sum(
            1
            for key in self._display_data
            if check_value_range(key, self._display_data[key], self._current_material)
            is not None
        )

        # Row 4: Icon legend (only when inherited keys or recommendations exist)
        has_inherited = inherited_count > 0
        has_recommendations = rec_param_count > 0
        if has_inherited or has_recommendations:
            self._build_legend_row(header_frame, has_inherited, has_recommendations)

        return header_frame

    def _build_legend_row(
        self, header_frame: tk.Frame, has_inherited: bool, has_recommendations: bool
    ) -> None:
        """Build the color legend row at the bottom of the header."""
        theme = self.theme
        legend = tk.Frame(header_frame, bg=theme.bg2)
        legend.pack(fill="x", pady=(2, 0))
        parts = []
        if has_inherited:
            parts.append(("\u21b0", theme.inherited, "Inherited"))
        if has_recommendations:
            parts.append(("\u25bc", theme.info, "Below recommended"))
            parts.append(("\u25b2", theme.warning, "Above recommended"))
            parts.append(("\u24d8", theme.fg3, "Smart recommendation"))
        for i, (icon, color, desc) in enumerate(parts):
            if i > 0:
                tk.Label(legend, text="  ", bg=theme.bg2).pack(side="left")
            tk.Label(
                legend, text=icon, bg=theme.bg2, fg=color, font=(UI_FONT, 12, "bold")
            ).pack(side="left")
            tk.Label(
                legend, text=f" {desc}", bg=theme.bg2, fg=theme.fg3, font=(UI_FONT, 12)
            ).pack(side="left")

    def _show_changelog(self, profile: Profile) -> None:
        theme = self.theme
        dlg = tk.Toplevel(self)
        dlg.title(f"Undo / Changelog \u2014 {profile.name}")
        dlg.configure(bg=theme.bg)
        dlg.resizable(True, True)
        dlg.transient(self.winfo_toplevel())

        title_lbl = tk.Label(
            dlg,
            text=f'Change history for "{profile.name}"',
            bg=theme.bg,
            fg=theme.fg,
            font=(UI_FONT, 14, "bold"),
        )
        title_lbl.pack(padx=16, pady=(12, 8), anchor="w")

        list_frame = tk.Frame(
            dlg, bg=theme.bg3, highlightbackground=theme.border, highlightthickness=1
        )
        list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # Use a frame inside a canvas for scrollable content with embedded buttons
        canvas = tk.Canvas(
            list_frame, bg=theme.bg3, highlightthickness=0, yscrollincrement=4
        )
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=theme.bg3)
        content.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _build_changelog_entry(parent: tk.Widget, index: int, entry: tuple) -> None:
            """Build a single changelog entry row with optional undo button."""
            if len(entry) < 3:
                return
            ts, action, details = entry[0], entry[1], entry[2]
            has_snapshot = len(entry) >= 4 and entry[3] is not None
            real_idx = len(profile.changelog) - 1 - index

            row = tk.Frame(parent, bg=theme.bg3)
            row.pack(fill="x", padx=10, pady=(6, 2))

            # Timestamp + action on one line
            header = tk.Frame(row, bg=theme.bg3)
            header.pack(fill="x")
            tk.Label(
                header,
                text=action,
                bg=theme.bg3,
                fg=theme.accent,
                font=(UI_FONT, 13, "bold"),
                anchor="w",
            ).pack(side="left")
            tk.Label(
                header,
                text=f"  {ts}",
                bg=theme.bg3,
                fg=theme.fg3,
                font=(UI_FONT, 12),
                anchor="w",
            ).pack(side="left", pady=(2, 0))

            if details:
                tk.Label(
                    row,
                    text=details,
                    bg=theme.bg3,
                    fg=theme.fg2,
                    font=(UI_FONT, 12),
                    anchor="w",
                    wraplength=380,
                    justify="left",
                ).pack(anchor="w", pady=(2, 0))

            # Undo button below the entry text, left-aligned
            if has_snapshot and real_idx == len(profile.changelog) - 1:

                def _undo(idx: int = real_idx) -> None:
                    profile.restore_snapshot(idx)
                    title_lbl.configure(text=f'Change history for "{profile.name}"')
                    _rebuild_entries()
                    self._refresh_after_undo(profile)

                _make_btn(
                    row,
                    "\u21a9 Undo this change",
                    _undo,
                    bg=theme.bg4,
                    fg=theme.warning,
                    font=(UI_FONT, 12),
                    padx=10,
                    pady=4,
                ).pack(anchor="w", pady=(6, 2))

        def _rebuild_entries() -> None:
            for w in content.winfo_children():
                w.destroy()

            for i, entry in enumerate(reversed(profile.changelog)):
                if i > 0:
                    tk.Frame(content, bg=theme.border, height=1).pack(
                        fill="x", padx=8, pady=(4, 4)
                    )
                _build_changelog_entry(content, i, entry)

            if not profile.changelog:
                tk.Label(
                    content,
                    text="No changes recorded.",
                    bg=theme.bg3,
                    fg=theme.fg3,
                    font=(UI_FONT, 12),
                ).pack(padx=16, pady=16)

            # Bind scroll on all children so mousewheel works everywhere
            def _bind_recursive(w: tk.Widget) -> None:
                bind_scroll(w, canvas)
                for child in w.winfo_children():
                    _bind_recursive(child)

            _bind_recursive(content)

        _rebuild_entries()

        _make_btn(
            dlg,
            "Close",
            dlg.destroy,
            bg=theme.bg4,
            fg=theme.fg2,
            font=(UI_FONT, 12),
            padx=12,
            pady=5,
        ).pack(pady=(4, 12))

        # Size the window to fit content, with reasonable bounds
        dlg.update_idletasks()
        w = min(max(dlg.winfo_reqwidth(), 360), 520)
        h = min(max(dlg.winfo_reqheight(), 180), 500)
        x = self.winfo_rootx() + 60
        y = self.winfo_rooty() + 60
        dlg.geometry(f"{w}x{h}+{x}+{y}")

    def _refresh_after_undo(self, profile: Profile) -> None:
        # Walk up to find the ProfileListPanel parent
        ProfileListPanel = _get_profile_list_panel_class()
        parent = _find_ancestor(self, ProfileListPanel)
        if parent:
            parent._refresh_list()
        # Re-display the profile
        self.show_profile(profile)

    def _start_header_rename(self) -> None:
        if not self.current_profile:
            return
        if getattr(self, "_header_rename_active", False):
            return
        self._header_rename_active = True
        theme = self.theme
        profile = self.current_profile
        ptype_upper = profile.profile_type.upper()

        self._name_label.destroy()
        name_row = self._name_row

        name_frame = tk.Frame(name_row, bg=theme.bg2)
        name_frame.pack(side="left", fill="x", expand=True)

        prefix = tk.Label(
            name_frame,
            text=f"{ptype_upper}  \u2022  ",
            bg=theme.bg2,
            fg=theme.fg,
            font=(UI_FONT, 17, "bold"),
        )
        prefix.pack(side="left")

        name_var = tk.StringVar(value=profile.name)
        entry = tk.Entry(
            name_frame,
            textvariable=name_var,
            bg=theme.bg3,
            fg=theme.fg,
            insertbackground=theme.fg,
            font=(UI_FONT, 17, "bold"),
            highlightbackground=theme.accent,
            highlightthickness=1,
            relief="flat",
        )
        entry.pack(side="left", fill="x", expand=True)
        entry.focus_set()
        entry.select_range(0, "end")

        def _rebuild_label() -> None:
            name_frame.destroy()
            self._header_rename_active = False
            self._name_label = tk.Label(
                name_row,
                text=f"{ptype_upper}  \u2022  {profile.name}",
                bg=theme.bg2,
                fg=theme.fg,
                font=(UI_FONT, 17, "bold"),
            )
            self._name_label.pack(side="left", anchor="w")
            self._name_label.bind("<Double-1>", lambda e: self._start_header_rename())

        def _finish(event: Optional[tk.Event] = None) -> None:
            if not self._header_rename_active:
                return
            new_name = Profile.sanitize_name(name_var.get())
            if new_name and new_name != profile.name:
                old_name = profile.name
                snapshot = {"name": old_name, "_modified": profile.modified}
                profile.data["name"] = new_name
                profile.modified = True
                profile.log_change(
                    "Renamed", f"{old_name} \u2192 {new_name}", snapshot=snapshot
                )
            _rebuild_label()
            self._notify_list_refresh()

        def _cancel(event: Optional[tk.Event] = None) -> None:
            if not self._header_rename_active:
                return
            _rebuild_label()

        entry.bind("<Return>", _finish)
        entry.bind("<FocusOut>", _finish)
        entry.bind("<Escape>", _cancel)

    def _save_profile(self) -> None:
        if not self.current_profile:
            return
        self._commit_edits()
        profile = self.current_profile
        init_dir = (
            os.path.dirname(profile.source_path)
            if profile.source_path
            and os.path.exists(os.path.dirname(profile.source_path))
            else os.path.expanduser("~")
        )
        fp = filedialog.asksaveasfilename(
            title="Save Profile",
            initialdir=init_dir,
            initialfile=profile.suggested_filename(),
            defaultextension=".json",
            filetypes=[
                ("JSON Profile", "*.json"),
                ("PrusaSlicer INI", "*.ini"),
                ("All files", "*.*"),
            ],
        )
        if not fp:
            return
        try:
            if fp.lower().endswith(".ini"):
                content = profile.to_prusa_ini()
            else:
                content = profile.to_json()
            with open(fp, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("Saved", f"Profile saved to:\n{os.path.basename(fp)}")
        except OSError as e:
            messagebox.showerror("Save Failed", str(e))

    # -- SECTION: Tab Management and Content Rendering --

    def _build_tab_bar(self, layout: dict) -> list:
        theme = self.theme

        # -- Sub-tab bar --
        tab_bar = tk.Frame(self, bg=theme.bg2)
        tab_bar.pack(fill="x", padx=10, pady=(6, 0))

        tab_names = list(layout.keys())

        for tab_name in tab_names:
            tab_frame = tk.Frame(
                tab_bar,
                bg=theme.bg3,
                highlightbackground=theme.border,
                highlightthickness=1,
            )
            tab_frame.pack(side="left", padx=(0, 2))
            lbl = tk.Label(
                tab_frame,
                text=tab_name,
                bg=theme.bg3,
                fg=theme.fg,
                font=(UI_FONT, 13),
                padx=10,
                pady=4,
            )
            lbl.pack(side="left")
            if tab_name in ORCA_ONLY_TABS:
                orca_badge = tk.Label(
                    tab_frame,
                    text="O",
                    bg="#028A0F",
                    fg=theme.accent_fg,
                    font=(UI_FONT, 9, "bold"),
                    padx=3,
                    pady=1,
                )
                orca_badge._is_orca_badge = True  # type: ignore
                orca_badge.pack(side="left", padx=(0, 6))
                orca_badge.bind(
                    "<Button-1>", lambda e, tn=tab_name: self._switch_tab(tn)
                )
            tab_frame.bind("<Button-1>", lambda e, tn=tab_name: self._switch_tab(tn))
            lbl.bind("<Button-1>", lambda e, tn=tab_name: self._switch_tab(tn))
            self._tab_buttons.append((tab_name, tab_frame))

        # Separator below tabs
        tk.Frame(self, bg=theme.border, height=1).pack(fill="x", padx=8, pady=(2, 0))

        return tab_names

    def _build_content_area(self) -> None:
        theme = self.theme

        # -- Content area --
        content_container = tk.Frame(self, bg=theme.param_bg)
        content_container.pack(fill="both", expand=True)

        self._content_canvas = tk.Canvas(
            content_container,
            bg=theme.param_bg,
            highlightthickness=0,
            yscrollincrement=4,
        )
        self._content_sb = ttk.Scrollbar(
            content_container, orient="vertical", command=self._content_canvas.yview
        )
        self._content_frame = tk.Frame(self._content_canvas, bg=theme.param_bg)
        self._content_frame.bind(
            "<Configure>",
            lambda e: self._content_canvas.configure(
                scrollregion=self._content_canvas.bbox("all")
            ),
        )
        self._canvas_window = self._content_canvas.create_window(
            (0, 0), window=self._content_frame, anchor="nw"
        )
        self._content_canvas.configure(yscrollcommand=self._content_sb.set)
        self._content_canvas.pack(side="left", fill="both", expand=True)
        self._content_sb.pack(side="right", fill="y")

        self._content_canvas.bind(
            "<Configure>",
            lambda e: self._content_canvas.itemconfig(
                self._canvas_window, width=e.width
            ),
        )
        # Scroll binding -- bind to canvas initially (see _switch_tab for recursive bind)
        bind_scroll(self._content_canvas, self._content_canvas)

    def show_profile(self, profile: Profile) -> None:
        self._commit_edits()
        # Save current undo stack before switching profiles
        if self.current_profile:
            self._profile_undo_stacks[id(self.current_profile)] = self._undo_stack
        self.current_profile = profile
        self._edit_vars = {}
        self._undo_stack = self._profile_undo_stacks.get(id(profile), [])
        self._pre_edit_modified = None
        self._param_order = []
        self._indicator_frames = {}
        self._tab_buttons = []
        self._current_tab = None
        self._scroll_bound = False
        for w in self.winfo_children():
            w.destroy()

        layout = FILAMENT_LAYOUT

        if profile.inherits and not profile.resolved_data:
            try:
                app = self.winfo_toplevel()
                if hasattr(app, "preset_index"):
                    app.preset_index.resolve(profile)
            except (KeyError, AttributeError) as e:
                logger.debug("Failed to resolve inheritance: %s", e)

        self._display_data = (
            profile.resolved_data if profile.resolved_data else profile.data
        )
        self._inherited_keys = (
            profile.inherited_keys if profile.inherited_keys else set()
        )

        self._current_material = detect_material(self._display_data)

        self._header_frame = self._build_header(profile)

        # Informational note when inherited base profile could not be found
        if profile.inherits and not profile.resolved_data:
            theme = self.theme
            note = tk.Frame(self, bg=theme.bg3)
            note.pack(fill="x", padx=8, pady=(4, 0))
            tk.Label(
                note,
                text=f'Inherits from "{profile.inherits}" (base profile not found on this system).',
                bg=theme.bg3,
                fg=theme.fg2,
                font=(UI_FONT, 12),
                padx=10,
                pady=6,
                anchor="w",
            ).pack(anchor="w")

        tab_names = self._build_tab_bar(layout)
        self._build_content_area()

        if tab_names:
            self._switch_tab(tab_names[0])

    def _switch_tab(self, tab_name: str) -> None:
        """Switch to a different tab and render its content."""
        self._commit_edits()
        theme = self.theme
        self._current_tab = tab_name
        self._param_order = []  # Reset navigation order for new tab
        self._indicator_frames = {}  # Reset indicator references for new tab

        for tn, tab_frame in self._tab_buttons:
            active = tn == tab_name
            bg = theme.accent2 if active else theme.bg3
            fg = theme.accent_fg if active else theme.fg
            font = (UI_FONT, 13, "bold") if active else (UI_FONT, 13)
            hb = theme.accent2 if active else theme.border
            tab_frame.configure(bg=bg, highlightbackground=hb)
            for child in tab_frame.winfo_children():
                if isinstance(child, tk.Label):
                    if getattr(child, "_is_orca_badge", False):
                        continue  # preserve badge color on tab switch
                    else:
                        child.configure(fg=fg, bg=bg, font=font)

        for w in self._content_frame.winfo_children():
            w.destroy()

        profile = self.current_profile
        layout = FILAMENT_LAYOUT
        sections = layout.get(tab_name, {})

        display_data = self._display_data
        has_content = False
        if sections:
            for section_name, params in sections.items():
                if self._render_section(section_name, params, display_data):
                    has_content = True

        # On the last tab, show discovered (unrecognized) keys
        tab_names = list(layout.keys())
        if tab_name == tab_names[-1]:
            known = set()
            for secs in layout.values():
                for ps in secs.values():
                    for entry in ps:
                        known.add(entry[0])
            known.update(_IDENTITY_KEYS)
            extra = {k: v for k, v in display_data.items() if k not in known}
            if extra:
                has_content = True
                # Humanize raw JSON keys: "adaptive_layer_height" -> "Adaptive layer height"
                humanized = [
                    (k, k.replace("_", " ").capitalize()) for k in sorted(extra)
                ]
                self._render_section(
                    "Unrecognized parameters", humanized, display_data, discovered=True
                )

        if not has_content and not sections:
            tk.Label(
                self._content_frame,
                text="No settings in this tab",
                bg=theme.param_bg,
                fg=theme.fg2,
                font=(UI_FONT, 13),
            ).pack(pady=20)

        # Rebind scroll on every tab switch -- widgets are recreated each time
        self.bind_scroll_recursive(self._content_frame)

    def bind_scroll_recursive(self, widget: tk.Widget) -> None:
        bind_scroll(widget, self._content_canvas)
        for child in widget.winfo_children():
            self.bind_scroll_recursive(child)

    # -- SECTION: Parameter Rendering --

    def _render_section(
        self, section_name: str, params: list, data: dict, discovered: bool = False
    ) -> bool:
        theme = self.theme

        visible = [
            (e[0], e[1], e[2] if len(e) > 2 else None) for e in params if e[0] in data
        ]

        # Always render section header so the user knows it exists
        section_header = tk.Frame(self._content_frame, bg=theme.param_bg)
        section_header.pack(fill="x", padx=10, pady=(10, 3))
        accent_bar = tk.Frame(
            section_header, bg=theme.warning if discovered else theme.accent, width=3
        )
        accent_bar.pack(side="left", fill="y", padx=(0, 8))
        fg = theme.warning if discovered else theme.btn_fg
        tk.Label(
            section_header,
            text=section_name,
            bg=theme.param_bg,
            fg=fg,
            font=(UI_FONT, 15, "bold"),
        ).pack(side="left")

        if not visible:
            # Determine if the section is irrelevant to this profile's slicer
            slicer_short = ""
            if self.current_profile and self.current_profile.origin:
                slicer_short = SLICER_SHORT_LABELS.get(
                    self.current_profile.origin, self.current_profile.origin
                )
            tags = {e[2] if len(e) > 2 else None for e in params}
            tags.discard(None)
            if tags and slicer_short and slicer_short not in tags:
                empty_msg = f"Not used in {self.current_profile.origin}"
            else:
                empty_msg = "No values set in this section"
            tk.Label(
                self._content_frame,
                text=empty_msg,
                bg=theme.param_bg,
                fg=theme.fg3,
                font=(UI_FONT, 12, "italic"),
            ).pack(anchor="w", padx=24, pady=(2, 0))
            return True

        for json_key, ui_label, slicer_tag in visible:
            value = data[json_key]
            self._render_param(
                ui_label, json_key, value, discovered=discovered, slicer_tag=slicer_tag
            )

        # Render missing conversion keys that belong to this section
        if self.current_profile and self.current_profile._missing_conversion_keys:
            missing = self.current_profile._missing_conversion_keys
            for entry in params:
                json_key = entry[0]
                if json_key in missing and json_key not in data:
                    ui_label = entry[1]
                    slicer_tag = entry[2] if len(entry) > 2 else None
                    self._render_missing_param(
                        ui_label, json_key, slicer_tag=slicer_tag
                    )

        return True

    def _get_raw_enum_str(self, value: Any) -> Optional[str]:
        """Extract the raw string for enum lookup, unwrapping single-element lists.

        BambuStudio stores per-extruder enum arrays where all elements are identical.
        Unwrap to a single string for enum lookup when the array is uniform.

        Args:
            value: Value to extract enum string from.

        Returns:
            String representation of enum value, or None if list is non-uniform.
        """
        if isinstance(value, list):
            if len(set(str(v) for v in value)) == 1:
                return str(value[0])
        return str(value) if not isinstance(value, list) else None

    # Badge colors and short labels for slicer tags
    _SLICER_BADGE_COLORS = {
        "Prusa": "#FF7B15",
        "Bambu": "#028A0F",
        "Orca": "#2196F3",
    }
    _SLICER_BADGE_LABELS = {
        "Prusa": "P",
        "Bambu": "B",
        "Orca": "O",
    }

    def _render_param(
        self,
        label: str,
        key: str,
        value: Any,
        discovered: bool = False,
        slicer_tag: str | None = None,
    ) -> None:
        theme = self.theme
        is_inherited = key in self._inherited_keys

        row = tk.Frame(self._content_frame, bg=theme.param_bg)
        row.pack(fill="x", padx=14, pady=2)
        row.columnconfigure(0, weight=1, minsize=_LABEL_COL_WIDTH)
        row.columnconfigure(1, minsize=_VAL_COL_WIDTH, weight=0)
        row.columnconfigure(2, minsize=24, weight=0)
        row.columnconfigure(3, minsize=20, weight=0)

        label_fg = theme.fg2 if is_inherited else theme.fg
        label_font = (UI_FONT, 13) if is_inherited else (UI_FONT, 13, "bold")
        label_frame = tk.Frame(row, bg=theme.param_bg)
        label_frame.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        if is_inherited:
            inherit_icon = tk.Label(
                label_frame,
                text="\u21b0",
                bg=theme.param_bg,
                fg=theme.inherited,
                font=(UI_FONT, 12),
            )
            inherit_icon.pack(side="left", padx=(0, 3))
            _Tooltip(
                inherit_icon,
                f"Inherited from base profile. Click the value to customize it.",
                theme=theme,
            )
        lbl = tk.Label(
            label_frame,
            text=label,
            bg=theme.param_bg,
            fg=label_fg,
            font=label_font,
            anchor="w",
        )
        lbl.pack(side="left", fill="x", expand=True)
        if discovered:
            _Tooltip(lbl, f"JSON key: {key}", theme=theme)

        display = self._format_value(value, key=key)
        if display == "nil":
            display = "0"

        raw_str = self._get_raw_enum_str(value)
        is_enum = key in ENUM_VALUES and raw_str is not None

        if key.endswith("_gcode") or key == "post_process" or key == "filament_notes":
            mono = (MONO_FONT, MONO_FONT_SIZE)
            txt = tk.Text(
                row,
                bg=theme.bg3,
                fg=theme.fg,
                font=mono,
                height=min(8, max(2, str(value).count("\n") + 1)),
                width=40,
                highlightbackground=theme.border,
                highlightthickness=1,
                wrap="word",
            )
            txt.insert("1.0", str(value) if value else "")
            txt.grid(row=0, column=1, sticky="ew", padx=(4, 0))
            self._edit_vars[key] = (txt, value, "text")
        elif is_enum:
            self._render_enum_dropdown(row, key, value, raw_str, is_inherited)
        else:
            val_fg = theme.fg2 if is_inherited else theme.fg
            val_frame = tk.Frame(
                row,
                bg=theme.edit_bg,
                highlightbackground=theme.border,
                highlightthickness=1,
                padx=4,
                pady=1,
                width=_VAL_COL_WIDTH,
            )
            val_frame.grid(row=0, column=1, sticky="w", padx=(4, 0))
            val_frame.grid_propagate(False)
            val_frame.configure(height=28)
            val_lbl = tk.Label(
                val_frame,
                text=display,
                bg=theme.edit_bg,
                fg=val_fg,
                font=(UI_FONT, 13),
                anchor="w",
                cursor="xterm",
            )
            val_lbl.pack(fill="x")
            val_lbl.bind(
                "<Button-1>",
                lambda e, r=val_frame, l=val_lbl, k=key, v=value, fg=val_fg: self._activate_edit(
                    r, l, k, v, fg
                ),
            )
            val_frame.bind(
                "<Button-1>",
                lambda e, r=val_frame, l=val_lbl, k=key, v=value, fg=val_fg: self._activate_edit(
                    r, l, k, v, fg
                ),
            )
            self._edit_vars[key] = (None, value, "label")
            self._param_order.append((key, val_frame, val_fg))

        indicator_frame = tk.Frame(row, bg=theme.param_bg, width=24)
        indicator_frame.grid(row=0, column=2, sticky="e", padx=(4, 0))
        if key in RECOMMENDATIONS:
            self._indicator_frames[key] = indicator_frame
            self._update_indicator(key, value)

        info_frame = tk.Frame(row, bg=theme.param_bg, width=20)
        info_frame.grid(row=0, column=3, sticky="e", padx=(2, 0))
        if key in RECOMMENDATIONS and not discovered:
            info_icon = tk.Label(
                info_frame,
                text="\u24d8",
                bg=theme.param_bg,
                fg=theme.fg3,
                font=(UI_FONT, 12),
                cursor="pointinghand",
            )
            info_icon.pack()
            info_icon.bind(
                "<Enter>", lambda e, w=info_icon: w.configure(fg=theme.accent)
            )
            info_icon.bind("<Leave>", lambda e, w=info_icon: w.configure(fg=theme.fg3))
            _InfoPopup(info_icon, key, self._current_material, theme=theme)

    def _render_missing_param(
        self, label: str, key: str, slicer_tag: str | None = None
    ) -> None:
        """Render a row for a missing conversion param with a fill-from-typical badge."""
        theme = self.theme
        row = tk.Frame(self._content_frame, bg=theme.param_bg)
        row.pack(fill="x", padx=14, pady=2)
        row.columnconfigure(0, weight=1, minsize=_LABEL_COL_WIDTH)
        row.columnconfigure(1, minsize=_VAL_COL_WIDTH, weight=0)

        label_frame = tk.Frame(row, bg=theme.param_bg)
        label_frame.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        lbl = tk.Label(
            label_frame,
            text=label,
            bg=theme.param_bg,
            fg=theme.fg3,
            font=(UI_FONT, 13, "italic"),
            anchor="w",
        )
        lbl.pack(side="left", fill="x", expand=True)

        # Value area: show fill button if recommendation exists, else "not set"
        rec = get_recommendation(key, self._current_material)
        val_frame = tk.Frame(row, bg=theme.param_bg)
        val_frame.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        if rec and "typical" in rec:
            typical = rec["typical"]
            fill_btn = tk.Label(
                val_frame,
                text=f"\u24d8 Fill ({typical})",
                bg=theme.recommended,
                fg=theme.fg,
                font=(UI_FONT, 11, "bold"),
                padx=6,
                pady=1,
                cursor="pointinghand",
            )
            fill_btn.pack(side="left")
            _Tooltip(
                fill_btn,
                f"Missing after conversion. Click to set typical value: {typical}",
                theme=theme,
            )
            fill_btn.bind(
                "<Button-1>", lambda e, k=key, v=typical: self._fill_missing_param(k, v)
            )
        else:
            tk.Label(
                val_frame,
                text="(not set)",
                bg=theme.param_bg,
                fg=theme.fg3,
                font=(UI_FONT, 12, "italic"),
            ).pack(side="left")
            _Tooltip(
                lbl,
                f"Expected by target slicer \u2014 no typical value available, set manually",
                theme=theme,
            )

    def _fill_missing_param(self, key: str, value: Any) -> None:
        """Fill a missing conversion param with the given value."""
        if not self.current_profile:
            return
        was_in_data = key in self.current_profile.data
        self._undo_stack.append((key, self.current_profile.data.get(key), was_in_data))
        if len(self._undo_stack) > 200:
            self._undo_stack.pop(0)
        self.current_profile.data[key] = value
        if self.current_profile.resolved_data is not None:
            self.current_profile.resolved_data[key] = value
        self.current_profile._missing_conversion_keys.discard(key)
        self.current_profile.modified = True
        self.current_profile.log_change(
            "fill_missing", f"Set {key} = {value} (typical)"
        )
        self.show_profile(self.current_profile)

    def _fill_all_missing(self) -> None:
        """Batch-fill all missing conversion params with typical values."""
        if not self.current_profile:
            return
        profile = self.current_profile
        material = self._current_material
        filled = 0
        manual = 0
        for key in list(profile._missing_conversion_keys):
            rec = get_recommendation(key, material)
            if rec and "typical" in rec:
                was_in_data = key in profile.data
                old_val = profile.data.get(key)
                profile.data[key] = rec["typical"]
                if profile.resolved_data is not None:
                    profile.resolved_data[key] = rec["typical"]
                self._undo_stack.append((key, old_val, was_in_data))
                profile._missing_conversion_keys.discard(key)
                filled += 1
            else:
                manual += 1
        if filled:
            profile.modified = True
            profile.log_change(
                "fill_missing_batch", f"Filled {filled} params with typical values"
            )
        msg = f"Filled {filled} parameter(s) with typical values."
        if manual:
            msg += f"\n{manual} parameter(s) have no typical value \u2014 set manually."
        from tkinter import messagebox

        messagebox.showinfo("Fill Missing", msg, parent=self)
        self.show_profile(profile)

    def _update_indicator(self, key: str, value: Any = None) -> None:
        frame = self._indicator_frames.get(key)
        if not frame:
            return
        theme = self.theme
        for w in frame.winfo_children():
            w.destroy()
        if value is None:
            value = self.current_profile.data.get(key) if self.current_profile else None
        if value is None:
            return
        material = self._current_material
        range_status = check_value_range(key, value, material)
        if range_status == "low":
            ind = tk.Label(
                frame,
                text="\u25bc",
                bg=theme.param_bg,
                fg=theme.info,
                font=(UI_FONT, 12, "bold"),
            )
            ind.pack()
            rec = get_recommendation(key, material)
            tip = f"Below recommended range"
            if rec:
                tip += f" ({rec.get('min', '?')} \u2013 {rec.get('max', '?')})"
            _Tooltip(ind, tip, theme=theme)
            bind_scroll(ind, self._content_canvas)
        elif range_status == "high":
            ind = tk.Label(
                frame,
                text="\u25b2",
                bg=theme.param_bg,
                fg=theme.warning,
                font=(UI_FONT, 12, "bold"),
            )
            ind.pack()
            rec = get_recommendation(key, material)
            tip = f"Above recommended range"
            if rec:
                tip += f" ({rec.get('min', '?')} \u2013 {rec.get('max', '?')})"
            _Tooltip(ind, tip, theme=theme)
            bind_scroll(ind, self._content_canvas)

    def _render_enum_dropdown(
        self,
        row: tk.Frame,
        key: str,
        original_value: Any,
        raw_str: str,
        is_inherited: bool,
    ) -> None:
        theme = self.theme
        known_pairs = ENUM_VALUES[key]

        # Build human labels list; ensure current value is included
        human_labels = [hl for _, hl in known_pairs]
        known_json_vals = {jv for jv, _ in known_pairs}

        current_label = get_enum_human_label(key, raw_str)
        extra_label_to_json = {}
        if raw_str not in known_json_vals:
            # Unknown value -- append humanized label; remember the reverse mapping
            human_labels.append(current_label)
            extra_label_to_json[current_label] = raw_str

        value_var = tk.StringVar(value=current_label)
        # Fit dropdown width to longest option text, minimum 14 chars
        max_len = max((len(hl) for hl in human_labels), default=10)
        cb_width = max(max_len + 2, 14)
        combobox = ttk.Combobox(
            row,
            textvariable=value_var,
            values=human_labels,
            state="readonly",
            style="Param.TCombobox",
            font=(UI_FONT, 13),
            width=cb_width,
        )
        combobox.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        def _on_enum_change(event: Optional[tk.Event] = None) -> None:
            selected_label = value_var.get()
            _sentinel = object()
            known_reverse = _ENUM_LABEL_TO_JSON.get(key, {})
            new_json_val = known_reverse.get(selected_label, _sentinel)
            if new_json_val is _sentinel:
                new_json_val = extra_label_to_json.get(selected_label, selected_label)
            if isinstance(original_value, list):
                new_val = [new_json_val] * len(original_value)
            else:
                new_val = new_json_val
            if new_val != original_value:
                if self._pre_edit_modified is None:
                    self._pre_edit_modified = self.current_profile.modified
                was_in_data = key in self.current_profile.data
                self._undo_stack.append((key, original_value, was_in_data))
                if len(self._undo_stack) > 200:
                    self._undo_stack.pop(0)
                self.current_profile.data[key] = new_val
                if self.current_profile.resolved_data is not None:
                    self.current_profile.resolved_data[key] = new_val
                self.current_profile.modified = True
                self.current_profile.log_change(
                    "Parameter edited", f"{key}: {original_value} \u2192 {new_val}"
                )
                self._edit_vars[key] = (value_var, new_val, "combo")
                self._update_indicator(key, new_val)

        combobox.bind("<<ComboboxSelected>>", _on_enum_change)
        self._edit_vars[key] = (value_var, original_value, "combo")
        val_fg = theme.fg2 if is_inherited else theme.fg
        self._param_order.append((key, row, val_fg))

    # -- SECTION: Edit Tracking and Commit Logic --

    def _activate_edit(
        self,
        container: tk.Frame,
        label_widget: tk.Label,
        key: str,
        original_value: Any,
        fg_color: str,
    ) -> None:
        theme = self.theme
        label_widget.destroy()
        container.configure(highlightbackground=theme.accent)

        display = self._format_value(original_value, key=key)
        value_var = tk.StringVar(value=display)
        entry = tk.Entry(
            container,
            textvariable=value_var,
            bg=theme.edit_bg,
            fg=fg_color,
            font=(UI_FONT, 13),
            insertbackground=theme.fg,
            highlightthickness=0,
            relief="flat",
            width=_ENTRY_CHARS,
        )
        entry.pack(fill="x")
        entry.focus_set()
        entry.select_range(0, "end")

        self._edit_vars[key] = (value_var, original_value, "entry")

        def finish_edit(event: Optional[tk.Event] = None) -> None:
            if getattr(self, "_commit_in_progress", False):
                return
            self._commit_in_progress = True
            raw_text = value_var.get().strip()
            self._commit_single(key)
            new_val = self.current_profile.data.get(key, original_value)
            new_display = self._format_value(new_val, key=key)
            input_rejected = (
                new_val == original_value
                and raw_text != self._format_value(original_value, key=key)
            )
            entry.destroy()
            if input_rejected:
                container.configure(highlightbackground=theme.error)
                container.after(
                    800,
                    lambda c=container: (
                        c.configure(highlightbackground=theme.border)
                        if c.winfo_exists()
                        else None
                    ),
                )
            else:
                container.configure(highlightbackground=theme.border)
            new_lbl = tk.Label(
                container,
                text=new_display,
                bg=theme.edit_bg,
                fg=fg_color,
                font=(UI_FONT, 13),
                anchor="w",
                cursor="xterm",
            )
            new_lbl.pack(fill="x")
            new_lbl.bind(
                "<Button-1>",
                lambda e, r=container, l=new_lbl, k=key, v=new_val, f=fg_color: self._activate_edit(
                    r, l, k, v, f
                ),
            )
            container.bind(
                "<Button-1>",
                lambda e, r=container, l=new_lbl, k=key, v=new_val, f=fg_color: self._activate_edit(
                    r, l, k, v, f
                ),
            )
            self._edit_vars[key] = (None, new_val, "label")
            self._update_indicator(key, new_val)
            self._commit_in_progress = False

        def cancel_edit(event: Optional[tk.Event] = None) -> None:
            if getattr(self, "_commit_in_progress", False):
                return
            self._commit_in_progress = True
            try:
                entry.destroy()
                restore_display = self._format_value(original_value, key=key)
                container.configure(highlightbackground=theme.border)
                new_lbl = tk.Label(
                    container,
                    text=restore_display,
                    bg=theme.edit_bg,
                    fg=fg_color,
                    font=(UI_FONT, 13),
                    anchor="w",
                    cursor="xterm",
                )
                new_lbl.pack(fill="x")
                new_lbl.bind(
                    "<Button-1>",
                    lambda e, r=container, l=new_lbl, k=key, v=original_value, f=fg_color: self._activate_edit(
                        r, l, k, v, f
                    ),
                )
                container.bind(
                    "<Button-1>",
                    lambda e, r=container, l=new_lbl, k=key, v=original_value, f=fg_color: self._activate_edit(
                        r, l, k, v, f
                    ),
                )
                self._edit_vars[key] = (None, original_value, "label")
            finally:
                self._commit_in_progress = False

        def tab_next(event: Optional[tk.Event] = None) -> str:
            finish_edit()
            idx = next(
                (i for i, (k, *_) in enumerate(self._param_order) if k == key), -1
            )
            if idx >= 0 and idx + 1 < len(self._param_order):
                next_key, next_container, next_fg = self._param_order[idx + 1]
                next_val = self.current_profile.data.get(next_key)
                if next_val is not None:
                    children = next_container.winfo_children()
                    if children:
                        self._activate_edit(
                            next_container, children[0], next_key, next_val, next_fg
                        )
            return "break"

        entry.bind("<Return>", finish_edit)
        entry.bind("<Tab>", tab_next)
        entry.bind("<FocusOut>", finish_edit)
        entry.bind("<Escape>", cancel_edit)

    def _commit_single(self, key: str) -> None:
        if not self.current_profile or key not in self._edit_vars:
            return
        var_or_widget, original, kind = self._edit_vars[key]
        try:
            if kind == "entry":
                new_str = var_or_widget.get()
            elif kind == "text":
                new_str = var_or_widget.get("1.0", "end-1c")
            elif kind == "combo":
                # Combo edits are committed immediately in _on_enum_change;
                # nothing to do here -- the profile.data is already up to date.
                return
            else:
                return  # "label" kind -- not actively editing
        except tk.TclError:
            return

        new_val = self._parse_edit(new_str, original)
        if new_val != original:
            if self._pre_edit_modified is None:
                self._pre_edit_modified = self.current_profile.modified
            was_in_data = key in self.current_profile.data
            self._undo_stack.append((key, original, was_in_data))
            if len(self._undo_stack) > 200:
                self._undo_stack.pop(0)
            self.current_profile.data[key] = new_val
            if self.current_profile.resolved_data is not None:
                self.current_profile.resolved_data[key] = new_val
            self.current_profile.modified = True
            self._edit_vars[key] = (var_or_widget, new_val, kind)
            self.current_profile.log_change(
                "Parameter edited", f"{key}: {original} \u2192 {new_val}"
            )

    def _commit_edits(self) -> None:
        if not self.current_profile:
            return
        for key in list(self._edit_vars):
            self._commit_single(key)

    @staticmethod
    def _parse_edit(text: str, original: Any) -> Any:
        """Convert edited text back to the appropriate Python type,
        matching the original value's type.

        Args:
            text: Text input from user.
            original: Original value (used to determine type).

        Returns:
            Parsed value, or original if parsing fails.
        """
        text = text.strip()
        if len(text) > 10_000:
            logger.warning("Input too long (%d chars), max 10000", len(text))
            return original
        # IMPORTANT: bool check must come BEFORE int -- bool is a subclass of int in Python.
        if isinstance(original, bool):
            return text.lower() in ("yes", "true", "1")
        if isinstance(original, int):
            try:
                val = int(text)
            except ValueError:
                try:
                    val = int(float(text))
                    if not math.isfinite(float(text)):
                        return original
                except (ValueError, OverflowError):
                    logger.debug(
                        "Edit parse failed for key, reverting to original: text=%r, original=%r",
                        text,
                        original,
                    )
                    return original
            if abs(val) > 10**9:
                return original
            return val
        if isinstance(original, float):
            try:
                val = float(text)
                if not math.isfinite(val):
                    return original
                if abs(val) > 1e15:
                    return original
                return val
            except ValueError:
                logger.debug(
                    "Edit parse failed for key, reverting to original: text=%r, original=%r",
                    text,
                    original,
                )
                return original
        if isinstance(original, list):
            # If user entered a single value, wrap in list matching original length
            parts = [s.strip() for s in text.split(",") if s.strip()]
            result = []
            for i, part in enumerate(parts):
                type_reference = (
                    original[i]
                    if i < len(original)
                    else original[0] if original else ""
                )
                if isinstance(type_reference, int):
                    try:
                        v = int(part)
                        if abs(v) > 10**9:
                            v = type_reference
                        result.append(v)
                    except ValueError:
                        result.append(type_reference)
                elif isinstance(type_reference, float):
                    try:
                        v = float(part)
                        if not math.isfinite(v):
                            v = type_reference
                        result.append(v)
                    except ValueError:
                        result.append(type_reference)
                else:
                    result.append(part)
            # Truncate extra items to match original length.
            if len(result) > len(original):
                result = result[: len(original)]
            # Pad shorter input to original length using last entered value.
            # Guard: if all parts failed to parse, result may be empty -- don't crash.
            if result and len(result) < len(original):
                result.extend([result[-1]] * (len(original) - len(result)))
            return result
        return text

    @staticmethod
    def _nil_to_zero(v: Any) -> Any:
        """Convert slicer 'nil' values to 0 for display."""
        if isinstance(v, str) and v.strip().lower() == "nil":
            return "0"
        return v

    @staticmethod
    def _format_value(value: Any, key: Optional[str] = None) -> str:
        """Format a value for display."""
        if isinstance(value, list):
            # Replace nil entries in lists
            value = [ProfileDetailPanel._nil_to_zero(v) for v in value]
            # BambuStudio stores per-extruder values as arrays where all elements
            # are identical (e.g., [210, 210, 210] for nozzle temp across 3 extruders).
            # Collapse to a single display value when all entries match.
            if len(set(str(v) for v in value)) == 1:
                raw = str(value[0])
                if key and key in ENUM_VALUES:
                    return get_enum_human_label(key, raw)
                return raw
            return ", ".join(str(v) for v in value)
        elif isinstance(value, bool):
            return "Yes" if value else "No"
        elif value is None:
            return "N/A"
        value = ProfileDetailPanel._nil_to_zero(value)
        value_str = str(value)
        if key and key in ENUM_VALUES:
            return get_enum_human_label(key, value_str)
        return (
            value_str[:_VALUE_TRUNCATE_LONG] + "..."
            if len(value_str) > _VALUE_TRUNCATE_LONG
            else value_str
        )

    # -- SECTION: Clear Compare --

    def _on_clear_compare(self) -> None:
        """Clear current comparison and show waiting state."""
        try:
            ProfileListPanel = _get_profile_list_panel_class()
            parent = _find_ancestor(self, ProfileListPanel)
            if parent and parent.app:
                parent.app._close_compare()
        except tk.TclError:
            logger.exception("Error in _on_clear_compare")

    # -- SECTION: Smart Recommendations Integration --

    def _open_recommendations(self) -> None:
        if not self.current_profile:
            return
        try:
            if (
                hasattr(self, "_rec_dialog")
                and self._rec_dialog
                and self._rec_dialog.dlg.winfo_exists()
            ):
                self._rec_dialog.dlg.lift()
                return
        except (tk.TclError, AttributeError):
            self._rec_dialog = None
        # Gather all loaded profiles of the same type for statistical comparison
        all_profiles = []
        try:
            ProfileListPanel = _get_profile_list_panel_class()
            parent = _find_ancestor(self, ProfileListPanel)
            if parent:
                all_profiles = parent.profiles
        except tk.TclError:
            pass
        from .dialogs import RecommendationsDialog

        self._rec_dialog = RecommendationsDialog(
            self,
            self.theme,
            self.current_profile,
            all_profiles,
            refresh_callback=lambda p: self.show_profile(p),
        )

    def _detect_material_from_siblings(self) -> str:
        try:
            ProfileListPanel = _get_profile_list_panel_class()
            parent = _find_ancestor(self, ProfileListPanel)
            if parent:
                # Look at the app's filament tab for loaded filament profiles
                app = parent.app
                if hasattr(app, "filament_panel") and app.filament_panel.profiles:
                    # Use the first filament profile's material
                    for fp in app.filament_panel.profiles:
                        mat = detect_material(fp.data)
                        if mat != "General":
                            return mat
        except (KeyError, AttributeError) as e:
            logger.debug("Failed to detect material from siblings: %s", e)
        return "General"
