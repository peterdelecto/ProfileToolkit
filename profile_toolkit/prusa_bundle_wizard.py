"""PrusaBundleWizard — import filament profiles from PrusaSlicer bundles."""

from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Any, Callable, Optional

from .constants import UI_FONT
from .theme import Theme
from .models import ProfileEngine
from .utils import lighten_color
from .widgets import make_btn, ScrollableFrame

logger = logging.getLogger(__name__)


class PrusaBundleWizard(tk.Toplevel):
    """2-step wizard for importing filament profiles from a PrusaSlicer factory bundle.

    Step 1: Select printer families (CORE One, MK4S, etc.)
    Step 2: Select filament profiles (filtered by selected printers)
    Result: list of selected filament section names, or None if cancelled.
    """

    def __init__(self, parent: tk.Widget, theme: Theme, bundle_path: str) -> None:
        super().__init__(parent)
        self.theme = theme
        self.bundle_path = bundle_path
        self.result: list[str] | None = None

        self.title("Import Prusa Factory Profiles")
        self.configure(bg=theme.bg)
        self.geometry("620x520")
        self.minsize(500, 400)
        self.transient(parent)
        self.grab_set()

        self._body = tk.Frame(self, bg=theme.bg)
        self._body.pack(fill="both", expand=True, padx=16, pady=(10, 0))

        self._btn_frame = tk.Frame(self, bg=theme.bg)
        self._btn_frame.pack(fill="x", padx=16, pady=10)

        # Show loading state while parsing bundle in background
        self._loading_label = tk.Label(
            self._body,
            text="Loading bundle...",
            bg=theme.bg,
            fg=theme.fg,
            font=(UI_FONT, 14),
        )
        self._loading_label.pack(expand=True)

        self._sections: dict = {}
        self._all_filaments: list[str] = []
        self._matching_filaments: list[str] = []
        self.parsed_sections: dict | None = None  # expose to caller to avoid re-parse

        # Parse in background thread, poll for completion from main thread
        import threading

        self._parse_result: list | None = None
        self._parse_error: str | None = None
        self._poll_count: int = 0
        self._bundle_path = bundle_path

        def _parse():
            try:
                sections = ProfileEngine.parse_prusa_bundle(bundle_path)
                all_names = sorted(
                    [
                        name
                        for name in sections.get("filaments", {})
                        if not (name.startswith("*") and name.endswith("*"))
                    ]
                )
                self._parse_result = (sections, all_names)
            except Exception as e:
                logger.error("Failed to parse bundle: %s", e, exc_info=True)
                self._parse_error = str(e)
                self._parse_result = {}  # signals completion with error

        threading.Thread(target=_parse, daemon=True).start()
        self._poll_parse()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.wait_window(self)

    def _poll_parse(self) -> None:
        """Poll for background parse completion from the main thread."""
        self._poll_count += 1
        if self._poll_count > 300:  # 30 seconds at 100ms intervals
            self._show_error(
                "Bundle parsing timed out. The file may be too large or corrupted."
            )
            return
        if self._parse_result is None:
            self.after(100, self._poll_parse)
            return
        if self._parse_error:
            self._show_error(f"Failed to parse bundle:\n{self._parse_error}")
            return
        sections, all_names = self._parse_result
        self._sections = sections
        self.parsed_sections = sections  # cache for caller
        self._all_filaments = all_names
        self._matching_filaments = all_names
        self._loading_label.destroy()
        self._build_filament_list()

    def _show_error(self, msg: str) -> None:
        messagebox.showerror("Bundle Error", msg, parent=self)
        self.destroy()

    def _clear_body(self) -> None:
        for w in self._body.winfo_children():
            w.destroy()

    def _go_back(self) -> None:
        """Navigate back to the filament selection step."""
        self._build_filament_list()
        self._build_nav_buttons(
            back=False, next_label="Import", next_cmd=self._on_import
        )

    def _build_nav_buttons(
        self,
        back: bool = False,
        next_label: str = "Next",
        next_cmd: Callable | None = None,
    ) -> None:
        for w in self._btn_frame.winfo_children():
            w.destroy()
        theme = self.theme

        if back:
            back_btn = make_btn(
                self._btn_frame,
                "Back",
                self._go_back,
                bg=theme.bg4,
                fg=theme.btn_fg,
                font=(UI_FONT, 12),
                padx=14,
                pady=6,
            )
            back_btn.pack(side="left")

        cancel_btn = make_btn(
            self._btn_frame,
            "Cancel",
            self._on_cancel,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 12),
            padx=14,
            pady=6,
        )
        cancel_btn.pack(side="right", padx=(4, 0))

        if next_cmd:
            next_btn = make_btn(
                self._btn_frame,
                next_label,
                next_cmd,
                bg=theme.accent2,
                fg=theme.accent_fg,
                font=(UI_FONT, 12, "bold"),
                padx=14,
                pady=6,
            )
            next_btn.pack(side="right", padx=(4, 0))

    # ── Filament selection (treeview) ──

    def _build_groups(self) -> dict[str, list[str]]:
        """Group filament names by base name (before @)."""
        from collections import OrderedDict

        groups: dict[str, list[str]] = {}
        for name in self._all_filaments:
            base = name.split("@")[0].strip() if "@" in name else name
            groups.setdefault(base, []).append(name)
        return dict(sorted(groups.items()))

    def _build_filament_list(self) -> None:
        self._clear_body()
        theme = self.theme
        self._groups = self._build_groups()

        hdr = tk.Frame(self._body, bg=theme.bg)
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(
            hdr,
            text="Select Filament Profiles",
            bg=theme.bg,
            fg=theme.fg,
            font=(UI_FONT, 15, "bold"),
        ).pack(side="left")
        self._count_lbl = tk.Label(
            hdr, text="", bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12)
        )
        self._count_lbl.pack(side="right")

        ctrl = tk.Frame(self._body, bg=theme.bg)
        ctrl.pack(fill="x", pady=(0, 4))
        sa = make_btn(
            ctrl,
            "Select All",
            self._select_all,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 12),
            padx=10,
            pady=4,
        )
        sa.pack(side="left", padx=(0, 4))
        sn = make_btn(
            ctrl,
            "Select None",
            self._select_none,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 12),
            padx=10,
            pady=4,
        )
        sn.pack(side="left")

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter_tree())
        search = tk.Entry(
            ctrl,
            textvariable=self._search_var,
            bg=theme.bg2,
            fg=theme.fg,
            insertbackground=theme.fg,
            font=(UI_FONT, 12),
            width=20,
        )
        search.pack(side="right", padx=(8, 0))
        tk.Label(
            ctrl, text="Filter:", bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12)
        ).pack(side="right")

        # Treeview with checkmark column
        tree_frame = tk.Frame(self._body, bg=theme.bg)
        tree_frame.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure(
            "Prusa.Treeview",
            background=theme.bg,
            foreground=theme.fg,
            fieldbackground=theme.bg,
            rowheight=24,
            font=(UI_FONT, 12),
        )
        style.configure(
            "Prusa.Treeview.Heading",
            background=theme.bg2,
            foreground=theme.fg,
            font=(UI_FONT, 11, "bold"),
        )
        style.map(
            "Prusa.Treeview",
            background=[("selected", theme.accent)],
            foreground=[("selected", "#FFFFFF")],
        )

        self._tree = ttk.Treeview(
            tree_frame,
            columns=("check",),
            show="tree",
            style="Prusa.Treeview",
            selectmode="none",
        )
        self._tree.column("#0", width=500, stretch=True)
        self._tree.column("check", width=30, anchor="center", stretch=False)

        scrollbar = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self._tree.yview
        )
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Track checked state: all filament names start checked
        self._checked: set[str] = set()

        self._populate_tree(self._groups)
        self._update_count()
        self._tree.bind("<Button-1>", self._on_tree_click)

        self._build_nav_buttons(
            back=False, next_label="Import", next_cmd=self._on_import
        )

    def _populate_tree(self, groups: dict[str, list[str]]) -> None:
        self._tree.delete(*self._tree.get_children())
        for base, variants in groups.items():
            check = (
                "\u2611"
                if all(v in self._checked for v in variants)
                else (
                    "\u2610"
                    if not any(v in self._checked for v in variants)
                    else "\u2592"
                )
            )
            if len(variants) == 1 and variants[0] == base:
                # Single variant — no need for a group
                self._tree.insert(
                    "",
                    "end",
                    iid=base,
                    text=f"  {base}",
                    values=(check,),
                    tags=("leaf",),
                )
            else:
                parent = self._tree.insert(
                    "",
                    "end",
                    iid=f"_grp_{base}",
                    text=f"  {base}",
                    values=(check,),
                    tags=("group",),
                )
                for name in variants:
                    suffix = (
                        name.split("@", 1)[1].strip() if "@" in name else "(generic)"
                    )
                    ch = "\u2611" if name in self._checked else "\u2610"
                    self._tree.insert(
                        parent,
                        "end",
                        iid=name,
                        text=f"  {suffix}",
                        values=(ch,),
                        tags=("leaf",),
                    )

    def _on_tree_click(self, event: tk.Event) -> None:
        item = self._tree.identify_row(event.y)
        if not item:
            return
        tags = self._tree.item(item, "tags")
        if "group" in tags:
            # Toggle all children
            children = self._tree.get_children(item)
            child_names = [c for c in children]
            all_checked = all(c in self._checked for c in child_names)
            for c in child_names:
                if all_checked:
                    self._checked.discard(c)
                else:
                    self._checked.add(c)
        elif "leaf" in tags:
            name = item
            if name in self._checked:
                self._checked.discard(name)
            else:
                self._checked.add(name)
        self._refresh_checks()
        self._update_count()

    def _refresh_checks(self) -> None:
        for item in self._tree.get_children():
            tags = self._tree.item(item, "tags")
            if "group" in tags:
                children = self._tree.get_children(item)
                for c in children:
                    ch = "\u2611" if c in self._checked else "\u2610"
                    self._tree.set(c, "check", ch)
                all_on = all(c in self._checked for c in children)
                none_on = not any(c in self._checked for c in children)
                grp_ch = "\u2611" if all_on else ("\u2610" if none_on else "\u2592")
                self._tree.set(item, "check", grp_ch)
            elif "leaf" in tags:
                ch = "\u2611" if item in self._checked else "\u2610"
                self._tree.set(item, "check", ch)

    def _filter_tree(self) -> None:
        query = self._search_var.get().lower()
        if not query:
            self._populate_tree(self._groups)
            return
        filtered = {}
        for base, variants in self._groups.items():
            matches = [v for v in variants if query in v.lower()]
            if matches:
                filtered[base] = matches
        self._populate_tree(filtered)

    def _update_count(self) -> None:
        count = len(self._checked)
        total = len(self._all_filaments)
        if hasattr(self, "_count_lbl"):
            self._count_lbl.configure(text=f"{count} / {total} selected")

    def _select_all(self) -> None:
        self._checked = set(self._all_filaments)
        self._refresh_checks()
        self._update_count()

    def _select_none(self) -> None:
        self._checked.clear()
        self._refresh_checks()
        self._update_count()

    def _on_import(self) -> None:
        selected = sorted(self._checked)
        if not selected:
            messagebox.showwarning(
                "No Selection", "Select at least one filament profile.", parent=self
            )
            return
        self.result = selected
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
