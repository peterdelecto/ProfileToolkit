# Profile detail viewer/editor and profile list manager

from __future__ import annotations

import logging
import os
import platform
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Any, Callable, Optional

from .constants import (
    PROCESS_LAYOUT,
    FILAMENT_LAYOUT,
    _ALL_PROCESS_KEYS,
    _ALL_FILAMENT_KEYS,
    _IDENTITY_KEYS,
    _PLATFORM,
    _WIN_SCROLL_DELTA_DIVISOR,
    _TREE_ROW_HEIGHT,
    _TREE_TOOLTIP_DELAY_MS,
    _VALUE_TRUNCATE_LONG,
    _LABEL_COL_WIDTH,
    ENUM_VALUES,
    RECOMMENDATIONS,
    _ENUM_LABEL_TO_JSON,
    UI_FONT,
)
from .theme import Theme
from .models import Profile
from .state import save_profile_state
from .utils import (
    bind_scroll,
    lighten_color,
    detect_material,
    get_recommendation,
    check_value_range,
    get_enum_human_label,
    get_recommendation_info,
)
from .widgets import Tooltip as _Tooltip, InfoPopup as _InfoPopup, ScrollableFrame, make_btn as _make_btn

logger = logging.getLogger(__name__)

# Utility function aliases for backward compatibility
_bind_scroll = bind_scroll
_detect_material = detect_material
_check_value_range = check_value_range
_get_recommendation = get_recommendation
_get_enum_human_label = get_enum_human_label
_get_recommendation_info = get_recommendation_info


def _find_ancestor(widget: tk.Widget, ancestor_type: type) -> Optional[Any]:
    """Walk up the widget tree to find the nearest ancestor of the given type.

    Fixes audit #37: Extract utility to replace repeated parent-tree-walk pattern.

    Args:
        widget: Starting widget to search from.
        ancestor_type: Class type to search for.

    Returns:
        The first ancestor of the given type, or None if not found.
    """
    parent = getattr(widget, 'master', None)
    while parent:
        if isinstance(parent, ancestor_type):
            return parent
        parent = getattr(parent, 'master', None)
    return None


class ProfileDetailPanel(tk.Frame):
    """Renders a profile's settings using BambuStudio's exact tab/section layout.

    This panel displays and edits profile parameters organized by tabs and sections.
    It supports inheritance resolution, smart recommendations, undo/redo, and inline
    parameter editing with type-aware validation.
    """

    def __init__(self, parent: tk.Widget, theme: Theme, icons: Any = None, icons_sm: Any = None) -> None:
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
            tk.Label(self, text=text, bg=theme.bg2, fg=theme.fg2, font=(UI_FONT, 13)).pack(pady=40)
        else:
            # Empty state with centered message and actions
            container = tk.Frame(self, bg=theme.bg2)
            container.place(relx=0.5, rely=0.4, anchor="center")
            tk.Label(container, text="\u2699", bg=theme.bg2, fg=theme.fg3,
                     font=(UI_FONT, 28)).pack()
            tk.Label(container, text="No profile selected", bg=theme.bg2, fg=theme.fg2,
                     font=(UI_FONT, 14)).pack(pady=(4, 8))
            actions = tk.Frame(container, bg=theme.bg2)
            actions.pack()
            # Bind clicks — find the App instance
            def _find_app(widget: tk.Widget) -> Optional[Any]:
                w = widget
                while w:
                    from . import App
                    if isinstance(w, App):
                        return w
                    w = w.master
                return None
            json_lbl = tk.Label(actions, text="Import JSON", bg=theme.bg2, fg=theme.accent,
                                font=(UI_FONT, 13, "bold"), cursor="hand2")
            json_lbl.pack(side="left", padx=(0, 6))
            json_lbl.bind("<Enter>", lambda e: json_lbl.configure(fg=theme.accent2))
            json_lbl.bind("<Leave>", lambda e: json_lbl.configure(fg=theme.accent))
            json_lbl.bind("<Button-1>", lambda e: (_find_app(self) or e) and _find_app(self)._on_import_json())
            tk.Label(actions, text="|", bg=theme.bg2, fg=theme.fg3,
                     font=(UI_FONT, 13)).pack(side="left", padx=(0, 6))
            mf_lbl = tk.Label(actions, text="Extract from 3MF", bg=theme.bg2, fg=theme.accent,
                              font=(UI_FONT, 13, "bold"), cursor="hand2")
            mf_lbl.pack(side="left", padx=(0, 6))
            mf_lbl.bind("<Enter>", lambda e: mf_lbl.configure(fg=theme.accent2))
            mf_lbl.bind("<Leave>", lambda e: mf_lbl.configure(fg=theme.accent))
            mf_lbl.bind("<Button-1>", lambda e: (_find_app(self) or e) and _find_app(self)._on_extract_3mf())
            tk.Label(actions, text="|", bg=theme.bg2, fg=theme.fg3,
                     font=(UI_FONT, 13)).pack(side="left", padx=(0, 6))
            lp_lbl = tk.Label(actions, text="Load System Presets", bg=theme.bg2, fg=theme.accent,
                              font=(UI_FONT, 13, "bold"), cursor="hand2")
            lp_lbl.pack(side="left")
            lp_lbl.bind("<Enter>", lambda e: lp_lbl.configure(fg=theme.accent2))
            lp_lbl.bind("<Leave>", lambda e: lp_lbl.configure(fg=theme.accent))
            lp_lbl.bind("<Button-1>", lambda e: (_find_app(self) or e) and _find_app(self)._on_load_presets())

    def _on_undo(self, event: Optional[tk.Event] = None) -> str:
        """Undo the last parameter edit."""
        if not self._undo_stack or not self.current_profile:
            return "break"
        key, old_value = self._undo_stack.pop()
        self.current_profile.data[key] = old_value
        if not self._undo_stack and self._pre_edit_modified is not None:
            self.current_profile.modified = self._pre_edit_modified
            self._pre_edit_modified = None
        if self._current_tab:
            self._switch_tab(self._current_tab)
        self._notify_list_refresh()
        return "break"

    def _notify_list_refresh(self) -> None:
        parent = _find_ancestor(self, ProfileListPanel)
        if parent:
            parent._refresh_list()

    # ── SECTION: Header Rendering ──

    def _build_header(self, profile: Profile) -> tk.Frame:
        theme = self.theme

        # ── Header (compact: 3 rows max) ──
        header_frame = tk.Frame(self, bg=theme.bg2)
        header_frame.pack(fill="x", padx=10, pady=(6, 0))

        # Row 1: profile name (left) + Save button (right)
        self._name_row = tk.Frame(header_frame, bg=theme.bg2)
        self._name_row.pack(fill="x")
        name_row = self._name_row

        save_btn = _make_btn(name_row, "Save", self._save_profile,
                             bg=theme.bg4, fg=theme.fg2,
                             font=(UI_FONT, 12), padx=8, pady=2,
                             image=self.icons_sm.save if self.icons_sm else None,
                             compound="left")
        save_btn.pack(side="right", pady=(4, 0))

        # Clear Compare button — resets comparison and lets user pick new profiles
        clear_icon = self.icons_sm.clear if (self.icons_sm and hasattr(self.icons_sm, 'clear')) else None
        clear_btn = _make_btn(name_row, "Clear", self._on_clear_compare,
                              bg=theme.bg4, fg=theme.fg2,
                              font=(UI_FONT, 12), padx=8, pady=2,
                              image=clear_icon, compound="left")
        clear_btn.pack(side="right", pady=(4, 0), padx=(0, 4))

        # Smart Recommendations button
        rec_btn = _make_btn(name_row, "\u2699 Recommendations", self._open_recommendations,
                            bg=theme.bg4, fg=theme.fg2,
                            font=(UI_FONT, 12), padx=8, pady=2)
        rec_btn.pack(side="right", pady=(4, 0), padx=(0, 4))

        ptype_upper = profile.profile_type.upper()
        self._name_label = tk.Label(name_row, text=f"{ptype_upper}  \u2022  {profile.name}",
                 bg=theme.bg2, fg=theme.fg, font=(UI_FONT, 17, "bold"))
        self._name_label.pack(side="left", anchor="w")
        self._name_label.bind("<Double-1>", lambda e: self._start_header_rename())
        _Tooltip(self._name_label, "Double-click to rename")

        # Row 2: status + inheritance + source — one line, plain text
        row2 = tk.Frame(header_frame, bg=theme.bg2)
        row2.pack(fill="x", pady=(2, 0))

        # Status text (colored, no bg box)
        if profile.modified:
            status_text = "Unlocked"
            status_fg = theme.converted
        elif profile.is_locked:
            printers = profile.compatible_printers
            if printers:
                status_text = "Locked"
                status_fg = theme.locked
            else:
                # Locked to a printer profile via printer_settings_id
                psid = profile.data.get("printer_settings_id", "")
                if isinstance(psid, list):
                    psid = psid[0] if psid else ""
                if psid:
                    status_text = f"Locked to {psid}"
                    status_fg = theme.locked
                else:
                    status_text = "Custom"
                    status_fg = theme.accent
        else:
            status_text = "Custom"
            status_fg = theme.accent
        tk.Label(row2, text=status_text, bg=theme.bg2, fg=status_fg,
                 font=(UI_FONT, 13, "bold")).pack(side="left")

        # Separator dot + inheritance + source
        info_parts = []
        if profile.inherits:
            inherit_str = f"inherits from {profile.inherits}"
            if not profile.resolved_data:
                inherit_str += " (not found)"
            info_parts.append(inherit_str)
        info_parts.append(profile.source_label)
        if info_parts:
            tk.Label(row2, text="  \u00b7  " + "  \u00b7  ".join(info_parts),
                     bg=theme.bg2, fg=theme.fg2, font=(UI_FONT, 13)).pack(side="left")

        # History link (only when changelog exists)
        if profile.changelog:
            hist_lbl = tk.Label(row2, text=f"  \u00b7  History ({len(profile.changelog)})",
                                bg=theme.bg2, fg=theme.converted, font=(UI_FONT, 13, "underline"),
                                cursor="hand2")
            hist_lbl.pack(side="left")
            hist_lbl.bind("<Button-1>", lambda e, p=profile: self._show_changelog(p))

        # Material badge + inherited count for legend
        inherited_count = len(self._inherited_keys)

        row3 = tk.Frame(header_frame, bg=theme.bg2)
        row3.pack(fill="x", pady=(1, 0))

        # Material badge (from Smart Recommendations)
        if self._current_material != "General":
            tk.Label(row3, text=f"Material: {self._current_material}",
                     bg=theme.bg2, fg=theme.accent, font=(UI_FONT, 12, "bold")).pack(side="left")

        # Count how many params have recommendations (for legend decision)
        rec_param_count = sum(1 for key in self._display_data
                              if _check_value_range(key, self._display_data[key],
                                                    self._current_material) is not None)

        # Row 4: Icon legend (only when inherited keys or recommendations exist)
        has_inherited = inherited_count > 0
        has_recommendations = rec_param_count > 0
        if has_inherited or has_recommendations:
            legend = tk.Frame(header_frame, bg=theme.bg2)
            legend.pack(fill="x", pady=(2, 0))
            parts = []
            if has_inherited:
                parts.append(("\u21b0", theme.converted, "Inherited"))
            if has_recommendations:
                parts.append(("\u25bc", theme.converted, "Below typical"))
                parts.append(("\u25b2", theme.warning, "Above typical"))
                parts.append(("\u24d8", theme.fg3, "Smart recommendation"))
            for i, (icon, color, desc) in enumerate(parts):
                if i > 0:
                    tk.Label(legend, text="  ", bg=theme.bg2).pack(side="left")
                tk.Label(legend, text=icon, bg=theme.bg2, fg=color,
                         font=(UI_FONT, 12, "bold")).pack(side="left")
                tk.Label(legend, text=f" {desc}", bg=theme.bg2, fg=theme.fg3,
                         font=(UI_FONT, 12)).pack(side="left")

        return header_frame

    def _show_changelog(self, profile: Profile) -> None:
        theme = self.theme
        dlg = tk.Toplevel(self)
        dlg.title(f"Change History — {profile.name}")
        dlg.configure(bg=theme.bg)
        dlg.resizable(True, True)
        dlg.transient(self.winfo_toplevel())

        title_lbl = tk.Label(dlg, text=f"Change history for \"{profile.name}\"",
                             bg=theme.bg, fg=theme.fg,
                             font=(UI_FONT, 14, "bold"))
        title_lbl.pack(padx=16, pady=(12, 8), anchor="w")

        list_frame = tk.Frame(dlg, bg=theme.bg3, highlightbackground=theme.border,
                               highlightthickness=1)
        list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # Use a frame inside a canvas for scrollable content with embedded buttons
        canvas = tk.Canvas(list_frame, bg=theme.bg3, highlightthickness=0)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=theme.bg3)
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _rebuild_entries() -> None:
            for w in content.winfo_children():
                w.destroy()

            for i, entry in enumerate(reversed(profile.changelog)):
                ts, action, details = entry[0], entry[1], entry[2]
                has_snapshot = len(entry) >= 4 and entry[3] is not None
                real_idx = len(profile.changelog) - 1 - i

                if i > 0:
                    tk.Frame(content, bg=theme.border, height=1).pack(
                        fill="x", padx=8, pady=(4, 4))

                row = tk.Frame(content, bg=theme.bg3)
                row.pack(fill="x", padx=10, pady=(6, 2))

                # Timestamp + action on one line
                header = tk.Frame(row, bg=theme.bg3)
                header.pack(fill="x")
                tk.Label(header, text=action, bg=theme.bg3, fg=theme.accent,
                         font=(UI_FONT, 13, "bold"), anchor="w").pack(
                             side="left")
                tk.Label(header, text=f"  {ts}", bg=theme.bg3, fg=theme.fg3,
                         font=(UI_FONT, 12), anchor="w").pack(
                             side="left", pady=(2, 0))

                if details:
                    tk.Label(row, text=details, bg=theme.bg3, fg=theme.fg2,
                             font=(UI_FONT, 12), anchor="w",
                             wraplength=380, justify="left").pack(
                                 anchor="w", pady=(2, 0))

                # Undo button below the entry text, left-aligned
                if has_snapshot and real_idx == len(profile.changelog) - 1:
                    def _undo(idx: int = real_idx) -> None:
                        profile.restore_snapshot(idx)
                        title_lbl.configure(
                            text=f"Change history for \"{profile.name}\"")
                        _rebuild_entries()
                        self._refresh_after_undo(profile)

                    _make_btn(row, "↩ Undo this change", _undo,
                              bg=theme.bg4, fg=theme.warning,
                              font=(UI_FONT, 12), padx=10, pady=4).pack(
                                  anchor="w", pady=(6, 2))

            if not profile.changelog:
                tk.Label(content, text="No changes recorded.",
                         bg=theme.bg3, fg=theme.fg3,
                         font=(UI_FONT, 12)).pack(padx=16, pady=16)

        _rebuild_entries()

        _make_btn(dlg, "Close", dlg.destroy,
                  bg=theme.bg4, fg=theme.fg2,
                  font=(UI_FONT, 12), padx=12, pady=5).pack(pady=(4, 12))

        # Size the window to fit content, with reasonable bounds
        dlg.update_idletasks()
        w = min(max(dlg.winfo_reqwidth(), 360), 520)
        h = min(max(dlg.winfo_reqheight(), 180), 500)
        x = self.winfo_rootx() + 60
        y = self.winfo_rooty() + 60
        dlg.geometry(f"{w}x{h}+{x}+{y}")

    def _refresh_after_undo(self, profile: Profile) -> None:
        # Walk up to find the ProfileListPanel parent
        parent = _find_ancestor(self, ProfileListPanel)
        if parent:
            parent._refresh_list()
        # Re-display the profile
        self.show_profile(profile)

    def _start_header_rename(self) -> None:
        if not self.current_profile:
            return
        theme = self.theme
        profile = self.current_profile
        ptype_upper = profile.profile_type.upper()

        self._name_label.destroy()
        name_row = self._name_row

        name_frame = tk.Frame(name_row, bg=theme.bg2)
        name_frame.pack(side="left", fill="x", expand=True)

        prefix = tk.Label(name_frame, text=f"{ptype_upper}  \u2022  ",
                          bg=theme.bg2, fg=theme.fg, font=(UI_FONT, 17, "bold"))
        prefix.pack(side="left")

        name_var = tk.StringVar(value=profile.name)
        entry = tk.Entry(name_frame, textvariable=name_var, bg=theme.bg3, fg=theme.fg,
                         insertbackground=theme.fg, font=(UI_FONT, 17, "bold"),
                         highlightbackground=theme.accent, highlightthickness=1,
                         relief="flat")
        entry.pack(side="left", fill="x", expand=True)
        entry.focus_set()
        entry.select_range(0, "end")

        def _rebuild_label() -> None:
            name_frame.destroy()
            self._name_label = tk.Label(name_row, text=f"{ptype_upper}  \u2022  {profile.name}",
                     bg=theme.bg2, fg=theme.fg, font=(UI_FONT, 17, "bold"))
            self._name_label.pack(side="left", anchor="w")
            self._name_label.bind("<Double-1>", lambda e: self._start_header_rename())

        def _finish(event: Optional[tk.Event] = None) -> None:
            new_name = Profile.sanitize_name(name_var.get())
            if new_name and new_name != profile.name:
                old_name = profile.name
                snapshot = {"name": old_name, "_modified": profile.modified}
                profile.data["name"] = new_name
                profile.modified = True
                profile.log_change("Renamed", f"{old_name} \u2192 {new_name}",
                                   snapshot=snapshot)
            _rebuild_label()

        def _cancel(event: Optional[tk.Event] = None) -> None:
            _rebuild_label()

        entry.bind("<Return>", _finish)
        entry.bind("<FocusOut>", _finish)
        entry.bind("<Escape>", _cancel)

    def _save_profile(self) -> None:
        if not self.current_profile:
            return
        self._commit_edits()
        profile = self.current_profile
        init_dir = (os.path.dirname(profile.source_path)
                    if profile.source_path and os.path.exists(os.path.dirname(profile.source_path))
                    else os.path.expanduser("~"))
        fp = filedialog.asksaveasfilename(
            title="Save Profile",
            initialdir=init_dir,
            initialfile=profile.suggested_filename(),
            defaultextension=".json",
            filetypes=[("JSON Profile", "*.json"), ("All files", "*.*")],
        )
        if not fp:
            return
        try:
            with open(fp, "w", encoding="utf-8") as f:
                f.write(profile.to_json())
            messagebox.showinfo("Saved", f"Profile saved to:\n{os.path.basename(fp)}")
        except OSError as e:
            messagebox.showerror("Save Failed", str(e))

    # ── SECTION: Tab Management and Content Rendering ──

    def _build_tab_bar(self, layout: dict) -> list:
        theme = self.theme

        # ── Sub-tab bar ──
        tab_bar = tk.Frame(self, bg=theme.bg2)
        tab_bar.pack(fill="x", padx=10, pady=(6, 0))

        tab_names = list(layout.keys())

        for tab_name in tab_names:
            btn = tk.Label(tab_bar, text=tab_name, bg=theme.bg3, fg=theme.fg,
                           font=(UI_FONT, 13), padx=10, pady=4,
                           highlightbackground=theme.border, highlightthickness=1)
            btn.pack(side="left", padx=(0, 2))
            btn.bind("<Button-1>", lambda e, tn=tab_name: self._switch_tab(tn))
            self._tab_buttons.append((tab_name, btn))

        # Separator below tabs
        tk.Frame(self, bg=theme.border, height=1).pack(fill="x", padx=8, pady=(2, 0))

        return tab_names

    def _build_content_area(self) -> None:
        theme = self.theme

        # ── Content area ──
        content_container = tk.Frame(self, bg=theme.param_bg)
        content_container.pack(fill="both", expand=True)

        self._content_canvas = tk.Canvas(content_container, bg=theme.param_bg, highlightthickness=0)
        self._content_sb = ttk.Scrollbar(content_container, orient="vertical",
                                          command=self._content_canvas.yview)
        self._content_frame = tk.Frame(self._content_canvas, bg=theme.param_bg)
        self._content_frame.bind("<Configure>",
                                  lambda e: self._content_canvas.configure(
                                      scrollregion=self._content_canvas.bbox("all")))
        self._canvas_window = self._content_canvas.create_window(
            (0, 0), window=self._content_frame, anchor="nw")
        self._content_canvas.configure(yscrollcommand=self._content_sb.set)
        self._content_canvas.pack(side="left", fill="both", expand=True)
        self._content_sb.pack(side="right", fill="y")

        self._content_canvas.bind("<Configure>",
                                   lambda e: self._content_canvas.itemconfig(
                                       self._canvas_window, width=e.width))
        # Scroll binding — bind to canvas initially (see _switch_tab for recursive bind)
        _bind_scroll(self._content_canvas, self._content_canvas)

    def show_profile(self, profile: Profile) -> None:
        self._commit_edits()
        self.current_profile = profile
        self._edit_vars = {}
        self._undo_stack = []
        self._pre_edit_modified = None
        self._param_order = []
        self._indicator_frames = {}
        self._tab_buttons = []
        self._current_tab = None
        self._scroll_bound = False
        for w in self.winfo_children():
            w.destroy()

        layout = FILAMENT_LAYOUT if profile.profile_type == "filament" else PROCESS_LAYOUT

        if profile.inherits and not profile.resolved_data:
            try:
                app = self.winfo_toplevel()
                if hasattr(app, 'preset_index'):
                    app.preset_index.resolve(profile)
            except Exception as e:
                logger.debug("Failed to resolve inheritance: %s", e)

        self._display_data = profile.resolved_data if profile.resolved_data else profile.data
        self._inherited_keys = profile.inherited_keys if profile.inherited_keys else set()

        self._current_material = _detect_material(self._display_data)
        if profile.profile_type == "process" and self._current_material == "General":
            self._current_material = self._detect_material_from_siblings()

        self._header_frame = self._build_header(profile)

        # Informational note when inherited base profile could not be found
        if profile.inherits and not profile.resolved_data:
            theme = self.theme
            note = tk.Frame(self, bg=theme.bg3)
            note.pack(fill="x", padx=8, pady=(4, 0))
            tk.Label(note,
                     text=f"Inherits from \"{profile.inherits}\" (base profile not found on this system).",
                     bg=theme.bg3, fg=theme.fg2, font=(UI_FONT, 12),
                     padx=10, pady=6, anchor="w").pack(anchor="w")

        tab_names = self._build_tab_bar(layout)
        self._build_content_area()

        if tab_names:
            self._switch_tab(tab_names[0])

    def _switch_tab(self, tab_name: str) -> None:
        """Switch to a different tab and render its content."""
        theme = self.theme
        self._current_tab = tab_name
        self._param_order = []  # Reset navigation order for new tab
        self._indicator_frames = {}  # Reset indicator references for new tab

        for tn, btn in self._tab_buttons:
            if tn == tab_name:
                btn.configure(fg=theme.accent_fg, bg=theme.accent2, font=(UI_FONT, 13, "bold"),
                              highlightbackground=theme.accent2)
            else:
                btn.configure(fg=theme.fg, bg=theme.bg3, font=(UI_FONT, 13),
                              highlightbackground=theme.border)

        for w in self._content_frame.winfo_children():
            w.destroy()

        profile = self.current_profile
        layout = FILAMENT_LAYOUT if profile.profile_type == "filament" else PROCESS_LAYOUT
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
                    for k, _ in ps:
                        known.add(k)
            known.update(_IDENTITY_KEYS)
            extra = {k: v for k, v in display_data.items() if k not in known}
            if extra:
                has_content = True
                # Humanize raw JSON keys: "adaptive_layer_height" → "Adaptive layer height"
                humanized = [(k, k.replace("_", " ").capitalize()) for k in sorted(extra)]
                self._render_section(
                    "Unrecognized parameters",
                    humanized,
                    display_data,
                    discovered=True
                )

        if not has_content:
            if sections and profile.inherits and not profile.resolved_data:
                # Inherited base profile not loaded — no customized keys in this tab
                tk.Label(self._content_frame,
                         text="No customized settings in this tab.",
                         bg=theme.param_bg, fg=theme.fg2, font=(UI_FONT, 13)).pack(pady=20)
            elif sections:
                tk.Label(self._content_frame,
                         text="(No parameters set in this tab)",
                         bg=theme.param_bg, fg=theme.fg2, font=(UI_FONT, 13)).pack(pady=20)
            else:
                tk.Label(self._content_frame, text="(No settings in this tab)",
                         bg=theme.param_bg, fg=theme.fg2, font=(UI_FONT, 13)).pack(pady=20)

        # Only bind scroll once per render
        if not self._scroll_bound:
            self._bind_scroll_recursive(self._content_frame)
            self._scroll_bound = True

    def _bind_scroll_recursive(self, widget: tk.Widget) -> None:
        _bind_scroll(widget, self._content_canvas)
        for child in widget.winfo_children():
            self._bind_scroll_recursive(child)

    # ── SECTION: Parameter Rendering ──

    def _render_section(self, section_name: str, params: list, data: dict, discovered: bool = False) -> bool:
        theme = self.theme

        visible = [(k, l) for k, l in params if k in data]
        if not visible:
            return False

        section_header = tk.Frame(self._content_frame, bg=theme.param_bg)
        section_header.pack(fill="x", padx=10, pady=(10, 3))
        accent_bar = tk.Frame(section_header, bg=theme.warning if discovered else theme.accent, width=3)
        accent_bar.pack(side="left", fill="y", padx=(0, 8))
        fg = theme.warning if discovered else theme.btn_fg
        tk.Label(section_header, text=section_name, bg=theme.param_bg, fg=fg,
                 font=(UI_FONT, 15, "bold")).pack(side="left")

        for json_key, ui_label in visible:
            value = data[json_key]
            self._render_param(ui_label, json_key, value, discovered=discovered)

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

    def _render_param(self, label: str, key: str, value: Any, discovered: bool = False) -> None:
        theme = self.theme
        is_inherited = key in self._inherited_keys

        row = tk.Frame(self._content_frame, bg=theme.param_bg)
        row.pack(fill="x", padx=14, pady=2)
        row.columnconfigure(0, minsize=_LABEL_COL_WIDTH)
        row.columnconfigure(1, weight=1)
        row.columnconfigure(2, minsize=24)
        row.columnconfigure(3, minsize=20)

        label_fg = theme.fg2 if is_inherited else theme.fg
        label_font = (UI_FONT, 13) if is_inherited else (UI_FONT, 13, "bold")
        label_frame = tk.Frame(row, bg=theme.param_bg)
        label_frame.grid(row=0, column=0, sticky="w", padx=(0, 12))
        if is_inherited:
            inherit_icon = tk.Label(label_frame, text="\u21b0", bg=theme.param_bg,
                                    fg=theme.converted, font=(UI_FONT, 12))
            inherit_icon.pack(side="left", padx=(0, 3))
            _Tooltip(inherit_icon,
                     f"Inherited from base profile. Click the value to customize it.")
        lbl = tk.Label(label_frame, text=label, bg=theme.param_bg, fg=label_fg, font=label_font,
                       anchor="w", width=0)
        lbl.pack(side="left")
        if discovered:
            _Tooltip(lbl, f"JSON key: {key}")

        display = self._format_value(value, key=key)
        if display == "nil":
            display = "0"

        raw_str = self._get_raw_enum_str(value)
        is_enum = key in ENUM_VALUES and raw_str is not None

        if key.endswith("_gcode") or key == "post_process" or key == "filament_notes":
            mono = ("Menlo", 13) if platform.system() == "Darwin" else ("Consolas", 13)
            txt = tk.Text(row, bg=theme.bg3, fg=theme.fg, font=mono,
                          height=min(8, max(2, str(value).count("\n") + 1)), width=40,
                          highlightbackground=theme.border, highlightthickness=1, wrap="word")
            txt.insert("1.0", str(value) if value else "")
            txt.grid(row=0, column=1, sticky="ew", padx=(4, 0))
            self._edit_vars[key] = (txt, value, "text")
        elif is_enum:
            self._render_enum_dropdown(row, key, value, raw_str, is_inherited)
        else:
            val_fg = theme.fg2 if is_inherited else theme.fg
            val_frame = tk.Frame(row, bg=theme.edit_bg, highlightbackground=theme.border,
                                 highlightthickness=1, padx=4, pady=1)
            val_frame.grid(row=0, column=1, sticky="ew", padx=(4, 0))
            val_lbl = tk.Label(val_frame, text=display, bg=theme.edit_bg, fg=val_fg,
                               font=(UI_FONT, 13), anchor="w", cursor="xterm")
            val_lbl.pack(fill="x")
            val_lbl.bind("<Button-1>",
                         lambda e, r=val_frame, l=val_lbl, k=key, v=value, fg=val_fg:
                             self._activate_edit(r, l, k, v, fg))
            val_frame.bind("<Button-1>",
                           lambda e, r=val_frame, l=val_lbl, k=key, v=value, fg=val_fg:
                               self._activate_edit(r, l, k, v, fg))
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
            info_icon = tk.Label(info_frame, text="\u24d8", bg=theme.param_bg,
                                 fg=theme.fg3, font=(UI_FONT, 12), cursor="hand2")
            info_icon.pack()
            info_icon.bind("<Enter>", lambda e, w=info_icon: w.configure(fg=theme.accent))
            info_icon.bind("<Leave>", lambda e, w=info_icon: w.configure(fg=theme.fg3))
            _InfoPopup(info_icon, key, self._current_material)

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
        range_status = _check_value_range(key, value, material)
        if range_status == "low":
            ind = tk.Label(frame, text="\u25bc", bg=theme.param_bg,
                           fg=theme.converted, font=(UI_FONT, 12, "bold"))
            ind.pack()
            rec = _get_recommendation(key, material)
            tip = f"Below recommended range"
            if rec:
                tip += f" ({rec.get('min', '?')} – {rec.get('max', '?')})"
            _Tooltip(ind, tip)
            _bind_scroll(ind, self._content_canvas)
        elif range_status == "high":
            ind = tk.Label(frame, text="\u25b2", bg=theme.param_bg,
                           fg=theme.warning, font=(UI_FONT, 12, "bold"))
            ind.pack()
            rec = _get_recommendation(key, material)
            tip = f"Above recommended range"
            if rec:
                tip += f" ({rec.get('min', '?')} – {rec.get('max', '?')})"
            _Tooltip(ind, tip)
            _bind_scroll(ind, self._content_canvas)

    def _render_enum_dropdown(self, row: tk.Frame, key: str, original_value: Any,
                              raw_str: str, is_inherited: bool) -> None:
        theme = self.theme
        known_pairs = ENUM_VALUES[key]

        # Build human labels list; ensure current value is included
        human_labels = [hl for _, hl in known_pairs]
        known_json_vals = {jv for jv, _ in known_pairs}

        current_label = _get_enum_human_label(key, raw_str)
        extra_label_to_json = {}
        if raw_str not in known_json_vals:
            # Unknown value — append humanized label; remember the reverse mapping
            human_labels.append(current_label)
            extra_label_to_json[current_label] = raw_str

        value_var = tk.StringVar(value=current_label)
        # Fit dropdown width to longest option text
        max_len = max((len(hl) for hl in human_labels), default=10)
        cb_width = max(max_len + 2, 12)
        combobox = ttk.Combobox(row, textvariable=value_var, values=human_labels,
                          state="readonly", style="Param.TCombobox",
                          font=(UI_FONT, 13), width=cb_width)
        combobox.grid(row=0, column=1, sticky="w", padx=(4, 0))

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
                self._undo_stack.append((key, original_value))
                self.current_profile.data[key] = new_val
                self.current_profile.modified = True
                self.current_profile.log_change("Parameter edited",
                                                f"{key}: {original_value} → {new_val}")
                self._edit_vars[key] = (value_var, new_val, "combo")
                self._update_indicator(key, new_val)

        combobox.bind("<<ComboboxSelected>>", _on_enum_change)
        self._edit_vars[key] = (value_var, original_value, "combo")

    # ── SECTION: Edit Tracking and Commit Logic ──

    def _activate_edit(self, container: tk.Frame, label_widget: tk.Label, key: str,
                       original_value: Any, fg_color: str) -> None:
        theme = self.theme
        label_widget.destroy()
        container.configure(highlightbackground=theme.accent)

        display = self._format_value(original_value, key=key)
        value_var = tk.StringVar(value=display)
        entry = tk.Entry(container, textvariable=value_var, bg=theme.edit_bg, fg=fg_color,
                         font=(UI_FONT, 13), insertbackground=theme.fg,
                         highlightthickness=0, relief="flat")
        entry.pack(fill="x")
        entry.focus_set()
        entry.select_range(0, "end")

        self._edit_vars[key] = (value_var, original_value, "entry")

        def finish_edit(event: Optional[tk.Event] = None) -> None:
            raw_text = value_var.get().strip()
            self._commit_single(key)
            new_val = self.current_profile.data.get(key, original_value)
            new_display = self._format_value(new_val, key=key)
            input_rejected = (new_val == original_value and raw_text != self._format_value(original_value, key=key))
            entry.destroy()
            if input_rejected:
                container.configure(highlightbackground=theme.error)
                container.after(800, lambda: container.configure(highlightbackground=theme.border))
            else:
                container.configure(highlightbackground=theme.border)
            new_lbl = tk.Label(container, text=new_display, bg=theme.edit_bg, fg=fg_color,
                               font=(UI_FONT, 13), anchor="w", cursor="xterm")
            new_lbl.pack(fill="x")
            new_lbl.bind("<Button-1>",
                         lambda e, r=container, l=new_lbl, k=key, v=new_val, f=fg_color:
                             self._activate_edit(r, l, k, v, f))
            container.bind("<Button-1>",
                           lambda e, r=container, l=new_lbl, k=key, v=new_val, f=fg_color:
                               self._activate_edit(r, l, k, v, f))
            self._edit_vars[key] = (None, new_val, "label")
            self._update_indicator(key, new_val)

        def tab_next(event: Optional[tk.Event] = None) -> str:
            finish_edit()
            idx = next((i for i, (k, *_) in enumerate(self._param_order) if k == key), -1)
            if idx >= 0 and idx + 1 < len(self._param_order):
                next_key, next_container, next_fg = self._param_order[idx + 1]
                next_val = self.current_profile.data.get(next_key)
                if next_val is not None:
                    children = next_container.winfo_children()
                    if children:
                        self._activate_edit(next_container, children[0],
                                            next_key, next_val, next_fg)
            return "break"

        entry.bind("<Return>", finish_edit)
        entry.bind("<Tab>", tab_next)
        entry.bind("<FocusOut>", finish_edit)
        entry.bind("<Escape>", lambda e: finish_edit())

    def _commit_single(self, key: str) -> None:
        if not self.current_profile or key not in self._edit_vars:
            return
        var_or_widget, original, kind = self._edit_vars[key]
        if kind == "entry":
            new_str = var_or_widget.get()
        elif kind == "text":
            new_str = var_or_widget.get("1.0", "end-1c")
        elif kind == "combo":
            # Combo edits are committed immediately in _on_enum_change;
            # nothing to do here — the profile.data is already up to date.
            return
        else:
            return  # "label" kind — not actively editing

        new_val = self._parse_edit(new_str, original)
        if new_val != original:
            if self._pre_edit_modified is None:
                self._pre_edit_modified = self.current_profile.modified
            self._undo_stack.append((key, original))
            self.current_profile.data[key] = new_val
            self.current_profile.modified = True
            self._edit_vars[key] = (var_or_widget, new_val, kind)
            self.current_profile.log_change("Parameter edited",
                                            f"{key}: {original} \u2192 {new_val}")

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
        # IMPORTANT: bool check must come BEFORE int — bool is a subclass of int in Python.
        if isinstance(original, bool):
            return text.lower() in ("yes", "true", "1")
        if isinstance(original, int):
            try:
                return int(text)
            except ValueError:
                try:
                    return int(float(text))
                except ValueError:
                    logger.debug("Edit parse failed for key, reverting to original: text=%r, original=%r", text, original)
                    return original
        if isinstance(original, float):
            try:
                return float(text)
            except ValueError:
                logger.debug("Edit parse failed for key, reverting to original: text=%r, original=%r", text, original)
                return original
        if isinstance(original, list):
            # If user entered a single value, wrap in list matching original length
            parts = [s.strip() for s in text.split(",")]
            result = []
            for i, part in enumerate(parts):
                type_reference = original[i] if i < len(original) else original[0] if original else ""
                if isinstance(type_reference, int):
                    try:
                        result.append(int(part))
                    except ValueError:
                        result.append(type_reference)
                elif isinstance(type_reference, float):
                    try:
                        result.append(float(part))
                    except ValueError:
                        result.append(type_reference)
                else:
                    result.append(part)
            # Pad shorter input to original length using last entered value.
            # Guard: if all parts failed to parse, result may be empty — don't crash.
            if result and len(result) < len(original):
                result.extend([result[-1]] * (len(original) - len(result)))
            return result
        return text

    @staticmethod
    def _format_value(value: Any, key: Optional[str] = None) -> str:
        """Format a value for display."""
        if isinstance(value, list):
            # BambuStudio stores per-extruder values as arrays where all elements
            # are identical (e.g., [210, 210, 210] for nozzle temp across 3 extruders).
            # Collapse to a single display value when all entries match.
            if len(set(str(v) for v in value)) == 1:
                raw = str(value[0])
                if key and key in ENUM_VALUES:
                    return _get_enum_human_label(key, raw)
                return raw
            return ", ".join(str(v) for v in value)
        elif isinstance(value, bool):
            return "Yes" if value else "No"
        elif value is None:
            return "N/A"
        value_str = str(value)
        if key and key in ENUM_VALUES:
            return _get_enum_human_label(key, value_str)
        return value_str[:_VALUE_TRUNCATE_LONG] + "..." if len(value_str) > _VALUE_TRUNCATE_LONG else value_str

    # ── SECTION: Clear Compare ──

    def _on_clear_compare(self) -> None:
        """Clear current comparison and show waiting state."""
        try:
            parent = _find_ancestor(self, ProfileListPanel)
            if parent and parent.app:
                parent.app._close_compare()
        except Exception:
            logger.exception("Error in _on_clear_compare")

    # ── SECTION: Smart Recommendations Integration ──

    def _open_recommendations(self) -> None:
        if not self.current_profile:
            return
        # Gather all loaded profiles of the same type for statistical comparison
        all_profiles = []
        try:
            parent = _find_ancestor(self, ProfileListPanel)
            if parent:
                all_profiles = parent.profiles
        except Exception:
            pass
        from .dialogs import RecommendationsDialog
        RecommendationsDialog(self, self.theme, self.current_profile, all_profiles)

    def _detect_material_from_siblings(self) -> str:
        try:
            parent = _find_ancestor(self, ProfileListPanel)
            if parent:
                # Look at the app's filament tab for loaded filament profiles
                app = parent.app
                if hasattr(app, 'filament_panel') and app.filament_panel.profiles:
                    # Use the first filament profile's material
                    for fp in app.filament_panel.profiles:
                        mat = _detect_material(fp.data)
                        if mat != "General":
                            return mat
        except Exception as e:
            logger.debug("Failed to detect material from siblings: %s", e)
        return "General"


class ProfileListPanel(tk.Frame):
    """Left panel with a list of profiles and a detail viewer on the right."""

    def __init__(self, parent: tk.Widget, theme: Theme, profile_type: str, app: Any) -> None:
        super().__init__(parent, bg=theme.bg)
        self.theme = theme
        self.profile_type = profile_type  # "process" or "filament"
        self.app = app
        self.profiles = []

        self._build()

    def _build(self) -> None:
        theme = self.theme

        paned = tk.PanedWindow(self, orient="horizontal", bg=theme.border,
                                sashwidth=8, sashrelief="flat",
                                opaqueresize=True)
        paned.pack(fill="both", expand=True)

        left = tk.Frame(paned, bg=theme.bg2)
        paned.add(left, minsize=320, width=480, stretch="never")

        self._build_filter(left)
        self._build_tree(left)
        self._build_actions(left)

        # ── Right: detail panel ──
        self.detail = ProfileDetailPanel(paned, theme,
                                         icons=self.app.icons if self.app else None,
                                         icons_sm=self.app.icons_sm if self.app else None)
        paned.add(self.detail, minsize=300, stretch="always")

        # Register filter trace now that tree exists
        self._filter_var.trace_add("write", lambda *a: self._refresh_list())

        # Overlay state
        self._overlay = None

    # ── SECTION: Filter UI ──

    def _build_filter(self, parent: tk.Widget) -> None:
        theme = self.theme

        # ── Filter row ──
        filter_frame = tk.Frame(parent, bg=theme.bg3, highlightbackground=theme.border, highlightthickness=1)
        filter_frame.pack(fill="x", padx=6, pady=(0, 4))
        _search_icon = self.app.icons_sm.search if (self.app and self.app.icons_sm) else None
        if _search_icon:
            tk.Label(filter_frame, image=_search_icon, bg=theme.bg3,
                     padx=6).pack(side="left")
        else:
            tk.Label(filter_frame, text="\u2315", bg=theme.bg3, fg=theme.fg3, font=(UI_FONT, 14),
                     padx=6).pack(side="left")
        self._filter_var = tk.StringVar()
        self._filter = tk.Entry(filter_frame, textvariable=self._filter_var, bg=theme.bg3, fg=theme.fg,
                                insertbackground=theme.fg, highlightthickness=0,
                                font=(UI_FONT, 13), relief="flat", bd=0)
        self._filter.pack(side="left", fill="x", expand=True, ipady=4)
        self._filter.insert(0, "Filter...")
        self._filter.configure(fg=theme.placeholder_fg, font=(UI_FONT, 13, "italic"))
        self._filter.bind("<FocusIn>", self._filter_in)
        self._filter.bind("<FocusOut>", self._filter_out)
        self._placeholder = True

        # ── Filter-by column dropdown ──
        filter_options = {
            "All columns": "none",
            "Printer": "printer",
            "Manufacturer": "manufacturer",
            "Material": "material",
            "Nozzle size": "nozzle",
            "Status": "status",
        }
        self._filter_labels = list(filter_options.keys())
        self._filter_values = list(filter_options.values())
        self._filter_col_var = tk.StringVar(value=self._filter_labels[0])
        self._filter_by = "none"

        filter_dd_frame = tk.Frame(parent, bg=theme.bg2)
        filter_dd_frame.pack(fill="x", padx=6, pady=(0, 4))
        tk.Label(filter_dd_frame, text="Filter:", bg=theme.bg2, fg=theme.fg3,
                 font=(UI_FONT, 13)).pack(side="left", padx=(2, 6))
        filter_cb = ttk.Combobox(filter_dd_frame, textvariable=self._filter_col_var,
                                 values=self._filter_labels,
                                 state="readonly", style="Param.TCombobox",
                                 font=(UI_FONT, 13), width=16)
        filter_cb.pack(side="left")
        filter_cb.bind("<<ComboboxSelected>>", self._on_filter_change)

    def _filter_in(self, event: tk.Event) -> None:
        if self._placeholder:
            self._filter.delete(0, "end")
            self._filter.configure(fg=self.theme.fg, font=(UI_FONT, 13))
            self._placeholder = False

    def _filter_out(self, event: tk.Event) -> None:
        if not self._filter_var.get():
            # Set placeholder flag BEFORE inserting text so the trace-triggered
            # _refresh_list sees _placeholder=True and ignores the placeholder string
            self._placeholder = True
            self._filter.insert(0, "Filter...")
            self._filter.configure(fg=self.theme.placeholder_fg, font=(UI_FONT, 13, "italic"))

    def _on_filter_change(self, event: Optional[tk.Event] = None) -> None:
        try:
            idx = self._filter_labels.index(self._filter_col_var.get())
        except ValueError:
            idx = 0  # Fall back to "All columns"
        self._filter_by = self._filter_values[idx]
        self._refresh_list()

    # ── SECTION: Treeview Rendering and Sorting ──

    def _build_tree(self, parent: tk.Widget) -> None:
        theme = self.theme
        self._rename_active = False  # Guard against overlapping rename operations

        # ── Treeview (must exist before trace) ──
        tree_frame = tk.Frame(parent, bg=theme.bg2)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self._tree_frame = tree_frame  # Keep reference for overlay

        self.tree = ttk.Treeview(tree_frame,
                                  columns=("name", "printer", "material", "manufacturer",
                                           "nozzle", "status", "origin", "location"),
                                  show="headings", selectmode="extended")
        self._sort_col = None   # Currently sorted column (None = insertion order)
        self._sort_asc = True   # Sort direction

        col_defs = [
            ("name",         "Profile Name",  200, 100, True),
            ("printer",      "Printer",       110,  60, True),
            ("material",     "Material",       80,  50, True),
            ("manufacturer", "Manufacturer",   90,  50, True),
            ("nozzle",       "Nozzle",         55,  40, False),
            ("status",       "Status",         90,  60, False),
            ("origin",       "Origin",         80,  50, True),
            ("location",     "Location",      110,  60, True),
        ]
        for col_id, col_text, width, minw, stretch in col_defs:
            self.tree.heading(col_id, text=col_text,
                              command=lambda c=col_id: self._on_heading_click(c))
            self.tree.column(col_id, width=width, minwidth=minw, stretch=stretch)
        # Tag styles for alternating rows and colored status
        self.tree.tag_configure("row_even", background=theme.bg2)
        self.tree.tag_configure("row_odd", background=theme.bg3)
        self.tree.tag_configure("status_universal", foreground=theme.accent)
        self.tree.tag_configure("status_locked", foreground=theme.locked)
        self.tree.tag_configure("status_converted", foreground=theme.converted)

        tree_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click_rename)

        self._setup_tree_tooltip()

        if _PLATFORM == "Darwin":
            self.tree.bind("<Button-2>", self._on_context_menu)
            self.tree.bind("<Control-Button-1>", self._on_context_menu)
        else:
            self.tree.bind("<Button-3>", self._on_context_menu)

    def _setup_tree_tooltip(self) -> None:
        self._tree_tip = None
        self._tree_tip_after = None
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", self._on_tree_leave)

    def _on_heading_click(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        col_labels = {"name": "Profile Name", "printer": "Printer",
                      "material": "Material", "manufacturer": "Manufacturer",
                      "nozzle": "Nozzle", "status": "Status",
                      "origin": "Origin", "location": "Location"}
        for c, label in col_labels.items():
            arrow = ""
            if c == col:
                arrow = " \u25b4" if self._sort_asc else " \u25be"
            self.tree.heading(c, text=label + arrow)

        self._refresh_list()

    def _sort_key_for_profile(self, profile: Profile) -> str:
        col = self._sort_col
        if col == "name":
            return profile.name.lower()
        elif col == "printer":
            return (profile.printer_group or "").lower()
        elif col == "material":
            return (profile.material_group or "").lower()
        elif col == "manufacturer":
            return (profile.manufacturer_group or "").lower()
        elif col == "nozzle":
            return (profile.nozzle_group or "").lower()
        elif col == "status":
            text, _ = self._profile_status(profile)
            return text.lower()
        elif col == "origin":
            return (profile.origin or "").lower()
        elif col == "location":
            return self._short_location(profile.source_path).lower()
        return ""

    @staticmethod
    def _profile_status(p: Profile) -> tuple:
        if p.modified:
            return ("Unlocked", "status_converted")
        elif p.is_locked:
            if p.compatible_printers:
                return ("Locked", "status_locked")
            else:
                return ("Locked to profile", "status_locked")
        else:
            return ("Custom", "status_universal")

    @staticmethod
    def _short_location(source_path: Optional[str]) -> str:
        if not source_path:
            return "\u2014"
        folder = os.path.dirname(source_path)
        if not folder:
            return "\u2014"
        home = os.path.expanduser("~")
        if folder.startswith(home):
            folder = "~" + folder[len(home):]
        parts = folder.replace("\\", "/").split("/")
        if len(parts) > 2:
            return "\u2026/" + "/".join(parts[-2:])
        return folder

    def _insert_profile_row(self, profile_idx: int, profile: Profile, row_idx: int) -> None:
        status, status_tag = self._profile_status(profile)
        alt_tag = "row_even" if row_idx % 2 == 0 else "row_odd"
        location = self._short_location(profile.source_path)
        self.tree.insert("", "end", iid=str(profile_idx),
                         values=(profile.name,
                                 profile.printer_group or "\u2014",
                                 profile.material_group or "\u2014",
                                 profile.manufacturer_group or "\u2014",
                                 profile.nozzle_group or "\u2014",
                                 status,
                                 profile.origin or "\u2014",
                                 location),
                         tags=(alt_tag, status_tag))

    def _refresh_list(self) -> None:
        """Refresh the treeview with filtered and sorted profiles.

        Preserves selection across rebuilds when possible. If previously
        selected item IDs are still present after filtering, they are
        re-selected. Otherwise falls back to selecting the first item.

        Note: O(n) rebuild. Could use virtual treeview for large profile sets.
        """
        saved_widths = {}
        for col_id in self.tree["columns"]:
            saved_widths[col_id] = self.tree.column(col_id, "width")

        # Save current selection before clearing tree
        prev_selection = set(self.tree.selection())

        self.tree.delete(*self.tree.get_children())
        filter_text = "" if self._placeholder else self._filter_var.get().lower()

        visible = []
        filter_col = self._filter_by
        for i, profile in enumerate(self.profiles):
            if filter_text:
                status_text, _ = self._profile_status(profile)
                if filter_col == "none":
                    searchable = (f"{profile.name} {profile.origin} {profile.source_label} "
                                  f"{status_text} {profile.material_group} "
                                  f"{profile.printer_group} {profile.manufacturer_group} "
                                  f"{profile.nozzle_group}").lower()
                elif filter_col == "printer":
                    searchable = (profile.printer_group or "").lower()
                elif filter_col == "manufacturer":
                    searchable = (profile.manufacturer_group or "").lower()
                elif filter_col == "material":
                    searchable = (profile.material_group or "").lower()
                elif filter_col == "nozzle":
                    searchable = (profile.nozzle_group or "").lower()
                elif filter_col == "status":
                    searchable = status_text.lower()
                else:
                    searchable = profile.name.lower()
                if filter_text not in searchable:
                    continue
            visible.append((i, profile))

        if self._sort_col:
            visible.sort(key=lambda item: self._sort_key_for_profile(item[1]),
                         reverse=not self._sort_asc)

        row_idx = 0
        for i, profile in visible:
            self._insert_profile_row(i, profile, row_idx)
            row_idx += 1

        for col_id, w in saved_widths.items():
            if w > 0:
                self.tree.column(col_id, width=w)

        children = self.tree.get_children()
        if children:
            # Restore previous selection if items still exist
            restore = [iid for iid in prev_selection if iid in set(children)]
            if restore:
                self.tree.selection_set(restore)
            else:
                self.tree.selection_set(children[0])
        # Always notify — selection may have shrunk to 0 (empty tree) or changed count
        self._on_select()

    def _on_select(self, event: Optional[tk.Event] = None) -> None:
        sel = self.tree.selection()

        if len(sel) == 1:
            idx = int(sel[0])
            if idx < len(self.profiles):
                self.detail.show_profile(self.profiles[idx])
        elif len(sel) > 1:
            self.detail._show_placeholder(
                f"{len(sel)} profiles selected.\n\nUse 'Unlock Selected' to modify\nor select exactly 2 for 'Compare'.")
        else:
            self.detail._show_placeholder()

        # Notify app about selection change (for Compare Filament auto-launch)
        if self.app and self.profile_type == "filament":
            if hasattr(self.app, '_on_filament_selection_changed'):
                self.app._on_filament_selection_changed()

    # ── SECTION: Overlay Status UI ──

    def _show_overlay(self, text: str, show_spinner: bool = False,
                       show_progress: bool = False) -> None:
        self._hide_overlay()
        theme = self.theme
        overlay = tk.Frame(self._tree_frame, bg=theme.bg2)
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        inner = tk.Frame(overlay, bg=theme.bg2)
        inner.place(relx=0.5, rely=0.4, anchor="center")
        if show_spinner:
            _hg_icon = self.app.icons.hourglass if (self.app and self.app.icons) else None
            if _hg_icon:
                self._spinner_label = tk.Label(inner, image=_hg_icon, bg=theme.bg2)
            else:
                self._spinner_label = tk.Label(inner, text="\u23F3", bg=theme.bg2,
                                               fg=theme.fg3, font=(UI_FONT, 28))
            self._spinner_label.pack()
            self._spinner_chars = ["\u23F3", "\u2699", "\u25E6", "\u2022"]
            self._spinner_idx = 0
            self._spinner_animate()
        self._overlay_text = tk.Label(inner, text=text, bg=theme.bg2, fg=theme.fg2,
                                      font=(UI_FONT, 14), wraplength=350, justify="center")
        self._overlay_text.pack(pady=(4, 0))

        # Determinate progress bar
        self._progress_canvas = None
        if show_progress:
            bar_frame = tk.Frame(inner, bg=theme.bg2)
            bar_frame.pack(pady=(10, 0))
            bar_w, bar_h = 280, 10
            canvas = tk.Canvas(bar_frame, width=bar_w, height=bar_h,
                               bg=theme.bg4, highlightthickness=0, bd=0)
            canvas.pack()
            canvas.create_rectangle(0, 0, 0, bar_h, fill=theme.accent, outline="",
                                    tags="fill")
            self._progress_canvas = canvas
            self._progress_bar_w = bar_w
            self._progress_bar_h = bar_h

        self._overlay = overlay

    def _update_overlay_text(self, text: str) -> None:
        if self._overlay and hasattr(self, '_overlay_text'):
            try:
                self._overlay_text.configure(text=text)
            except tk.TclError:
                pass

    def _update_overlay_progress(self, current: int, total: int) -> None:
        """Update the determinate progress bar fill."""
        canvas = getattr(self, '_progress_canvas', None)
        if not canvas or not self._overlay:
            return
        try:
            frac = current / max(total, 1)
            fill_w = int(self._progress_bar_w * frac)
            canvas.coords("fill", 0, 0, fill_w, self._progress_bar_h)
        except tk.TclError:
            pass

    def _spinner_animate(self) -> None:
        if not self._overlay or not hasattr(self, '_spinner_label'):
            return
        try:
            self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_chars)
            self._spinner_label.configure(text=self._spinner_chars[self._spinner_idx])
            self._overlay.after(400, self._spinner_animate)
        except tk.TclError:
            pass

    def _hide_overlay(self) -> None:
        if self._overlay:
            try:
                self._overlay.destroy()
            except tk.TclError:
                pass
            self._overlay = None
            self._progress_canvas = None

    # ── SECTION: Tooltip Support ──

    def _on_tree_motion(self, event: tk.Event) -> None:
        item = self.tree.identify_row(event.y)
        if self._tree_tip_after:
            self.tree.after_cancel(self._tree_tip_after)
            self._tree_tip_after = None
        if self._tree_tip:
            self._tree_tip.destroy()
            self._tree_tip = None
        if not item:
            return
        idx = int(item)
        if idx >= len(self.profiles):
            return
        profile = self.profiles[idx]
        tip_text = profile.name
        def _show() -> None:
            # Don't show tooltips when app isn't focused — avoids
            # stealing focus from other applications on macOS.
            try:
                if not self.tree.winfo_toplevel().focus_displayof():
                    return
            except (tk.TclError, AttributeError):
                pass
            if self._tree_tip:
                self._tree_tip.destroy()
            x = self.tree.winfo_rootx() + event.x + 16
            y = self.tree.winfo_rooty() + event.y + 20
            tooltip_window = tk.Toplevel(self.tree)
            tooltip_window.wm_overrideredirect(True)
            tooltip_window.wm_geometry(f"+{x}+{y}")
            tk.Label(tooltip_window, text=f"{tip_text}\n(double-click to rename)",
                     bg=self.theme.bg4, fg=self.theme.fg, font=(UI_FONT, 12),
                     padx=8, pady=4, relief="solid", bd=1, justify="left").pack()
            self._tree_tip = tooltip_window
        self._tree_tip_after = self.tree.after(_TREE_TOOLTIP_DELAY_MS, _show)

    def _on_tree_leave(self, event: tk.Event) -> None:
        """Handle tree leave event.

        Args:
            event: Tkinter event.
        """
        if self._tree_tip_after:
            self.tree.after_cancel(self._tree_tip_after)
            self._tree_tip_after = None
        if self._tree_tip:
            self._tree_tip.destroy()
            self._tree_tip = None

    # ── SECTION: Actions and Context Menu ──

    def _build_actions(self, parent: tk.Widget) -> None:
        """Build action button rows below the treeview.

        Args:
            parent: Parent container frame.
        """
        theme = self.theme

        # ── Action rows below treeview ──
        # Row 1: list management (left) + utility (right)
        action_row1 = tk.Frame(parent, bg=theme.bg2)
        action_row1.pack(fill="x", padx=6, pady=(0, 2))
        _make_btn(action_row1, "Clear List",
                  lambda: self.app._on_clear_list(),
                  bg=theme.bg4, fg=theme.warning,
                  font=(UI_FONT, 12), padx=8, pady=3).pack(side="left", padx=(0, 4))
        _make_btn(action_row1, "Remove Selected",
                  lambda: self.app._on_remove(),
                  bg=theme.bg4, fg=theme.fg2,
                  font=(UI_FONT, 12), padx=8, pady=3).pack(side="left", padx=(0, 4))
        _make_btn(action_row1, "Show Folder",
                  lambda: self.app._on_show_folder(),
                  bg=theme.bg4, fg=theme.btn_fg,
                  font=(UI_FONT, 12), padx=8, pady=3).pack(side="right", padx=(0, 4))
        _make_btn(action_row1, "Batch Rename",
                  lambda: self._on_batch_rename(),
                  bg=theme.bg4, fg=theme.btn_fg,
                  font=(UI_FONT, 12), padx=8, pady=3).pack(side="right", padx=(0, 4))

        # Thin separator between secondary and primary actions
        tk.Frame(parent, bg=theme.border, height=1).pack(fill="x", padx=6, pady=(2, 2))

        # Row 2: primary unlock action
        action_row2 = tk.Frame(parent, bg=theme.bg2)
        action_row2.pack(fill="x", padx=6, pady=(0, 4))
        _make_btn(action_row2, "Unlock Selected",
                  lambda: self.app._on_unlock(),
                  bg=theme.accent2, fg=theme.accent_fg,
                  font=(UI_FONT, 12, "bold"),
                  padx=8, pady=4).pack(side="right", padx=(0, 4))

    def _on_context_menu(self, event: tk.Event) -> None:
        theme = self.theme
        # Select the item under cursor if not already selected
        item = self.tree.identify_row(event.y)
        if item:
            current = self.tree.selection()
            if item not in current:
                self.tree.selection_set(item)
                self._on_select()

        sel = self.tree.selection()
        if not sel:
            return

        menu = tk.Menu(self, tearoff=0, bg=theme.bg3, fg=theme.fg,
                       activebackground=theme.accent2, activeforeground=theme.accent_fg,
                       font=(UI_FONT, 12))

        count = len(sel)
        sel_profiles = self.get_selected_profiles()

        # ── Primary actions ──
        menu.add_command(label=f"Unlock {count} profile{'s' if count > 1 else ''}...",
                         command=self.app._on_unlock)
        menu.add_command(label=f"Export {count} profile{'s' if count > 1 else ''}...",
                         command=self.app._on_export)

        # Export to Slicer submenu
        slicers = self.app.detected_slicers
        if slicers:
            slicer_menu = tk.Menu(menu, tearoff=0, bg=theme.bg3, fg=theme.fg,
                                  activebackground=theme.accent2, activeforeground=theme.accent_fg,
                                  font=(UI_FONT, 12))
            for name, path in slicers.items():
                slicer_menu.add_command(
                    label=name,
                    command=lambda n=name, p=path: self.app._on_install_to_slicer(n, p))
            menu.add_cascade(label="Export to Slicer", menu=slicer_menu)

        # ── Edit ──
        menu.add_separator()
        if count == 1:
            menu.add_command(label="Rename", command=self._rename_selected)
        if count >= 2:
            menu.add_command(label="Batch Rename...", command=self._on_batch_rename)
        if count == 1:
            menu.add_command(label="Duplicate", command=self.app._on_create_from_profile)

        # ── View ──
        menu.add_separator()
        if count == 2:
            menu.add_command(
                label="Compare",
                command=lambda: self.app._launch_compare(sel_profiles[0], sel_profiles[1]),
            )
        menu.add_command(label="Show Folder", command=self.app._on_show_folder)
        if len(sel_profiles) == 1 and sel_profiles[0].changelog:
            menu.add_command(label="View History",
                             command=lambda p=sel_profiles[0]: self.detail._show_changelog(p))

        # ── Remove ──
        menu.add_separator()
        menu.add_command(label="Remove from list", command=self.app._on_remove)
        menu.add_command(label="Delete from disk...", command=lambda: self._on_delete_from_disk())

        menu.tk_popup(event.x_root, event.y_root)

    # ── SECTION: Inline and Batch Rename ──

    def _on_batch_rename(self) -> None:
        """Open batch rename dialog for selected profiles."""
        from .dialogs import BatchRenameDialog
        selected = self.get_selected_profiles()
        if not selected:
            messagebox.showinfo("No Selection", "Select profiles to rename.", parent=self)
            return
        BatchRenameDialog(self, self._theme, selected, self._refresh_list)

    def _rename_selected(self) -> None:
        """Rename the single selected profile."""
        sel = list(self.tree.selection())
        if len(sel) != 1:
            return
        idx = int(sel[0])
        if idx < len(self.profiles):
            self._start_inline_rename(sel[0], idx)

    def _start_inline_rename(self, iid: str, idx: int) -> None:
        if self._rename_active:
            return  # Another rename is in progress — prevent race condition
        self._rename_active = True
        theme = self.theme
        profile = self.profiles[idx]

        # Get the bounding box of the "name" column for this item
        try:
            bbox = self.tree.bbox(iid, column="name")
        except Exception as e:
            logger.debug("Failed to get bbox for rename: %s", e)
            self._rename_active = False
            return
        if not bbox:
            self._rename_active = False
            return
        x, y, w, h = bbox

        name_var = tk.StringVar(value=profile.name)
        entry = tk.Entry(self.tree, textvariable=name_var, bg=theme.bg3, fg=theme.fg,
                         insertbackground=theme.fg, font=(UI_FONT, 12),
                         highlightbackground=theme.accent, highlightthickness=1,
                         relief="flat")
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.select_range(0, "end")

        def _finish(event: Optional[tk.Event] = None) -> None:
            self._rename_active = False
            new_name = Profile.sanitize_name(name_var.get())
            entry.destroy()
            if new_name and new_name != profile.name:
                old_name = profile.name
                snapshot = {"name": old_name, "_modified": profile.modified}
                profile.data["name"] = new_name
                profile.modified = True
                profile.log_change("Renamed", f"{old_name} \u2192 {new_name}",
                                   snapshot=snapshot)
                self._refresh_list()
                # Re-select and show updated profile
                try:
                    self.tree.selection_set(str(idx))
                except Exception:
                    pass
                self._on_select()

        def _cancel(event: Optional[tk.Event] = None) -> None:
            self._rename_active = False
            entry.destroy()

        entry.bind("<Return>", _finish)
        entry.bind("<FocusOut>", _finish)
        entry.bind("<Escape>", _cancel)

    def _on_double_click_rename(self, event: tk.Event) -> str:
        item = self.tree.identify_row(event.y)
        if not item:
            return ""
        idx = int(item)
        if idx < len(self.profiles):
            self._start_inline_rename(item, idx)
        return "break"  # Prevent default expand/collapse behavior

    # ── SECTION: Profile Management ──

    def get_selected_profiles(self) -> list:
        seen_indices = set()
        result = []
        for iid in self.tree.selection():
            idx = int(iid)
            if idx < len(self.profiles) and idx not in seen_indices:
                seen_indices.add(idx)
                result.append(self.profiles[idx])
        return result

    def add_profiles(self, new_profiles: list) -> None:
        # Deduplicate: skip profiles that match an existing one by name + source path
        existing = {(p.name, p.source_path) for p in self.profiles}
        for profile in new_profiles:
            key = (profile.name, profile.source_path)
            if key not in existing:
                self.profiles.append(profile)
                existing.add(key)
        self._refresh_list()

    def remove_selected(self) -> None:
        indices = set()
        for iid in self.tree.selection():
            indices.add(int(iid))
        for i in sorted(indices, reverse=True):
            if i < len(self.profiles):
                self.profiles.pop(i)
        self._refresh_list()
        self.detail._show_placeholder()

    def select_all(self) -> None:
        all_items = list(self.tree.get_children())
        if all_items:
            self.tree.selection_set(all_items)

    def _on_delete_from_disk(self) -> None:
        selected = self.get_selected_profiles()
        if not selected:
            return
        # Collect unique file paths
        paths = []
        for profile in selected:
            if profile.source_path and os.path.isfile(profile.source_path):
                if profile.source_path not in [x[1] for x in paths]:
                    paths.append((profile.name, profile.source_path))

        if not paths:
            messagebox.showinfo("Nothing to delete",
                                "No source files found on disk for the selected profiles.")
            return

        # Build confirmation message
        count = len(paths)
        if count == 1:
            name, fpath = paths[0]
            msg = (f"PERMANENTLY delete this profile from your disk?\n\n"
                   f"  {os.path.basename(fpath)}\n\n"
                   f"Location: {os.path.dirname(fpath)}\n\n"
                   f"This will permanently erase the file from your computer.\n"
                   f"This action cannot be undone — the file cannot be recovered.")
        else:
            file_list = "\n".join(f"  \u2022 {os.path.basename(fp)}" for _, fp in paths[:8])
            if count > 8:
                file_list += f"\n  ... and {count - 8} more"
            msg = (f"PERMANENTLY delete {count} profiles from your disk?\n\n"
                   f"{file_list}\n\n"
                   f"This will permanently erase these files from your computer.\n"
                   f"This action cannot be undone — the files cannot be recovered.")

        confirmed = messagebox.askyesno("Permanently Delete from Disk", msg, icon="warning")
        if not confirmed:
            return

        deleted = 0
        errors = []
        for name, fpath in paths:
            try:
                os.remove(fpath)
                deleted += 1
            except OSError as e:
                errors.append(f"{os.path.basename(fpath)}: {e.strerror}")

        # Also remove from list
        self.remove_selected()

        if errors:
            messagebox.showwarning("Some files could not be deleted",
                                   "\n".join(errors))
        else:
            self.app._update_status(f"Deleted {deleted} file{'s' if deleted != 1 else ''} from disk.")

    def _on_clear(self) -> None:
        if self.profiles:
            self.profiles.clear()
            self._refresh_list()
            self.detail._show_placeholder()
            # Notify app that selection is now empty (cache must clear)
            if self.app and self.profile_type == "filament":
                if hasattr(self.app, '_on_filament_selection_changed'):
                    self.app._on_filament_selection_changed()
            self.app._update_status("List cleared.")


class ComparePanel(tk.Frame):
    """Side-by-side filament profile comparison with filtering, search, and navigation.

    Mirrors the detail panel layout vertically — section headers (Filament,
    Cooling, Overrides, etc.) run down the page with two value columns
    (one per profile).  Differences are highlighted.

    Color assignments:
      Profile A values:  accent / lime  (#C6FF00)
      Profile B values:  success / cyan (#4DD0E1)
      Changed row bg:    theme.compare_changed_bg (plum tint) + warning left border
      Missing row bg:    theme.compare_missing_bg (red-plum)  + error left border
    """

    def __init__(self, parent: tk.Widget, theme: Theme, app: Any) -> None:
        super().__init__(parent, bg=theme.bg)
        self.theme = theme
        self.app = app
        self._profile_a: Optional[Profile] = None
        self._profile_b: Optional[Profile] = None
        self._profile_b_fg = theme.success
        self._waiting = False  # True when waiting for user to select 2 filaments
        self._profile_type_label = "Filament"

        # Undo stack
        self._undo_stack: list[tuple] = []
        self._pending_count = 0

        # Filter / search / collapse state
        self._filter_mode: str = "diffs"  # "diffs", "missing", "all", "pending"
        self._pending_keys: set[str] = set()
        self._collapsed_sections: set[str] = set()
        self._search_var: Optional[tk.StringVar] = None
        self._search_entry: Optional[tk.Entry] = None
        self._section_widgets: dict[str, tk.Widget] = {}
        self._nav_items: dict[str, tk.Frame] = {}
        self._show_empty = False

        self._show_waiting_ui()

    # ── Public API ──────────────────────────────────────────────

    def load(self, profile_a: Profile, profile_b: Profile) -> None:
        """Populate with two profiles and build the comparison view."""
        if not profile_a or not profile_b:
            logger.warning("ComparePanel.load called with None profile: a=%s b=%s",
                           profile_a, profile_b)
            self.show_waiting()
            return
        logger.debug("ComparePanel.load: '%s' vs '%s'", profile_a.name, profile_b.name)
        self._profile_a = profile_a
        self._profile_b = profile_b
        self._waiting = False
        self._undo_stack.clear()
        self._pending_count = 0
        self._pending_keys = set()
        self._collapsed_sections = set()
        self._filter_mode = "diffs"
        try:
            self._rebuild()
        except Exception:
            logger.exception("ComparePanel._rebuild() crashed")

    def show_waiting(self) -> None:
        """Show the 'select two filament profiles' prompt."""
        self._profile_a = None
        self._profile_b = None
        self._waiting = True
        for child in self.winfo_children():
            child.destroy()
        self._show_waiting_ui()

    def is_waiting(self) -> bool:
        return self._waiting

    def clear(self) -> None:
        """Reset to waiting state."""
        self.show_waiting()

    # ── Waiting UI ──────────────────────────────────────────────

    def _show_waiting_ui(self) -> None:
        theme = self.theme
        container = tk.Frame(self, bg=theme.bg2)
        container.place(relx=0.5, rely=0.4, anchor="center")
        tk.Label(
            container, text="\u2194", bg=theme.bg2, fg=theme.fg3,
            font=(UI_FONT, 28),
        ).pack()
        tk.Label(
            container, text="Compare Filament Profiles", bg=theme.bg2,
            fg=theme.fg, font=(UI_FONT, 15, "bold"),
        ).pack(pady=(6, 10))
        tk.Label(
            container, text="Select two filament profiles\nin the Filament tab, then click Compare Filament.",
            bg=theme.bg2, fg=theme.fg3, font=(UI_FONT, 13),
            justify="center",
        ).pack(pady=(0, 8))

    # ── Main rebuild ────────────────────────────────────────────

    def _rebuild(self) -> None:
        for child in self.winfo_children():
            child.destroy()

        theme = self.theme
        pa, pb = self._profile_a, self._profile_b
        if not pa or not pb:
            self._show_waiting_ui()
            return

        layout = FILAMENT_LAYOUT
        data_a = pa.resolved_data if pa.resolved_data else pa.data
        data_b = pb.resolved_data if pb.resolved_data else pb.data

        # Diff detection
        all_keys = (set(data_a.keys()) | set(data_b.keys())) - _IDENTITY_KEYS
        diff_keys: set[str] = set()
        for k in all_keys:
            if data_a.get(k) != data_b.get(k):
                diff_keys.add(k)

        self._layout = layout
        self._data_a = data_a
        self._data_b = data_b
        self._diff_keys = diff_keys
        self._diff_count = len(diff_keys)
        self._total_params = sum(
            len(params) for sections in layout.values() for params in sections.values()
        )

        # ── Header bar ──
        header = tk.Frame(self, bg=theme.bg)
        header.pack(fill="x", padx=16, pady=(8, 0))

        # Profile names: A (lime) vs B (cyan)
        tk.Label(
            header, text=pa.name, bg=theme.bg, fg=theme.accent,
            font=(UI_FONT, 14, "bold"),
        ).pack(side="left")
        tk.Label(
            header, text="  vs  ", bg=theme.bg, fg=theme.fg3,
            font=(UI_FONT, 13),
        ).pack(side="left")
        tk.Label(
            header, text=pb.name, bg=theme.bg, fg=self._profile_b_fg,
            font=(UI_FONT, 14, "bold"),
        ).pack(side="left")

        # Summary
        tk.Label(
            header,
            text=f"   \u2022  {self._diff_count} difference{'s' if self._diff_count != 1 else ''}",
            bg=theme.bg, fg=theme.fg3, font=(UI_FONT, 12),
        ).pack(side="left", padx=(8, 0))
        self._summary_label = header.winfo_children()[-1]

        # Clear button (far right)
        _make_btn(
            header, "\u21bb  Clear",
            lambda: self.app._close_compare(),
            bg=theme.bg4, fg=theme.btn_fg,
            font=(UI_FONT, 11), padx=10, pady=3,
        ).pack(side="right")

        # History link
        self._history_label = tk.Label(
            header, text="", bg=theme.bg,
            fg=theme.converted if hasattr(theme, "converted") else theme.secondary,
            font=(UI_FONT, 12, "underline"), cursor="hand2",
        )
        self._history_label.pack(side="right", padx=(0, 8))
        self._history_label.bind("<Button-1>", lambda e: self._show_changelog())
        self._update_history_label()

        # ── Filter chip bar + search (Tier 1.1 + Tier 2.2) ──
        filter_bar = tk.Frame(self, bg=theme.bg)
        filter_bar.pack(fill="x", padx=16, pady=(8, 4))

        self._chip_labels: dict[str, tk.Label] = {}
        chip_defs = [
            ("diffs", "Differences only"),
            ("missing", "Missing values"),
            ("all", "All parameters"),
            ("pending", f"Pending ({len(self._pending_keys)})"),
        ]
        for mode, text in chip_defs:
            chip = tk.Label(
                filter_bar, text=f" {text} ", bg=theme.bg3, fg=theme.fg2,
                font=(UI_FONT, 11), padx=12, pady=3, cursor="hand2",
                highlightbackground=theme.border, highlightthickness=1,
            )
            chip.pack(side="left", padx=(0, 8))
            chip.bind("<Button-1>", lambda e, m=mode: self._set_filter_mode(m))
            self._chip_labels[mode] = chip

        self._update_chip_styles()

        # Search entry (right-aligned)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._on_search_changed())
        self._search_entry = tk.Entry(
            filter_bar, textvariable=self._search_var,
            bg=theme.bg3, fg=theme.fg, insertbackground=theme.fg,
            font=(UI_FONT, 12), relief="flat", width=25,
            highlightbackground=theme.border, highlightthickness=1,
        )
        self._search_entry.pack(side="right", padx=(8, 0), pady=2)
        # Placeholder behavior
        self._search_placeholder_active = True
        self._search_entry.insert(0, "Search parameters...")
        self._search_entry.configure(fg=theme.placeholder_fg)
        self._search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self._search_entry.bind("<FocusOut>", self._on_search_focus_out)

        # ── Main horizontal container (nav rail + content) ──
        main_container = tk.Frame(self, bg=theme.bg)
        main_container.pack(fill="both", expand=True)

        # Nav rail (left, fixed width) — Tier 2.1
        self._nav_rail = tk.Frame(main_container, bg=theme.bg, width=190)
        self._nav_rail.pack(side="left", fill="y", padx=(16, 0))
        self._nav_rail.pack_propagate(False)

        # Nav rail title
        tk.Label(
            self._nav_rail, text="SECTIONS", bg=theme.bg, fg=theme.fg3,
            font=(UI_FONT, 10, "bold"), anchor="w", padx=12, pady=(8, 4),
        ).pack(fill="x")

        # Nav rail separator
        tk.Frame(self._nav_rail, bg=theme.border, height=1).pack(fill="x", padx=8)

        # Build nav items
        self._nav_items = {}
        self._build_nav_rail()

        # Content area (right, fills remaining space)
        content_area = tk.Frame(main_container, bg=theme.bg)
        content_area.pack(side="left", fill="both", expand=True)

        # ── Column header row ──
        # Right padx includes ~17px scrollbar compensation so columns
        # align with the scrollable body below.
        col_hdr = tk.Frame(content_area, bg=theme.bg4)
        col_hdr.pack(fill="x", padx=(0, 17), pady=(0, 0))
        # 5 columns: param | sep | value A | sep | value B
        col_hdr.columnconfigure(0, weight=2, minsize=200)
        col_hdr.columnconfigure(1, weight=0, minsize=1)  # separator
        col_hdr.columnconfigure(2, weight=2, minsize=180)
        col_hdr.columnconfigure(3, weight=0, minsize=1)  # separator
        col_hdr.columnconfigure(4, weight=2, minsize=180)

        tk.Label(
            col_hdr, text="Parameter", bg=theme.bg4, fg=theme.fg,
            font=(UI_FONT, 12, "bold"), anchor="w", padx=10, pady=5,
        ).grid(row=0, column=0, sticky="ew")
        tk.Frame(col_hdr, bg=theme.border, width=1).grid(
            row=0, column=1, sticky="ns", padx=0)
        tk.Label(
            col_hdr, text=self._truncate_name(pa.name, 28), bg=theme.bg4,
            fg=theme.accent, font=(UI_FONT, 12, "bold"), anchor="w", padx=8, pady=5,
        ).grid(row=0, column=2, sticky="ew")
        tk.Frame(col_hdr, bg=theme.border, width=1).grid(
            row=0, column=3, sticky="ns", padx=0)
        tk.Label(
            col_hdr, text=self._truncate_name(pb.name, 28), bg=theme.bg4,
            fg=self._profile_b_fg, font=(UI_FONT, 12, "bold"), anchor="w", padx=8, pady=5,
        ).grid(row=0, column=4, sticky="ew")

        # ── Scrollable body ──
        scroll_container = tk.Frame(content_area, bg=theme.bg)
        scroll_container.pack(fill="both", expand=True)

        self._scroll_frame = ScrollableFrame(scroll_container, bg=theme.bg2)
        self._scroll_frame.pack(fill="both", expand=True)
        self._body = self._scroll_frame.body
        self._canvas = self._scroll_frame.canvas

        # Track scroll position for active nav highlighting
        self._canvas.bind("<Configure>", self._on_canvas_scroll)
        self._canvas.bind("<MouseWheel>", lambda e: self.after(50, self._update_active_nav))
        if _PLATFORM != "Darwin":
            self._canvas.bind("<Button-4>", lambda e: self.after(50, self._update_active_nav))
            self._canvas.bind("<Button-5>", lambda e: self.after(50, self._update_active_nav))

        self._render_rows()

        # ── Status bar (Tier 3.3) ──
        status = tk.Frame(self, bg=theme.bg)
        status.pack(fill="x")
        tk.Frame(status, bg=theme.border, height=1).pack(fill="x")

        status_inner = tk.Frame(status, bg=theme.bg)
        status_inner.pack(fill="x", padx=12, pady=3)

        # Left: diff count + pending
        left_status = tk.Frame(status_inner, bg=theme.bg)
        left_status.pack(side="left")
        self._status_diff_label = tk.Label(
            left_status, text=f"{self._diff_count} differences",
            bg=theme.bg, fg=theme.fg, font=(UI_FONT, 11, "bold"),
        )
        self._status_diff_label.pack(side="left")
        tk.Label(
            left_status, text=" \u2022 ", bg=theme.bg, fg=theme.fg3,
            font=(UI_FONT, 11),
        ).pack(side="left")
        pending_fg = theme.converted if self._pending_count > 0 else theme.fg3
        pending_weight = "bold" if self._pending_count > 0 else "normal"
        self._status_pending_label = tk.Label(
            left_status,
            text=f"{self._pending_count} pending" if self._pending_count > 0 else "No changes",
            bg=theme.bg, fg=pending_fg, font=(UI_FONT, 11, pending_weight),
        )
        self._status_pending_label.pack(side="left")

        # Right: active filter
        _filter_label_map = {
            "diffs": "Differences only", "missing": "Missing values",
            "all": "All parameters", "pending": "Pending changes",
        }
        self._status_filter_label = tk.Label(
            status_inner,
            text=f"Showing: {_filter_label_map.get(self._filter_mode, self._filter_mode)}",
            bg=theme.bg, fg=theme.fg3, font=(UI_FONT, 11),
        )
        self._status_filter_label.pack(side="right")

        # Keyboard shortcuts (Tier 2.5)
        self.bind_all("<Control-f>", lambda e: self._focus_search())
        self.bind_all("<Key-d>", lambda e: self._toggle_diff_filter() if not self._search_focused() else None)

    # ── Filter chip management ──────────────────────────────────

    def _set_filter_mode(self, mode: str) -> None:
        """Change active filter and re-render rows."""
        self._filter_mode = mode
        self._update_chip_styles()
        self._render_rows()
        self._update_nav_badges()
        self._update_status_bar()

    def _update_chip_styles(self) -> None:
        """Restyle filter chips based on active mode."""
        theme = self.theme
        for mode, chip in self._chip_labels.items():
            if mode == self._filter_mode:
                chip.configure(
                    bg=theme.accent, fg=theme.accent_fg,
                    font=(UI_FONT, 11, "bold"),
                    highlightthickness=0,
                )
            else:
                chip.configure(
                    bg=theme.bg3, fg=theme.fg2,
                    font=(UI_FONT, 11),
                    highlightbackground=theme.border, highlightthickness=1,
                )
        # Update pending chip count
        if "pending" in self._chip_labels:
            self._chip_labels["pending"].configure(
                text=f" Pending ({len(self._pending_keys)}) ",
            )

    # ── Search (Tier 2.2) ───────────────────────────────────────

    def _on_search_focus_in(self, event: Optional[tk.Event] = None) -> None:
        if self._search_placeholder_active:
            self._search_entry.delete(0, "end")
            self._search_entry.configure(fg=self.theme.fg)
            self._search_placeholder_active = False

    def _on_search_focus_out(self, event: Optional[tk.Event] = None) -> None:
        if not self._search_var.get().strip():
            self._search_placeholder_active = True
            self._search_entry.insert(0, "Search parameters...")
            self._search_entry.configure(fg=self.theme.placeholder_fg)

    def _on_search_changed(self) -> None:
        """Re-render rows when search text changes."""
        if not hasattr(self, "_body") or not self._body.winfo_exists():
            return  # Guard: trace fires during _rebuild before body exists
        self._render_rows()
        self._update_nav_badges()

    def _focus_search(self) -> None:
        """Focus the search entry (Ctrl+F)."""
        if self._search_entry and self._search_entry.winfo_exists():
            self._search_entry.focus_set()
            if not self._search_placeholder_active:
                self._search_entry.select_range(0, "end")

    def _search_focused(self) -> bool:
        """Check if search entry currently has focus."""
        try:
            return self._search_entry is not None and self.focus_get() is self._search_entry
        except (KeyError, tk.TclError):
            return False

    def _get_search_text(self) -> str:
        """Get active search filter text (empty string if placeholder)."""
        if self._search_var is None:
            return ""
        txt = self._search_var.get().strip().lower()
        if txt == "search parameters...":
            return ""
        return txt

    def _toggle_diff_filter(self) -> None:
        """Toggle between diffs and all filter modes (D key)."""
        if self._filter_mode == "diffs":
            self._set_filter_mode("all")
        else:
            self._set_filter_mode("diffs")

    # ── Nav rail (Tier 2.1) ─────────────────────────────────────

    def _build_nav_rail(self) -> None:
        """Build navigation rail items from FILAMENT_LAYOUT sections."""
        theme = self.theme
        self._nav_items = {}

        for tab_name, sections in self._layout.items():
            if not sections:
                continue
            for sec_name, params in sections.items():
                if not params:
                    continue
                section_key = f"{tab_name}::{sec_name}"
                diff_count = self._section_diff_count(params)
                has_missing = self._section_has_missing(params)

                nav_row = tk.Frame(self._nav_rail, bg=theme.bg, cursor="hand2")
                nav_row.pack(fill="x", pady=1)

                # Left accent border (hidden by default, shown when active)
                accent_bar = tk.Frame(nav_row, bg=theme.bg, width=3)
                accent_bar.pack(side="left", fill="y")

                # Section name
                name_lbl = tk.Label(
                    nav_row, text=sec_name, bg=theme.bg, fg=theme.fg2,
                    font=(UI_FONT, 11), anchor="w", padx=8, pady=3,
                )
                name_lbl.pack(side="left", fill="x", expand=True)

                # Diff count badge
                badge_bg = theme.error if has_missing else (theme.warning if diff_count > 0 else theme.bg4)
                badge_fg = theme.accent_fg if diff_count > 0 else theme.fg3
                badge = tk.Label(
                    nav_row, text=f" {diff_count} ", bg=badge_bg, fg=badge_fg,
                    font=(UI_FONT, 10, "bold"), padx=4, pady=1,
                )
                badge.pack(side="right", padx=(4, 8))

                # Store references
                nav_row._accent_bar = accent_bar  # type: ignore
                nav_row._name_lbl = name_lbl  # type: ignore
                nav_row._badge = badge  # type: ignore
                self._nav_items[section_key] = nav_row

                # Click to scroll
                def _on_nav_click(e, sk=section_key):
                    self._jump_to_section(sk)
                nav_row.bind("<Button-1>", _on_nav_click)
                name_lbl.bind("<Button-1>", _on_nav_click)
                badge.bind("<Button-1>", _on_nav_click)

    def _update_nav_badges(self) -> None:
        """Update nav rail badge counts after filter/search changes."""
        theme = self.theme
        for tab_name, sections in self._layout.items():
            if not sections:
                continue
            for sec_name, params in sections.items():
                if not params:
                    continue
                section_key = f"{tab_name}::{sec_name}"
                nav_row = self._nav_items.get(section_key)
                if not nav_row:
                    continue
                diff_count = self._section_diff_count(params)
                has_missing = self._section_has_missing(params)
                badge = nav_row._badge  # type: ignore
                badge_bg = theme.error if has_missing else (theme.warning if diff_count > 0 else theme.bg4)
                badge_fg = theme.accent_fg if diff_count > 0 else theme.fg3
                badge.configure(text=f" {diff_count} ", bg=badge_bg, fg=badge_fg)

    def _jump_to_section(self, section_key: str) -> None:
        """Scroll the main table to the given section."""
        widget = self._section_widgets.get(section_key)
        if not widget or not widget.winfo_exists():
            return
        self._body.update_idletasks()
        y = widget.winfo_y()
        total_height = self._body.winfo_reqheight()
        if total_height > 0:
            fraction = max(0.0, min(1.0, y / total_height))
            self._canvas.yview_moveto(fraction)
        self._highlight_nav_item(section_key)

    def _highlight_nav_item(self, active_key: str) -> None:
        """Highlight the active section in the nav rail."""
        theme = self.theme
        for key, nav_row in self._nav_items.items():
            is_active = key == active_key
            accent_bar = nav_row._accent_bar  # type: ignore
            name_lbl = nav_row._name_lbl  # type: ignore
            accent_bar.configure(bg=theme.accent if is_active else theme.bg)
            name_lbl.configure(
                fg=theme.fg if is_active else theme.fg2,
                font=(UI_FONT, 11, "bold") if is_active else (UI_FONT, 11),
            )

    def _on_canvas_scroll(self, event: Optional[tk.Event] = None) -> None:
        """Update active nav item on scroll."""
        self.after(50, self._update_active_nav)

    def _update_active_nav(self) -> None:
        """Determine which section is visible at top and highlight it in nav."""
        if not self._section_widgets:
            return
        try:
            view_top = self._canvas.yview()[0]
        except tk.TclError:
            return
        total_height = self._body.winfo_reqheight()
        if total_height <= 0:
            return
        pixel_top = view_top * total_height

        best_key = None
        best_y = -1
        for key, widget in self._section_widgets.items():
            if not widget.winfo_exists():
                continue
            wy = widget.winfo_y()
            if wy <= pixel_top + 20 and wy > best_y:
                best_y = wy
                best_key = key

        if best_key:
            self._highlight_nav_item(best_key)

    def _section_diff_count(self, section_params: list) -> int:
        return sum(1 for k, _ in section_params if k in self._diff_keys)

    def _section_has_missing(self, section_params: list) -> bool:
        return any(
            (self._data_a.get(k) is None) != (self._data_b.get(k) is None)
            for k, _ in section_params if k in self._diff_keys
        )

    # ── Row rendering ───────────────────────────────────────────

    def _render_rows(self) -> None:
        """Render section headers and parameter rows in side-by-side layout."""
        body = self._body
        canvas = self._canvas
        theme = self.theme
        data_a, data_b = self._data_a, self._data_b
        diff_keys = self._diff_keys
        search_text = self._get_search_text()

        # Suppress <Configure> during bulk widget creation (O(n^2) prevention)
        body.unbind("<Configure>")

        for child in body.winfo_children():
            child.destroy()

        self._section_widgets = {}
        row_idx = 0

        for tab_name, sections in self._layout.items():
            if not sections:
                continue  # Skip empty tabs (e.g. "Multi Filament")

            # Pre-check: does this tab have ANY visible rows after filtering?
            tab_has_visible = False
            for sec_name, params in sections.items():
                if not params:
                    continue
                for json_key, ui_label in params:
                    if self._is_row_visible(json_key, ui_label, data_a, data_b, diff_keys, search_text):
                        tab_has_visible = True
                        break
                if tab_has_visible:
                    break

            if not tab_has_visible:
                continue  # Skip entire tab if no visible rows

            # Count diffs in this tab
            tab_diff_count = sum(
                1 for params in sections.values()
                for k, _ in params if k in diff_keys
            )

            # ── Tab header (section title) ──
            tab_hdr = tk.Frame(body, bg=theme.section_bg)
            tab_hdr.pack(fill="x", pady=(12 if row_idx > 0 else 4, 2))

            # Lime left border (4px)
            tk.Frame(tab_hdr, bg=theme.accent, width=4).pack(side="left", fill="y")

            tk.Label(
                tab_hdr, text=tab_name, bg=theme.section_bg,
                fg=theme.fg, font=(UI_FONT, 13, "bold"),
                anchor="w", padx=8, pady=5,
            ).pack(side="left")

            if tab_diff_count > 0:
                tk.Label(
                    tab_hdr, text=f" {tab_diff_count} differ ",
                    bg=theme.warning, fg=theme.accent_fg,
                    font=(UI_FONT, 10, "bold"), padx=6, pady=1,
                ).pack(side="right", padx=8)

            _bind_scroll(tab_hdr, canvas)
            for ch in tab_hdr.winfo_children():
                _bind_scroll(ch, canvas)
            row_idx += 1

            # ── Sections within this tab ──
            for sec_name, params in sections.items():
                if not params:
                    continue

                section_key = f"{tab_name}::{sec_name}"

                # Pre-check: does this section have any visible rows?
                section_visible_rows = []
                for json_key, ui_label in params:
                    if self._is_row_visible(json_key, ui_label, data_a, data_b, diff_keys, search_text):
                        section_visible_rows.append((json_key, ui_label))

                if not section_visible_rows:
                    continue  # Skip empty sections

                is_collapsed = section_key in self._collapsed_sections
                diff_count = self._section_diff_count(params)
                has_missing = self._section_has_missing(params)

                # Section header (Tier 2.3 collapse + Tier 2.6 enhanced badges)
                sec_hdr = tk.Frame(body, bg=theme.section_bg, cursor="hand2")
                sec_hdr.pack(fill="x", pady=(4, 1))
                self._section_widgets[section_key] = sec_hdr

                tk.Frame(sec_hdr, bg=theme.accent_dark, width=3).pack(side="left", fill="y")

                # Chevron (Tier 2.3)
                chevron_text = "\u25B8" if is_collapsed else "\u25BE"
                chevron_label = tk.Label(
                    sec_hdr, text=chevron_text, bg=theme.section_bg, fg=theme.fg3,
                    font=(UI_FONT, 10), cursor="hand2",
                )
                chevron_label.pack(side="left", padx=(4, 0))

                sec_name_label = tk.Label(
                    sec_hdr, text=sec_name, bg=theme.section_bg, fg=theme.fg2,
                    font=(UI_FONT, 12, "bold"), padx=6, pady=3, anchor="w",
                    cursor="hand2",
                )
                sec_name_label.pack(side="left")

                # Enhanced diff badge (Tier 2.6)
                badge_bg = theme.error if has_missing else (theme.warning if diff_count > 0 else theme.bg4)
                badge_fg = theme.accent_fg if diff_count > 0 else theme.fg3
                badge = tk.Label(
                    sec_hdr, text=f" {diff_count} ", bg=badge_bg, fg=badge_fg,
                    font=(UI_FONT, 10, "bold"), padx=6, pady=1,
                )
                badge.pack(side="right", padx=8)

                # Batch copy links (Tier 3.1) — shown on hover
                batch_frame = tk.Frame(sec_hdr, bg=theme.section_bg)
                ab_link = tk.Label(
                    batch_frame, text="A \u2192 B", bg=theme.section_bg,
                    fg=theme.accent, font=(UI_FONT, 11), cursor="hand2",
                )
                ab_link.pack(side="left", padx=(0, 8))
                ba_link = tk.Label(
                    batch_frame, text="B \u2192 A", bg=theme.section_bg,
                    fg=self._profile_b_fg, font=(UI_FONT, 11), cursor="hand2",
                )
                ba_link.pack(side="left")

                def _batch_ab(prms=params):
                    for jk, _ in prms:
                        if jk in self._diff_keys:
                            self._copy_a_to_b(jk)
                def _batch_ba(prms=params):
                    for jk, _ in prms:
                        if jk in self._diff_keys:
                            self._copy_b_to_a(jk)

                ab_link.bind("<Button-1>", lambda e, fn=_batch_ab: fn())
                ba_link.bind("<Button-1>", lambda e, fn=_batch_ba: fn())

                def _show_batch(e, bf=batch_frame):
                    bf.pack(side="right", padx=(0, 4))
                def _hide_batch(e, bf=batch_frame):
                    bf.pack_forget()

                sec_hdr.bind("<Enter>", _show_batch)
                sec_hdr.bind("<Leave>", _hide_batch)

                # Collapse toggle
                def _toggle(e=None, key=section_key):
                    if key in self._collapsed_sections:
                        self._collapsed_sections.discard(key)
                    else:
                        self._collapsed_sections.add(key)
                    self._render_rows()

                sec_hdr.bind("<Button-1>", _toggle)
                chevron_label.bind("<Button-1>", _toggle)
                sec_name_label.bind("<Button-1>", _toggle)

                _bind_scroll(sec_hdr, canvas)
                for ch in sec_hdr.winfo_children():
                    _bind_scroll(ch, canvas)

                # Skip params if collapsed (Tier 2.3)
                if is_collapsed:
                    continue

                # Parameter rows
                for json_key, ui_label in section_visible_rows:
                    val_a = data_a.get(json_key)
                    val_b = data_b.get(json_key)
                    is_diff = json_key in diff_keys
                    is_missing_a = val_a is None and val_b is not None
                    is_missing_b = val_b is None and val_a is not None

                    self._render_param_row(
                        body, canvas, json_key, ui_label,
                        val_a, val_b, is_diff, is_missing_a, is_missing_b,
                        row_idx,
                    )
                    row_idx += 1

        # ── Uncategorized keys ──
        key_in_layout: set[str] = set()
        for sections in self._layout.values():
            for params in sections.values():
                for k, _ in params:
                    key_in_layout.add(k)

        uncategorized_diffs = diff_keys - key_in_layout - _IDENTITY_KEYS
        if uncategorized_diffs:
            unc_hdr = tk.Frame(body, bg=theme.section_bg)
            unc_hdr.pack(fill="x", pady=(12, 2))
            tk.Frame(unc_hdr, bg=theme.fg3, width=4).pack(side="left", fill="y")
            tk.Label(
                unc_hdr, text="  Other (not in standard layout)",
                bg=theme.section_bg, fg=theme.fg3,
                font=(UI_FONT, 13, "bold"), anchor="w", padx=6, pady=4,
            ).pack(side="left", fill="x", expand=True)
            _bind_scroll(unc_hdr, canvas)

            for json_key in sorted(uncategorized_diffs):
                val_a = data_a.get(json_key)
                val_b = data_b.get(json_key)
                if not self._is_row_visible(json_key, json_key, data_a, data_b, diff_keys, search_text):
                    continue
                self._render_param_row(
                    body, canvas, json_key, json_key,
                    val_a, val_b, True, val_a is None, val_b is None,
                    row_idx,
                )
                row_idx += 1

        _bind_scroll(body, canvas)

        # Re-enable <Configure> and do a single scrollregion update
        body.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _is_row_visible(
        self,
        json_key: str,
        ui_label: str,
        data_a: dict,
        data_b: dict,
        diff_keys: set,
        search_text: str,
    ) -> bool:
        """Determine if a parameter row should be visible given current filters."""
        val_a = data_a.get(json_key)
        val_b = data_b.get(json_key)
        is_diff = json_key in diff_keys
        is_missing_a = val_a is None and val_b is not None
        is_missing_b = val_b is None and val_a is not None

        # Filter mode
        if self._filter_mode == "diffs" and not is_diff:
            return False
        if self._filter_mode == "missing" and not (is_missing_a or is_missing_b):
            return False
        if self._filter_mode == "pending" and json_key not in self._pending_keys:
            return False
        # In "all" mode, hide double-empty rows (both None)
        if self._filter_mode == "all" and val_a is None and val_b is None and not self._show_empty:
            return False

        # Search filter
        if search_text and search_text not in ui_label.lower():
            return False

        return True

    # Keys containing G-code or other long multiline text
    _GCODE_KEYS = {"filament_start_gcode", "filament_end_gcode", "machine_start_gcode",
                   "machine_end_gcode", "change_filament_gcode", "layer_change_gcode",
                   "filament_notes"}

    def _render_param_row(
        self,
        body: tk.Widget,
        canvas: tk.Canvas,
        json_key: str,
        ui_label: str,
        val_a: Any,
        val_b: Any,
        is_diff: bool,
        is_missing_a: bool,
        is_missing_b: bool,
        row_idx: int,
    ) -> None:
        """Render a single parameter row: name | sep | value A | sep | value B."""
        theme = self.theme
        is_gcode = json_key in self._GCODE_KEYS

        # Row background (Tier 1.2 — plum-tinted)
        if is_missing_a or is_missing_b:
            bg = theme.compare_missing_bg
            border_color = theme.error
        elif is_diff:
            bg = theme.compare_changed_bg
            border_color = theme.warning
        else:
            bg = theme.bg2 if row_idx % 2 == 0 else theme.bg3
            border_color = None

        row = tk.Frame(body, bg=bg)
        row.pack(fill="x")

        # Left border indicator (prominent 5px strip)
        if border_color:
            tk.Frame(row, bg=border_color, width=5).place(x=0, y=0, relheight=1.0)

        # Format values
        va_str = self._fmt(val_a, json_key)
        vb_str = self._fmt(val_b, json_key)

        if is_gcode and is_diff:
            # G-code / long text: full-width stacked layout
            self._render_gcode_row(row, canvas, json_key, ui_label, va_str, vb_str,
                                   val_a, val_b, is_diff, is_missing_a, is_missing_b,
                                   border_color, bg)
        else:
            # Standard columnar layout: param | sep | val A | sep | val B
            row.columnconfigure(0, weight=2, minsize=200)
            row.columnconfigure(1, weight=0, minsize=1)  # separator
            row.columnconfigure(2, weight=2, minsize=180)
            row.columnconfigure(3, weight=0, minsize=1)  # separator
            row.columnconfigure(4, weight=2, minsize=180)

            # Pending blue dot (Tier 2.4)
            param_padx_left = 12
            if json_key in self._pending_keys:
                dot = tk.Canvas(row, width=8, height=8, bg=bg, highlightthickness=0)
                dot.create_oval(1, 1, 7, 7, fill=theme.converted, outline="")
                dot.grid(row=0, column=0, sticky="w", padx=(4, 0))
                _bind_scroll(dot, canvas)
                param_padx_left = 16

            # Parameter name
            label_fg = theme.fg if is_diff else theme.fg3
            label_weight = "bold" if is_diff else "normal"
            tk.Label(
                row, text=ui_label, bg=bg, fg=label_fg,
                font=(UI_FONT, 12, label_weight), anchor="w", pady=4,
            ).grid(row=0, column=0, sticky="ew", padx=(param_padx_left, 4))

            # Separator
            tk.Frame(row, bg=theme.border, width=1).grid(
                row=0, column=1, sticky="ns")

            # Value A (Tier 1.3 — "(not set)" for missing)
            if is_missing_a:
                va_fg = theme.error
                va_display = "(not set)"
                va_font = (UI_FONT, 12, "italic")
            elif is_diff:
                va_fg = theme.accent
                va_display = va_str
                va_font = (UI_FONT, 12, "bold")
            else:
                va_fg = theme.fg3
                va_display = va_str
                va_font = (UI_FONT, 12)
            va_label = tk.Label(
                row, text=va_display, bg=bg, fg=va_fg,
                font=va_font, anchor="w", pady=4,
            )
            va_label.grid(row=0, column=2, sticky="ew", padx=8)

            # Separator
            tk.Frame(row, bg=theme.border, width=1).grid(
                row=0, column=3, sticky="ns")

            # Value B (Tier 1.3 — "(not set)" for missing)
            if is_missing_b:
                vb_fg = theme.error
                vb_display = "(not set)"
                vb_font = (UI_FONT, 12, "italic")
            elif is_diff:
                vb_fg = self._profile_b_fg
                vb_display = vb_str
                vb_font = (UI_FONT, 12, "bold")
            else:
                vb_fg = theme.fg3
                vb_display = vb_str
                vb_font = (UI_FONT, 12)
            vb_label = tk.Label(
                row, text=vb_display, bg=bg, fg=vb_fg,
                font=vb_font, anchor="w", pady=4,
            )
            vb_label.grid(row=0, column=4, sticky="ew", padx=8)

            # Copy arrows centered between columns (only for diffs) — Tier 1.5
            if is_diff:
                delta_text = self._compute_delta(val_a, val_b)
                key = json_key

                # A→B arrow (muted by default, colored on hover)
                ab_btn = tk.Label(
                    row, text="\u2192", bg=bg, fg=theme.fg3,
                    font=(UI_FONT, 12, "bold"), cursor="hand2",
                )
                ab_btn.grid(row=0, column=2, sticky="e", padx=(0, 4))
                ab_btn.bind("<Button-1>", lambda e, k=key: self._copy_a_to_b(k))
                ab_btn.bind("<Enter>", lambda e, l=ab_btn: l.configure(fg=theme.accent))
                ab_btn.bind("<Leave>", lambda e, l=ab_btn: l.configure(fg=theme.fg3))
                _Tooltip(ab_btn, f"Copy to {self._profile_b.name}")

                # B→A arrow (muted by default, colored on hover)
                ba_btn = tk.Label(
                    row, text="\u2190", bg=bg, fg=theme.fg3,
                    font=(UI_FONT, 12, "bold"), cursor="hand2",
                )
                ba_btn.grid(row=0, column=4, sticky="w", padx=(4, 0))
                ba_btn.bind("<Button-1>", lambda e, k=key: self._copy_b_to_a(k))
                ba_btn.bind("<Enter>", lambda e, l=ba_btn: l.configure(fg=self._profile_b_fg))
                ba_btn.bind("<Leave>", lambda e, l=ba_btn: l.configure(fg=theme.fg3))
                _Tooltip(ba_btn, f"Copy to {self._profile_a.name}")

                # Delta indicator after Profile B value (Tier 3.2)
                if delta_text:
                    is_neg = delta_text.startswith("\u2212") or delta_text.startswith("-")
                    tk.Label(
                        row, text=f"({delta_text})", bg=bg,
                        fg=theme.error if is_neg else theme.warning,
                        font=(UI_FONT, 10), anchor="e",
                    ).grid(row=0, column=4, sticky="e", padx=(0, 40))

        # Scroll bindings
        _bind_scroll(row, canvas)
        for child in row.winfo_children():
            _bind_scroll(child, canvas)

    def _render_gcode_row(
        self, row: tk.Frame, canvas: tk.Canvas,
        json_key: str, ui_label: str,
        va_str: str, vb_str: str,
        val_a: Any, val_b: Any,
        is_diff: bool, is_missing_a: bool, is_missing_b: bool,
        border_color: Any, bg: str,
    ) -> None:
        """Render a G-code / long-text parameter as a stacked full-width row."""
        theme = self.theme

        # Label row
        label_fg = theme.fg if is_diff else theme.fg3
        label_weight = "bold" if is_diff else "normal"
        tk.Label(
            row, text=ui_label, bg=bg, fg=label_fg,
            font=(UI_FONT, 12, label_weight), anchor="w", pady=4,
        ).pack(fill="x", padx=(12, 10))

        # Two side-by-side text blocks
        cols = tk.Frame(row, bg=bg)
        cols.pack(fill="x", padx=(12, 10), pady=(0, 6))
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=0, minsize=1)
        cols.columnconfigure(2, weight=1)

        # Truncate very long G-code for display
        max_lines = 6
        def _truncate_gcode(s: str) -> str:
            lines = s.splitlines()
            if len(lines) > max_lines:
                return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
            return s

        va_display = _truncate_gcode(va_str)
        vb_display = _truncate_gcode(vb_str)

        if is_missing_a:
            va_fg = theme.error
            va_display = "(not set)"
        else:
            va_fg = theme.accent if is_diff else theme.fg3

        if is_missing_b:
            vb_fg = theme.error
            vb_display = "(not set)"
        else:
            vb_fg = self._profile_b_fg if is_diff else theme.fg3

        tk.Label(
            cols, text=va_display, bg=bg, fg=va_fg,
            font=(UI_FONT, 10), anchor="nw", justify="left",
            wraplength=300,
        ).grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        tk.Frame(cols, bg=theme.border, width=1).grid(row=0, column=1, sticky="ns")

        tk.Label(
            cols, text=vb_display, bg=bg, fg=vb_fg,
            font=(UI_FONT, 10), anchor="nw", justify="left",
            wraplength=300,
        ).grid(row=0, column=2, sticky="nsew", padx=(4, 0))

        # Copy arrows below the text
        if is_diff:
            arrow_row = tk.Frame(row, bg=bg)
            arrow_row.pack(fill="x", padx=12, pady=(0, 4))

            key = json_key
            ab_btn = tk.Label(
                arrow_row, text="A \u2192 B", bg=bg, fg=theme.fg3,
                font=(UI_FONT, 12, "bold"), cursor="hand2",
            )
            ab_btn.pack(side="left", padx=(0, 16))
            ab_btn.bind("<Button-1>", lambda e, k=key: self._copy_a_to_b(k))
            ab_btn.bind("<Enter>", lambda e, l=ab_btn: l.configure(fg=theme.accent))
            ab_btn.bind("<Leave>", lambda e, l=ab_btn: l.configure(fg=theme.fg3))
            _Tooltip(ab_btn, f"Copy to {self._profile_b.name}")

            ba_btn = tk.Label(
                arrow_row, text="B \u2192 A", bg=bg, fg=theme.fg3,
                font=(UI_FONT, 12, "bold"), cursor="hand2",
            )
            ba_btn.pack(side="left")
            ba_btn.bind("<Button-1>", lambda e, k=key: self._copy_b_to_a(k))
            ba_btn.bind("<Enter>", lambda e, l=ba_btn: l.configure(fg=self._profile_b_fg))
            ba_btn.bind("<Leave>", lambda e, l=ba_btn: l.configure(fg=theme.fg3))
            _Tooltip(ba_btn, f"Copy to {self._profile_a.name}")

    # ── Copy operations (with changelog + undo) ──────────────────

    def _copy_a_to_b(self, json_key: str) -> None:
        """Copy value from Profile A to Profile B for a single parameter."""
        if not self._profile_b:
            return
        new_val = self._data_a.get(json_key)
        old_val = self._data_b.get(json_key)
        if new_val is None or new_val == old_val:
            return
        was_modified = self._profile_b.modified

        # Snapshot for undo via profile.restore_snapshot
        from copy import deepcopy
        snapshot = {json_key: deepcopy(old_val), "_modified": was_modified}

        # Apply the change
        self._profile_b.data[json_key] = deepcopy(new_val)
        if self._profile_b.resolved_data:
            self._profile_b.resolved_data[json_key] = deepcopy(new_val)
        self._profile_b.modified = True

        # Log to profile changelog (with snapshot for undo)
        self._profile_b.log_change(
            "Compare: copied from A",
            f"{json_key}: {old_val} \u2192 {new_val}  (from \"{self._profile_a.name}\")",
            snapshot,
        )

        # Push to local undo stack and track pending
        self._undo_stack.append((self._profile_b, json_key, old_val, was_modified))
        self._pending_count += 1
        self._pending_keys.add(json_key)

        self._refresh_diff()
        save_profile_state(self._profile_b)

    def _copy_b_to_a(self, json_key: str) -> None:
        """Copy value from Profile B to Profile A for a single parameter."""
        if not self._profile_a:
            return
        new_val = self._data_b.get(json_key)
        old_val = self._data_a.get(json_key)
        if new_val is None or new_val == old_val:
            return
        was_modified = self._profile_a.modified

        from copy import deepcopy
        snapshot = {json_key: deepcopy(old_val), "_modified": was_modified}

        self._profile_a.data[json_key] = deepcopy(new_val)
        if self._profile_a.resolved_data:
            self._profile_a.resolved_data[json_key] = deepcopy(new_val)
        self._profile_a.modified = True

        self._profile_a.log_change(
            "Compare: copied from B",
            f"{json_key}: {old_val} \u2192 {new_val}  (from \"{self._profile_b.name}\")",
            snapshot,
        )

        self._undo_stack.append((self._profile_a, json_key, old_val, was_modified))
        self._pending_count += 1
        self._pending_keys.add(json_key)

        self._refresh_diff()
        save_profile_state(self._profile_a)

    # ── Undo ────────────────────────────────────────────────────

    def _on_undo(self, event: Optional[tk.Event] = None) -> Optional[str]:
        """Undo the last copy operation (Ctrl+Z / Cmd+Z)."""
        if not self._undo_stack:
            return None  # Let other handlers process
        profile, json_key, old_val, was_modified = self._undo_stack.pop()

        # Restore the value
        from copy import deepcopy
        profile.data[json_key] = deepcopy(old_val)
        if profile.resolved_data:
            profile.resolved_data[json_key] = deepcopy(old_val)
        profile.modified = was_modified

        # Remove the last changelog entry (the one we just undid)
        if profile.changelog:
            profile.changelog.pop()

        self._pending_count = max(0, self._pending_count - 1)
        self._pending_keys.discard(json_key)

        self._refresh_diff()
        save_profile_state(profile)
        return "break"

    # ── Refresh ─────────────────────────────────────────────────

    def _refresh_diff(self) -> None:
        """Recompute diff keys, update counters, and re-render."""
        data_a = self._profile_a.resolved_data if self._profile_a.resolved_data else self._profile_a.data
        data_b = self._profile_b.resolved_data if self._profile_b.resolved_data else self._profile_b.data
        self._data_a = data_a
        self._data_b = data_b

        all_keys = (set(data_a.keys()) | set(data_b.keys())) - _IDENTITY_KEYS
        self._diff_keys = {k for k in all_keys if data_a.get(k) != data_b.get(k)}
        self._diff_count = len(self._diff_keys)

        if hasattr(self, "_summary_label"):
            self._summary_label.configure(
                text=f"{self._diff_count} difference{'s' if self._diff_count != 1 else ''} across {self._total_params} parameters",
            )
        self._update_history_label()
        self._update_chip_styles()
        self._update_status_bar()
        self._update_nav_badges()
        self._render_rows()

    # ── Status / history helpers ────────────────────────────────

    def _update_status_bar(self) -> None:
        theme = self.theme
        if hasattr(self, "_status_diff_label"):
            self._status_diff_label.configure(
                text=f"{self._diff_count} differences",
            )
        if hasattr(self, "_status_pending_label"):
            pending_fg = theme.converted if self._pending_count > 0 else theme.fg3
            pending_weight = "bold" if self._pending_count > 0 else "normal"
            self._status_pending_label.configure(
                text=f"{self._pending_count} pending" if self._pending_count > 0 else "No changes",
                fg=pending_fg, font=(UI_FONT, 11, pending_weight),
            )
        if hasattr(self, "_status_filter_label"):
            _filter_label_map = {
                "diffs": "Differences only", "missing": "Missing values",
                "all": "All parameters", "pending": "Pending changes",
            }
            self._status_filter_label.configure(
                text=f"Showing: {_filter_label_map.get(self._filter_mode, self._filter_mode)}",
            )

    def _update_history_label(self) -> None:
        """Show/hide the History link based on combined changelog length."""
        if not hasattr(self, "_history_label"):
            return
        total = 0
        if self._profile_a:
            total += len(self._profile_a.changelog)
        if self._profile_b:
            total += len(self._profile_b.changelog)
        if total > 0:
            self._history_label.configure(text=f"\u00b7  History ({total})")
        else:
            self._history_label.configure(text="")

    # ── Changelog dialog ────────────────────────────────────────

    def _show_changelog(self) -> None:
        """Open a dialog showing combined changelog for both profiles, with undo."""
        theme = self.theme
        pa, pb = self._profile_a, self._profile_b
        if not pa and not pb:
            return

        dlg = tk.Toplevel(self)
        dlg.title("Compare — Change History")
        dlg.configure(bg=theme.bg)
        dlg.resizable(True, True)
        dlg.transient(self.winfo_toplevel())

        tk.Label(
            dlg, text="Change History",
            bg=theme.bg, fg=theme.fg, font=(UI_FONT, 14, "bold"),
        ).pack(padx=16, pady=(12, 8), anchor="w")

        list_frame = tk.Frame(
            dlg, bg=theme.bg3,
            highlightbackground=theme.border, highlightthickness=1,
        )
        list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        canvas = tk.Canvas(list_frame, bg=theme.bg3, highlightthickness=0)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=theme.bg3)
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _rebuild_entries() -> None:
            for w in content.winfo_children():
                w.destroy()

            # Merge changelogs from both profiles with profile attribution
            entries = []
            for profile in [pa, pb]:
                if not profile:
                    continue
                for idx, entry in enumerate(profile.changelog):
                    ts = entry[0]
                    entries.append((ts, profile, idx, entry))

            # Sort newest first
            entries.sort(key=lambda x: x[0], reverse=True)

            if not entries:
                tk.Label(
                    content, text="No changes recorded.",
                    bg=theme.bg3, fg=theme.fg3, font=(UI_FONT, 12),
                ).pack(padx=16, pady=16)
                return

            for i, (ts, profile, real_idx, entry) in enumerate(entries):
                action, details = entry[1], entry[2]
                has_snapshot = len(entry) >= 4 and entry[3] is not None

                if i > 0:
                    tk.Frame(content, bg=theme.border, height=1).pack(
                        fill="x", padx=8, pady=(4, 4))

                row = tk.Frame(content, bg=theme.bg3)
                row.pack(fill="x", padx=10, pady=(6, 2))

                # Profile name badge
                is_a = profile is pa
                profile_fg = theme.accent if is_a else self._profile_b_fg
                header = tk.Frame(row, bg=theme.bg3)
                header.pack(fill="x")

                tk.Label(
                    header, text=profile.name,
                    bg=theme.bg3, fg=profile_fg,
                    font=(UI_FONT, 12, "bold"),
                ).pack(side="left")
                tk.Label(
                    header, text=f"  {action}",
                    bg=theme.bg3, fg=theme.accent
                    if hasattr(theme, "converted") and theme.accent else theme.fg,
                    font=(UI_FONT, 12, "bold"),
                ).pack(side="left")
                tk.Label(
                    header, text=f"  {ts}",
                    bg=theme.bg3, fg=theme.fg3, font=(UI_FONT, 11),
                ).pack(side="left", pady=(1, 0))

                if details:
                    tk.Label(
                        row, text=details, bg=theme.bg3, fg=theme.fg2,
                        font=(UI_FONT, 12), anchor="w",
                        wraplength=420, justify="left",
                    ).pack(anchor="w", pady=(2, 0))

                # Undo button — only for the most recent entry of that profile
                if has_snapshot and real_idx == len(profile.changelog) - 1:
                    _prof = profile
                    _idx = real_idx
                    def _undo(p=_prof, idx=_idx) -> None:
                        p.restore_snapshot(idx)
                        # Also pop from local undo stack if it matches
                        if self._undo_stack and self._undo_stack[-1][0] is p:
                            self._undo_stack.pop()
                        self._pending_count = max(0, self._pending_count - 1)
                        _rebuild_entries()
                        self._refresh_diff()
                        save_profile_state(p)

                    _make_btn(
                        row, "\u21a9 Undo this change", _undo,
                        bg=theme.bg4, fg=theme.warning,
                        font=(UI_FONT, 12), padx=10, pady=4,
                    ).pack(anchor="w", pady=(6, 2))

        _rebuild_entries()

        _make_btn(
            dlg, "Close", dlg.destroy,
            bg=theme.bg4, fg=theme.fg2,
            font=(UI_FONT, 12), padx=12, pady=5,
        ).pack(pady=(4, 12))

        dlg.update_idletasks()
        w = min(max(dlg.winfo_reqwidth(), 420), 580)
        h = min(max(dlg.winfo_reqheight(), 200), 520)
        x = self.winfo_rootx() + 60
        y = self.winfo_rooty() + 60
        dlg.geometry(f"{w}x{h}+{x}+{y}")

    # ── Delta computation ───────────────────────────────────────

    @staticmethod
    def _compute_delta(val_a: Any, val_b: Any) -> str:
        """Compute a percentage delta string for numeric values. Empty if non-numeric."""
        try:
            fa = float(val_a) if not isinstance(val_a, (list, dict, bool)) else None
            fb = float(val_b) if not isinstance(val_b, (list, dict, bool)) else None
        except (TypeError, ValueError):
            return ""
        if fa is None or fb is None:
            return ""
        if fa == 0 and fb == 0:
            return ""
        if fa == 0:
            return "+\u221E" if fb > 0 else "\u2212\u221E"
        pct = ((fb - fa) / abs(fa)) * 100
        if abs(pct) < 0.5:
            return ""
        sign = "+" if pct > 0 else "\u2212"
        return f"{sign}{abs(pct):.0f}%"

    # ── Formatting helpers ──────────────────────────────────────

    def _fmt(self, value: Any, key: Optional[str] = None) -> str:
        if value is None:
            return "\u2014"  # em-dash for missing values
        # Handle string "nil" from slicer JSON — treat as not set
        if isinstance(value, str) and value.strip().lower() == "nil":
            return "\u2014"
        if isinstance(value, list):
            unique = list(dict.fromkeys(str(x) for x in value))
            # Filter out "nil" entries
            unique = [x for x in unique if x.strip().lower() != "nil"]
            if not unique:
                return "\u2014"
            if len(unique) == 1:
                raw = unique[0]
                if key and key in ENUM_VALUES:
                    return _get_enum_human_label(key, raw)
                return raw
            return ", ".join(unique)
        if isinstance(value, bool):
            return "Yes" if value else "No"
        s = str(value)
        if key and key in ENUM_VALUES:
            return _get_enum_human_label(key, s)
        return s[:_VALUE_TRUNCATE_LONG] + "..." if len(s) > _VALUE_TRUNCATE_LONG else s

    @staticmethod
    def _truncate_name(name: str, max_len: int) -> str:
        return name if len(name) <= max_len else name[:max_len - 1] + "\u2026"
