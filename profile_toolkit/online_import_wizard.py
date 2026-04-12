"""OnlineImportWizard — browse and import profiles from online sources."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import re
import threading
import time
import tkinter as tk
import urllib.error
import webbrowser
from tkinter import ttk, filedialog, messagebox
from typing import Any, Callable, Optional

from .constants import (
    _PLATFORM,
    _WIN_SCROLL_DELTA_DIVISOR,
    FETCH_TIMEOUT_MS,
    UI_FONT,
)
from .theme import Theme
from .models import Profile, SlicerDetector
from .providers import ALL_PROVIDERS, PROVIDER_CATEGORIES, OnlineProfileEntry
from .providers_pkg.base import OnlineProvider
from .state import load_online_prefs, save_online_prefs
from .utils import bind_scroll, lighten_color, user_error
from .widgets import ScrollableFrame, make_btn

logger = logging.getLogger(__name__)


class OnlineImportWizard(tk.Toplevel):
    """3-step wizard: Choose Source -> Browse & Select -> Confirm & Import."""

    _WIDTH: int = 920
    _HEIGHT: int = 560

    def __init__(
        self, parent: tk.Widget, theme: Theme, load_callback: Callable
    ) -> None:
        super().__init__(parent)
        self.theme = theme
        self._load_callback = load_callback
        self.title("Import from Online Sources")
        self.configure(bg=theme.bg)
        self.geometry(f"{self._WIDTH}x{self._HEIGHT}")
        self.minsize(750, 450)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 60, parent.winfo_rooty() + 40))

        self._prefs = load_online_prefs()
        self._current_step = 0
        self._selected_provider = None
        self._catalog = []  # list of OnlineProfileEntry
        self._catalog_provider_id = ""  # provider that fetched current catalog
        self._filtered_catalog = []  # after applying filters
        self._selected_entries = []  # entries user checked
        self._import_status = tk.StringVar(value="")  # download progress text
        self._cancelled = False  # flag for thread cancellation

        # Filter state
        self._filter_material = tk.StringVar(value="All")
        self._filter_brand = tk.StringVar(value="All")
        self._filter_machine = tk.StringVar(value="All")
        self._filter_nozzle = tk.StringVar(value="All")
        self._suppress_filter_trace = False

        # Style comboboxes for dark theme
        self._style_combos()

        self._active_canvas = None  # current scrollable canvas for mousewheel
        self._scroll_bind_id = None
        self._fetch_done = threading.Event()  # thread-safe flag for fetch completion
        self._watchdog_id = None  # after() ID for watchdog cancellation
        self._fetch_last_activity = 0.0  # heartbeat timestamp for watchdog

        self._build_chrome()
        self._init_traces_and_shortcuts()

    def _safe_after(self, ms: int, func) -> None:
        """Schedule callback only if widget still exists (prevents TclError from threads)."""
        try:
            if self.winfo_exists():
                self.after(ms, func)
        except tk.TclError:
            pass

    def _safe_after_id(self, ms: int, func) -> str | None:
        """Like _safe_after but returns the after ID (needed for after_cancel)."""
        try:
            if self.winfo_exists():
                return self.after(ms, func)
        except tk.TclError:
            pass
        return None

    def _init_traces_and_shortcuts(self) -> None:
        """Register filter traces and keyboard shortcuts (called once from __init__)."""
        self._show_step(0)

        # Filter change traces (added once here, guarded in _apply_filters)
        self._trace_ids = []
        self._trace_ids.append(
            (
                self._filter_material,
                self._filter_material.trace_add(
                    "write", lambda *a: self._apply_filters()
                ),
            )
        )
        self._trace_ids.append(
            (
                self._filter_brand,
                self._filter_brand.trace_add("write", lambda *a: self._apply_filters()),
            )
        )
        self._trace_ids.append(
            (
                self._filter_machine,
                self._filter_machine.trace_add(
                    "write", lambda *a: self._apply_filters()
                ),
            )
        )
        self._trace_ids.append(
            (
                self._filter_nozzle,
                self._filter_nozzle.trace_add(
                    "write", lambda *a: self._apply_filters()
                ),
            )
        )

        # Keyboard shortcuts
        self.bind("<Return>", lambda e: self._on_next())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.bind(
            "<Up>", lambda e: self._nav_source(-1) if self._current_step == 0 else None
        )
        self.bind(
            "<Down>", lambda e: self._nav_source(1) if self._current_step == 0 else None
        )

    def _bind_wizard_scroll(self, canvas: tk.Canvas) -> None:
        # Unbind previous (MouseWheel + Linux Button-4/5)
        if self._scroll_bind_id:
            self.unbind("<MouseWheel>", self._scroll_bind_id)
        for attr in ("_scroll_b4_id", "_scroll_b5_id"):
            bid = getattr(self, attr, None)
            if bid:
                self.unbind("<Button-4>" if "b4" in attr else "<Button-5>", bid)
        self._active_canvas = canvas
        is_mac = _PLATFORM == "Darwin"

        def _on_wheel(e: tk.Event) -> None:
            if self._active_canvas:
                if is_mac:
                    self._active_canvas.yview_scroll(int(-1 * e.delta), "units")
                else:
                    units = round(-1 * e.delta / _WIN_SCROLL_DELTA_DIVISOR)
                    if units == 0:
                        units = -1 if e.delta > 0 else 1
                    self._active_canvas.yview_scroll(units, "units")

        self._scroll_bind_id = self.bind("<MouseWheel>", _on_wheel)
        # Also bind Button-4/5 for Linux — track IDs to unbind later
        self._scroll_b4_id = self.bind(
            "<Button-4>", lambda e: canvas.yview_scroll(-3, "units")
        )
        self._scroll_b5_id = self.bind(
            "<Button-5>", lambda e: canvas.yview_scroll(3, "units")
        )

    def _style_combos(self) -> None:
        theme = self.theme
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Dark.TCombobox",
            fieldbackground=theme.bg3,
            background=theme.bg4,
            foreground=theme.fg,
            arrowcolor=theme.fg,
            selectbackground=theme.sel,
            selectforeground=theme.fg,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", theme.bg3)],
            foreground=[("readonly", theme.fg)],
            selectbackground=[("readonly", theme.sel)],
            selectforeground=[("readonly", theme.fg)],
        )
        # Style the dropdown list
        self.option_add("*TCombobox*Listbox.background", theme.bg3)
        self.option_add("*TCombobox*Listbox.foreground", theme.fg)
        self.option_add("*TCombobox*Listbox.selectBackground", theme.accent2)
        self.option_add("*TCombobox*Listbox.selectForeground", theme.accent_fg)

    def _build_chrome(self) -> None:
        theme = self.theme

        # --- Step indicator bar ---
        self._step_bar = tk.Frame(self, bg=theme.bg2)
        self._step_bar.pack(fill="x")
        self._step_labels = []
        steps = ["Source", "Browse & Select", "Confirm & Import"]
        for i, label in enumerate(steps):
            fg = theme.accent if i == 0 else theme.fg3
            font_weight = "bold" if i == 0 else "normal"
            lbl = tk.Label(
                self._step_bar,
                text=f"  {i+1}. {label}  ",
                bg=theme.bg2,
                fg=fg,
                font=(UI_FONT, 12, font_weight),
                padx=8,
                pady=8,
            )
            lbl.pack(side="left")
            self._step_labels.append(lbl)
            if i < len(steps) - 1:
                tk.Label(
                    self._step_bar,
                    text="\u203a",
                    bg=theme.bg2,
                    fg=theme.fg3,
                    font=(UI_FONT, 12),
                ).pack(side="left")

        # --- Separator ---
        tk.Frame(self, bg=theme.border, height=1).pack(fill="x")

        # --- Footer nav buttons (pack bottom-first so they're always visible) ---
        self._footer_sep = tk.Frame(self, bg=theme.border, height=1)
        self._footer_sep.pack(fill="x", side="bottom")
        self._footer = tk.Frame(self, bg=theme.bg2)
        self._footer.pack(fill="x", side="bottom")

        # --- Content area (fills remaining space between step bar and footer) ---
        self._content = tk.Frame(self, bg=theme.bg)
        self._content.pack(fill="both", expand=True)
        self._btn_cancel = make_btn(
            self._footer,
            "Cancel",
            self._on_cancel,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 12),
            padx=14,
            pady=6,
        )
        self._btn_cancel.pack(side="left", padx=12, pady=10)

        self._btn_next = make_btn(
            self._footer,
            "  Next \u203a  ",
            self._on_next,
            bg=theme.accent2,
            fg=theme.accent_fg,
            font=(UI_FONT, 12, "bold"),
            padx=14,
            pady=6,
        )
        self._btn_next.pack(side="right", padx=12, pady=10)

        self._btn_back = make_btn(
            self._footer,
            "  \u2039 Back  ",
            self._on_back,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 12),
            padx=14,
            pady=6,
        )
        self._btn_back.pack(side="right", padx=(0, 4), pady=10)

    def _update_step_bar(self, step: int) -> None:
        theme = self.theme
        for i, lbl in enumerate(self._step_labels):
            if i == step:
                lbl.configure(fg=theme.accent, font=(UI_FONT, 12, "bold"))
            elif i < step:
                lbl.configure(fg=theme.info, font=(UI_FONT, 12, "normal"))
            else:
                lbl.configure(fg=theme.fg3, font=(UI_FONT, 12, "normal"))

    def _clear_content(self) -> None:
        for w in self._content.winfo_children():
            w.destroy()

    def _show_step(self, step: int) -> None:
        self._current_step = step
        self._update_step_bar(step)
        self._clear_content()

        # Update nav button visibility
        if step == 0:
            self._btn_back.pack_forget()
        else:
            self._btn_back.pack(side="right", padx=(0, 4), pady=10)

        if step == 2:
            self._btn_next.configure(
                text="  Import  ", bg=self.theme.accent, fg=self.theme.accent_fg
            )
        else:
            self._btn_next.configure(
                text="  Next \u203a  ", bg=self.theme.accent2, fg=self.theme.accent_fg
            )

        builders = [
            self._build_step_source,
            self._build_step_browse,
            self._build_step_confirm,
        ]
        builders[step]()

    # --- Step 1: Choose Source ---

    def _build_step_source(self) -> None:
        theme = self.theme
        frame = self._content

        tk.Label(
            frame,
            text="Choose a profile source",
            bg=theme.bg,
            fg=theme.fg,
            font=(UI_FONT, 14, "bold"),
        ).pack(anchor="w", padx=20, pady=(16, 12))

        # Scrollable list of providers grouped by category
        container = tk.Frame(frame, bg=theme.bg)
        container.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        scroll_frame = ScrollableFrame(container, bg=theme.bg)
        scroll_frame.pack(fill="both", expand=True)
        body = scroll_frame.body
        canvas = scroll_frame.canvas

        self._source_var = tk.StringVar(value="")

        self._source_rows = (
            {}
        )  # provider_id -> (row, text_frame, name_lbl, desc_lbl, name_row, hint_lbl)

        def _select_source(pid: str) -> None:
            self._source_var.set(pid)
            # Update visual selection on all rows
            for rid, (rw, tf, nlbl, dlbl, nrow, hlbl) in self._source_rows.items():
                if rid == pid:
                    row_bg = theme.sel
                    nlbl.configure(bg=row_bg, fg=theme.accent)
                else:
                    row_bg = theme.bg3
                    nlbl.configure(bg=row_bg, fg=theme.fg)
                for w in (rw, tf, dlbl, nrow):
                    w.configure(bg=row_bg)
                if hlbl:
                    hlbl.configure(bg=row_bg)
                # Update any link labels or other direct children of row
                for child in rw.winfo_children():
                    try:
                        child.configure(bg=row_bg)
                    except tk.TclError:
                        pass

        for cat in PROVIDER_CATEGORIES:
            providers = [p for p in ALL_PROVIDERS if p.category == cat]
            if not providers:
                continue

            # Category header
            cat_frame = tk.Frame(body, bg=theme.bg)
            cat_frame.pack(fill="x", pady=(10, 2))
            bar = tk.Frame(cat_frame, bg=theme.accent, width=3)
            bar.pack(side="left", fill="y", padx=(0, 8))
            bar.configure(height=18)
            tk.Label(
                cat_frame,
                text=cat,
                bg=theme.bg,
                fg=theme.fg,
                font=(UI_FONT, 12, "bold"),
            ).pack(side="left")

            for provider in providers:
                is_selected = self._source_var.get() == provider.id
                row_bg = theme.sel if is_selected else theme.bg3
                row = tk.Frame(body, bg=row_bg)
                row.pack(fill="x", padx=(16, 0), pady=2)

                text_frame = tk.Frame(row, bg=row_bg)
                text_frame.pack(side="left", fill="x", expand=True, padx=12, pady=8)
                name_row = tk.Frame(text_frame, bg=row_bg)
                name_row.pack(anchor="w")
                name_lbl = tk.Label(
                    name_row,
                    text=provider.name,
                    bg=row_bg,
                    fg=theme.accent if is_selected else theme.fg,
                    font=(UI_FONT, 12, "bold"),
                    anchor="w",
                )
                name_lbl.pack(side="left")

                source_hint = getattr(provider, "source_hint", "")
                if source_hint:
                    hint_lbl = tk.Label(
                        name_row,
                        text=source_hint,
                        bg=row_bg,
                        fg=theme.fg3,
                        font=(UI_FONT, 11, "italic"),
                        anchor="w",
                    )
                    hint_lbl.pack(side="left", padx=(8, 0))
                else:
                    hint_lbl = None

                desc_lbl = tk.Label(
                    text_frame,
                    text=provider.description,
                    bg=row_bg,
                    fg=theme.fg3,
                    font=(UI_FONT, 12),
                    anchor="w",
                )
                desc_lbl.pack(anchor="w")

                # Website hyperlink (opens in browser, doesn't select row)
                if provider.website:
                    link_lbl = tk.Label(
                        row,
                        text="\u2197 Visit source",
                        bg=row_bg,
                        fg=theme.fg3,
                        font=(UI_FONT, 11),
                        cursor="pointinghand",
                        padx=8,
                    )
                    link_lbl.pack(side="right", padx=(0, 8), pady=8)
                    link_lbl.bind(
                        "<Button-1>",
                        lambda e, url=provider.website: webbrowser.open(url),
                    )

                self._source_rows[provider.id] = (
                    row,
                    text_frame,
                    name_lbl,
                    desc_lbl,
                    name_row,
                    hint_lbl,
                )

                # Click anywhere on row to select
                click_targets = [row, text_frame, name_lbl, desc_lbl, name_row]
                if hint_lbl:
                    click_targets.append(hint_lbl)
                for widget in click_targets:
                    widget.bind(
                        "<Button-1>", lambda e, pid=provider.id: _select_source(pid)
                    )

        self._bind_wizard_scroll(canvas)

        # Store select function for keyboard nav (no pre-selection)
        self._select_source_fn = _select_source

    def _nav_source(self, delta: int) -> None:
        """Move source selection up/down by delta."""
        ids = list(getattr(self, "_source_rows", {}).keys())
        if not ids:
            return
        fn = getattr(self, "_select_source_fn", None)
        if not fn:
            return
        current = self._source_var.get()
        try:
            idx = ids.index(current) + delta
        except ValueError:
            idx = 0
        idx = max(0, min(idx, len(ids) - 1))
        fn(ids[idx])

    # --- Step 2: Browse & Select ---

    def _build_step_browse(self) -> None:
        theme = self.theme
        frame = self._content

        provider = self._get_provider(self._source_var.get())
        if not provider:
            tk.Label(
                frame,
                text="No source selected.",
                bg=theme.bg,
                fg=theme.error,
                font=(UI_FONT, 13),
            ).pack(pady=40)
            return

        self._build_browse_header(frame, provider)
        self._build_browse_filters(frame)
        self._build_browse_list_container(frame)

        # Reuse catalog if same provider and we already have data (#4)
        if self._catalog and self._catalog_provider_id == provider.id:
            self._on_catalog_loaded(self._catalog)
            return

        # Fetch catalog in background thread
        self._catalog = []
        self._check_vars = {}
        self._fetch_done.clear()

        self._start_catalog_fetch(provider)

    def _build_browse_header(self, frame: tk.Frame, provider) -> None:
        hdr = tk.Frame(frame, bg=self.theme.bg)
        hdr.pack(fill="x", padx=20, pady=(12, 4))
        self._browse_hdr = hdr  # kept for update badge placement
        tk.Label(
            hdr,
            text=f"Browsing: {provider.name}",
            bg=self.theme.bg,
            fg=self.theme.fg,
            font=(UI_FONT, 14, "bold"),
        ).pack(side="left")

        # SSL degradation warning
        if OnlineProvider.ssl_is_degraded():
            warn = tk.Label(
                hdr,
                text="\u26a0 SSL verification disabled — downloads may be insecure",
                bg=self.theme.note,
                fg=self.theme.bg,
                font=(UI_FONT, 11),
                padx=8,
                pady=2,
            )
            warn.pack(side="right", padx=(8, 0))

        # Status var — displayed inside the profile list pane
        self._browse_status = tk.StringVar(value="Fetching catalog...")

    def _build_browse_filters(self, frame: tk.Frame) -> None:
        theme = self.theme
        filter_row = tk.Frame(frame, bg=theme.bg)
        filter_row.pack(fill="x", padx=20, pady=(8, 4))

        tk.Label(
            filter_row, text="Material:", bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12)
        ).pack(side="left", padx=(0, 4))
        self._mat_combo = ttk.Combobox(
            filter_row,
            textvariable=self._filter_material,
            values=["All"],
            state="readonly",
            width=10,
            style="Dark.TCombobox",
        )
        self._mat_combo.pack(side="left", padx=(0, 12))

        self._brand_label = tk.Label(
            filter_row, text="Brand:", bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12)
        )
        self._brand_label.pack(side="left", padx=(0, 4))
        self._brand_combo = ttk.Combobox(
            filter_row,
            textvariable=self._filter_brand,
            values=["All"],
            state="readonly",
            width=12,
            style="Dark.TCombobox",
        )
        self._brand_combo.pack(side="left", padx=(0, 12))

        tk.Label(
            filter_row, text="Printer:", bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12)
        ).pack(side="left", padx=(0, 4))
        self._machine_combo = ttk.Combobox(
            filter_row,
            textvariable=self._filter_machine,
            values=["All"],
            state="readonly",
            width=14,
            style="Dark.TCombobox",
        )
        self._machine_combo.pack(side="left", padx=(0, 12))

        self._nozzle_label = tk.Label(
            filter_row, text="Nozzle:", bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12)
        )
        self._nozzle_label.pack(side="left", padx=(0, 4))
        self._nozzle_combo = ttk.Combobox(
            filter_row,
            textvariable=self._filter_nozzle,
            values=["All"],
            state="readonly",
            width=8,
            style="Dark.TCombobox",
        )
        self._nozzle_combo.pack(side="left")

        # Filter traces registered once in __init__ (not here — avoids trace leak)

    def _build_browse_list_container(self, frame: tk.Frame) -> None:
        theme = self.theme

        # Select All / Deselect All row
        sel_row = tk.Frame(frame, bg=theme.bg)
        sel_row.pack(fill="x", padx=20, pady=(2, 2))
        make_btn(
            sel_row,
            "Select All",
            self._select_all_browse,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 12),
            padx=10,
            pady=3,
        ).pack(side="left", padx=(0, 6))
        make_btn(
            sel_row,
            "Deselect All",
            self._deselect_all_browse,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 12),
            padx=10,
            pady=3,
        ).pack(side="left")

        # Profile list area (scrollable)
        list_container = tk.Frame(
            frame, bg=theme.bg3, highlightbackground=theme.border, highlightthickness=1
        )
        list_container.pack(fill="both", expand=True, padx=20, pady=(4, 8))

        # Status bar inside list_container (bottom of the pane)
        self._list_status_label = tk.Label(
            list_container,
            textvariable=self._browse_status,
            bg=theme.bg3,
            fg=theme.fg2,
            font=(UI_FONT, 12),
            anchor="w",
            padx=8,
            pady=4,
        )
        self._list_status_label.pack(fill="x", side="bottom")

        self._browse_canvas = tk.Canvas(
            list_container, bg=theme.bg3, highlightthickness=0
        )
        self._browse_scrollbar = ttk.Scrollbar(
            list_container, orient="vertical", command=self._browse_canvas.yview
        )
        self._browse_body = tk.Frame(self._browse_canvas, bg=theme.bg3)
        self._browse_body.bind(
            "<Configure>",
            lambda e: self._browse_canvas.configure(
                scrollregion=self._browse_canvas.bbox("all")
            ),
        )
        self._browse_cw = self._browse_canvas.create_window(
            (0, 0), window=self._browse_body, anchor="nw"
        )
        self._browse_canvas.configure(yscrollcommand=self._browse_scrollbar.set)
        self._browse_canvas.pack(side="left", fill="both", expand=True)
        self._browse_scrollbar.pack(side="right", fill="y")
        self._browse_canvas.bind(
            "<Configure>",
            lambda e: self._browse_canvas.itemconfig(self._browse_cw, width=e.width),
        )

        # Show initial loading message inside the browse body too
        self._show_pane_status("Fetching catalog...")

    def _start_catalog_fetch(self, provider) -> None:
        self._fetch_last_activity = time.time()

        def _status_update(msg: str) -> None:

            self._fetch_last_activity = time.time()  # heartbeat

            def _update(m: str = msg) -> None:
                self._browse_status.set(m)
                if self._fetch_done.is_set():
                    return
                lbl = getattr(self, "_pane_status_label", None)
                if lbl and lbl.winfo_exists():
                    lbl.configure(text=m)
                    match = re.search(r"(\d+)/(\d+)", m)
                    pb = getattr(self, "_pane_progress", None)
                    if match and pb and pb.winfo_exists():
                        cur, tot = int(match.group(1)), int(match.group(2))
                        if tot > 0:
                            pb.stop()
                            pb.configure(mode="determinate", maximum=tot, value=cur)
                else:
                    self._show_pane_status(m)

            try:
                if self.winfo_exists():
                    self.after(0, _update)
            except tk.TclError:
                pass

        def _fetch() -> None:
            try:
                catalog = provider.fetch_catalog(
                    status_fn=_status_update,
                    cancel_check=lambda: self._cancelled or self._fetch_done.is_set(),
                )
                if self._fetch_done.is_set() or self._cancelled:
                    return
                self._fetch_done.set()
                self._safe_after(0, lambda: self._on_catalog_loaded(catalog))
            except urllib.error.HTTPError as ex:
                if self._fetch_done.is_set() or self._cancelled:
                    return
                self._fetch_done.set()
                if ex.code == 403:
                    msg = "GitHub API rate limit exceeded — try again in a few minutes"
                elif ex.code == 404:
                    msg = "Source not found (404) — URL may have changed"
                else:
                    msg = f"HTTP error {ex.code}: {ex.reason}"
                self._safe_after(0, lambda m=msg: self._on_catalog_error(m))
            except urllib.error.URLError as ex:
                if self._fetch_done.is_set() or self._cancelled:
                    return
                self._fetch_done.set()
                msg = f"Network error: {ex.reason}"
                self._safe_after(0, lambda m=msg: self._on_catalog_error(m))
            except Exception as ex:
                if self._fetch_done.is_set() or self._cancelled:
                    return
                self._fetch_done.set()
                msg = user_error(
                    "Could not connect to this source.",
                    ex,
                    "Check your internet connection.",
                )
                self._safe_after(0, lambda m=msg: self._on_catalog_error(m))

        threading.Thread(target=_fetch, daemon=True).start()

        # Heartbeat-based watchdog: re-arms while status updates arrive (#5, #8)
        def _watchdog() -> None:
            if self._fetch_done.is_set() or self._cancelled:
                return
            idle = time.time() - self._fetch_last_activity
            if idle < FETCH_TIMEOUT_MS / 1000:
                remaining = int((FETCH_TIMEOUT_MS / 1000 - idle) * 1000) + 1000
                self._watchdog_id = self._safe_after_id(remaining, _watchdog)
                return
            self._fetch_done.set()
            self._on_catalog_error(
                "Request timed out — check your internet connection "
                "or try a different source."
            )

        self._watchdog_id = self._safe_after_id(FETCH_TIMEOUT_MS, _watchdog)

    def _show_pane_status(self, msg: str, icon: Optional[str] = None) -> None:
        theme = self.theme
        for w in self._browse_body.winfo_children():
            w.destroy()
        wrapper = tk.Frame(self._browse_body, bg=theme.bg3)
        wrapper.pack(fill="x", padx=20, pady=30)
        display = f"{icon}  {msg}" if icon else msg
        self._pane_status_label = tk.Label(
            wrapper,
            text=display,
            bg=theme.bg3,
            fg=theme.fg2,
            font=(UI_FONT, 12),
            wraplength=500,
            justify="center",
        )
        self._pane_status_label.pack(anchor="center")

        # Progress bar (indeterminate while fetching)
        self._pane_progress = ttk.Progressbar(
            wrapper, orient="horizontal", length=300, mode="indeterminate"
        )
        self._pane_progress.pack(anchor="center", pady=(10, 0))
        self._pane_progress.start(15)

    def _on_catalog_loaded(self, catalog: list[OnlineProfileEntry]) -> None:
        if self._current_step != 1:
            return  # User navigated away; don't touch destroyed widgets
        self._catalog = catalog
        self._catalog_provider_id = (
            self._selected_provider.id if self._selected_provider else ""
        )
        if not catalog:
            self._browse_status.set("No profiles found from this source.")
            self._show_pane_status("No profiles found from this source.")
            return

        # Reset filters to "All" before repopulating (avoids stale values
        # from a previous source lingering in the dropdown display)
        self._suppress_filter_trace = True
        self._filter_material.set("All")
        self._filter_brand.set("All")
        self._filter_machine.set("All")
        self._filter_nozzle.set("All")
        self._suppress_filter_trace = False

        # Populate filter dropdowns
        materials = sorted(set(e.material for e in catalog if e.material))
        brands = sorted(set(e.brand for e in catalog if e.brand))
        machines = sorted(set(e.printer for e in catalog if e.printer))
        nozzles = sorted(set(e.nozzle for e in catalog if e.nozzle))

        self._mat_combo["values"] = ["All"] + materials
        # Hide brand filter if all entries share the same brand
        if len(brands) <= 1:
            self._brand_label.pack_forget()
            self._brand_combo.pack_forget()
        else:
            self._brand_label.pack(side="left", padx=(0, 4))
            self._brand_combo.pack(side="left", padx=(0, 12))
        self._brand_combo["values"] = ["All"] + brands
        self._machine_combo["values"] = ["All"] + machines
        self._nozzle_combo["values"] = ["All"] + nozzles
        # Hide nozzle filter if no nozzle data
        if not nozzles:
            self._nozzle_label.pack_forget()
            self._nozzle_combo.pack_forget()
        # Auto-size combobox widths to fit longest value
        for combo, vals in (
            (self._mat_combo, materials),
            (self._brand_combo, brands),
            (self._machine_combo, machines),
        ):
            max_len = max((len(v) for v in vals), default=6)
            combo.configure(width=min(max_len + 2, 30))

        # Show delta if this was a refresh
        prev_count = getattr(self, "_prev_catalog_count", None)
        prev_names = getattr(self, "_prev_catalog_names", None)
        if prev_count is not None and prev_names is not None:
            new_names = {e.name for e in catalog}
            added = len(new_names - prev_names)
            removed = len(prev_names - new_names)
            parts = [f"{len(catalog)} profiles available"]
            if added:
                parts.append(f"+{added} new")
            if removed:
                parts.append(f"-{removed} removed")
            if not added and not removed:
                parts.append("no changes")
            self._browse_status.set("  \u2022  ".join(parts))
            self._prev_catalog_count = None
            self._prev_catalog_names = None
        else:
            self._browse_status.set(f"{len(catalog)} profiles available")

        self._apply_filters()

        # Fire non-blocking freshness check if catalog came from bundle
        if any(e.metadata.get("bundled") for e in catalog):
            self._safe_after(500, self._check_for_updates)

    # --- Freshness badge ---

    def _check_for_updates(self) -> None:
        """Background thread: ask the current provider if updates exist."""
        provider = self._selected_provider
        if not provider:
            return

        def _check() -> None:
            try:
                has_updates = provider.check_for_updates()
            except (urllib.error.URLError, OSError, RuntimeError, ValueError):
                logger.debug("Provider update check failed", exc_info=True)
                has_updates = False
            if has_updates and not self._cancelled:
                self._safe_after(0, self._show_update_badge)

        threading.Thread(target=_check, daemon=True).start()

    def _show_update_badge(self) -> None:
        """Display a clickable 'Updates available' label in the browse header."""
        hdr = getattr(self, "_browse_hdr", None)
        if not hdr or not hdr.winfo_exists():
            return
        theme = self.theme
        badge = tk.Label(
            hdr,
            text="\u2197 Updates available \u2014 click to refresh from online",
            bg=theme.bg,
            fg=theme.converted,
            font=(UI_FONT, 11, "italic"),
            cursor="pointinghand",
        )
        badge.pack(side="right")
        badge.bind("<Button-1>", lambda e: self._refresh_from_online(badge))

    def _refresh_from_online(self, badge: tk.Widget) -> None:
        """Replace bundled catalog with a live online fetch."""
        badge.destroy()
        provider = self._selected_provider
        if not provider:
            return
        provider.clear_cache()
        self._prev_catalog_count = len(self._catalog)
        self._prev_catalog_names = {e.name for e in self._catalog}
        self._fetch_done.clear()
        self._browse_status.set("Refreshing from online...")
        self._show_pane_status("Refreshing from online...")
        self._start_catalog_fetch_online(provider)

    def _start_catalog_fetch_online(self, provider) -> None:
        """Fetch catalog using the provider's online path (skipping bundle)."""
        self._fetch_last_activity = time.time()

        def _status_update(msg: str) -> None:
            self._fetch_last_activity = time.time()

            def _update(m: str = msg) -> None:
                self._browse_status.set(m)
                if not self._fetch_done.is_set():
                    self._show_pane_status(m)

            self._safe_after(0, _update)

        def _fetch() -> None:
            try:
                provider._cancel_check = (
                    lambda: self._cancelled or self._fetch_done.is_set()
                )
                catalog = provider._fetch_catalog_online(
                    status_fn=_status_update,
                )
                if self._fetch_done.is_set() or self._cancelled:
                    return
                # Save refreshed catalog to disk cache (#18)
                if catalog:
                    provider._save_catalog_cache(catalog)
                self._fetch_done.set()
                self._safe_after(0, lambda: self._on_catalog_loaded(catalog))
            except Exception as ex:
                if self._fetch_done.is_set() or self._cancelled:
                    return
                self._fetch_done.set()
                msg = user_error(
                    "Could not connect to this source.",
                    ex,
                    "Check your internet connection.",
                )
                self._safe_after(0, lambda m=msg: self._on_catalog_error(m))

        threading.Thread(target=_fetch, daemon=True).start()

        # Heartbeat-based watchdog
        def _watchdog() -> None:
            if self._fetch_done.is_set() or self._cancelled:
                return
            idle = time.time() - self._fetch_last_activity
            if idle < FETCH_TIMEOUT_MS / 1000:
                remaining = int((FETCH_TIMEOUT_MS / 1000 - idle) * 1000) + 1000
                self._watchdog_id = self._safe_after_id(remaining, _watchdog)
                return
            self._fetch_done.set()
            self._on_catalog_error(
                "Request timed out — check your internet connection "
                "or try a different source."
            )

        self._watchdog_id = self._safe_after_id(FETCH_TIMEOUT_MS, _watchdog)

    def _on_catalog_error(self, err: str) -> None:
        if self._current_step != 1:
            return  # User navigated away; don't touch destroyed widgets
        self._browse_status.set(f"\u26a0 {err}")
        # Also show in the list body so it's unmissable
        theme = self.theme
        for w in self._browse_body.winfo_children():
            w.destroy()
        err_frame = tk.Frame(self._browse_body, bg=theme.bg3)
        err_frame.pack(fill="x", padx=12, pady=20)
        tk.Label(
            err_frame,
            text="\u26a0 Failed to load profiles",
            bg=theme.bg3,
            fg=theme.warning,
            font=(UI_FONT, 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            err_frame,
            text=err,
            bg=theme.bg3,
            fg=theme.fg2,
            font=(UI_FONT, 12),
            wraplength=600,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

    def _apply_filters(self) -> None:
        if self._suppress_filter_trace:
            return
        if self._current_step != 1 or not self._catalog:
            return
        mat = self._filter_material.get()
        brand = self._filter_brand.get()
        machine = self._filter_machine.get()
        nozzle = self._filter_nozzle.get()

        filtered = self._catalog
        if mat != "All":
            filtered = [e for e in filtered if e.material == mat]
        if brand != "All":
            filtered = [e for e in filtered if e.brand == brand]
        if machine != "All":
            filtered = [e for e in filtered if e.printer == machine]
        if nozzle != "All":
            filtered = [e for e in filtered if e.nozzle == nozzle]

        self._filtered_catalog = filtered
        self._cascade_filter_values(mat, brand, machine, nozzle)
        self._render_browse_list(filtered)

    def _cascade_filter_values(
        self, mat: str, brand: str, machine: str, nozzle: str
    ) -> None:
        """Update dropdown values to reflect available options given other filters."""
        catalog = self._catalog

        def _vals(entries: list, attr: str) -> list[str]:
            return sorted(set(getattr(e, attr) for e in entries if getattr(e, attr)))

        # Material: filter by brand, machine, nozzle
        filt = catalog
        if brand != "All":
            filt = [e for e in filt if e.brand == brand]
        if machine != "All":
            filt = [e for e in filt if e.printer == machine]
        if nozzle != "All":
            filt = [e for e in filt if e.nozzle == nozzle]
        self._mat_combo["values"] = ["All"] + _vals(filt, "material")

        # Brand
        filt = catalog
        if mat != "All":
            filt = [e for e in filt if e.material == mat]
        if machine != "All":
            filt = [e for e in filt if e.printer == machine]
        if nozzle != "All":
            filt = [e for e in filt if e.nozzle == nozzle]
        self._brand_combo["values"] = ["All"] + _vals(filt, "brand")

        # Machine
        filt = catalog
        if mat != "All":
            filt = [e for e in filt if e.material == mat]
        if brand != "All":
            filt = [e for e in filt if e.brand == brand]
        if nozzle != "All":
            filt = [e for e in filt if e.nozzle == nozzle]
        self._machine_combo["values"] = ["All"] + _vals(filt, "printer")

        # Nozzle
        filt = catalog
        if mat != "All":
            filt = [e for e in filt if e.material == mat]
        if brand != "All":
            filt = [e for e in filt if e.brand == brand]
        if machine != "All":
            filt = [e for e in filt if e.printer == machine]
        self._nozzle_combo["values"] = ["All"] + _vals(filt, "nozzle")

    _MAX_VISIBLE_ROWS = 200  # Cap rendered rows to avoid widget explosion

    def _render_browse_list(self, entries: list[OnlineProfileEntry]) -> None:
        theme = self.theme
        for w in self._browse_body.winfo_children():
            w.destroy()
        self._check_vars = {}
        self._all_filtered_entries = entries  # keep ref for "Show more"

        if not entries:
            tk.Label(
                self._browse_body,
                text="No profiles match the current filters.",
                bg=theme.bg3,
                fg=theme.fg3,
                font=(UI_FONT, 12),
                pady=20,
            ).pack()
            return

        # Track how many rows are currently rendered
        self._rendered_count = 0
        self._render_batch(entries, 0)

    def _render_batch(self, entries: list[OnlineProfileEntry], start: int) -> None:
        """Render up to _MAX_VISIBLE_ROWS entries starting at *start*."""
        theme = self.theme
        end = min(start + self._MAX_VISIBLE_ROWS, len(entries))

        for i in range(start, end):
            entry = entries[i]
            bg = theme.bg3 if i % 2 == 0 else theme.param_bg
            row = tk.Frame(self._browse_body, bg=bg)
            row.pack(fill="x")

            var = tk.BooleanVar(value=entry.selected)
            self._check_vars[(entry.name, entry.url)] = (var, entry)

            cb = tk.Checkbutton(
                row,
                text=entry.name,
                variable=var,
                bg=bg,
                fg=theme.fg,
                selectcolor=theme.bg4,
                activebackground=bg,
                activeforeground=theme.fg,
                highlightthickness=0,
                font=(UI_FONT, 12, "bold"),
                anchor="w",
                wraplength=600,
                command=lambda e=entry, v=var: setattr(e, "selected", v.get()),
            )
            cb.pack(side="left", padx=(8, 4), pady=4)

            # Detail tags (right-aligned so they stay in a consistent column)
            detail_parts = []
            if entry.material:
                detail_parts.append(entry.material)
            if entry.brand:
                detail_parts.append(entry.brand)
            if entry.slicer:
                detail_parts.append(entry.slicer)
            if detail_parts:
                text_frame = tk.Frame(row, bg=bg)
                text_frame.pack(side="right", padx=(4, 8), pady=4)
                tk.Label(
                    text_frame,
                    text=" \u2022 ".join(detail_parts),
                    bg=bg,
                    fg=theme.fg3,
                    font=(UI_FONT, 12),
                    anchor="e",
                ).pack(anchor="e")

            # Bind scroll on this row and its children directly (avoids full-tree walk)
            bind_scroll(row, self._browse_canvas)
            for child in row.winfo_children():
                bind_scroll(child, self._browse_canvas)
                for grandchild in child.winfo_children():
                    bind_scroll(grandchild, self._browse_canvas)

        self._rendered_count = end

        # Show "load more" footer if there are remaining entries
        if end < len(entries):
            remaining = len(entries) - end
            footer = tk.Frame(self._browse_body, bg=theme.bg3)
            footer.pack(fill="x", pady=(8, 4))
            btn_text = f"Show next {min(remaining, self._MAX_VISIBLE_ROWS)} of {remaining} remaining"
            show_more_btn = tk.Label(
                footer,
                text=btn_text,
                bg=theme.bg3,
                fg=theme.converted,
                font=(UI_FONT, 11, "underline"),
                cursor="pointinghand",
                pady=8,
            )
            show_more_btn.pack(anchor="center")
            show_more_btn.bind(
                "<Button-1>",
                lambda e, s=end: self._load_more_rows(s),
            )
            bind_scroll(footer, self._browse_canvas)
            bind_scroll(show_more_btn, self._browse_canvas)

        self._bind_wizard_scroll(self._browse_canvas)

    def _load_more_rows(self, start: int) -> None:
        """Remove the 'Show more' footer and render the next batch."""
        # Remove the footer (last child of browse_body)
        children = self._browse_body.winfo_children()
        if children:
            children[-1].destroy()
        entries = getattr(self, "_all_filtered_entries", [])
        if start < len(entries):
            self._render_batch(entries, start)

    def _select_all_browse(self) -> None:
        entries = getattr(self, "_all_filtered_entries", [])
        for entry in entries:
            entry.selected = True
        for var, _entry in self._check_vars.values():
            var.set(True)
        count = len(entries)
        rendered = len(self._check_vars)
        if count > rendered:
            self._browse_status.set(
                f"Selected all {count} filtered profiles "
                f"({count - rendered} beyond visible list)"
            )

    def _deselect_all_browse(self) -> None:
        for entry in getattr(self, "_all_filtered_entries", []):
            entry.selected = False
        for var, _entry in self._check_vars.values():
            var.set(False)
        self._browse_status.set(f"{len(self._catalog)} profiles available")

    # --- Step 3: Confirm & Import ---

    def _detect_slicer_filament_dirs(self) -> list[tuple[str, str]]:
        targets = []
        slicers = SlicerDetector.find_all()
        for slicer_name, slicer_path in slicers.items():
            export_dir = SlicerDetector.get_export_dir(slicer_path)
            if export_dir:
                filament_dir = os.path.join(export_dir, "filament")
                if os.path.isdir(filament_dir):
                    targets.append((f"{slicer_name} filament folder", filament_dir))
                else:
                    # The filament subdir may not exist yet — offer parent
                    targets.append((f"{slicer_name} user folder", export_dir))
        return targets

    def _on_browse_target(self) -> None:
        d = filedialog.askdirectory(title="Choose Target Folder", parent=self)
        if d:
            self._custom_dir_path = d
            self._custom_dir_var.set(True)
            self._custom_dir_label.configure(text=d)

    def _build_step_confirm(self) -> None:
        theme = self.theme
        frame = self._content

        # Get final selection from browse step
        final = [e for e in self._catalog if e.selected]
        self._selected_entries = final

        # Spacer (heading removed — step title shown in wizard header)
        tk.Frame(frame, bg=theme.bg, height=16).pack()

        # Summary
        summary_frame = tk.Frame(
            frame, bg=theme.bg3, highlightbackground=theme.border, highlightthickness=1
        )
        summary_frame.pack(fill="x", padx=20, pady=(0, 6))

        provider = self._get_provider(self._source_var.get())
        src_name = provider.name if provider else "Unknown"

        tk.Label(
            summary_frame,
            text=f"Source: {src_name}",
            bg=theme.bg3,
            fg=theme.fg2,
            font=(UI_FONT, 12),
            anchor="w",
            padx=12,
        ).pack(anchor="w", pady=(8, 2))
        tk.Label(
            summary_frame,
            text=f"Profiles to import: {len(final)}",
            bg=theme.bg3,
            fg=theme.fg,
            font=(UI_FONT, 12, "bold"),
            anchor="w",
            padx=12,
        ).pack(anchor="w", pady=(2, 2))

        tk.Frame(summary_frame, bg=theme.bg3, height=8).pack()

        # --- Save-to checkboxes ---
        target_frame = tk.Frame(frame, bg=theme.bg)
        target_frame.pack(fill="x", padx=20, pady=(4, 6))

        tk.Label(
            target_frame,
            text="Save to:",
            bg=theme.bg,
            fg=theme.fg,
            font=(UI_FONT, 12, "bold"),
        ).pack(anchor="w")

        # Build target options as checkboxes
        self._save_targets = []  # list of (BooleanVar, label, path)

        # "Load into app" is always on (not a checkbox — just a note)
        tk.Label(
            target_frame,
            text="\u2713  Loaded into ProfileToolkit",
            bg=theme.bg,
            fg=theme.fg2,
            font=(UI_FONT, 12),
            padx=4,
        ).pack(anchor="w", pady=(4, 2))

        slicer_targets = self._detect_slicer_filament_dirs()
        # Restore last-checked targets from prefs
        last_checked = set(self._prefs.get("last_targets", []))

        for label, path in slicer_targets:
            var = tk.BooleanVar(value=(label in last_checked))
            cb_row = tk.Frame(target_frame, bg=theme.bg)
            cb_row.pack(anchor="w", padx=4)
            tk.Checkbutton(
                cb_row,
                text=label,
                variable=var,
                bg=theme.bg,
                fg=theme.fg,
                selectcolor=theme.bg3,
                activebackground=theme.bg,
                activeforeground=theme.fg,
                font=(UI_FONT, 12),
            ).pack(side="left")
            tk.Label(
                cb_row, text=path, bg=theme.bg, fg=theme.fg3, font=(UI_FONT, 12)
            ).pack(side="left", padx=(6, 0))
            self._save_targets.append((var, label, path))

        # Custom folder option
        self._custom_dir_var = tk.BooleanVar(value=False)
        self._custom_dir_path = None
        custom_row = tk.Frame(target_frame, bg=theme.bg)
        custom_row.pack(anchor="w", padx=4, pady=(2, 0))
        tk.Checkbutton(
            custom_row,
            text="Custom folder:",
            variable=self._custom_dir_var,
            bg=theme.bg,
            fg=theme.fg,
            selectcolor=theme.bg3,
            activebackground=theme.bg,
            activeforeground=theme.fg,
            font=(UI_FONT, 12),
        ).pack(side="left")
        self._custom_dir_label = tk.Label(
            custom_row,
            text="(none selected)",
            bg=theme.bg,
            fg=theme.fg3,
            font=(UI_FONT, 12),
        )
        self._custom_dir_label.pack(side="left", padx=(4, 0))
        make_btn(
            custom_row,
            "Browse...",
            self._on_browse_target,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 12),
            padx=6,
            pady=2,
        ).pack(side="left", padx=(6, 0))

        # --- Profile list ---
        list_frame = tk.Frame(frame, bg=theme.bg)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(4, 6))

        scroll_frame = ScrollableFrame(
            list_frame, bg=theme.bg3, highlight_border=theme.border
        )
        scroll_frame.pack(fill="both", expand=True)
        body = scroll_frame.body
        canvas = scroll_frame.canvas

        for i, entry in enumerate(final):
            bg = theme.bg3 if i % 2 == 0 else theme.param_bg
            row = tk.Frame(body, bg=bg)
            row.pack(fill="x")

            tk.Label(
                row, text="\u2713", bg=bg, fg=theme.info, font=(UI_FONT, 12), padx=8
            ).pack(side="left")
            tk.Label(
                row,
                text=entry.name,
                bg=bg,
                fg=theme.fg,
                font=(UI_FONT, 12),
                anchor="w",
                padx=4,
                pady=4,
            ).pack(side="left", fill="x", expand=True)
        # Download status area with progress bar (#22)
        self._import_status.set("")
        status_row = tk.Frame(frame, bg=theme.bg)
        status_row.pack(fill="x", padx=20, pady=(0, 4))
        tk.Label(
            status_row,
            textvariable=self._import_status,
            bg=theme.bg,
            fg=theme.fg3,
            font=(UI_FONT, 12),
        ).pack(anchor="w")
        self._import_progress = ttk.Progressbar(
            status_row,
            orient="horizontal",
            length=400,
            mode="determinate",
            maximum=max(len(final), 1),
        )
        self._import_progress.pack(anchor="w", pady=(4, 0))

        self._bind_wizard_scroll(canvas)

    # --- Navigation ---

    def _on_next(self) -> None:
        if getattr(self, "_importing", False):
            return
        step = self._current_step

        if step == 0:
            # Validate source selected
            pid = self._source_var.get()
            if not pid:
                messagebox.showwarning(
                    "No Source", "Select a profile source to continue.", parent=self
                )
                return
            self._selected_provider = self._get_provider(pid)
            self._show_step(1)

        elif step == 1:
            # Check at least one selected
            selected = [e for e in self._catalog if e.selected]
            if not selected:
                messagebox.showwarning(
                    "No Profiles",
                    "Select at least one profile to continue.",
                    parent=self,
                )
                return
            self._selected_entries = selected
            self._show_step(2)

        elif step == 2:
            # Validate custom folder (#21)
            if self._custom_dir_var.get() and not self._custom_dir_path:
                messagebox.showwarning(
                    "No Folder Selected",
                    'You checked "Custom folder" but didn\'t select a path.\n'
                    "Click Browse to choose a folder, or uncheck the option.",
                    parent=self,
                )
                return
            self._do_import()

    def _on_back(self) -> None:
        if getattr(self, "_importing", False):
            return
        if self._current_step > 0:
            # Signal any in-flight fetch to stop before tearing down its UI
            if not self._fetch_done.is_set():
                self._fetch_done.set()
            if self._watchdog_id:
                self.after_cancel(self._watchdog_id)
                self._watchdog_id = None
            self._show_step(self._current_step - 1)

    def _on_cancel(self) -> None:
        self._cancelled = True
        # Cancel any pending watchdog timer
        if self._watchdog_id:
            try:
                self.after_cancel(self._watchdog_id)
            except (tk.TclError, ValueError):
                pass
            self._watchdog_id = None
        # Remove filter traces to prevent leaks on reopen
        for var, tid in self._trace_ids:
            try:
                var.trace_remove("write", tid)
            except (tk.TclError, ValueError):
                pass
        self._trace_ids.clear()
        save_online_prefs(self._prefs)
        self.destroy()

    def _get_provider(self, provider_id: str) -> Optional[Any]:
        for p in ALL_PROVIDERS:
            if p.id == provider_id:
                return p
        return None

    # --- Import Execution ---

    def _collect_target_dirs(self) -> list[str]:
        dirs = []
        checked_labels = []
        for var, label, path in self._save_targets:
            if var.get():
                dirs.append(path)
                checked_labels.append(label)
        if self._custom_dir_var.get() and self._custom_dir_path:
            dirs.append(self._custom_dir_path)
            checked_labels.append("Custom folder")
        # Save preference
        self._prefs["last_targets"] = checked_labels
        return dirs

    def _do_import(self) -> None:
        entries = self._selected_entries
        if not entries:
            return

        target_dirs = self._collect_target_dirs()

        provider = self._selected_provider
        n = len(entries)
        self._import_status.set(
            f"Downloading {n} {'profile' if n == 1 else 'profiles'}..."
        )
        self._btn_next.configure(text="  Importing...  ")
        self._importing = True

        def _download() -> None:
            import shutil

            results = []
            tmp_dirs = []
            errors = []
            saved_dirs = set()
            written_files = []  # Track for cancel rollback (#13)
            try:
                for i, entry in enumerate(entries):
                    if self._cancelled:
                        # Roll back files written to target dirs (#13)
                        for fpath in written_files:
                            try:
                                os.unlink(fpath)
                            except OSError:
                                pass
                        for td in tmp_dirs:
                            shutil.rmtree(td, ignore_errors=True)
                        return

                    def _update_progress(idx: int = i, name: str = entry.name) -> None:
                        self._import_status.set(
                            f"Downloading {idx+1}/{len(entries)}: {name}"
                        )
                        pb = getattr(self, "_import_progress", None)
                        if pb:
                            pb.configure(value=idx + 1)

                    self._safe_after(0, _update_progress)
                    try:
                        data, fname = provider.download_profile(entry)
                        if data and fname:
                            fname = os.path.basename(fname).replace("\x00", "")
                            if not fname or fname.startswith("."):
                                fname = (
                                    entry.name.replace(" ", "_").replace("/", "-")
                                    + ".json"
                                )

                            # Save to each checked target directory
                            primary_path = None
                            for tdir in target_dirs:
                                os.makedirs(tdir, exist_ok=True)
                                dest = os.path.realpath(os.path.join(tdir, fname))
                                # Avoid overwriting existing files (#14)
                                base_dest, ext_part = os.path.splitext(dest)
                                counter = 2
                                while os.path.exists(dest):
                                    dest = f"{base_dest}_{counter}{ext_part}"
                                    counter += 1
                                    if counter > 100:
                                        raise ValueError(
                                            f"Too many collisions: {fname}"
                                        )
                                if not dest.startswith(os.path.realpath(tdir) + os.sep):
                                    raise ValueError(f"Path traversal blocked: {fname}")
                                with open(dest, "wb") as f:
                                    f.write(data)
                                written_files.append(dest)
                                saved_dirs.add(tdir)
                                if primary_path is None:
                                    primary_path = dest

                            if primary_path:
                                results.append((primary_path, None, provider.name))
                            else:
                                tmp_dir = tempfile.mkdtemp(prefix="ppc_import_")
                                tmp_dirs.append(tmp_dir)
                                tmp_path = os.path.join(tmp_dir, fname)
                                with open(tmp_path, "wb") as f:
                                    f.write(data)
                                results.append((tmp_path, None, provider.name))
                    except Exception as ex:
                        errors.append(f"{entry.name}: {ex}")
                        logger.warning("Download failed: %s", entry.name, exc_info=True)

                try:
                    if self.winfo_exists():
                        self.after(
                            0,
                            lambda: self._on_download_complete(
                                results, errors, list(saved_dirs), tmp_dirs
                            ),
                        )
                    else:
                        # Widget destroyed — clean up tmp_dirs directly
                        for td in tmp_dirs:
                            shutil.rmtree(td, ignore_errors=True)
                except tk.TclError:
                    for td in tmp_dirs:
                        shutil.rmtree(td, ignore_errors=True)
            finally:
                self._importing = False

        threading.Thread(target=_download, daemon=True).start()

    def _on_download_complete(
        self,
        results: list[tuple[str, Optional[str], str]],
        errors: list[str],
        saved_dirs: list[str],
        tmp_dirs: Optional[list[str]] = None,
    ) -> None:
        import shutil

        try:
            save_online_prefs(self._prefs)

            if errors:
                err_msg = "\n".join(errors[:5])
                if len(errors) > 5:
                    err_msg += f"\n... and {len(errors) - 5} more"
                messagebox.showwarning(
                    "Some Downloads Failed",
                    f"Downloaded {len(results)}, failed {len(errors)}:\n\n{err_msg}\n\nYou can retry by running the import again.",
                    parent=self,
                )

            if results:
                load_ok = True
                try:
                    self._load_callback(results)
                except Exception:
                    load_ok = False
                    logger.exception("Failed to load imported profiles")
                    messagebox.showwarning(
                        "Load Error",
                        "Some profiles could not be loaded \u2014 they may be in an unsupported format.",
                        parent=self,
                    )
                if saved_dirs and load_ok:
                    dir_list = "\n".join(saved_dirs)
                    messagebox.showinfo(
                        "Import Complete",
                        f"Imported {len(results)} {'profile' if len(results) == 1 else 'profiles'} to "
                        f"{len(saved_dirs)} location{'s' if len(saved_dirs) != 1 else ''}:\n"
                        f"{dir_list}",
                        parent=self,
                    )
        except Exception:
            logger.exception("Error during import completion")
        finally:
            for td in tmp_dirs or []:
                shutil.rmtree(td, ignore_errors=True)
            self.destroy()
