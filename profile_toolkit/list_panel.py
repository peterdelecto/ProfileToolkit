# Profile list panel — extracted from panels.py

from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Optional

from .constants import (
    _PLATFORM,
    _TREE_TOOLTIP_DELAY_MS,
    SLICER_SHORT_LABELS,
    UI_FONT,
)
from .theme import Theme
from .models import Profile
from .widgets import make_btn as _make_btn, Tooltip as _Tooltip
from .detail_panel import ProfileDetailPanel

logger = logging.getLogger(__name__)


class ProfileListPanel(tk.Frame):
    """Left panel with a list of profiles and a detail viewer on the right."""

    def __init__(
        self, parent: tk.Widget, theme: Theme, profile_type: str, app: Any
    ) -> None:
        super().__init__(parent, bg=theme.bg)
        self.theme = theme
        self.profile_type = profile_type  # "process" or "filament"
        self.app = app
        self.profiles = []
        self._mode = "detail"  # "detail" or "convert"

        self._build()

    def _build(self) -> None:
        theme = self.theme

        paned = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=theme.border,
            sashwidth=8,
            sashrelief="flat",
            opaqueresize=True,
        )
        paned.pack(fill="both", expand=True)
        self._paned = paned

        left = tk.Frame(paned, bg=theme.bg2)
        paned.add(left, minsize=320, stretch="always")
        # Set left pane to 40% of available width once layout is ready
        self.after(50, self._set_initial_sash)
        # Re-fire when panel is first mapped (handles initially-hidden tabs)
        self._sash_needs_init = True
        self.bind("<Map>", self._on_map_sash, add="+")

        self._build_filter(left)
        self._build_tree(left)
        self._build_actions(left)

        # ── Right: container holds both detail and convert panels (stacked via grid) ──
        self._right_container = tk.Frame(paned, bg=theme.bg)
        paned.add(self._right_container, minsize=300, stretch="always")
        self._right_container.grid_rowconfigure(0, weight=1)
        self._right_container.grid_columnconfigure(0, weight=1)

        self.detail = ProfileDetailPanel(
            self._right_container,
            theme,
            icons=self.app.icons if self.app else None,
            icons_sm=self.app.icons_sm if self.app else None,
        )
        self.detail.grid(row=0, column=0, sticky="nsew")

        from .convert_panel import ConvertDetailPanel

        self.convert_detail = ConvertDetailPanel(self._right_container, theme, self.app)
        self.convert_detail.grid(row=0, column=0, sticky="nsew")

        # Detail panel on top by default
        self.detail.tkraise()

        # Register filter trace now that tree exists (debounced)
        self._filter_after_id = None

        def _debounced_refresh(*args):
            if self._filter_after_id:
                self.after_cancel(self._filter_after_id)
            self._filter_after_id = self.after(150, self._refresh_list)

        self._filter_trace_id = self._filter_var.trace_add("write", _debounced_refresh)
        self.bind("<Destroy>", self._on_destroy_list_panel, add="+")

        # Overlay state
        self._overlay = None

    def _on_destroy_list_panel(self, event=None) -> None:
        """Remove StringVar traces to prevent leaks on panel recreation."""
        if event and event.widget is not self:
            return
        try:
            self._filter_var.trace_remove("write", self._filter_trace_id)
        except (tk.TclError, ValueError, AttributeError):
            pass

    def _set_initial_sash(self) -> None:
        """Position sash at 40% of panel width on first render."""
        w = self._paned.winfo_width()
        if w > 1:
            self._paned.sash_place(0, int(w * 0.4), 0)
            self._sash_needs_init = False

    def _on_map_sash(self, event=None) -> None:
        """Re-apply sash position when panel is first mapped (for initially-hidden tabs)."""
        if self._sash_needs_init:
            self.after(50, self._set_initial_sash)

    def set_mode(self, mode: str) -> None:
        """Switch right pane between 'detail' and 'convert' modes.

        Both panels live in _right_container stacked via grid.
        tkraise() swaps visibility without touching the PanedWindow,
        so sash position and left pane are completely untouched.
        """
        if mode == self._mode:
            return

        self._mode = mode

        if mode == "convert":
            self.convert_detail.tkraise()
        else:
            self.detail.tkraise()

        # Refresh the right panel for current selection
        self._on_select()

    # ── SECTION: Filter UI ──

    def _build_filter(self, parent: tk.Widget) -> None:
        theme = self.theme

        # ── Filter row ──
        filter_frame = tk.Frame(
            parent, bg=theme.bg3, highlightbackground=theme.border, highlightthickness=1
        )
        filter_frame.pack(fill="x", padx=6, pady=(0, 4))
        _search_icon = (
            self.app.icons_sm.search if (self.app and self.app.icons_sm) else None
        )
        if _search_icon:
            tk.Label(filter_frame, image=_search_icon, bg=theme.bg3, padx=6).pack(
                side="left"
            )
        else:
            tk.Label(
                filter_frame,
                text="\u2315",
                bg=theme.bg3,
                fg=theme.fg3,
                font=(UI_FONT, 14),
                padx=6,
            ).pack(side="left")
        self._filter_var = tk.StringVar()
        self._filter = tk.Entry(
            filter_frame,
            textvariable=self._filter_var,
            bg=theme.bg3,
            fg=theme.fg,
            insertbackground=theme.fg,
            highlightthickness=0,
            font=(UI_FONT, 13),
            relief="flat",
            bd=0,
        )
        self._filter.pack(side="left", fill="x", expand=True, ipady=4)
        self._filter.insert(0, "Search profiles\u2026")
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
            "Status": "status",
        }
        self._filter_labels = list(filter_options.keys())
        self._filter_values = list(filter_options.values())
        self._filter_col_var = tk.StringVar(value=self._filter_labels[0])
        self._filter_by = "none"

        filter_dd_frame = tk.Frame(parent, bg=theme.bg2)
        filter_dd_frame.pack(fill="x", padx=6, pady=(0, 4))
        tk.Label(
            filter_dd_frame,
            text="Filter:",
            bg=theme.bg2,
            fg=theme.fg3,
            font=(UI_FONT, 13),
        ).pack(side="left", padx=(2, 6))
        filter_cb = ttk.Combobox(
            filter_dd_frame,
            textvariable=self._filter_col_var,
            values=self._filter_labels,
            state="readonly",
            style="Param.TCombobox",
            font=(UI_FONT, 13),
            width=16,
        )
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
            self._filter.insert(0, "Search profiles\u2026")
            self._filter.configure(
                fg=self.theme.placeholder_fg, font=(UI_FONT, 13, "italic")
            )

    def _on_filter_change(self, event: Optional[tk.Event] = None) -> None:
        try:
            idx = self._filter_labels.index(self._filter_col_var.get())
        except ValueError:
            idx = 0  # Fall back to "All columns"
        self._filter_by = self._filter_values[idx]
        if self._filter_after_id:
            self.after_cancel(self._filter_after_id)
        self._filter_after_id = self.after(150, self._refresh_list)

    # ── SECTION: Treeview Rendering and Sorting ──

    def _build_tree(self, parent: tk.Widget) -> None:
        theme = self.theme
        self._rename_active = False  # Guard against overlapping rename operations

        # ── Treeview (must exist before trace) ──
        tree_frame = tk.Frame(parent, bg=theme.bg2)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self._tree_frame = tree_frame  # Keep reference for overlay

        # Generate slicer badge images (colored circles with letter)
        self._slicer_badge_images = self._create_slicer_badges()

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("name", "manufacturer", "material", "printer", "status"),
            show="tree headings",
            selectmode="extended",
        )
        # #0 column: slicer badge image
        self.tree.heading(
            "#0", text="", command=lambda: self._on_heading_click("slicer")
        )
        self.tree.column("#0", width=36, minwidth=36, stretch=False, anchor="center")

        self._sort_col = None  # Currently sorted column (None = insertion order)
        self._sort_asc = True  # Sort direction

        col_defs = [
            ("name", "Profile Name", 260, 140, True),
            ("manufacturer", "Manufacturer", 110, 70, True),
            ("material", "Material", 90, 60, True),
            ("printer", "Printer", 130, 80, True),
            ("status", "Status", 90, 60, False),
        ]
        # Full and abbreviated heading labels (include #0 as "slicer" for sort)
        self._col_labels_full = {c: t for c, t, *_ in col_defs}
        self._col_labels_full["slicer"] = ""
        self._col_labels_short = {
            "slicer": "",
            "name": "Name",
            "manufacturer": "Brand",
            "material": "Type",
            "printer": "Printer",
            "status": "Status",
        }
        for col_id, col_text, width, minw, stretch in col_defs:
            self.tree.heading(
                col_id,
                text=col_text,
                command=lambda c=col_id: self._on_heading_click(c),
            )
            self.tree.column(col_id, width=width, minwidth=minw, stretch=stretch)
        # Tag styles for alternating rows and colored status
        self.tree.tag_configure("row_even", background=theme.bg2)
        self.tree.tag_configure("row_odd", background=theme.bg3)
        self.tree.tag_configure("status_universal", foreground=theme.fg)
        self.tree.tag_configure("status_locked", foreground=theme.locked)
        self.tree.tag_configure("status_converted", foreground=theme.modified)

        tree_scrollbar = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=tree_scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click_rename)
        self.tree.bind("<Configure>", self._on_tree_configure)

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
        self.tree.bind("<MouseWheel>", self._on_tree_leave)
        self.tree.bind("<Button-4>", self._on_tree_leave)  # Linux scroll up
        self.tree.bind("<Button-5>", self._on_tree_leave)  # Linux scroll down

    def _heading_label(self, col_id: str) -> str:
        """Return full or abbreviated heading based on current column width."""
        import tkinter.font as tkfont

        w = self.tree.column(col_id, "width")
        full = self._col_labels_full[col_id]
        short = self._col_labels_short[col_id]
        font = tkfont.nametofont("TkDefaultFont")
        # Add padding for sort arrow + margins
        if font.measure(full) + 24 > w and short != full:
            return short
        return full

    def _on_tree_configure(self, _event=None) -> None:
        """Update heading text when columns are resized."""
        for col_id in self.tree["columns"]:
            label = self._heading_label(col_id)
            arrow = ""
            if self._sort_col == col_id:
                arrow = " \u25b4" if self._sort_asc else " \u25be"
            self.tree.heading(col_id, text=label + arrow)
        # Update #0 (slicer) heading arrow
        slicer_arrow = ""
        if self._sort_col == "slicer":
            slicer_arrow = "\u25b4" if self._sort_asc else "\u25be"
        self.tree.heading("#0", text=slicer_arrow)

    def _on_heading_click(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        for c in self.tree["columns"]:
            label = self._heading_label(c)
            arrow = ""
            if c == col:
                arrow = " \u25b4" if self._sort_asc else " \u25be"
            self.tree.heading(c, text=label + arrow)
        # Update #0 (slicer) heading arrow
        slicer_arrow = ""
        if col == "slicer":
            slicer_arrow = "\u25b4" if self._sort_asc else "\u25be"
        self.tree.heading("#0", text=slicer_arrow)

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
        elif col == "status":
            text, _ = self._profile_status(profile)
            return text.lower()
        elif col == "slicer":
            return (profile.origin or "").lower()
        return ""

    @staticmethod
    def _profile_status(p: Profile) -> tuple:
        if p.modified:
            return ("Universal", "status_converted")
        elif p.is_locked:
            if p.compatible_printers:
                return ("Printer-Locked", "status_locked")
            else:
                return ("Printer-Locked", "status_locked")
        else:
            return ("Modified", "status_universal")

    # Slicer badge letters for the tree column
    _SLICER_LETTERS = {
        "PrusaSlicer": "P",
        "BambuStudio": "B",
        "OrcaSlicer": "O",
    }

    @staticmethod
    def _create_slicer_badges() -> dict[str, tk.PhotoImage]:
        """Generate 20x20 colored circle badge images with slicer letters."""
        badges = {}
        specs = {
            "PrusaSlicer": ("#FF7B15", "P"),
            "BambuStudio": ("#028A0F", "B"),
            "OrcaSlicer": ("#2196F3", "O"),
        }
        size = 20
        for origin, (color, letter) in specs.items():
            img = tk.PhotoImage(width=size, height=size)
            # Parse hex color
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            cx, cy, radius = size // 2, size // 2, size // 2 - 1
            for y in range(size):
                for x in range(size):
                    dx, dy = x - cx, y - cy
                    if dx * dx + dy * dy <= radius * radius:
                        img.put(color, (x, y))
            # Draw letter (white) -- simple 5x7 bitmap font for P, B, O
            glyphs = {
                "P": [
                    "####.",
                    "#...#",
                    "#...#",
                    "####.",
                    "#....",
                    "#....",
                    "#....",
                ],
                "B": [
                    "####.",
                    "#...#",
                    "#...#",
                    "####.",
                    "#...#",
                    "#...#",
                    "####.",
                ],
                "O": [
                    ".###.",
                    "#...#",
                    "#...#",
                    "#...#",
                    "#...#",
                    "#...#",
                    ".###.",
                ],
            }
            glyph = glyphs.get(letter, [])
            gw, gh = 5, 7
            ox, oy = cx - gw // 2, cy - gh // 2
            for gy, row_str in enumerate(glyph):
                for gx, ch in enumerate(row_str):
                    if ch == "#":
                        px, py = ox + gx, oy + gy
                        if 0 <= px < size and 0 <= py < size:
                            img.put("#FFFFFF", (px, py))
            badges[origin] = img
        return badges

    def _insert_profile_row(
        self, profile_idx: int, profile: Profile, row_idx: int
    ) -> None:
        status, status_tag = self._profile_status(profile)
        alt_tag = "row_even" if row_idx % 2 == 0 else "row_odd"
        badge_img = self._slicer_badge_images.get(profile.origin)
        self.tree.insert(
            "",
            "end",
            iid=str(profile_idx),
            text="",
            image=badge_img or "",
            values=(
                profile.name,
                profile.manufacturer_group or "\u2014",
                profile.material_group or "\u2014",
                profile.printer_group or "\u2014",
                status,
            ),
            tags=(alt_tag, status_tag),
        )

    def _refresh_list(self) -> None:
        """Refresh the treeview with filtered and sorted profiles.

        Preserves selection across rebuilds when possible. If previously
        selected item IDs are still present after filtering, they are
        re-selected. Otherwise falls back to selecting the first item.
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
                    searchable = (
                        f"{profile.name} {profile.origin} {profile.source_label} "
                        f"{status_text} {profile.material_group} "
                        f"{profile.printer_group} {profile.manufacturer_group}"
                    ).lower()
                elif filter_col == "printer":
                    searchable = (profile.printer_group or "").lower()
                elif filter_col == "manufacturer":
                    searchable = (profile.manufacturer_group or "").lower()
                elif filter_col == "material":
                    searchable = (profile.material_group or "").lower()
                elif filter_col == "status":
                    searchable = status_text.lower()
                else:
                    searchable = profile.name.lower()
                if filter_text not in searchable:
                    continue
            visible.append((i, profile))

        if self._sort_col:
            visible.sort(
                key=lambda item: self._sort_key_for_profile(item[1]),
                reverse=not self._sort_asc,
            )

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
        # Always notify -- selection may have shrunk to 0 (empty tree) or changed count
        self._on_select()

    def _on_select(self, event: Optional[tk.Event] = None) -> None:
        sel = self.tree.selection()

        if len(sel) == 1:
            idx = int(sel[0])
            if idx < len(self.profiles):
                if self._mode == "convert":
                    self.convert_detail.show_profile(self.profiles[idx])
                else:
                    self.detail.show_profile(self.profiles[idx])
            else:
                self.detail._show_placeholder()
        elif len(sel) > 1:
            if self._mode == "detail":
                self.detail._show_placeholder(
                    f"{len(sel)} profiles selected.\nSelect one to view, or two to compare."
                )
            else:
                self.convert_detail.clear()
        else:
            if self._mode == "detail":
                self.detail._show_placeholder()
            else:
                self.convert_detail.clear()

        # Notify app about selection change (for Compare Filament auto-launch)
        if self.app and self.profile_type == "filament":
            if hasattr(self.app, "_on_filament_selection_changed"):
                self.app._on_filament_selection_changed()

    # ── SECTION: Overlay Status UI ──

    def _show_overlay(
        self, text: str, show_spinner: bool = False, show_progress: bool = False
    ) -> None:
        self._hide_overlay()
        theme = self.theme
        overlay = tk.Frame(self._tree_frame, bg=theme.bg2)
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        inner = tk.Frame(overlay, bg=theme.bg2)
        inner.place(relx=0.5, rely=0.4, anchor="center")
        if show_spinner:
            _hg_icon = (
                self.app.icons.hourglass if (self.app and self.app.icons) else None
            )
            if _hg_icon:
                self._spinner_label = tk.Label(inner, image=_hg_icon, bg=theme.bg2)
            else:
                self._spinner_label = tk.Label(
                    inner, text="\u23f3", bg=theme.bg2, fg=theme.fg3, font=(UI_FONT, 28)
                )
            self._spinner_label.pack()
            self._spinner_chars = ["\u23f3", "\u2699", "\u25e6", "\u2022"]
            self._spinner_idx = 0
            self._spinner_animate()
        self._overlay_text = tk.Label(
            inner,
            text=text,
            bg=theme.bg2,
            fg=theme.fg2,
            font=(UI_FONT, 14),
            wraplength=350,
            justify="center",
        )
        self._overlay_text.pack(pady=(4, 0))

        # Determinate progress bar
        self._progress_canvas = None
        if show_progress:
            bar_frame = tk.Frame(inner, bg=theme.bg2)
            bar_frame.pack(pady=(10, 0))
            bar_w, bar_h = 280, 10
            canvas = tk.Canvas(
                bar_frame,
                width=bar_w,
                height=bar_h,
                bg=theme.bg4,
                highlightthickness=0,
                bd=0,
            )
            canvas.pack()
            canvas.create_rectangle(
                0, 0, 0, bar_h, fill=theme.accent, outline="", tags="fill"
            )
            self._progress_canvas = canvas
            self._progress_bar_w = bar_w
            self._progress_bar_h = bar_h

        self._overlay = overlay

    def _update_overlay_text(self, text: str) -> None:
        if self._overlay and hasattr(self, "_overlay_text"):
            try:
                self._overlay_text.configure(text=text)
            except tk.TclError:
                pass

    def _update_overlay_progress(self, current: int, total: int) -> None:
        """Update the determinate progress bar fill."""
        canvas = getattr(self, "_progress_canvas", None)
        if not canvas or not self._overlay:
            return
        try:
            frac = current / max(total, 1)
            fill_w = int(self._progress_bar_w * frac)
            canvas.coords("fill", 0, 0, fill_w, self._progress_bar_h)
        except tk.TclError:
            pass

    def _spinner_animate(self) -> None:
        if not self._overlay or not hasattr(self, "_spinner_label"):
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
            if idx >= len(self.profiles):
                return
            # Don't show tooltips when app isn't focused -- avoids
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
            tk.Label(
                tooltip_window,
                text=f"{tip_text}\n(double-click to rename)",
                bg=self.theme.bg4,
                fg=self.theme.fg,
                font=(UI_FONT, 12),
                padx=8,
                pady=4,
                relief="solid",
                bd=1,
                justify="left",
            ).pack()
            self._tree_tip = tooltip_window

        self._tree_tip_after = self.tree.after(_TREE_TOOLTIP_DELAY_MS, _show)

    def _on_tree_leave(self, event: tk.Event) -> None:
        if self._tree_tip_after:
            self.tree.after_cancel(self._tree_tip_after)
            self._tree_tip_after = None
        if self._tree_tip:
            self._tree_tip.destroy()
            self._tree_tip = None

    # ── SECTION: Actions and Context Menu ──

    def _build_actions(self, parent: tk.Widget) -> None:
        theme = self.theme

        # ── Action rows below treeview ──
        # Row 1: list management (left) + utility (right)
        action_row1 = tk.Frame(parent, bg=theme.bg2)
        action_row1.pack(fill="x", padx=6, pady=(0, 2))
        _make_btn(
            action_row1,
            "Clear All...",
            lambda: self.app._on_clear_list(),
            bg=theme.bg4,
            fg=theme.warning,
            font=(UI_FONT, 12),
            padx=8,
            pady=3,
        ).pack(side="left", padx=(0, 4))
        _make_btn(
            action_row1,
            "Remove from List",
            lambda: self.app._on_remove(),
            bg=theme.bg4,
            fg=theme.warning,
            font=(UI_FONT, 12),
            padx=8,
            pady=3,
        ).pack(side="left", padx=(0, 4))
        _make_btn(
            action_row1,
            "Show Source Folder",
            lambda: self.app._on_show_folder(),
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 12),
            padx=8,
            pady=3,
        ).pack(side="right", padx=(0, 8))
        _make_btn(
            action_row1,
            "Batch Rename",
            lambda: self._on_batch_rename(),
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 12),
            padx=8,
            pady=3,
        ).pack(side="right", padx=(0, 4))

        # Thin separator between secondary and primary actions
        tk.Frame(parent, bg=theme.border, height=1).pack(fill="x", padx=6, pady=(2, 2))

        # Row 2: primary unlock action
        action_row2 = tk.Frame(parent, bg=theme.bg2)
        action_row2.pack(fill="x", padx=6, pady=(0, 4))
        unlock_btn = _make_btn(
            action_row2,
            "Make Universal",
            lambda: self.app._on_unlock(),
            bg=theme.accent2,
            fg=theme.accent_fg,
            font=(UI_FONT, 12, "bold"),
            padx=8,
            pady=4,
        )
        unlock_btn.pack(side="right", padx=(0, 4))
        _Tooltip(
            unlock_btn,
            "Remove printer restriction so this profile works on any printer",
            theme=theme,
        )
        _make_btn(
            action_row2,
            "Delete from Disk",
            lambda: self._on_delete_from_disk(),
            bg=theme.error,
            fg=theme.accent_fg,
            font=(UI_FONT, 12, "bold"),
            padx=8,
            pady=4,
        ).pack(side="left", padx=(4, 0))

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

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=theme.bg3,
            fg=theme.fg,
            activebackground=theme.accent,
            activeforeground=theme.accent_fg,
            font=(UI_FONT, 12),
        )

        count = len(sel)
        sel_profiles = self.get_selected_profiles()

        # ── Primary actions ──
        menu.add_command(
            label=f"Make {count} profile{'s' if count > 1 else ''} universal...",
            command=self.app._on_unlock,
        )
        menu.add_command(
            label=f"Export {count} profile{'s' if count > 1 else ''}...",
            command=self.app._on_export,
        )

        # Export to Slicer submenu
        slicers = self.app.detected_slicers
        if slicers:
            slicer_menu = tk.Menu(
                menu,
                tearoff=0,
                bg=theme.bg3,
                fg=theme.fg,
                activebackground=theme.accent,
                activeforeground=theme.accent_fg,
                font=(UI_FONT, 12),
            )
            for name, path in slicers.items():
                slicer_menu.add_command(
                    label=name,
                    command=lambda n=name, p=path: self.app._on_install_to_slicer(n, p),
                )
            menu.add_cascade(label="Export to Slicer", menu=slicer_menu)

        # Convert to Slicer submenu (single selection only)
        if count == 1:
            profile = sel_profiles[0]
            convert_targets = ["PrusaSlicer", "BambuStudio", "OrcaSlicer"]
            convert_menu = tk.Menu(
                menu,
                tearoff=0,
                bg=theme.bg3,
                fg=theme.fg,
                activebackground=theme.accent,
                activeforeground=theme.accent_fg,
                font=(UI_FONT, 12),
            )
            for target in convert_targets:
                if target == profile.origin:
                    continue
                short = SLICER_SHORT_LABELS.get(target, target)
                convert_menu.add_command(
                    label=short,
                    command=lambda t=target, p=profile: self.app._on_convert_profile(
                        p, t
                    ),
                )
            menu.add_cascade(label="Convert to...", menu=convert_menu)

        # ── Edit ──
        menu.add_separator()
        if count == 1:
            menu.add_command(label="Rename", command=self._rename_selected)
        if count >= 2:
            menu.add_command(label="Batch Rename...", command=self._on_batch_rename)
        if count == 1:
            menu.add_command(
                label="Duplicate", command=self.app._on_create_from_profile
            )

        # ── View ──
        menu.add_separator()
        if count == 2:
            menu.add_command(
                label="Compare",
                command=lambda: self.app._launch_compare(
                    sel_profiles[0], sel_profiles[1]
                ),
            )
        menu.add_command(label="Show Source Folder", command=self.app._on_show_folder)
        if len(sel_profiles) == 1:
            p = sel_profiles[0]
            hist_n = len(p.changelog) if p.changelog else 0
            menu.add_command(
                label=f"Change History ({hist_n} changes)",
                command=lambda p=p: self.detail._show_changelog(p),
            )

        # ── Remove ──
        menu.add_separator()
        menu.add_command(label="Remove from list", command=self.app._on_remove)
        menu.add_command(
            label="\u26a0 Delete from disk...",
            command=lambda: self._on_delete_from_disk(),
        )

        menu.tk_popup(event.x_root, event.y_root)

    # ── SECTION: Inline and Batch Rename ──

    def _on_batch_rename(self) -> None:
        """Open batch rename dialog for selected profiles."""
        from .dialogs import BatchRenameDialog

        selected = self.get_selected_profiles()
        if not selected:
            messagebox.showinfo(
                "No Selection",
                "Select profiles to rename. Click one or more profiles in the list, then try again.",
                parent=self,
            )
            return
        BatchRenameDialog(self, self.theme, selected, self._refresh_list)

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
            return  # Another rename is in progress -- prevent race condition
        self._rename_active = True
        theme = self.theme
        profile = self.profiles[idx]

        # Get the bounding box of the "name" column for this item
        try:
            bbox = self.tree.bbox(iid, column="name")
        except tk.TclError as e:
            logger.debug("Failed to get bbox for rename: %s", e)
            self._rename_active = False
            return
        if not bbox:
            self._rename_active = False
            return
        x, y, w, h = bbox

        name_var = tk.StringVar(value=profile.name)
        entry = tk.Entry(
            self.tree,
            textvariable=name_var,
            bg=theme.bg3,
            fg=theme.fg,
            insertbackground=theme.fg,
            font=(UI_FONT, 12),
            highlightbackground=theme.accent,
            highlightthickness=1,
            relief="flat",
        )
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.select_range(0, "end")

        def _finish(event: Optional[tk.Event] = None) -> None:
            if getattr(self, "_rename_finishing", False):
                return
            self._rename_finishing = True
            try:
                self._rename_active = False
                new_name = Profile.sanitize_name(name_var.get())
                entry.destroy()
                if new_name and new_name != profile.name:
                    # Check for duplicate names
                    duplicate = any(
                        p.name == new_name for p in self.profiles if p is not profile
                    )
                    if duplicate:
                        messagebox.showwarning(
                            "Duplicate Name",
                            f'A profile named "{new_name}" already exists.',
                            parent=self.tree,
                        )
                        return
                    old_name = profile.name
                    snapshot = {"name": old_name, "_modified": profile.modified}
                    profile.data["name"] = new_name
                    profile.modified = True
                    profile.log_change(
                        "Renamed", f"{old_name} \u2192 {new_name}", snapshot=snapshot
                    )
                    self._refresh_list()
                    # Re-select and show updated profile
                    try:
                        self.tree.selection_set(str(idx))
                    except tk.TclError:
                        pass
                    self._on_select()
            finally:
                self._rename_finishing = False

        def _cancel(event: Optional[tk.Event] = None) -> None:
            self._rename_finishing = True
            self._rename_active = False
            try:
                entry.destroy()
            except tk.TclError:
                pass
            finally:
                self._rename_finishing = False

        entry.bind("<Return>", _finish)
        entry.bind("<FocusOut>", _finish)
        entry.bind("<Escape>", _cancel)

    def _on_double_click_rename(self, event: tk.Event) -> str:
        col = self.tree.identify_column(event.x)
        if col != "#0" and col != "#1":  # Only trigger on icon/name column
            return ""
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
        if (
            hasattr(self, "_mode")
            and self._mode == "convert"
            and hasattr(self, "convert_detail")
        ):
            self.convert_detail.clear()
        # Notify app that selection changed (clears comparison cache)
        if self.app and self.profile_type == "filament":
            if hasattr(self.app, "_on_filament_selection_changed"):
                self.app._on_filament_selection_changed()

    def select_all(self) -> None:
        all_items = list(self.tree.get_children())
        if all_items:
            self.tree.selection_set(all_items)
            self._on_select()

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
            messagebox.showinfo(
                "Nothing to delete",
                "No source files found on disk for the selected profiles.",
            )
            return

        # Build confirmation message
        count = len(paths)
        if count == 1:
            name, fpath = paths[0]
            msg = (
                f"Permanently delete this profile?\n\n"
                f"  {os.path.basename(fpath)}\n\n"
                f"Location: {os.path.dirname(fpath)}\n\n"
                f"This cannot be undone."
            )
        else:
            file_list = "\n".join(
                f"  \u2022 {os.path.basename(fp)}" for _, fp in paths[:8]
            )
            if count > 8:
                file_list += f"\n  ... and {count - 8} more"
            msg = (
                f"Permanently delete {count} profiles?\n\n"
                f"{file_list}\n\n"
                f"This cannot be undone."
            )

        confirmed = messagebox.askyesno(
            "Permanently Delete from Disk", msg, icon="warning"
        )
        if not confirmed:
            return

        deleted = 0
        errors = []
        successfully_deleted = []
        for name, fpath in paths:
            try:
                fpath = os.path.realpath(fpath)
                # Reject paths outside user's home or containing suspicious traversal
                if ".." in os.path.relpath(fpath, os.path.expanduser("~")):
                    errors.append(
                        f"{os.path.basename(fpath)}: path outside home directory"
                    )
                    continue
                os.remove(fpath)
                deleted += 1
                successfully_deleted.append(fpath)
            except OSError as e:
                errors.append(f"{os.path.basename(fpath)}: {e.strerror}")

        # Only remove profiles whose files were successfully deleted
        if successfully_deleted:
            deleted_set = set(successfully_deleted)
            indices_to_remove = [
                i for i, p in enumerate(self.profiles) if p.source_path in deleted_set
            ]
            for i in sorted(indices_to_remove, reverse=True):
                self.profiles.pop(i)
            self._refresh_list()
            self.detail._show_placeholder()
            if (
                hasattr(self, "_mode")
                and self._mode == "convert"
                and hasattr(self, "convert_detail")
            ):
                self.convert_detail.clear()

        if errors:
            messagebox.showwarning("Some files could not be deleted", "\n".join(errors))
        if deleted:
            self.app._update_status(
                f"Deleted {deleted} file{'s' if deleted != 1 else ''} from disk."
            )

    def _on_clear(self) -> None:
        if self.profiles:
            self.profiles.clear()
            self._refresh_list()
            self.detail._show_placeholder()
            if (
                hasattr(self, "_mode")
                and self._mode == "convert"
                and hasattr(self, "convert_detail")
            ):
                self.convert_detail.clear()
            # Notify app that selection is now empty (cache must clear)
            if self.app and self.profile_type == "filament":
                if hasattr(self.app, "_on_filament_selection_changed"):
                    self.app._on_filament_selection_changed()
            self.app._update_status("List cleared.")
