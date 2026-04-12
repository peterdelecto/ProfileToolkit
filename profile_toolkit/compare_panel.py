# ComparePanel — side-by-side filament profile comparison
# Extracted from panels.py

from __future__ import annotations

import logging
import os
import io
import traceback
import tkinter as tk
import tkinter.font as tkfont
from collections import Counter
from copy import deepcopy
from tkinter import ttk, filedialog, messagebox
from typing import Any, Optional

from .constants import (
    FILAMENT_LAYOUT,
    ORCA_ONLY_TABS,
    _IDENTITY_KEYS,
    _PLATFORM,
    _WIN_SCROLL_DELTA_DIVISOR,
    ENUM_VALUES,
    SLICER_COLORS,
    SLICER_SHORT_LABELS,
    UI_FONT,
    MONO_FONT,
    MONO_FONT_SIZE,
    COMPARE_DEBUG_LOG,
    MAX_UNDO_STACK_SIZE,
)
from .theme import Theme
from .models import Profile
from .state import save_profile_state
from .utils import (
    bind_scroll,
    get_enum_human_label,
    nil_to_zero,
)
from .widgets import (
    Tooltip as _Tooltip,
    ScrollableFrame,
    make_btn as _make_btn,
)

logger = logging.getLogger(__name__)


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
        self._profile_b_fg = theme.info
        self._waiting = False  # True when waiting for user to select 2 filaments

        # Undo stack
        self._undo_stack: list[tuple] = []
        self._rebuild_generation = (
            0  # incremented on each load() to cancel stale deferred work
        )

        # Filter / search / collapse state
        self._filter_mode: str = "all"  # "diffs", "missing", "all", "pending"
        self._pending_keys: Counter[str] = Counter()
        self._collapsed_sections: set[str] = set()
        self._search_var: Optional[tk.StringVar] = None
        self._search_entry: Optional[tk.Entry] = None
        self._search_after_id: Optional[str] = None
        self._section_widgets: dict[str, tk.Widget] = {}
        self._nav_items: dict[str, tk.Frame] = {}
        # Cached row widgets for fast filter toggle (W1 optimization)
        self._row_cache: dict[str, tk.Widget] = {}  # json_key -> row frame
        self._row_metadata: dict[str, tuple[str, str]] = (
            {}
        )  # json_key -> (section_key, ui_label)
        self._sec_visible_rows: dict[str, list[str]] = (
            {}
        )  # section_key -> [json_key, ...]
        self._can_fast_filter = False  # True after a full render builds the cache

        # Per-pair state caches: keyed by sorted (source_path_a, source_path_b)
        self._pair_undo_cache: dict[tuple[str, str], tuple[list, Counter]] = {}
        self._pair_collapse_cache: dict[tuple[str, str], set[str]] = {}

        self._show_waiting_ui()

    @property
    def _pending_count(self) -> int:
        """Derived from _pending_keys — no separate attribute to keep in sync."""
        return sum(self._pending_keys.values())

    @staticmethod
    def _pair_cache_key(a: Any, b: Any) -> tuple[str, str]:
        """Order-independent stable cache key for a profile pair.

        Uses source_path instead of id() to avoid stale cache hits after GC
        reuses an object id.
        """
        ka = getattr(a, "source_path", "") or str(id(a))
        kb = getattr(b, "source_path", "") or str(id(b))
        return (min(ka, kb), max(ka, kb))

    def _cancel_debounce(self) -> None:
        """Cancel all pending debounced after() callbacks."""
        for attr in (
            "_resize_after_id",
            "_refresh_render_id",
            "_search_after_id",
            "_chunk_render_id",
        ):
            after_id = getattr(self, attr, None)
            if after_id:
                self.after_cancel(after_id)
                setattr(self, attr, None)

    def _on_destroy_compare_panel(self, event=None) -> None:
        """Remove StringVar traces to prevent leaks on panel recreation."""
        if event and event.widget is not self:
            return
        try:
            if self._search_var and hasattr(self, "_search_trace_id"):
                self._search_var.trace_remove("write", self._search_trace_id)
        except (tk.TclError, ValueError, AttributeError):
            pass

    # --- Public API ---

    def load(self, profile_a: Profile, profile_b: Profile) -> None:
        """Populate with two profiles and build the comparison view."""
        if not profile_a or not profile_b:
            logger.warning(
                "ComparePanel.load called with None profile: a=%s b=%s",
                profile_a,
                profile_b,
            )
            self.show_waiting()
            return
        if profile_a is profile_b:
            logger.info("ComparePanel.load: same profile selected twice, ignoring")
            return
        # Warn about unsaved changes before switching to different profiles
        if (
            self._pending_keys
            and self._profile_a is not None
            and (profile_a is not self._profile_a or profile_b is not self._profile_b)
        ):
            if not messagebox.askyesno(
                "Unsaved Changes",
                f"Discard {len(self._pending_keys)} {'change' if len(self._pending_keys) == 1 else 'changes'}?",
                parent=self,
            ):
                return
        logger.debug("ComparePanel.load: '%s' vs '%s'", profile_a.name, profile_b.name)
        # Save current state for the outgoing pair (order-independent key)
        if self._profile_a is not None and self._profile_b is not None:
            old_key = self._pair_cache_key(self._profile_a, self._profile_b)
            if self._undo_stack:
                self._pair_undo_cache[old_key] = (
                    list(self._undo_stack),
                    Counter(self._pending_keys),
                )
            # Always preserve collapse state
            self._pair_collapse_cache[old_key] = set(self._collapsed_sections)
        self._profile_a = profile_a
        self._profile_b = profile_b
        self._waiting = False

        # Update bulk copy button labels with profile names
        a_short = (
            (profile_a.name[:15] + "…")
            if len(profile_a.name or "") > 15
            else (profile_a.name or "A")
        )
        b_short = (
            (profile_b.name[:15] + "…")
            if len(profile_b.name or "") > 15
            else (profile_b.name or "B")
        )
        if hasattr(self, "_copy_all_ba_btn"):
            self._copy_all_ba_btn.configure(text=f"Copy {b_short} → {a_short}")
        if hasattr(self, "_copy_all_ab_btn"):
            self._copy_all_ab_btn.configure(text=f"Copy {a_short} → {b_short}")
        # Cancel any pending debounced renders from previous session
        self._cancel_debounce()
        # Restore cached undo state for this pair, or start fresh
        new_key = self._pair_cache_key(profile_a, profile_b)
        cached = self._pair_undo_cache.pop(new_key, None)
        if cached:
            self._undo_stack, self._pending_keys = cached
        else:
            self._undo_stack.clear()
            self._pending_keys = Counter()
        self._collapsed_sections = self._pair_collapse_cache.pop(new_key, set())
        self._filter_mode = "all"
        self._changelog_start = {
            id(profile_a): len(profile_a.changelog),
            id(profile_b): len(profile_b.changelog),
        }
        self._rebuild_generation += 1
        self._rebuilding = True
        try:
            self._rebuild()
        except (KeyError, AttributeError, tk.TclError, ValueError) as exc:
            buf = io.StringIO()
            traceback.print_exc(file=buf)
            self._write_debug_log(buf.getvalue())
            logger.exception("ComparePanel._rebuild() crashed: %s", exc)
            # Show error fallback so the panel isn't blank
            for child in self.winfo_children():
                child.destroy()
            self._show_error_ui(str(exc))
        finally:
            self._rebuilding = False

    def _unbind_shortcuts(self) -> None:
        """Remove global keyboard bindings from toplevel window."""
        try:
            top = self.winfo_toplevel()
        except (tk.TclError, RuntimeError):
            self._bind_id_ctrl_f = None
            self._bind_id_ctrl_z = None
            self._bind_id_key_d = None
            return
        _mod = "Command" if _PLATFORM == "Darwin" else "Control"
        if getattr(self, "_bind_id_ctrl_f", None):
            try:
                top.unbind(f"<{_mod}-f>", self._bind_id_ctrl_f)
            except tk.TclError:
                pass
            self._bind_id_ctrl_f = None
        if getattr(self, "_bind_id_ctrl_z", None):
            try:
                top.unbind(f"<{_mod}-z>", self._bind_id_ctrl_z)
            except tk.TclError:
                pass
            self._bind_id_ctrl_z = None
        if getattr(self, "_bind_id_key_d", None):
            try:
                top.unbind("<Key-d>", self._bind_id_key_d)
            except tk.TclError:
                pass
            self._bind_id_key_d = None

    def show_waiting(self) -> None:
        """Show the 'select two filament profiles' prompt."""
        self._unbind_shortcuts()
        self._cancel_debounce()
        self._profile_a = None
        self._profile_b = None
        self._waiting = True
        self._undo_stack.clear()
        self._pending_keys = Counter()
        for child in self.winfo_children():
            child.destroy()
        self._show_waiting_ui()

    def is_waiting(self) -> bool:
        return self._waiting

    def clear(self) -> None:
        """Reset to waiting state."""
        self.show_waiting()

    def _write_debug_log(self, message: str) -> None:
        """Write to compare_debug.log with size management (truncate if >1MB)."""
        debug_log_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), COMPARE_DEBUG_LOG
        )

        # Check file size before writing
        keep_bytes = 100 * 1024
        try:
            if (
                os.path.exists(debug_log_path)
                and os.path.getsize(debug_log_path) > 1024 * 1024
            ):
                # Truncate: keep last 100KB using seek (avoids reading entire file)
                with open(debug_log_path, "rb") as f:
                    f.seek(0, 2)  # end
                    size = f.tell()
                    f.seek(max(0, size - keep_bytes))
                    tail = f.read()
                with open(debug_log_path, "wb") as f:
                    f.write(tail)
        except OSError:
            pass  # If truncation fails, just proceed with append

        try:
            with open(debug_log_path, "a", encoding="utf-8") as f:
                f.write(message + "\n")
        except OSError:
            logger.debug("Failed to write compare debug log to %s", debug_log_path)

    # --- Waiting UI ---

    def _show_waiting_ui(self) -> None:
        theme = self.theme
        container = tk.Frame(self, bg=theme.bg2)
        container.place(relx=0.5, rely=0.4, anchor="center")
        tk.Label(
            container,
            text="\u2194",
            bg=theme.bg2,
            fg=theme.fg3,
            font=(UI_FONT, 30),
        ).pack()
        tk.Label(
            container,
            text="Compare Filament Profiles",
            bg=theme.bg2,
            fg=theme.fg,
            font=(UI_FONT, 17, "bold"),
        ).pack(pady=(6, 10))
        tk.Label(
            container,
            text="Select two profiles, then click Compare.",
            bg=theme.bg2,
            fg=theme.fg3,
            font=(UI_FONT, 15),
            justify="center",
        ).pack(pady=(0, 8))

    def _show_error_ui(self, error_msg: str) -> None:
        """Fallback UI when _rebuild crashes — shows error instead of blank panel."""
        theme = self.theme
        container = tk.Frame(self, bg=theme.bg2)
        container.place(relx=0.5, rely=0.4, anchor="center")
        tk.Label(
            container,
            text="\u26a0",
            bg=theme.bg2,
            fg=theme.warning,
            font=(UI_FONT, 30),
        ).pack()
        tk.Label(
            container,
            text="Compare failed to load",
            bg=theme.bg2,
            fg=theme.fg,
            font=(UI_FONT, 17, "bold"),
        ).pack(pady=(6, 10))
        tk.Label(
            container,
            text=f"Error: {error_msg}\nCheck compare_debug.log for details.",
            bg=theme.bg2,
            fg=theme.fg3,
            font=(UI_FONT, 14),
            justify="center",
            wraplength=400,
        ).pack(pady=(0, 8))

    # --- Main rebuild ---

    def _rebuild(self) -> None:
        """Orchestrate the rebuild of the compare panel."""
        for child in self.winfo_children():
            child.destroy()

        theme = self.theme
        profile_a, profile_b = self._profile_a, self._profile_b
        if not profile_a or not profile_b:
            self._show_waiting_ui()
            return

        layout = FILAMENT_LAYOUT
        data_a = profile_a.resolved_data if profile_a.resolved_data else profile_a.data
        data_b = profile_b.resolved_data if profile_b.resolved_data else profile_b.data

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

        # Build main UI sections
        self._build_compare_header()
        self._build_filter_bar()
        main_container = self._build_main_container()
        self._build_compare_content(main_container)
        self._build_status_bar()

        # Keyboard shortcuts — unbind previous before rebinding
        self._unbind_shortcuts()
        _mod = "Command" if _PLATFORM == "Darwin" else "Control"
        top = self.winfo_toplevel()
        self._bind_id_ctrl_f = top.bind(f"<{_mod}-f>", lambda e: self._focus_search())
        self._bind_id_ctrl_z = top.bind(f"<{_mod}-z>", self._on_undo)
        self._bind_id_key_d = top.bind(
            "<Key-d>",
            lambda e: self._on_key_d(),
        )

    def _build_compare_header(self) -> None:
        """Build the header with profile names and history link."""
        theme = self.theme
        profile_a, profile_b = self._profile_a, self._profile_b

        header = tk.Frame(self, bg=theme.bg)
        header.pack(fill="x", padx=16, pady=(8, 0))

        # Profile names: A (lime) vs B (cyan) with factory badge
        _hdr_font = tkfont.Font(family=UI_FONT, size=14, weight="bold")
        _hdr_max_px = _hdr_font.measure("W" * 36)  # pixel budget ≈ 36 wide chars
        tk.Label(
            header,
            text=self._truncate_name(profile_a.name, _hdr_max_px, _hdr_font),
            bg=theme.bg,
            fg=theme.accent,
            font=(UI_FONT, 14, "bold"),
        ).pack(side="left")
        if profile_a.is_factory_preset:
            tk.Label(
                header,
                text=" FACTORY",
                bg=theme.bg,
                fg=theme.fg3,
                font=(UI_FONT, 10),
            ).pack(side="left", padx=(2, 0))
        tk.Label(
            header,
            text="  vs  ",
            bg=theme.bg,
            fg=theme.fg3,
            font=(UI_FONT, 15),
        ).pack(side="left")
        tk.Label(
            header,
            text=self._truncate_name(profile_b.name, _hdr_max_px, _hdr_font),
            bg=theme.bg,
            fg=self._profile_b_fg,
            font=(UI_FONT, 14, "bold"),
        ).pack(side="left")
        if profile_b.is_factory_preset:
            tk.Label(
                header,
                text=" FACTORY",
                bg=theme.bg,
                fg=theme.fg3,
                font=(UI_FONT, 10),
            ).pack(side="left", padx=(2, 0))

        # Summary
        self._summary_label = tk.Label(
            header,
            text=f"   \u2022  {self._diff_count} difference{'s' if self._diff_count != 1 else ''}",
            bg=theme.bg,
            fg=theme.fg3,
            font=(UI_FONT, 14),
        )
        self._summary_label.pack(side="left", padx=(8, 0))

        # Right side buttons: Clear | Reset | Save
        _make_btn(
            header,
            "\u2715  Close",
            lambda: self.app._close_compare(),
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 13),
            padx=10,
            pady=3,
        ).pack(side="right", padx=(4, 0))

        self._reset_btn = _make_btn(
            header,
            "Discard Changes",
            self._on_reset,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 13),
            padx=10,
            pady=3,
        )
        self._reset_btn.pack(side="right", padx=(4, 0))

        self._save_btn = _make_btn(
            header,
            "\u2713  Save",
            self._on_save,
            bg=theme.accent,
            fg=theme.accent_fg,
            font=(UI_FONT, 13, "bold"),
            padx=12,
            pady=3,
        )
        self._save_btn.pack(side="right", padx=(4, 0))

        # Bulk copy buttons
        self._copy_all_ba_btn = _make_btn(
            header,
            "Copy All B \u2192 A",
            self._copy_all_b_to_a,
            bg=theme.bg4,
            fg=self._profile_b_fg,
            font=(UI_FONT, 13),
            padx=8,
            pady=3,
        )
        self._copy_all_ba_btn.pack(side="right", padx=(4, 0))
        _Tooltip(self._copy_all_ba_btn, "Copy all diffs from B to A", theme=theme)

        self._copy_all_ab_btn = _make_btn(
            header,
            "Copy All A \u2192 B",
            self._copy_all_a_to_b,
            bg=theme.bg4,
            fg=theme.accent,
            font=(UI_FONT, 13),
            padx=8,
            pady=3,
        )
        self._copy_all_ab_btn.pack(side="right", padx=(4, 0))
        _Tooltip(self._copy_all_ab_btn, "Copy all diffs from A to B", theme=theme)

        # Undo / Changelog link
        self._history_label = tk.Label(
            header,
            text="",
            bg=theme.bg,
            fg=theme.modified,
            font=(UI_FONT, 14, "underline"),
            cursor="pointinghand",
        )
        self._history_label.pack(side="right", padx=(0, 8))
        self._history_label.bind("<Button-1>", lambda e: self._show_changelog())
        self._update_history_label()
        self._update_save_reset_state()

    def _build_filter_bar(self) -> None:
        """Build the filter/search bar with filter chips and search entry."""
        theme = self.theme

        filter_bar = tk.Frame(self, bg=theme.bg)
        filter_bar.pack(fill="x", padx=16, pady=(8, 4))

        self._chip_labels: dict[str, tk.Label] = {}

        # Filter chips (left side)
        chip_frame = tk.Frame(filter_bar, bg=theme.bg)
        chip_frame.pack(side="left")

        for mode, label_text in [
            ("all", " All "),
            ("diffs", " Changed "),
            ("missing", " Missing "),
            ("pending", f" Unsaved ({len(self._pending_keys)}) "),
        ]:
            chip = tk.Label(
                chip_frame,
                text=label_text,
                bg=theme.bg3,
                fg=theme.fg2,
                font=(UI_FONT, 13),
                padx=8,
                pady=2,
                cursor="pointinghand",
                highlightbackground=theme.border,
                highlightthickness=1,
            )
            chip.pack(side="left", padx=(0, 6))
            chip.bind("<Button-1>", lambda e, m=mode: self._set_filter_mode(m))
            self._chip_labels[mode] = chip

        self._update_chip_styles()

        # Search entry (right-aligned)
        self._search_var = tk.StringVar()
        self._search_trace_id = self._search_var.trace_add(
            "write", lambda *_: self._on_search_changed()
        )
        self.bind("<Destroy>", self._on_destroy_compare_panel, add="+")
        self._search_entry = tk.Entry(
            filter_bar,
            textvariable=self._search_var,
            bg=theme.bg3,
            fg=theme.fg,
            insertbackground=theme.fg,
            font=(UI_FONT, 14),
            relief="flat",
            width=25,
            highlightbackground=theme.border,
            highlightthickness=1,
        )
        self._search_entry.pack(side="right", padx=(8, 0), pady=2)
        # Placeholder behavior
        self._search_placeholder_active = True
        self._search_entry.insert(0, "Search parameters...")
        self._search_entry.configure(fg=theme.placeholder_fg)
        self._search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self._search_entry.bind("<FocusOut>", self._on_search_focus_out)

    def _build_main_container(self) -> tk.Frame:
        """Build the main horizontal container with nav rail, return content area parent."""
        theme = self.theme

        # --- Main horizontal container (PanedWindow: resizable nav rail + content) ---
        main_container = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=theme.border,
            sashwidth=6,
            sashrelief="flat",
            opaqueresize=True,
        )
        main_container.pack(fill="both", expand=True)

        # Compute initial nav rail width from longest section name
        name_font = tkfont.Font(family=UI_FONT, size=13)
        badge_font = tkfont.Font(family=UI_FONT, size=12, weight="bold")
        longest = max(
            (sec for secs in self._layout.values() for sec in secs),
            key=lambda s: name_font.measure(s),
            default="",
        )
        # accent(3) + padx(8*2) + name + gap(4) + badge(" 00 " ~) + padx(4+8) + margin
        nav_w = (
            name_font.measure(longest)
            + badge_font.measure(" 00 ")
            + 3
            + 16
            + 4
            + 12
            + 16
        )
        nav_w = max(nav_w, 180)  # floor
        self._nav_initial_w = nav_w

        self._nav_rail = tk.Frame(main_container, bg=theme.bg)
        main_container.add(self._nav_rail, minsize=nav_w, width=nav_w, stretch="never")

        # Nav rail title
        tk.Label(
            self._nav_rail,
            text="SECTIONS",
            bg=theme.bg,
            fg=theme.fg3,
            font=(UI_FONT, 12, "bold"),
            anchor="w",
            padx=12,
        ).pack(fill="x", pady=(8, 4))

        # Nav rail separator
        tk.Frame(self._nav_rail, bg=theme.border, height=1).pack(fill="x", padx=8)

        # Build nav items
        self._nav_items = {}
        self._build_nav_rail()

        return main_container

    def _build_compare_content(self, main_container: tk.PanedWindow) -> None:
        """Build the content area with column headers and scrollable rows."""
        theme = self.theme
        profile_a, profile_b = self._profile_a, self._profile_b

        # Content area (right pane, fills remaining space)
        content_area = tk.Frame(main_container, bg=theme.bg)
        main_container.add(content_area, minsize=300, stretch="always")

        # --- Column header row ---
        # Right padx compensates for scrollbar width so columns align
        # with the scrollable body below. Measure actual scrollbar width.
        _sb_width = ttk.Style().lookup("TScrollbar", "width") or 17
        try:
            _sb_width = int(_sb_width)
        except (TypeError, ValueError):
            _sb_width = 17
        col_hdr = tk.Frame(content_area, bg=theme.bg4, height=32)
        col_hdr.pack(fill="x", padx=(0, _sb_width), pady=(0, 0))
        col_hdr.pack_propagate(False)
        # Column proportions: param(45%) | sep | value A(22%) | arrows(6%) | sep | value B(27%)
        # Use pack with proportional relwidth so columns fill the entire content area.
        # Store ratios as instance attr so body rows use the same proportions.
        self._col_ratios = {
            "param": 0.38,
            "val_a": 0.24,
            "arrows": 0.08,
            "val_b": 0.30,
        }

        # Header: pack-based with place for proportional widths
        col_hdr.update_idletasks()
        param_hdr = tk.Label(
            col_hdr,
            text="Parameter",
            bg=theme.bg4,
            fg=theme.fg,
            font=(UI_FONT, 14, "bold"),
            anchor="w",
            padx=10,
            pady=5,
        )
        param_hdr.pack(side="left", fill="y")
        param_hdr.bind("<Configure>", lambda e: None)
        tk.Frame(col_hdr, bg=theme.border, width=1).pack(side="left", fill="y")
        _col_font = tkfont.Font(family=UI_FONT, size=14, weight="bold")
        _col_max_px = _col_font.measure("W" * 28)
        a_hdr = tk.Label(
            col_hdr,
            text=self._truncate_name(profile_a.name, _col_max_px, _col_font),
            bg=theme.bg4,
            fg=theme.accent,
            font=(UI_FONT, 14, "bold"),
            anchor="w",
            padx=8,
            pady=5,
        )
        a_hdr.pack(side="left", fill="y")
        tk.Frame(col_hdr, bg=theme.border, width=1).pack(side="left", fill="y")
        b_hdr = tk.Label(
            col_hdr,
            text=self._truncate_name(profile_b.name, _col_max_px, _col_font),
            bg=theme.bg4,
            fg=self._profile_b_fg,
            font=(UI_FONT, 14, "bold"),
            anchor="w",
            padx=8,
            pady=5,
        )
        b_hdr.pack(side="left", fill="y")

        # Slicer badge row (below column header)
        badge_row = tk.Frame(content_area, bg=theme.bg2, height=26)
        badge_row.pack(fill="x", padx=(0, 17), pady=0)
        badge_row.pack_propagate(False)

        # Empty param column placeholder
        badge_param = tk.Label(badge_row, text="", bg=theme.bg2)
        badge_param.pack(side="left", fill="y")
        tk.Frame(badge_row, bg=theme.border, width=1).pack(side="left", fill="y")

        # Profile A slicer badge
        a_origin = profile_a.origin or ""
        a_short = SLICER_SHORT_LABELS.get(a_origin, a_origin)
        a_badge_bg = SLICER_COLORS.get(a_origin, theme.bg4)
        a_badge_frame = tk.Frame(badge_row, bg=theme.bg2)
        a_badge_frame.pack(side="left", fill="y")
        if a_origin:
            tk.Label(
                a_badge_frame,
                text=f" {a_short} ",
                bg=a_badge_bg,
                fg=theme.accent_fg,
                font=(UI_FONT, 10, "bold"),
                padx=3,
                pady=1,
            ).pack(side="left", padx=(8, 0), pady=3)
        tk.Frame(badge_row, bg=theme.border, width=1).pack(side="left", fill="y")

        # Profile B slicer badge
        b_origin = profile_b.origin or ""
        b_short = SLICER_SHORT_LABELS.get(b_origin, b_origin)
        b_badge_bg = SLICER_COLORS.get(b_origin, theme.bg4)
        b_badge_frame = tk.Frame(badge_row, bg=theme.bg2)
        b_badge_frame.pack(side="left", fill="y")
        if b_origin:
            tk.Label(
                b_badge_frame,
                text=f" {b_short} ",
                bg=b_badge_bg,
                fg=theme.accent_fg,
                font=(UI_FONT, 10, "bold"),
                padx=3,
                pady=1,
            ).pack(side="left", padx=(8, 0), pady=3)

        # Use place for proportional column widths after initial pack
        def _layout_header(
            e=None,
            hdr=col_hdr,
            p=param_hdr,
            a=a_hdr,
            b=b_hdr,
            br=badge_row,
            bp=badge_param,
            ba=a_badge_frame,
            bb=b_badge_frame,
        ):
            w = hdr.winfo_width()
            if w < 10:
                return
            r = self._col_ratios
            px = 0
            param_width = int(w * r["param"])
            p.place(x=px, y=0, width=param_width, relheight=1.0)
            bp.place(x=px, y=0, width=param_width, relheight=1.0)
            px += param_width + 1  # +1 for separator
            value_a_width = int(w * (r["val_a"] + r["arrows"]))
            a.place(x=px, y=0, width=value_a_width, relheight=1.0)
            ba.place(x=px, y=0, width=value_a_width, relheight=1.0)
            px += value_a_width + 1
            value_b_width = w - px
            b.place(x=px, y=0, width=value_b_width, relheight=1.0)
            bb.place(x=px, y=0, width=value_b_width, relheight=1.0)

        col_hdr.bind("<Configure>", _layout_header)
        badge_row.bind("<Configure>", lambda e: _layout_header())

        # --- Scrollable body ---
        scroll_container = tk.Frame(content_area, bg=theme.bg)
        scroll_container.pack(fill="both", expand=True)

        self._scroll_frame = ScrollableFrame(scroll_container, bg=theme.bg2)
        self._scroll_frame.pack(fill="both", expand=True)
        self._body = self._scroll_frame.body
        self._canvas = self._scroll_frame.canvas

        # Track scroll position for active nav highlighting
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._last_canvas_w = 0
        self._resize_after_id = None
        self._canvas.bind(
            "<MouseWheel>",
            lambda e: (
                self.after(50, self._update_active_nav) if self.winfo_exists() else None
            ),
        )
        if _PLATFORM == "Linux":
            self._canvas.bind(
                "<Button-4>",
                lambda e: (
                    self.after(50, self._update_active_nav)
                    if self.winfo_exists()
                    else None
                ),
            )
            self._canvas.bind(
                "<Button-5>",
                lambda e: (
                    self.after(50, self._update_active_nav)
                    if self.winfo_exists()
                    else None
                ),
            )

        # Defer initial render until canvas has a real width — avoids
        # falling back to the 800px minimum on first layout.
        gen = self._rebuild_generation

        def _initial_render(e=None):
            self._canvas.unbind("<Map>")
            if self._rebuild_generation != gen:
                return  # stale — a newer load() superseded this rebuild
            if not self.winfo_exists():
                return
            self.after(10, self._render_rows)

        self._canvas.bind("<Map>", _initial_render)

    def _build_status_bar(self) -> None:
        """Build the status bar with diff count and filter info."""
        theme = self.theme

        # --- Status bar (Tier 3.3) ---
        status = tk.Frame(self, bg=theme.bg)
        status.pack(fill="x")
        tk.Frame(status, bg=theme.border, height=1).pack(fill="x")

        status_inner = tk.Frame(status, bg=theme.bg)
        status_inner.pack(fill="x", padx=12, pady=3)

        # Left: diff count + pending
        left_status = tk.Frame(status_inner, bg=theme.bg)
        left_status.pack(side="left")
        self._status_diff_label = tk.Label(
            left_status,
            text=f"{self._diff_count} differences",
            bg=theme.bg,
            fg=theme.fg,
            font=(UI_FONT, 13, "bold"),
        )
        self._status_diff_label.pack(side="left")
        tk.Label(
            left_status,
            text=" \u2022 ",
            bg=theme.bg,
            fg=theme.fg3,
            font=(UI_FONT, 13),
        ).pack(side="left")
        pending_fg = theme.modified if self._pending_count > 0 else theme.fg3
        pending_weight = "bold" if self._pending_count > 0 else "normal"
        self._status_pending_label = tk.Label(
            left_status,
            text=(
                f"{self._pending_count} unsaved"
                if self._pending_count > 0
                else "No changes"
            ),
            bg=theme.bg,
            fg=pending_fg,
            font=(UI_FONT, 13, pending_weight),
        )
        self._status_pending_label.pack(side="left")
        tk.Label(
            left_status,
            text=" \u2022 ",
            bg=theme.bg,
            fg=theme.fg3,
            font=(UI_FONT, 13),
        ).pack(side="left")
        missing_count = getattr(self, "_missing_count", 0)
        self._status_missing_label = tk.Label(
            left_status,
            text=(
                f"{missing_count} unmatched" if missing_count > 0 else "None unmatched"
            ),
            bg=theme.bg,
            fg=theme.error if missing_count > 0 else theme.fg3,
            font=(UI_FONT, 13),
        )
        self._status_missing_label.pack(side="left")

        # Right: active filter
        _filter_label_map = {
            "diffs": "Changed only",
            "missing": "Unmatched values",
            "all": "All parameters",
            "pending": "Unsaved changes",
        }
        self._status_filter_label = tk.Label(
            status_inner,
            text=f"Showing: {_filter_label_map.get(self._filter_mode, self._filter_mode)}",
            bg=theme.bg,
            fg=theme.fg3,
            font=(UI_FONT, 13),
        )
        self._status_filter_label.pack(side="right")

    # --- Filter chip management ---

    def _set_filter_mode(self, mode: str) -> None:
        """Change active filter and re-render rows."""
        self._filter_mode = mode
        self._update_chip_styles()
        self._refilter_rows()
        self._update_nav_badges()
        self._update_status_bar()

    def _update_chip_styles(self) -> None:
        """Restyle filter chips based on active mode."""
        theme = self.theme
        for mode, chip in self._chip_labels.items():
            if mode == self._filter_mode:
                chip.configure(
                    bg=theme.accent,
                    fg=theme.accent_fg,
                    font=(UI_FONT, 13, "bold"),
                    highlightthickness=0,
                )
            else:
                chip.configure(
                    bg=theme.bg3,
                    fg=theme.fg2,
                    font=(UI_FONT, 13),
                    highlightbackground=theme.border,
                    highlightthickness=1,
                )
        # Update pending chip count
        if "pending" in self._chip_labels:
            self._chip_labels["pending"].configure(
                text=f" Unsaved ({len(self._pending_keys)}) ",
            )

    # --- Search (Tier 2.2) ---

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
        """Re-render rows when search text changes (debounced)."""
        if getattr(self, "_rebuilding", False):
            return  # Guard: trace fires during _rebuild before body exists
        if not hasattr(self, "_body"):
            return
        try:
            if not self._body.winfo_exists():
                return
        except (tk.TclError, AttributeError):
            return
        if not self.winfo_exists():
            return
        if hasattr(self, "_search_after_id") and self._search_after_id:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(200, self._do_search_render)

    def _do_search_render(self) -> None:
        """Deferred search render callback."""
        self._search_after_id = None
        if not self.winfo_exists():
            return
        self._refilter_rows()
        self._update_nav_badges()

    def _focus_search(self) -> None:
        """Focus the search entry (Ctrl+F / Cmd+F)."""
        if getattr(self.app, "_current_tab", "") != "compare":
            return
        if self._search_entry and self._search_entry.winfo_exists():
            self._search_entry.focus_set()
            if not self._search_placeholder_active:
                self._search_entry.select_range(0, "end")

    def _on_key_d(self) -> None:
        """Handle global 'd' key — toggle diff filter unless focus is in a text field."""
        if getattr(self.app, "_current_tab", "") != "compare":
            return
        try:
            focused = self.focus_get()
        except (KeyError, tk.TclError):
            return
        if isinstance(focused, (tk.Entry, tk.Text, ttk.Entry)):
            return  # Don't intercept typing in any text field
        self._toggle_diff_filter()

    def _get_search_text(self) -> str:
        """Get active search filter text (empty string if placeholder)."""
        if self._search_var is None or self._search_placeholder_active:
            return ""
        return self._search_var.get().strip().lower()

    def _toggle_diff_filter(self) -> None:
        """Toggle between diffs and all filter modes (D key)."""
        if self._filter_mode == "diffs":
            self._set_filter_mode("all")
        else:
            self._set_filter_mode("diffs")

    # --- Nav rail (Tier 2.1) ---

    def _badge_colors(self, diff_count: int, has_missing: bool) -> tuple[str, str]:
        """Return (badge_bg, badge_fg) for a section diff badge."""
        theme = self.theme
        badge_bg = (
            theme.error
            if has_missing
            else (theme.warning if diff_count > 0 else theme.bg4)
        )
        badge_fg = theme.accent_fg if diff_count > 0 else theme.fg3
        return badge_bg, badge_fg

    def _build_nav_rail(self) -> None:
        """Build navigation rail items from FILAMENT_LAYOUT sections."""
        theme = self.theme
        self._nav_items = {}

        for tab_name, sections in self._layout.items():
            if not sections or tab_name == "Advanced":
                continue
            for sec_name, params in sections.items():
                section_key = f"{tab_name}::{sec_name}"
                diff_count = self._section_diff_count(params) if params else 0
                has_missing = self._section_has_missing(params) if params else False

                nav_row = tk.Frame(self._nav_rail, bg=theme.bg, cursor="pointinghand")
                nav_row.pack(fill="x", pady=1)

                # Left accent border (hidden by default, shown when active)
                accent_bar = tk.Frame(nav_row, bg=theme.bg, width=3)
                accent_bar.pack(side="left", fill="y")

                # Section name
                name_lbl = tk.Label(
                    nav_row,
                    text=sec_name,
                    bg=theme.bg,
                    fg=theme.fg2,
                    font=(UI_FONT, 13),
                    anchor="w",
                    padx=8,
                    pady=3,
                )
                name_lbl.pack(side="left", fill="x", expand=True)

                # Diff count badge
                badge_bg, badge_fg = self._badge_colors(diff_count, has_missing)
                badge = tk.Label(
                    nav_row,
                    text=str(diff_count),
                    bg=badge_bg,
                    fg=badge_fg,
                    font=(UI_FONT, 12, "bold"),
                    width=3,
                    anchor="center",
                    pady=1,
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
        if not hasattr(self, "_layout") or not hasattr(self, "_data_a"):
            return
        theme = self.theme
        for tab_name, sections in self._layout.items():
            if not sections or tab_name == "Advanced":
                continue
            for sec_name, params in sections.items():
                section_key = f"{tab_name}::{sec_name}"
                nav_row = self._nav_items.get(section_key)
                if not nav_row:
                    continue
                diff_count = self._section_diff_count(params) if params else 0
                has_missing = self._section_has_missing(params) if params else False
                badge = nav_row._badge  # type: ignore
                badge_bg, badge_fg = self._badge_colors(diff_count, has_missing)
                badge.configure(text=str(diff_count), bg=badge_bg, fg=badge_fg)

    def _jump_to_section(self, section_key: str) -> None:
        """Scroll the main table to the given section."""
        widget = self._section_widgets.get(section_key)
        if not widget or not widget.winfo_exists():
            # Section not visible in current filter — switch to "all" so it renders
            if self._filter_mode != "all":
                self._filter_mode = "all"
                self._render_rows()
                self._update_chip_styles()
                self._update_nav_badges()
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
                font=(UI_FONT, 13, "bold") if is_active else (UI_FONT, 13),
            )

    def _on_canvas_configure(self, event: Optional[tk.Event] = None) -> None:
        """Handle canvas resize — debounce re-render and update nav."""
        if not self.winfo_exists():
            return
        # Skip if compare tab is not active (avoid unnecessary renders)
        if getattr(self.app, "_current_tab", "") != "compare":
            return
        self.after(50, self._update_active_nav)
        w = self._canvas.winfo_width() if self._canvas.winfo_exists() else 0
        if w < 10 or abs(w - self._last_canvas_w) < 10:
            return
        # Debounce: cancel pending re-render, schedule a new one
        if self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(150, self._on_resize_render)

    def _on_resize_render(self) -> None:
        """Re-render rows after window resize settles."""
        self._resize_after_id = None
        if not self.winfo_exists():
            return
        w = self._canvas.winfo_width() if self._canvas.winfo_exists() else 0
        if w > 10 and abs(w - self._last_canvas_w) >= 10:
            self._last_canvas_w = w
            self._render_rows()

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
        return sum(1 for entry in section_params if entry[0] in self._diff_keys)

    def _section_has_missing(self, section_params: list) -> bool:
        return any(
            (self._data_a.get(entry[0]) is None) != (self._data_b.get(entry[0]) is None)
            for entry in section_params
            if entry[0] in self._diff_keys
        )

    # --- Row rendering ---

    _RENDER_CHUNK_SIZE = 80  # Rows per render chunk for large profiles

    def _render_rows(self) -> None:
        """Render section headers and parameter rows in side-by-side layout."""
        # Cancel any pending chunked render
        if getattr(self, "_chunk_render_id", None):
            self.after_cancel(self._chunk_render_id)
            self._chunk_render_id = None
        try:
            self._render_rows_inner()
        except (KeyError, AttributeError, tk.TclError, ValueError) as exc:
            buf = io.StringIO()
            traceback.print_exc(file=buf)
            self._write_debug_log(buf.getvalue())
            logger.exception("_render_rows crashed: %s", exc)

    def _render_rows_inner(self) -> None:
        body = self._body
        canvas = self._canvas
        theme = self.theme
        data_a, data_b = self._data_a, self._data_b
        diff_keys = self._diff_keys
        search_text = self._get_search_text()

        # Compute proportional column pixel widths from canvas width.
        # Avoid update_idletasks() here — it forces a synchronous geometry
        # pass that can trigger reentrant callbacks. Use cached width instead.
        total_w = max(canvas.winfo_width(), 800)
        self._last_canvas_w = total_w
        r = self._col_ratios
        sep_w = 1
        arrow_w = int(total_w * r["arrows"] / 2)  # split arrows col in half
        self._col_px = {
            "param": int(total_w * r["param"]),
            "sep": sep_w,
            "val_a": int(total_w * r["val_a"]),
            "arrow": arrow_w,
            "val_b": total_w
            - int(total_w * r["param"])
            - int(total_w * r["val_a"])
            - 2 * arrow_w
            - 2 * sep_w,
        }

        # Suppress <Configure> during bulk widget creation (O(n^2) prevention)
        body.unbind("<Configure>")

        self._can_fast_filter = False
        for child in body.winfo_children():
            child.destroy()

        self._section_widgets = {}
        self._row_cache = {}
        self._row_metadata = {}
        self._sec_visible_rows = {}
        deferred_rows: list[tuple] = []
        row_idx = 0

        for tab_name, sections in self._layout.items():
            if not sections:
                continue  # Skip empty tabs (e.g. "Multi Filament")

            # Count diffs in this tab
            tab_diff_count = sum(
                1
                for params in sections.values()
                for entry in params
                if entry[0] in diff_keys
            )

            # --- Tab header (section title) ---
            tab_hdr = tk.Frame(body, bg=theme.section_bg)
            tab_hdr.pack(fill="x", pady=(12 if row_idx > 0 else 4, 2))

            # Lime left border (4px)
            tk.Frame(tab_hdr, bg=theme.accent, width=4).pack(side="left", fill="y")

            tk.Label(
                tab_hdr,
                text=tab_name,
                bg=theme.section_bg,
                fg=theme.fg,
                font=(UI_FONT, 15, "bold"),
                anchor="w",
                padx=8,
                pady=5,
            ).pack(side="left")

            if tab_name in ORCA_ONLY_TABS:
                tk.Label(
                    tab_hdr,
                    text="Orca",
                    bg=theme.accent,
                    fg=theme.accent_fg,
                    font=(UI_FONT, 9, "bold"),
                    padx=3,
                    pady=1,
                ).pack(side="left", padx=(0, 8))

            if tab_diff_count > 0:
                tk.Label(
                    tab_hdr,
                    text=f" {tab_diff_count} diff ",
                    bg=theme.warning,
                    fg=theme.accent_fg,
                    font=(UI_FONT, 12, "bold"),
                    padx=6,
                    pady=1,
                ).pack(side="right", padx=8)

            bind_scroll(tab_hdr, canvas)
            for ch in tab_hdr.winfo_children():
                bind_scroll(ch, canvas)
            row_idx += 1

            # --- Sections within this tab ---
            for sec_name, params in sections.items():
                section_key = f"{tab_name}::{sec_name}"

                # All params always visible
                section_visible_rows = list(params) if params else []

                is_collapsed = section_key in self._collapsed_sections
                diff_count = self._section_diff_count(params) if params else 0
                has_missing = self._section_has_missing(params) if params else False

                # Section header (Tier 2.3 collapse + Tier 2.6 enhanced badges)
                sec_hdr = tk.Frame(body, bg=theme.section_bg, cursor="pointinghand")
                sec_hdr.pack(fill="x", pady=(4, 1))
                self._section_widgets[section_key] = sec_hdr

                tk.Frame(sec_hdr, bg=theme.accent_dark, width=3).pack(
                    side="left", fill="y"
                )

                # Chevron (Tier 2.3)
                chevron_text = "\u25b8" if is_collapsed else "\u25be"
                chevron_label = tk.Label(
                    sec_hdr,
                    text=chevron_text,
                    bg=theme.section_bg,
                    fg=theme.fg3,
                    font=(UI_FONT, 12),
                    cursor="pointinghand",
                )
                chevron_label.pack(side="left", padx=(4, 0))

                sec_name_label = tk.Label(
                    sec_hdr,
                    text=sec_name,
                    bg=theme.section_bg,
                    fg=theme.fg2,
                    font=(UI_FONT, 14, "bold"),
                    padx=6,
                    pady=3,
                    anchor="w",
                    cursor="pointinghand",
                )
                sec_name_label.pack(side="left")

                # Enhanced diff badge (Tier 2.6)
                badge_bg, badge_fg = self._badge_colors(diff_count, has_missing)
                badge = tk.Label(
                    sec_hdr,
                    text=str(diff_count),
                    bg=badge_bg,
                    fg=badge_fg,
                    font=(UI_FONT, 12, "bold"),
                    width=3,
                    anchor="center",
                    pady=1,
                )
                badge.pack(side="right", padx=8)

                # Collapse toggle
                def _toggle(e=None, key=section_key):
                    # Preserve scroll position across collapse/expand
                    try:
                        scroll_pos = self._canvas.yview()[0]
                    except tk.TclError:
                        scroll_pos = 0.0
                    if key in self._collapsed_sections:
                        self._collapsed_sections.discard(key)
                    else:
                        self._collapsed_sections.add(key)
                    self._render_rows()
                    self._canvas.yview_moveto(scroll_pos)

                sec_hdr.bind("<Button-1>", _toggle)
                chevron_label.bind("<Button-1>", _toggle)
                sec_name_label.bind("<Button-1>", _toggle)
                # Keyboard accessibility for section collapse/expand
                sec_hdr.bind("<Return>", _toggle)
                sec_hdr.bind("<space>", _toggle)

                bind_scroll(sec_hdr, canvas)
                for ch in sec_hdr.winfo_children():
                    bind_scroll(ch, canvas)

                # Build metadata for this section (always, even if collapsed)
                section_row_keys: list[str] = []
                for _meta_entry in params or []:
                    self._row_metadata[_meta_entry[0]] = (section_key, _meta_entry[1])
                    section_row_keys.append(_meta_entry[0])
                self._sec_visible_rows[section_key] = section_row_keys

                # Skip params if collapsed (Tier 2.3)
                if is_collapsed:
                    continue

                # Parameter rows — collect for chunked rendering
                for _row_entry in section_visible_rows:
                    json_key, ui_label = _row_entry[0], _row_entry[1]
                    if not self._is_row_visible(
                        json_key, ui_label, data_a, data_b, diff_keys, search_text
                    ):
                        continue
                    val_a = data_a.get(json_key)
                    val_b = data_b.get(json_key)
                    is_diff = json_key in diff_keys
                    is_missing_a = val_a is None and val_b is not None
                    is_missing_b = val_b is None and val_a is not None

                    if row_idx < self._RENDER_CHUNK_SIZE:
                        self._render_param_row(
                            body,
                            canvas,
                            json_key,
                            ui_label,
                            val_a,
                            val_b,
                            is_diff,
                            is_missing_a,
                            is_missing_b,
                            row_idx,
                        )
                    else:
                        deferred_rows.append(
                            (
                                json_key,
                                ui_label,
                                val_a,
                                val_b,
                                is_diff,
                                is_missing_a,
                                is_missing_b,
                                row_idx,
                            )
                        )
                    row_idx += 1

        # --- Uncategorized keys ---
        key_in_layout: set[str] = set()
        for sections in self._layout.values():
            for params in sections.values():
                for entry in params:
                    key_in_layout.add(entry[0])

        uncategorized_diffs = diff_keys - key_in_layout - _IDENTITY_KEYS
        if uncategorized_diffs:
            unc_hdr = tk.Frame(body, bg=theme.section_bg)
            unc_hdr.pack(fill="x", pady=(12, 2))
            tk.Frame(unc_hdr, bg=theme.fg3, width=4).pack(side="left", fill="y")
            tk.Label(
                unc_hdr,
                text="  Other Parameters",
                bg=theme.section_bg,
                fg=theme.fg3,
                font=(UI_FONT, 15, "bold"),
                anchor="w",
                padx=6,
                pady=4,
            ).pack(side="left", fill="x", expand=True)
            bind_scroll(unc_hdr, canvas)
            for ch in unc_hdr.winfo_children():
                bind_scroll(ch, canvas)

            for json_key in sorted(uncategorized_diffs):
                val_a = data_a.get(json_key)
                val_b = data_b.get(json_key)
                if not self._is_row_visible(
                    json_key, json_key, data_a, data_b, diff_keys, search_text
                ):
                    continue
                if row_idx < self._RENDER_CHUNK_SIZE:
                    self._render_param_row(
                        body,
                        canvas,
                        json_key,
                        json_key,
                        val_a,
                        val_b,
                        True,
                        val_a is None,
                        val_b is None,
                        row_idx,
                    )
                else:
                    deferred_rows.append(
                        (
                            json_key,
                            json_key,
                            val_a,
                            val_b,
                            True,
                            val_a is None,
                            val_b is None,
                            row_idx,
                        )
                    )
                row_idx += 1

        bind_scroll(body, canvas)

        # Re-enable <Configure> and do a single scrollregion update
        body.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.configure(scrollregion=canvas.bbox("all"))

        # Schedule deferred rows if any remain beyond the initial chunk
        if deferred_rows and self.winfo_exists():
            gen = self._rebuild_generation
            self._deferred_row_queue = deferred_rows
            self._chunk_render_id = self.after(
                1, lambda: self._render_deferred_chunk(body, canvas, gen)
            )
        else:
            self._can_fast_filter = True

    def _render_deferred_chunk(
        self, body: tk.Widget, canvas: tk.Canvas, gen: int
    ) -> None:
        """Render the next chunk of deferred rows (called via after())."""
        self._chunk_render_id = None
        if gen != self._rebuild_generation:
            return  # Stale — a new load/render superseded this
        queue = getattr(self, "_deferred_row_queue", [])
        if not queue:
            self._can_fast_filter = True
            return

        chunk = queue[: self._RENDER_CHUNK_SIZE]
        del queue[: self._RENDER_CHUNK_SIZE]

        body.unbind("<Configure>")
        for args in chunk:
            self._render_param_row(body, canvas, *args)
        body.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.configure(scrollregion=canvas.bbox("all"))

        if queue and self.winfo_exists():
            self._chunk_render_id = self.after(
                1, lambda: self._render_deferred_chunk(body, canvas, gen)
            )
        else:
            self._can_fast_filter = True
            bind_scroll(body, canvas)

    def _refilter_rows(self) -> None:
        """Fast-path: show/hide cached row widgets without destroying them.

        Only works when _can_fast_filter is True (after a full render).
        Falls back to full _render_rows() otherwise.
        """
        if not self._can_fast_filter or not self._row_cache:
            self._render_rows()
            return

        data_a, data_b = self._data_a, self._data_b
        diff_keys = self._diff_keys
        search_text = self._get_search_text()

        for json_key, row_widget in self._row_cache.items():
            meta = self._row_metadata.get(json_key)
            if not meta:
                continue
            section_key, ui_label = meta
            # Hidden if section is collapsed
            if section_key in self._collapsed_sections:
                row_widget.pack_forget()
                continue
            if self._is_row_visible(
                json_key, ui_label, data_a, data_b, diff_keys, search_text
            ):
                if not row_widget.winfo_ismapped():
                    row_widget.pack(fill="x")
            else:
                if row_widget.winfo_ismapped():
                    row_widget.pack_forget()

        # Update scrollregion
        try:
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        except tk.TclError:
            pass

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

        # Hide double-empty rows (both None)
        if val_a is None and val_b is None:
            return False

        # Search filter — match UI label only (not raw JSON key, which exposes internals)
        if search_text and search_text not in ui_label.lower():
            return False

        # Filter mode
        mode = self._filter_mode
        if mode == "diffs" and not is_diff and json_key not in self._pending_keys:
            return False
        if mode == "missing" and not (is_missing_a or is_missing_b):
            return False
        if mode == "pending" and json_key not in self._pending_keys:
            return False

        return True

    # Keys containing G-code or other long multiline text
    _GCODE_KEYS = {
        "filament_start_gcode",
        "filament_end_gcode",
        "machine_start_gcode",
        "machine_end_gcode",
        "change_filament_gcode",
        "layer_change_gcode",
        "filament_notes",
    }

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

        # Row background — subtle highlight for diffs, no emergency colors
        if is_diff or is_missing_a or is_missing_b:
            bg = theme.compare_changed_bg
            border_color = theme.warning
        else:
            bg = theme.bg2 if row_idx % 2 == 0 else theme.bg3
            border_color = None

        row = tk.Frame(body, bg=bg)
        row.pack(fill="x")
        self._row_cache[json_key] = row

        # Left border indicator (subtle 4px accent strip for diffs)
        if border_color:
            tk.Frame(row, bg=border_color, width=4).place(x=0, y=0, relheight=1.0)

        # Format values
        va_str = self._fmt(val_a, json_key)
        vb_str = self._fmt(val_b, json_key)

        if is_gcode and is_diff:
            # G-code / long text: full-width stacked layout
            self._render_gcode_row(
                row,
                canvas,
                json_key,
                ui_label,
                va_str,
                vb_str,
                val_a,
                val_b,
                is_diff,
                is_missing_a,
                is_missing_b,
                border_color,
                bg,
            )
        else:
            # Standard columnar layout using grid for proper height propagation.
            # pack_propagate(False) caused zero-height rows (garbled text).
            cpx = self._col_px
            val_a_wrap = max(cpx["val_a"] - 20, 100)
            val_b_wrap = max(cpx["val_b"] - 20, 100)

            # Configure grid columns: param | sep | val_a | arrow | sep | arrow | val_b
            row.columnconfigure(0, minsize=cpx["param"], weight=0)
            row.columnconfigure(1, minsize=cpx["sep"], weight=0)
            row.columnconfigure(2, minsize=cpx["val_a"], weight=0)
            row.columnconfigure(3, minsize=cpx["arrow"], weight=0)
            row.columnconfigure(4, minsize=cpx["sep"], weight=0)
            row.columnconfigure(5, minsize=cpx["arrow"], weight=0)
            row.columnconfigure(6, minsize=cpx["val_b"], weight=1)

            # Column 0: Parameter name
            param_cell = tk.Frame(row, bg=bg)
            param_cell.grid(row=0, column=0, sticky="nsew")

            # Pending blue dot (Tier 2.4)
            param_padx_left = 12
            if json_key in self._pending_keys:
                dot = tk.Canvas(
                    param_cell, width=8, height=8, bg=bg, highlightthickness=0
                )
                dot.create_oval(1, 1, 7, 7, fill=theme.modified, outline="")
                dot.pack(side="left", padx=(4, 0))
                _Tooltip(dot, "Unsaved change", theme)
                bind_scroll(dot, canvas)
                param_padx_left = 4

            label_fg = theme.fg if is_diff else theme.fg3
            param_lbl = tk.Label(
                param_cell,
                text=ui_label,
                bg=bg,
                fg=label_fg,
                font=(UI_FONT, 14),
                anchor="w",
                pady=4,
                wraplength=cpx["param"] - 20,
                justify="left",
            )
            param_lbl.pack(
                side="left", fill="both", expand=True, padx=(param_padx_left, 4)
            )

            # Column 1: Separator
            tk.Frame(row, bg=theme.border, width=cpx["sep"]).grid(
                row=0, column=1, sticky="ns"
            )

            # Column 2: Value A
            if is_missing_a:
                va_fg = theme.error
                va_display = "(not set)"
                va_font = (UI_FONT, 14, "italic")
            elif is_diff:
                va_fg = theme.success
                va_display = va_str
                va_font = (UI_FONT, 14)
            else:
                va_fg = theme.fg3
                va_display = va_str
                va_font = (UI_FONT, 14)
            va_cell = tk.Frame(row, bg=bg)
            va_cell.grid(row=0, column=2, sticky="nsew")
            va_label = tk.Label(
                va_cell,
                text=va_display,
                bg=bg,
                fg=va_fg,
                font=va_font,
                anchor="w",
                pady=4,
                wraplength=val_a_wrap,
                justify="left",
            )
            va_label.pack(fill="both", expand=True, padx=8)

            # Column 3: Copy arrow A→B (hidden when source value is None —
            # _copy_a_to_b silently ignores None, so showing the arrow is misleading)
            delta_text = ""
            arrow_ab_cell = tk.Frame(row, bg=bg)
            arrow_ab_cell.grid(row=0, column=3, sticky="nsew")
            if is_diff:
                delta_text = self._compute_delta(val_a, val_b)
                if val_a is not None:
                    self._build_copy_arrow(
                        arrow_ab_cell, json_key, "\u2192", theme.accent, canvas
                    )

            # Column 4: Separator
            tk.Frame(row, bg=theme.border, width=cpx["sep"]).grid(
                row=0, column=4, sticky="ns"
            )

            # Column 5: Copy arrow B→A (symmetric with A→B: show when diff and source not None)
            arrow_ba_cell = tk.Frame(row, bg=bg)
            arrow_ba_cell.grid(row=0, column=5, sticky="nsew")
            if is_diff and val_b is not None:
                self._build_copy_arrow(
                    arrow_ba_cell, json_key, "\u2190", self._profile_b_fg, canvas
                )

            # Column 6: Value B + optional delta
            if is_missing_b:
                vb_fg = theme.error
                vb_display = "(not set)"
                vb_font = (UI_FONT, 14, "italic")
            elif is_diff:
                vb_fg = theme.success
                vb_display = vb_str
                vb_font = (UI_FONT, 14)
            else:
                vb_fg = theme.fg3
                vb_display = vb_str
                vb_font = (UI_FONT, 14)
            vb_cell = tk.Frame(row, bg=bg)
            vb_cell.grid(row=0, column=6, sticky="nsew")
            vb_inner = tk.Frame(vb_cell, bg=bg)
            vb_inner.pack(fill="both", expand=True, padx=8)
            vb_label = tk.Label(
                vb_inner,
                text=vb_display,
                bg=bg,
                fg=vb_fg,
                font=vb_font,
                anchor="w",
                pady=4,
                wraplength=val_b_wrap,
                justify="left",
            )
            vb_label.pack(side="left", fill="x", expand=True)
            bind_scroll(vb_cell, canvas)
            bind_scroll(vb_inner, canvas)
            bind_scroll(vb_label, canvas)

            # Delta indicator after Profile B value (Tier 3.2)
            if is_diff and delta_text:
                is_neg = delta_text.startswith("\u2212") or delta_text.startswith("-")
                delta_lbl = tk.Label(
                    vb_inner,
                    text=f"({delta_text})",
                    bg=bg,
                    fg=theme.fg3 if is_neg else theme.warning,
                    font=(UI_FONT, 14),
                    anchor="e",
                )
                delta_lbl.pack(side="right")
                bind_scroll(delta_lbl, canvas)

        # Scroll bindings — recursive to cover all nested widgets
        bind_scroll(row, canvas)
        for child in row.winfo_children():
            bind_scroll(child, canvas)
            for grandchild in child.winfo_children():
                bind_scroll(grandchild, canvas)

    def _render_gcode_row(
        self,
        row: tk.Frame,
        canvas: tk.Canvas,
        json_key: str,
        ui_label: str,
        va_str: str,
        vb_str: str,
        val_a: Any,
        val_b: Any,
        is_diff: bool,
        is_missing_a: bool,
        is_missing_b: bool,
        border_color: Any,
        bg: str,
    ) -> None:
        """Render a G-code / long-text parameter as a stacked full-width row.

        Uses tk.Text widgets (read-only, monospace) so long gcode is fully
        visible without truncation and without breaking column alignment.
        """
        theme = self.theme

        # Label row with copy arrows inline
        header_frame = tk.Frame(row, bg=bg)
        header_frame.pack(fill="x", padx=(12, 10))
        label_fg = theme.fg if is_diff else theme.fg3
        label_weight = "bold" if is_diff else "normal"
        tk.Label(
            header_frame,
            text=ui_label,
            bg=bg,
            fg=label_fg,
            font=(UI_FONT, 14, label_weight),
            anchor="w",
            pady=4,
        ).pack(side="left")

        if is_diff:
            key = json_key
            ba_btn = tk.Label(
                header_frame,
                text="B \u2192 A",
                bg=bg,
                fg=theme.fg3,
                font=(UI_FONT, 12, "bold"),
                cursor="pointinghand",
            )
            ba_btn.pack(side="right", padx=(8, 0))
            ba_btn.bind("<Button-1>", lambda e, k=key: self._copy_b_to_a(k))
            ba_btn.bind(
                "<Enter>", lambda e, l=ba_btn: l.configure(fg=self._profile_b_fg)
            )
            ba_btn.bind("<Leave>", lambda e, l=ba_btn: l.configure(fg=theme.fg3))
            _Tooltip(
                ba_btn,
                f"Copy {self._profile_b.name} \u2192 {self._profile_a.name}",
                theme=theme,
            )

            ab_btn = tk.Label(
                header_frame,
                text="A \u2192 B",
                bg=bg,
                fg=theme.fg3,
                font=(UI_FONT, 12, "bold"),
                cursor="pointinghand",
            )
            ab_btn.pack(side="right", padx=(8, 0))
            ab_btn.bind("<Button-1>", lambda e, k=key: self._copy_a_to_b(k))
            ab_btn.bind("<Enter>", lambda e, l=ab_btn: l.configure(fg=theme.accent))
            ab_btn.bind("<Leave>", lambda e, l=ab_btn: l.configure(fg=theme.fg3))
            _Tooltip(
                ab_btn,
                f"Copy {self._profile_a.name} \u2192 {self._profile_b.name}",
                theme=theme,
            )

            bind_scroll(ab_btn, canvas)
            bind_scroll(ba_btn, canvas)

        # Two side-by-side Text widgets
        cols = tk.Frame(row, bg=bg)
        cols.pack(fill="x", padx=(12, 10), pady=(0, 6))
        cols.columnconfigure(0, weight=1, uniform="gcode")
        cols.columnconfigure(1, weight=0, minsize=1)
        cols.columnconfigure(2, weight=1, uniform="gcode")

        self._build_gcode_text_widget(cols, 0, va_str, is_missing_a, is_diff, 0, canvas)
        tk.Frame(cols, bg=theme.border, width=1).grid(row=0, column=1, sticky="ns")
        self._build_gcode_text_widget(cols, 2, vb_str, is_missing_b, is_diff, 1, canvas)

        # Scroll bindings for all gcode row children
        for child in row.winfo_children():
            bind_scroll(child, canvas)
            for grandchild in child.winfo_children():
                bind_scroll(grandchild, canvas)

    def _build_gcode_text_widget(
        self,
        parent: tk.Frame,
        col: int,
        text_content: str,
        is_missing: bool,
        is_diff: bool,
        profile_idx: int,
        canvas: tk.Canvas,
    ) -> None:
        """Build a read-only monospace Text widget for a g-code comparison column."""
        theme = self.theme
        if is_missing:
            fg = theme.fg3
            text_content = "(not set)"
        else:
            fg = (
                (theme.accent if profile_idx == 0 else self._profile_b_fg)
                if is_diff
                else theme.fg3
            )

        line_count = text_content.count("\n") + 1
        height = min(max(line_count, 2), 20)  # 2–20 visible lines

        # Wrapper frame to hold text + vertical scrollbar side by side
        wrapper = tk.Frame(parent, bg=theme.bg3)
        wrapper.grid(
            row=0,
            column=col,
            sticky="nsew",
            padx=(0 if col == 0 else 4, 4 if col == 0 else 0),
        )
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(0, weight=1)

        txt = tk.Text(
            wrapper,
            bg=theme.bg3,
            fg=fg,
            font=(MONO_FONT, MONO_FONT_SIZE),
            height=height,
            wrap="none",
            highlightbackground=theme.border,
            highlightthickness=1,
            borderwidth=0,
            padx=6,
            pady=4,
        )
        txt.insert("1.0", text_content)
        txt.configure(state="disabled")
        txt.grid(row=0, column=0, sticky="nsew")

        # Vertical scrollbar
        vsb = ttk.Scrollbar(wrapper, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")

        # Horizontal scrollbar
        hsb = ttk.Scrollbar(wrapper, orient="horizontal", command=txt.xview)
        txt.configure(xscrollcommand=hsb.set)
        hsb.grid(row=1, column=0, sticky="ew")

        # Scroll mousewheel within text widget (don't redirect to outer canvas)
        _is_mac = _PLATFORM == "Darwin"

        def _on_txt_wheel(event: tk.Event) -> str:
            if _is_mac:
                txt.yview_scroll(int(-1 * event.delta), "units")
            else:
                units = round(-1 * event.delta / _WIN_SCROLL_DELTA_DIVISOR)
                if units == 0:
                    units = -1 if event.delta > 0 else 1
                txt.yview_scroll(units, "units")
            return "break"

        txt.bind("<MouseWheel>", _on_txt_wheel)
        if not _is_mac:
            txt.bind(
                "<Button-4>",
                lambda e: (txt.yview_scroll(-3, "units"), "break")[-1],
            )
            txt.bind(
                "<Button-5>",
                lambda e: (txt.yview_scroll(3, "units"), "break")[-1],
            )

    def _build_copy_arrow(
        self, parent: tk.Frame, key: str, arrow: str, fg_color: str, canvas: tk.Canvas
    ) -> None:
        """Build a single copy arrow button packed into parent cell."""
        theme = self.theme
        bg = parent.cget("bg")
        is_left_arrow = arrow == "\u2190"
        btn = tk.Label(
            parent,
            text=arrow,
            bg=bg,
            fg=fg_color,
            font=(UI_FONT, 14, "bold"),
            cursor="pointinghand",
        )
        btn.pack(fill="both", expand=True)
        if is_left_arrow:
            btn.bind("<Button-1>", lambda e, k=key: self._copy_b_to_a(k))
            btn.bind("<Enter>", lambda e, l=btn: l.configure(fg=theme.fg))
            btn.bind("<Leave>", lambda e, l=btn: l.configure(fg=self._profile_b_fg))
            _Tooltip(btn, f"Copy to {self._profile_a.name}", theme=theme)
        else:
            btn.bind("<Button-1>", lambda e, k=key: self._copy_a_to_b(k))
            btn.bind("<Enter>", lambda e, l=btn: l.configure(fg=theme.fg))
            btn.bind("<Leave>", lambda e, l=btn: l.configure(fg=theme.accent))
            _Tooltip(btn, f"Copy to {self._profile_b.name}", theme=theme)
        bind_scroll(btn, canvas)

    # --- Copy operations (with changelog + undo) ---

    def _copy_value(
        self,
        source_profile: Profile,
        target_profile: Profile,
        source_data: dict,
        target_data: dict,
        json_key: str,
        direction: str,
    ) -> None:
        """Copy a single parameter value from source to target profile.

        Args:
            direction: label like "A" or "B" used in changelog messages.
        """
        new_val = source_data.get(json_key)
        old_val = target_data.get(json_key)
        if new_val == old_val:
            return
        was_modified = target_profile.modified

        snapshot = {json_key: deepcopy(old_val), "_modified": was_modified}

        # Both data and resolved_data must be mutated together: `data` is the
        # canonical store written back to the slicer file, while `resolved_data`
        # (if present) drives the compare-panel display after inheritance
        # resolution.  Keeping them in sync avoids a stale diff view.
        target_profile.data[json_key] = deepcopy(new_val)
        if target_profile.resolved_data is not None:
            target_profile.resolved_data[json_key] = deepcopy(new_val)
        target_profile.modified = True

        target_profile.log_change(
            f"Compare: copied from {direction}",
            f'{json_key}: {old_val} \u2192 {new_val}  (from "{source_profile.name}")',
            snapshot,
        )

        self._undo_stack.append((target_profile, json_key, old_val, was_modified))
        self._pending_keys[json_key] += 1

    def _copy_a_to_b(self, json_key: str) -> None:
        """Copy value from Profile A to Profile B for a single parameter."""
        if not self._profile_b:
            return
        self._copy_value(
            self._profile_a,
            self._profile_b,
            self._data_a,
            self._data_b,
            json_key,
            "A",
        )
        self._trim_undo_stack()
        self._refresh_diff(debounce_render=True)
        save_profile_state(self._profile_b)

    def _copy_b_to_a(self, json_key: str) -> None:
        """Copy value from Profile B to Profile A for a single parameter."""
        if not self._profile_a:
            return
        self._copy_value(
            self._profile_b,
            self._profile_a,
            self._data_b,
            self._data_a,
            json_key,
            "B",
        )
        self._trim_undo_stack()
        self._refresh_diff(debounce_render=True)
        save_profile_state(self._profile_a)

    # --- Bulk copy ---

    def _copy_all_values(
        self,
        source_profile: Profile,
        target_profile: Profile,
        source_data: dict,
        target_data: dict,
        direction: str,
    ) -> None:
        """Copy all differing values from source to target profile."""
        if not self._diff_keys or not target_profile:
            return
        count = len(self._diff_keys)
        if not messagebox.askyesno(
            f"Copy to {target_profile.name}",
            f"Copy {count} differing {'value' if count == 1 else 'values'} from "
            f'"{source_profile.name}" to "{target_profile.name}"?',
            parent=self,
        ):
            return
        for key in sorted(self._diff_keys):
            self._copy_value(
                source_profile,
                target_profile,
                source_data,
                target_data,
                key,
                direction,
            )
        self._trim_undo_stack()
        self._refresh_diff()
        save_profile_state(target_profile)

    def _copy_all_a_to_b(self) -> None:
        """Copy all differing values from Profile A to Profile B."""
        self._copy_all_values(
            self._profile_a,
            self._profile_b,
            self._data_a,
            self._data_b,
            "A",
        )

    def _copy_all_b_to_a(self) -> None:
        """Copy all differing values from Profile B to Profile A."""
        self._copy_all_values(
            self._profile_b,
            self._profile_a,
            self._data_b,
            self._data_a,
            "B",
        )

    # --- Undo ---

    def _trim_undo_stack(self) -> None:
        """Cap undo stack size, adjusting _pending_keys for dropped entries."""
        if len(self._undo_stack) <= MAX_UNDO_STACK_SIZE:
            return
        dropped = self._undo_stack[:-MAX_UNDO_STACK_SIZE]
        self._undo_stack = self._undo_stack[-MAX_UNDO_STACK_SIZE:]
        for _prof, key, _old, _was in dropped:
            self._pending_keys[key] -= 1
            if self._pending_keys[key] <= 0:
                del self._pending_keys[key]

    def _on_undo(self, event: Optional[tk.Event] = None) -> Optional[str]:
        """Undo the last copy operation (Ctrl+Z / Cmd+Z)."""
        if not self._undo_stack:
            return None  # Let other handlers process
        # Flush any pending debounced render to avoid stale UI after undo
        self._cancel_debounce()
        profile, json_key, old_val, was_modified = self._undo_stack.pop()

        # Restore the value
        profile.data[json_key] = deepcopy(old_val)
        if profile.resolved_data is not None:
            profile.resolved_data[json_key] = deepcopy(old_val)
        profile.modified = was_modified

        # Remove the last changelog entry (the one we just undid), but only
        # if there are session-appended entries remaining (guards against
        # partial-save having already cleared them).
        start = self._changelog_start.get(id(profile), 0)
        if len(profile.changelog) > start:
            profile.changelog.pop()

        self._pending_keys[json_key] -= 1
        if self._pending_keys[json_key] <= 0:
            del self._pending_keys[json_key]

        self._refresh_diff()
        save_profile_state(profile)
        return "break"

    # --- Save / Reset ---

    def _on_save(self) -> None:
        """Save pending changes — show review dialog then write to slicer."""
        if not self._pending_keys:
            return

        # Build review summary
        lines = []
        for key in sorted(self._pending_keys):
            val_a = self._data_a.get(key, "(not set)")
            val_b = self._data_b.get(key, "(not set)")
            lines.append(f"  {key}:  {val_a}  \u2192  {val_b}")

        # Determine which profiles were modified
        modified = []
        if self._profile_a.modified:
            modified.append(self._profile_a)
        if self._profile_b.modified:
            modified.append(self._profile_b)

        names = " and ".join(p.name for p in modified)
        n_changes = len(self._pending_keys)
        msg = (
            f"Save {n_changes} {'change' if n_changes == 1 else 'changes'} to {names}?\n\n"
            + "\n".join(lines[:30])
        )
        if len(lines) > 30:
            msg += f"\n  ... and {len(lines) - 30} more"

        if not messagebox.askyesno("Save Changes", msg, parent=self):
            return

        # Write back to slicer files — track successes for partial cleanup
        saved_profiles: set[int] = set()
        for profile in modified:
            try:
                self.app._save_back_to_slicer(profile)
                profile.modified = False
                # Delete only session-appended changelog entries (clamp start to
                # current length so undone entries that were already popped don't
                # cause an out-of-range slice).
                start = min(
                    self._changelog_start.get(id(profile), 0),
                    len(profile.changelog),
                )
                del profile.changelog[start:]
                # Reset the start index so a subsequent save in the same session
                # doesn't re-delete from the stale position.
                self._changelog_start[id(profile)] = len(profile.changelog)
                saved_profiles.add(id(profile))
            except OSError as exc:
                messagebox.showerror(
                    "Save Failed",
                    f"Could not save {profile.name}:\n{exc}",
                    parent=self,
                )
                continue

        if saved_profiles:
            # Remove undo entries and pending keys only for profiles that saved
            self._undo_stack = [
                entry
                for entry in self._undo_stack
                if id(entry[0]) not in saved_profiles
            ]
            # Rebuild pending_keys from remaining undo entries (clean slate
            # avoids phantom counts from partially-saved profiles)
            new_pending: Counter[str] = Counter()
            for entry in self._undo_stack:
                new_pending[entry[1]] += 1
            self._pending_keys = +new_pending  # unary + strips zero/negative counts

        if not self._undo_stack:
            self._pending_keys.clear()

        self._refresh_diff()
        self._update_save_reset_state()

    def _on_reset(self) -> None:
        """Discard all pending changes and restore original values."""
        if not self._pending_keys:
            return

        count = len(self._pending_keys)
        if not messagebox.askyesno(
            "Discard Changes",
            f"Discard {count} unsaved {'change' if count == 1 else 'changes'}?\nThis cannot be undone.",
            parent=self,
        ):
            return

        # Undo all changes in reverse order.
        # Guard changelog pops: after a partial save some entries may already
        # have been deleted, so only pop if the changelog is still longer than
        # it was at session start (i.e. there are session-appended entries).
        while self._undo_stack:
            profile, json_key, old_val, was_modified = self._undo_stack.pop()
            profile.data[json_key] = deepcopy(old_val)
            if profile.resolved_data:
                profile.resolved_data[json_key] = deepcopy(old_val)
            profile.modified = was_modified
            start = self._changelog_start.get(id(profile), 0)
            if len(profile.changelog) > start:
                profile.changelog.pop()
            save_profile_state(profile)

        self._pending_keys.clear()
        self._refresh_diff()
        self._update_save_reset_state()

    def _update_save_reset_state(self) -> None:
        """Enable/disable Save and Reset buttons based on pending state."""
        has_pending = len(self._pending_keys) > 0
        if hasattr(self, "_save_btn"):
            theme = self.theme
            if has_pending:
                self._save_btn.configure(
                    bg=theme.accent,
                    fg=theme.accent_fg,
                    cursor="pointinghand",
                    state="normal",
                )
                self._reset_btn.configure(cursor="pointinghand", state="normal")
            else:
                self._save_btn.configure(
                    bg=theme.bg4,
                    fg=theme.fg3,
                    cursor="arrow",
                    state="disabled",
                )
                self._reset_btn.configure(cursor="arrow", state="disabled")

    # --- Refresh ---

    def _refresh_diff(self, debounce_render: bool = False) -> None:
        """Recompute diff keys, update counters, and re-render.

        Args:
            debounce_render: If True, defer _render_rows by 50ms so rapid
                consecutive copy operations coalesce into a single re-render.
        """
        data_a = (
            self._profile_a.resolved_data
            if self._profile_a.resolved_data is not None
            else self._profile_a.data
        )
        data_b = (
            self._profile_b.resolved_data
            if self._profile_b.resolved_data is not None
            else self._profile_b.data
        )
        self._data_a = data_a
        self._data_b = data_b

        all_keys = (set(data_a.keys()) | set(data_b.keys())) - _IDENTITY_KEYS
        self._diff_keys = {k for k in all_keys if data_a.get(k) != data_b.get(k)}
        self._diff_count = len(self._diff_keys)
        self._missing_count = sum(
            1 for k in all_keys if data_a.get(k) is None or data_b.get(k) is None
        )

        if hasattr(self, "_summary_label"):
            self._summary_label.configure(
                text=f"{self._diff_count} difference{'s' if self._diff_count != 1 else ''} across {self._total_params} parameters",
            )
        self._update_history_label()
        self._update_chip_styles()
        self._update_status_bar()
        self._update_nav_badges()
        self._update_save_reset_state()
        if debounce_render:
            if getattr(self, "_refresh_render_id", None):
                self.after_cancel(self._refresh_render_id)
            if self.winfo_exists():
                self._refresh_render_id = self.after(50, self._deferred_render_rows)
        else:
            self._render_rows()

    def _deferred_render_rows(self) -> None:
        """Deferred row render callback (debounced from _refresh_diff)."""
        self._refresh_render_id = None
        self._render_rows()

    # --- Status / history helpers ---

    def _update_status_bar(self) -> None:
        theme = self.theme
        if hasattr(self, "_status_diff_label"):
            self._status_diff_label.configure(
                text=f"{self._diff_count} differences",
            )
        if hasattr(self, "_status_pending_label"):
            pending_fg = theme.modified if self._pending_count > 0 else theme.fg3
            pending_weight = "bold" if self._pending_count > 0 else "normal"
            self._status_pending_label.configure(
                text=(
                    f"{self._pending_count} unsaved"
                    if self._pending_count > 0
                    else "No changes"
                ),
                fg=pending_fg,
                font=(UI_FONT, 13, pending_weight),
            )
        if hasattr(self, "_status_missing_label"):
            missing_count = getattr(self, "_missing_count", 0)
            self._status_missing_label.configure(
                text=(
                    f"{missing_count} unmatched"
                    if missing_count > 0
                    else "None unmatched"
                ),
                fg=theme.error if missing_count > 0 else theme.fg3,
            )
        if hasattr(self, "_status_filter_label"):
            _filter_label_map = {
                "diffs": "Changed only",
                "missing": "Unmatched values",
                "all": "All parameters",
                "pending": "Unsaved changes",
            }
            self._status_filter_label.configure(
                text=f"Showing: {_filter_label_map.get(self._filter_mode, self._filter_mode)}",
            )

    def _update_history_label(self) -> None:
        """Show/hide the Undo / Changelog link based on combined changelog length."""
        if not hasattr(self, "_history_label"):
            return
        total = 0
        if self._profile_a:
            total += len(self._profile_a.changelog)
        if self._profile_b:
            total += len(self._profile_b.changelog)
        if total > 0:
            self._history_label.configure(text=f"\u00b7  Change History ({total})")
        else:
            self._history_label.configure(text="")

    # --- Changelog dialog ---

    def _show_changelog(self) -> None:
        """Open a dialog showing combined changelog for both profiles, with undo."""
        theme = self.theme
        profile_a, profile_b = self._profile_a, self._profile_b
        if not profile_a and not profile_b:
            return

        dialog = tk.Toplevel(self)
        dialog.title("Compare — Change History")
        dialog.configure(bg=theme.bg)
        dialog.resizable(True, True)
        dialog.transient(self.winfo_toplevel())
        dialog.geometry("640x480")
        dialog.minsize(560, 360)

        tk.Label(
            dialog,
            text="Change History",
            bg=theme.bg,
            fg=theme.fg,
            font=(UI_FONT, 14, "bold"),
        ).pack(padx=16, pady=(12, 8), anchor="w")

        list_frame = tk.Frame(
            dialog,
            bg=theme.bg3,
            highlightbackground=theme.border,
            highlightthickness=1,
        )
        list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        canvas = tk.Canvas(
            list_frame, bg=theme.bg3, highlightthickness=0, yscrollincrement=4
        )
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=theme.bg3)
        content.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _rebuild_entries() -> None:
            for w in content.winfo_children():
                w.destroy()

            # Merge changelogs from both profiles with profile attribution
            entries = []
            for profile in [profile_a, profile_b]:
                if not profile:
                    continue
                for idx, entry in enumerate(profile.changelog):
                    timestamp = entry[0]
                    entries.append((timestamp, profile, idx, entry))

            # Sort newest first
            entries.sort(key=lambda x: x[0], reverse=True)

            if not entries:
                tk.Label(
                    content,
                    text="No changes recorded.",
                    bg=theme.bg3,
                    fg=theme.fg3,
                    font=(UI_FONT, 14),
                ).pack(padx=16, pady=16)
                return

            for i, (timestamp, profile, real_idx, entry) in enumerate(entries):
                action, details = entry[1], entry[2]
                has_snapshot = len(entry) >= 4 and entry[3] is not None

                if i > 0:
                    tk.Frame(content, bg=theme.border, height=1).pack(
                        fill="x", padx=8, pady=(4, 4)
                    )

                row = tk.Frame(content, bg=theme.bg3)
                row.pack(fill="x", padx=10, pady=(6, 2))

                # Profile name badge
                is_a = profile is profile_a
                profile_fg = theme.accent if is_a else self._profile_b_fg
                header = tk.Frame(row, bg=theme.bg3)
                header.pack(fill="x")

                tk.Label(
                    header,
                    text=profile.name,
                    bg=theme.bg3,
                    fg=profile_fg,
                    font=(UI_FONT, 14, "bold"),
                ).pack(side="left")
                tk.Label(
                    header,
                    text=f"  {action}",
                    bg=theme.bg3,
                    fg=theme.modified,
                    font=(UI_FONT, 14, "bold"),
                ).pack(side="left")
                tk.Label(
                    header,
                    text=f"  {timestamp}",
                    bg=theme.bg3,
                    fg=theme.fg3,
                    font=(UI_FONT, 13),
                ).pack(side="left", pady=(1, 0))

                if details:
                    detail_lbl = tk.Label(
                        row,
                        text=details,
                        bg=theme.bg3,
                        fg=theme.fg2,
                        font=(UI_FONT, 14),
                        anchor="w",
                        justify="left",
                    )
                    detail_lbl.pack(anchor="w", fill="x", pady=(2, 0))
                    # Adapt wraplength to available width on resize
                    detail_lbl.bind(
                        "<Configure>",
                        lambda e, lbl=detail_lbl: lbl.configure(
                            wraplength=max(100, e.width - 10)
                        ),
                    )

                # Undo button — only for the most recent entry of that profile
                if has_snapshot and real_idx == len(profile.changelog) - 1:
                    _prof = profile
                    _idx = real_idx

                    def _undo(p=_prof, idx=_idx) -> None:
                        # Check undo-stack match BEFORE restore_snapshot pops the changelog entry
                        should_pop = (
                            self._undo_stack
                            and self._undo_stack[-1][0] is p
                            and len(p.changelog) - 1 == idx
                        )
                        p.restore_snapshot(idx)
                        if should_pop:
                            _, undo_key, _, _ = self._undo_stack.pop()
                            self._pending_keys[undo_key] -= 1
                            if self._pending_keys[undo_key] <= 0:
                                del self._pending_keys[undo_key]
                        _rebuild_entries()
                        self._refresh_diff()
                        save_profile_state(p)

                    _make_btn(
                        row,
                        "\u21a9 Undo this change",
                        _undo,
                        bg=theme.bg4,
                        fg=theme.warning,
                        font=(UI_FONT, 14),
                        padx=10,
                        pady=4,
                    ).pack(anchor="w", pady=(6, 2))

            # Bind scroll on all children so mousewheel works everywhere
            def _bind_recursive(w: tk.Widget) -> None:
                bind_scroll(w, canvas)
                for child in w.winfo_children():
                    _bind_recursive(child)

            _bind_recursive(content)

        _rebuild_entries()

        _make_btn(
            dialog,
            "Close",
            dialog.destroy,
            bg=theme.bg4,
            fg=theme.fg2,
            font=(UI_FONT, 14),
            padx=12,
            pady=5,
        ).pack(pady=(4, 12))

        dialog.update_idletasks()
        w = min(max(dialog.winfo_reqwidth(), 420), 580)
        h = min(max(dialog.winfo_reqheight(), 200), 520)
        x = self.winfo_rootx() + 60
        y = self.winfo_rooty() + 60
        dialog.geometry(f"{w}x{h}+{x}+{y}")

    # --- Delta computation ---

    @staticmethod
    def _compute_delta(val_a: Any, val_b: Any) -> str:
        """Compute a percentage delta string for numeric values. Empty if non-numeric."""
        try:
            float_a = (
                float(val_a) if not isinstance(val_a, (list, dict, bool)) else None
            )
            float_b = (
                float(val_b) if not isinstance(val_b, (list, dict, bool)) else None
            )
        except (TypeError, ValueError):
            return ""
        if float_a is None or float_b is None:
            return ""
        if float_a == 0 and float_b == 0:
            return ""
        if float_a == 0:
            return "+\u221e" if float_b > 0 else "\u2212\u221e"
        pct = ((float_b - float_a) / abs(float_a)) * 100
        if abs(pct) < 0.5:
            return ""
        sign = "+" if pct > 0 else "\u2212"
        return f"{sign}{abs(pct):.0f}%"

    # --- Formatting helpers ---

    def _fmt(self, value: Any, key: Optional[str] = None) -> str:
        if value is None:
            return "\u2014"  # em-dash for missing values
        value = nil_to_zero(value)
        if isinstance(value, list):
            value = [nil_to_zero(v) for v in value]
            unique = list(dict.fromkeys(str(x) for x in value))
            if not unique:
                return "\u2014"
            if len(unique) == 1:
                raw = unique[0]
                if key and key in ENUM_VALUES:
                    return get_enum_human_label(key, raw)
                return raw
            return ", ".join(unique)
        if isinstance(value, bool):
            return "Yes" if value else "No"
        s = str(value)
        if key and key in ENUM_VALUES:
            return get_enum_human_label(key, s)
        return s

    @staticmethod
    def _truncate_name(name: str, max_len: int, font: Any = None) -> str:
        """Truncate name to fit within max_len pixels (if font given) or characters."""
        if font is not None:
            # Pixel-based truncation using font metrics
            if font.measure(name) <= max_len:
                return name
            ellipsis = "\u2026"
            for i in range(len(name), 0, -1):
                if font.measure(name[:i] + ellipsis) <= max_len:
                    return name[:i] + ellipsis
            return ellipsis
        return name if len(name) <= max_len else name[: max_len - 1] + "\u2026"
