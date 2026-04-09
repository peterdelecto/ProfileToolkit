# Dialog windows (compare, recommendations, online import, batch rename)

from __future__ import annotations

import logging
import os
import tempfile
import threading
import tkinter as tk
import urllib.error
import webbrowser
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
    _DLG_COMPARE_WIDTH,
    _DLG_COMPARE_HEIGHT,
    _DLG_COMPARE_MIN_WIDTH,
    _DLG_COMPARE_MIN_HEIGHT,
    _VALUE_TRUNCATE_SHORT,
    UI_FONT,
    ENUM_VALUES,
    RECOMMENDATIONS,
)
from .theme import Theme
from .models import Profile, ProfileEngine, SlicerDetector
from .providers import ALL_PROVIDERS, PROVIDER_CATEGORIES, OnlineProfileEntry
from .state import load_online_prefs, save_online_prefs
from .utils import (
    bind_scroll,
    lighten_color,
    detect_material,
    get_recommendation,
    get_recommendation_info,
    check_value_range,
    get_enum_human_label,
)
from .widgets import ScrollableFrame, make_btn

logger = logging.getLogger(__name__)


class CompareDialog(tk.Toplevel):
    """Side-by-side comparison of two profiles, grouped by section."""

    def __init__(self, parent: tk.Widget, theme: Theme, profile_a: Profile, profile_b: Profile) -> None:
        super().__init__(parent)
        self.theme = theme
        self.title("Compare Profiles")
        self.configure(bg=theme.bg)
        self.geometry(f"{_DLG_COMPARE_WIDTH}x{_DLG_COMPARE_HEIGHT}")
        self.minsize(_DLG_COMPARE_MIN_WIDTH, _DLG_COMPARE_MIN_HEIGHT)
        self.transient(parent)
        self._build(profile_a, profile_b)

    def _build(self, profile_a: Profile, profile_b: Profile) -> None:
        theme = self.theme

        # ── Header: two profile name columns ──
        header_frame = tk.Frame(self, bg=theme.bg)
        header_frame.pack(fill="x", padx=16, pady=(10, 4))
        # Left name
        tk.Label(header_frame, text=profile_a.name, bg=theme.bg, fg=theme.accent,
                 font=(UI_FONT, 13, "bold")).pack(side="left")
        # Centered "vs"
        tk.Label(header_frame, text="  vs  ", bg=theme.bg, fg=theme.fg2,
                 font=(UI_FONT, 12)).pack(side="left")
        # Right name
        tk.Label(header_frame, text=profile_b.name, bg=theme.bg, fg=theme.warning,
                 font=(UI_FONT, 13, "bold")).pack(side="left")

        # ── Find differences and group by section ──
        all_keys = set(profile_a.data.keys()) | set(profile_b.data.keys())
        all_keys -= _IDENTITY_KEYS
        diffs = {}
        for k in all_keys:
            value_a = profile_a.data.get(k)
            value_b = profile_b.data.get(k)
            if value_a != value_b:
                diffs[k] = (value_a, value_b)

        # Build section lookup from layout
        layout = FILAMENT_LAYOUT if profile_a.profile_type == "filament" else PROCESS_LAYOUT
        key_to_label = {}
        key_to_group = {}  # key -> "Tab > Section"
        for tab_name, sections in layout.items():
            for sec_name, params in sections.items():
                for json_key, ui_label in params:
                    key_to_label[json_key] = ui_label
                    key_to_group[json_key] = f"{tab_name} \u203a {sec_name}"

        # Group diffs by section
        grouped = {}
        for key in sorted(diffs.keys(), key=lambda k: (key_to_group.get(k, "zzz"), k)):
            group = key_to_group.get(key, "Other")
            if group not in grouped:
                grouped[group] = []
            grouped[group].append(key)

        diff_count = len(diffs)
        tk.Label(self, text=f"{diff_count} parameter{'s' if diff_count != 1 else ''} differ",
                 bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12)).pack(anchor="w", padx=16, pady=(0, 6))

        # ── Column headers (fixed above scroll) ──
        col_hdr = tk.Frame(self, bg=theme.bg4)
        col_hdr.pack(fill="x", padx=16)
        tk.Label(col_hdr, text="Parameter", bg=theme.bg4, fg=theme.fg,
                 font=(UI_FONT, 12, "bold"), anchor="w",
                 padx=8, pady=4).pack(side="left", fill="x", expand=True)
        tk.Label(col_hdr, text="Left", bg=theme.bg4, fg=theme.accent,
                 font=(UI_FONT, 12, "bold"), width=18, anchor="w",
                 padx=4, pady=4).pack(side="left")
        tk.Label(col_hdr, text="Right", bg=theme.bg4, fg=theme.warning,
                 font=(UI_FONT, 12, "bold"), width=18, anchor="w",
                 padx=4, pady=4).pack(side="left")
        tk.Label(col_hdr, text="Change", bg=theme.bg4, fg=theme.fg2,
                 font=(UI_FONT, 12, "bold"), width=8, anchor="w",
                 padx=4, pady=4).pack(side="left")

        # ── Scrollable content ──
        container = tk.Frame(self, bg=theme.bg)
        container.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        scroll_frame = ScrollableFrame(container, bg=theme.bg2)
        scroll_frame.pack(fill="both", expand=True)
        body = scroll_frame.body
        canvas = scroll_frame.canvas

        # Scroll helper — bind to widget and all children
        def _bind_scroll_recursive(widget: tk.Widget) -> None:
            bind_scroll(widget, canvas)
            for child in widget.winfo_children():
                _bind_scroll_recursive(child)

        # ── Render grouped sections ──
        row_idx = 0
        for group_name, keys in grouped.items():
            # Section header
            sec_hdr = tk.Frame(body, bg=theme.bg2)
            sec_hdr.pack(fill="x", pady=(8, 2))
            bar = tk.Frame(sec_hdr, bg=theme.accent, width=3)
            bar.pack(side="left", fill="y", padx=(0, 8))
            tk.Label(sec_hdr, text=group_name, bg=theme.bg2, fg=theme.fg,
                     font=(UI_FONT, 12, "bold"), padx=4).pack(side="left")

            for key in keys:
                value_a, value_b = diffs[key]
                bg = theme.bg2 if row_idx % 2 == 0 else theme.bg3
                row = tk.Frame(body, bg=bg)
                row.pack(fill="x")

                label = key_to_label.get(key, key)
                va_str = self._fmt(value_a, key=key)
                vb_str = self._fmt(value_b, key=key)
                delta = self._delta(value_a, value_b)

                tk.Label(row, text=label, bg=bg, fg=theme.fg, font=(UI_FONT, 12),
                         anchor="w", padx=10, pady=3).pack(side="left", fill="x", expand=True)
                # Left value
                va_fg = theme.accent if value_a is not None else theme.fg3
                tk.Label(row, text=va_str, bg=bg, fg=va_fg, font=(UI_FONT, 12),
                         width=18, anchor="w", padx=4).pack(side="left")
                # Right value
                vb_fg = theme.warning if value_b is not None else theme.fg3
                tk.Label(row, text=vb_str, bg=bg, fg=vb_fg, font=(UI_FONT, 12),
                         width=18, anchor="w", padx=4).pack(side="left")
                # Delta
                delta_fg = theme.converted if delta != "\u2014" else theme.fg3
                tk.Label(row, text=delta, bg=bg, fg=delta_fg, font=(UI_FONT, 12),
                         width=8, anchor="w", padx=4).pack(side="left")
                row_idx += 1

        if not diffs:
            tk.Label(body, text="These profiles are identical.",
                     bg=theme.bg2, fg=theme.fg2, font=(UI_FONT, 13), pady=30).pack()

        _bind_scroll_recursive(body)

    def _fmt(self, value: Any, key: Optional[str] = None) -> str:
        if value is None:
            return "(not set)"
        if isinstance(value, list):
            unique = list(dict.fromkeys(str(x) for x in value))
            if len(unique) == 1:
                raw = unique[0]
                if key and key in ENUM_VALUES:
                    return get_enum_human_label(key, raw)
                return raw
            return ", ".join(str(x) for x in value)
        if isinstance(value, bool):
            return "Yes" if value else "No"
        s = str(value)
        if key and key in ENUM_VALUES:
            return get_enum_human_label(key, s)
        return s[:_VALUE_TRUNCATE_SHORT] + "..." if len(s) > _VALUE_TRUNCATE_SHORT else s

    def _delta(self, value_a: Any, value_b: Any) -> str:
        try:
            float_a = float(value_a[0] if isinstance(value_a, list) else value_a)
            float_b = float(value_b[0] if isinstance(value_b, list) else value_b)
            if float_a == 0:
                return f"+{float_b}" if float_b != 0 else "—"
            pct = ((float_b - float_a) / abs(float_a)) * 100
            sign = "+" if pct > 0 else ""
            return f"{sign}{pct:.0f}%"
        except (TypeError, ValueError, IndexError) as e:
            logger.debug("Could not compute delta for %r vs %r: %s", value_a, value_b, e)
            return "—"


class RecommendationsDialog:
    """Full recommendations dialog with statistical analysis of loaded profiles.

    Provides 'Apply Typical' action to set parameters to recommended values.
    """

    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        profile: Profile,
        all_profiles: Optional[list[Profile]] = None,
    ) -> None:
        self.theme = theme
        self.profile = profile
        self.all_profiles = all_profiles or []
        self._apply_vars = {}  # key -> BooleanVar for checkboxes

        display_data = profile.resolved_data if profile.resolved_data else profile.data
        material = detect_material(display_data)

        self.dlg = dlg = tk.Toplevel(parent)
        dlg.title(f"Smart Recommendations — {profile.name}")
        dlg.configure(bg=theme.bg)
        dlg.resizable(True, True)
        dlg.transient(parent.winfo_toplevel())
        dlg.geometry("720x560+%d+%d" % (parent.winfo_rootx() + 40, parent.winfo_rooty() + 40))
        dlg.minsize(600, 400)

        # Header
        hdr = tk.Frame(dlg, bg=theme.bg)
        hdr.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(hdr, text="\u2699 Smart Recommendations", bg=theme.bg, fg=theme.fg,
                 font=(UI_FONT, 16, "bold")).pack(side="left")
        mat_text = material if material != "General" else "Unknown material"
        tk.Label(hdr, text=f"  \u00b7  {mat_text}  \u00b7  {profile.name}",
                 bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 13)).pack(side="left")

        # Statistical summary bar
        stats = self._compute_stats(display_data, material)
        stats_frame = tk.Frame(dlg, bg=theme.bg3, highlightbackground=theme.border,
                               highlightthickness=1)
        stats_frame.pack(fill="x", padx=16, pady=(4, 8))
        stats_inner = tk.Frame(stats_frame, bg=theme.bg3, padx=12, pady=8)
        stats_inner.pack(fill="x")
        tk.Label(stats_inner,
                 text=f"{stats['total']} parameters checked  \u00b7  "
                      f"{stats['ok']} in range  \u00b7  "
                      f"{stats['low']} below  \u00b7  "
                      f"{stats['high']} above",
                 bg=theme.bg3, fg=theme.fg, font=(UI_FONT, 12)).pack(side="left")

        # Score visual
        if stats['total'] > 0:
            pct = round(100 * stats['ok'] / stats['total'])
            score_fg = theme.accent if pct >= 80 else theme.warning if pct >= 50 else theme.error
            tk.Label(stats_inner, text=f"{pct}% in range", bg=theme.bg3, fg=score_fg,
                     font=(UI_FONT, 13, "bold")).pack(side="right")

        # Loaded profiles statistical comparison
        if self.all_profiles and len(self.all_profiles) > 1:
            loaded_stats = self._compute_loaded_profile_stats(display_data, material)
            if loaded_stats:
                comp_frame = tk.Frame(dlg, bg=theme.bg3, highlightbackground=theme.border,
                                       highlightthickness=1)
                comp_frame.pack(fill="x", padx=16, pady=(0, 8))
                comp_inner = tk.Frame(comp_frame, bg=theme.bg3, padx=12, pady=6)
                comp_inner.pack(fill="x")
                tk.Label(comp_inner,
                         text=f"Compared against {len(self.all_profiles)} loaded profiles:",
                         bg=theme.bg3, fg=theme.fg2, font=(UI_FONT, 12)).pack(anchor="w")
                if loaded_stats.get("outliers"):
                    outlier_text = ", ".join(loaded_stats["outliers"][:5])
                    if len(loaded_stats["outliers"]) > 5:
                        outlier_text += f" +{len(loaded_stats['outliers']) - 5} more"
                    tk.Label(comp_inner,
                             text=f"Outliers vs loaded profiles: {outlier_text}",
                             bg=theme.bg3, fg=theme.warning, font=(UI_FONT, 12),
                             wraplength=650, justify="left").pack(anchor="w", pady=(2, 0))

        # Scrollable parameter list
        sf = ScrollableFrame(dlg, bg=theme.bg)
        sf.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        out_of_range = []
        layout = FILAMENT_LAYOUT if profile.profile_type == "filament" else PROCESS_LAYOUT
        for tab_name, sections in layout.items():
            for section_name, params in sections.items():
                for json_key, ui_label in params:
                    if json_key not in display_data:
                        continue
                    val = display_data[json_key]
                    status = check_value_range(json_key, val, material)
                    if status in ("low", "high"):
                        rec = get_recommendation(json_key, material)
                        out_of_range.append((json_key, ui_label, val, status, rec, tab_name))

        if out_of_range:
            # Select All / Deselect All
            sel_frame = tk.Frame(sf.body, bg=theme.bg)
            sel_frame.pack(fill="x", pady=(4, 6))
            self._select_all_var = tk.BooleanVar(value=True)

            def _toggle_all() -> None:
                val = self._select_all_var.get()
                for v in self._apply_vars.values():
                    v.set(val)

            cb = tk.Checkbutton(sel_frame, text="Select all", variable=self._select_all_var,
                                command=_toggle_all, bg=theme.bg, fg=theme.fg,
                                selectcolor=theme.bg3, activebackground=theme.bg,
                                activeforeground=theme.fg, font=(UI_FONT, 12))
            cb.pack(side="left")

            # Column headers
            hdr_row = tk.Frame(sf.body, bg=theme.bg3)
            hdr_row.pack(fill="x", pady=(0, 4))
            hdr_row.columnconfigure(0, minsize=30)
            hdr_row.columnconfigure(1, minsize=180)
            hdr_row.columnconfigure(2, minsize=80)
            hdr_row.columnconfigure(3, minsize=30)
            hdr_row.columnconfigure(4, minsize=100)
            hdr_row.columnconfigure(5, minsize=80)
            for ci, (text, w) in enumerate([
                ("", 30), ("Parameter", 180), ("Current", 80), ("", 30),
                ("Recommended", 100), ("Typical", 80)
            ]):
                tk.Label(hdr_row, text=text, bg=theme.bg3, fg=theme.fg2,
                         font=(UI_FONT, 12, "bold"), anchor="w").grid(
                    row=0, column=ci, sticky="w", padx=4, pady=4)

            for json_key, ui_label, val, status, rec, tab_name in out_of_range:
                self._render_rec_row(sf.body, json_key, ui_label, val, status, rec, tab_name)
        else:
            tk.Label(sf.body,
                     text="\u2705  All parameters are within recommended ranges!",
                     bg=theme.bg, fg=theme.accent, font=(UI_FONT, 14, "bold")).pack(pady=30)

        sf.bind_scroll_recursive()

        # Bottom buttons
        btn_frame = tk.Frame(dlg, bg=theme.bg)
        btn_frame.pack(fill="x", padx=16, pady=(0, 12))
        if out_of_range:
            apply_btn = make_btn(btn_frame, "Apply Typical Values", self._apply_typical,
                                  bg=theme.accent2, fg=theme.accent_fg,
                                  font=(UI_FONT, 12, "bold"), padx=16, pady=6)
            apply_btn.pack(side="left", padx=(0, 8))
        make_btn(btn_frame, "Close", dlg.destroy,
                  bg=theme.bg4, fg=theme.fg2,
                  font=(UI_FONT, 12), padx=16, pady=6).pack(side="right")

    def _render_rec_row(
        self,
        parent: tk.Widget,
        key: str,
        label: str,
        value: Any,
        status: str,
        rec: Optional[dict],
        tab_name: str,
    ) -> None:
        theme = self.theme
        row = tk.Frame(parent, bg=theme.param_bg)
        row.pack(fill="x", pady=1)
        row.columnconfigure(0, minsize=30)
        row.columnconfigure(1, minsize=180)
        row.columnconfigure(2, minsize=80)
        row.columnconfigure(3, minsize=30)
        row.columnconfigure(4, minsize=100)
        row.columnconfigure(5, minsize=80)

        # Checkbox
        var = tk.BooleanVar(value=True)
        self._apply_vars[key] = var
        cb = tk.Checkbutton(row, variable=var, bg=theme.param_bg,
                            selectcolor=theme.bg3, activebackground=theme.param_bg)
        cb.grid(row=0, column=0, sticky="w", padx=4)

        # Parameter name
        tk.Label(row, text=label, bg=theme.param_bg, fg=theme.fg,
                 font=(UI_FONT, 12, "bold"), anchor="w").grid(
            row=0, column=1, sticky="w", padx=4)

        # Current value
        disp_val = value
        if isinstance(value, list):
            unique = list(dict.fromkeys(str(v) for v in value))
            disp_val = unique[0] if len(unique) == 1 else ", ".join(str(v) for v in value)
        tk.Label(row, text=str(disp_val), bg=theme.param_bg, fg=theme.fg2,
                 font=(UI_FONT, 12), anchor="w").grid(
            row=0, column=2, sticky="w", padx=4)

        # Indicator arrow
        arrow = "\u25bc" if status == "low" else "\u25b2"
        arrow_fg = theme.converted if status == "low" else theme.warning
        tk.Label(row, text=arrow, bg=theme.param_bg, fg=arrow_fg,
                 font=(UI_FONT, 12, "bold")).grid(row=0, column=3, padx=2)

        # Recommended range
        if rec:
            range_text = f"{rec.get('min', '?')} – {rec.get('max', '?')}"
            tk.Label(row, text=range_text, bg=theme.param_bg, fg=theme.fg2,
                     font=(UI_FONT, 12), anchor="w").grid(
                row=0, column=4, sticky="w", padx=4)

            typical = rec.get("typical", "")
            tk.Label(row, text=str(typical), bg=theme.param_bg, fg=theme.accent,
                     font=(UI_FONT, 12, "bold"), anchor="w").grid(
                row=0, column=5, sticky="w", padx=4)

    def _apply_typical(self) -> None:
        if not self.profile:
            return
        material = detect_material(self.profile.data)
        applied = 0
        for key, var in self._apply_vars.items():
            if not var.get():
                continue
            rec = get_recommendation(key, material)
            if not rec or "typical" not in rec:
                continue
            typical = rec["typical"]
            original = self.profile.data.get(key)
            if original is None:
                continue
            if isinstance(original, list) and original:
                new_val = [type(original[0])(typical)] * len(original)
            elif isinstance(original, int):
                new_val = int(typical)
            elif isinstance(original, float):
                new_val = float(typical)
            else:
                new_val = typical
            if new_val != original:
                self.profile.data[key] = new_val
                self.profile.modified = True
                self.profile.log_change("Recommendation applied",
                                        f"{key}: {original} \u2192 {new_val}")
                applied += 1

        if applied:
            messagebox.showinfo("Applied",
                                f"Applied {applied} recommended typical value{'s' if applied != 1 else ''}.\n"
                                f"View the profile to see changes.",
                                parent=self.dlg)
            # Refresh the detail panel
            self._refresh_detail()
        self.dlg.destroy()

    def _refresh_detail(self) -> None:
        try:
            parent = self.dlg.master
            while parent:
                # Import here to avoid circular dependency
                from .panels import ProfileListPanel
                if isinstance(parent, ProfileListPanel):
                    parent.detail.show_profile(self.profile)
                    parent._refresh_list()
                    return
                parent = getattr(parent, 'master', None)
        except Exception:
            pass

    def _compute_stats(self, data: dict, material: str) -> dict[str, int]:
        total = ok = low = high = 0
        for key, val in data.items():
            status = check_value_range(key, val, material)
            if status is not None:
                total += 1
                if status == "ok":
                    ok += 1
                elif status == "low":
                    low += 1
                elif status == "high":
                    high += 1
        return {"total": total, "ok": ok, "low": low, "high": high}

    def _compute_loaded_profile_stats(self, data: dict, material: str) -> Optional[dict]:
        if len(self.all_profiles) < 2:
            return None
        outliers = []
        for key, val in data.items():
            if isinstance(val, list):
                val = val[0] if val else None
            try:
                num = float(val)
            except (ValueError, TypeError):
                continue
            # Gather values from all loaded profiles
            values = []
            for p in self.all_profiles:
                pdata = p.resolved_data if p.resolved_data else p.data
                pval = pdata.get(key)
                if isinstance(pval, list):
                    pval = pval[0] if pval else None
                try:
                    values.append(float(pval))
                except (ValueError, TypeError):
                    continue
            if len(values) < 3:
                continue
            avg = sum(values) / len(values)
            std = (sum((v - avg) ** 2 for v in values) / len(values)) ** 0.5
            if std > 0 and abs(num - avg) > 2 * std:
                # Find UI label
                ui_label = key.replace("_", " ").capitalize()
                for layout in (PROCESS_LAYOUT, FILAMENT_LAYOUT):
                    for sections in layout.values():
                        for params in sections.values():
                            for k, l in params:
                                if k == key:
                                    ui_label = l
                                    break
                outliers.append(ui_label)
        return {"outliers": outliers} if outliers else None


class OnlineImportWizard(tk.Toplevel):
    """3-step wizard: Choose Source -> Browse & Select -> Confirm & Import."""

    _WIDTH: int = 720
    _HEIGHT: int = 560

    def __init__(self, parent: tk.Widget, theme: Theme, load_callback: Callable) -> None:
        super().__init__(parent)
        self.theme = theme
        self._load_callback = load_callback
        self.title("Import from Online Sources")
        self.configure(bg=theme.bg)
        self.geometry(f"{self._WIDTH}x{self._HEIGHT}")
        self.minsize(600, 450)
        self.transient(parent)
        self.grab_set()
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 60, parent.winfo_rooty() + 40))

        self._prefs = load_online_prefs()
        self._current_step = 0
        self._selected_provider = None
        self._catalog = []           # list of OnlineProfileEntry
        self._filtered_catalog = []  # after applying filters
        self._selected_entries = []  # entries user checked
        self._import_status = tk.StringVar(value="")  # download progress text
        self._cancelled = False  # flag for thread cancellation

        # Filter state
        self._filter_material = tk.StringVar(value="All")
        self._filter_brand = tk.StringVar(value="All")
        self._filter_slicer = tk.StringVar(value="All")
        self._filter_machine = tk.StringVar(value="All")

        # Style comboboxes for dark theme
        self._style_combos()

        self._active_canvas = None  # current scrollable canvas for mousewheel
        self._scroll_bind_id = None
        self._fetch_done = False  # flag to prevent race conditions on fetch timeout

        self._build_chrome()
        self._show_step(0)

    def _bind_wizard_scroll(self, canvas: tk.Canvas) -> None:
        # Unbind previous
        if self._scroll_bind_id:
            self.unbind("<MouseWheel>", self._scroll_bind_id)
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
        # Also bind Button-4/5 for Linux
        self.bind("<Button-4>", lambda e: canvas.yview_scroll(-3, "units"))
        self.bind("<Button-5>", lambda e: canvas.yview_scroll(3, "units"))

    def _style_combos(self) -> None:
        theme = self.theme
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Dark.TCombobox",
                         fieldbackground=theme.bg3,
                         background=theme.bg4,
                         foreground=theme.fg,
                         arrowcolor=theme.fg,
                         selectbackground=theme.sel,
                         selectforeground=theme.fg)
        style.map("Dark.TCombobox",
                   fieldbackground=[("readonly", theme.bg3)],
                   foreground=[("readonly", theme.fg)],
                   selectbackground=[("readonly", theme.sel)],
                   selectforeground=[("readonly", theme.fg)])
        # Style the dropdown list
        self.option_add("*TCombobox*Listbox.background", theme.bg3)
        self.option_add("*TCombobox*Listbox.foreground", theme.fg)
        self.option_add("*TCombobox*Listbox.selectBackground", theme.accent2)
        self.option_add("*TCombobox*Listbox.selectForeground", theme.accent_fg)

    def _build_chrome(self) -> None:
        theme = self.theme

        # ── Step indicator bar ──
        self._step_bar = tk.Frame(self, bg=theme.bg2)
        self._step_bar.pack(fill="x")
        self._step_labels = []
        steps = ["Source", "Browse & Select", "Confirm & Import"]
        for i, label in enumerate(steps):
            fg = theme.accent if i == 0 else theme.fg3
            font_weight = "bold" if i == 0 else "normal"
            lbl = tk.Label(self._step_bar, text=f"  {i+1}. {label}  ",
                           bg=theme.bg2, fg=fg, font=(UI_FONT, 12, font_weight),
                           padx=8, pady=8)
            lbl.pack(side="left")
            self._step_labels.append(lbl)
            if i < len(steps) - 1:
                tk.Label(self._step_bar, text="\u203a", bg=theme.bg2, fg=theme.fg3,
                         font=(UI_FONT, 12)).pack(side="left")

        # ── Separator ──
        tk.Frame(self, bg=theme.border, height=1).pack(fill="x")

        # ── Footer nav buttons (pack bottom-first so they're always visible) ──
        self._footer_sep = tk.Frame(self, bg=theme.border, height=1)
        self._footer_sep.pack(fill="x", side="bottom")
        self._footer = tk.Frame(self, bg=theme.bg2)
        self._footer.pack(fill="x", side="bottom")

        # ── Content area (fills remaining space between step bar and footer) ──
        self._content = tk.Frame(self, bg=theme.bg)
        self._content.pack(fill="both", expand=True)
        self._btn_cancel = make_btn(self._footer, "Cancel", self._on_cancel,
                                     bg=theme.bg4, fg=theme.btn_fg,
                                     font=(UI_FONT, 12), padx=14, pady=6)
        self._btn_cancel.pack(side="left", padx=12, pady=10)

        self._btn_next = make_btn(self._footer, "  Next \u203a  ", self._on_next,
                                   bg=theme.accent2, fg=theme.accent_fg,
                                   font=(UI_FONT, 12, "bold"), padx=14, pady=6)
        self._btn_next.pack(side="right", padx=12, pady=10)

        self._btn_back = make_btn(self._footer, "  \u2039 Back  ", self._on_back,
                                   bg=theme.bg4, fg=theme.btn_fg,
                                   font=(UI_FONT, 12), padx=14, pady=6)
        self._btn_back.pack(side="right", padx=(0, 4), pady=10)

    def _update_step_bar(self, step: int) -> None:
        theme = self.theme
        for i, lbl in enumerate(self._step_labels):
            if i == step:
                lbl.configure(fg=theme.accent, font=(UI_FONT, 12, "bold"))
            elif i < step:
                lbl.configure(fg=theme.success, font=(UI_FONT, 12, "normal"))
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
            self._btn_next.configure(text="  Import  ", bg=self.theme.accent,
                                     fg=self.theme.accent_fg)
        else:
            self._btn_next.configure(text="  Next \u203a  ", bg=self.theme.accent2,
                                     fg=self.theme.accent_fg)

        builders = [self._build_step_source, self._build_step_browse,
                    self._build_step_confirm]
        builders[step]()

    # ── Step 1: Choose Source ──

    def _build_step_source(self) -> None:
        theme = self.theme
        frame = self._content

        tk.Label(frame, text="Choose a profile source", bg=theme.bg, fg=theme.fg,
                 font=(UI_FONT, 14, "bold")).pack(anchor="w", padx=20, pady=(16, 12))

        # Scrollable list of providers grouped by category
        container = tk.Frame(frame, bg=theme.bg)
        container.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        scroll_frame = ScrollableFrame(container, bg=theme.bg)
        scroll_frame.pack(fill="both", expand=True)
        body = scroll_frame.body
        canvas = scroll_frame.canvas

        self._source_var = tk.StringVar(
            value=self._prefs.get("last_provider", ""))

        self._source_rows = {}  # provider_id -> (row_frame, text_frame, name_label, desc_label)

        def _select_source(pid: str) -> None:
            self._source_var.set(pid)
            # Update visual selection on all rows
            for rid, (rw, tf, nlbl, dlbl) in self._source_rows.items():
                if rid == pid:
                    bg = theme.sel
                    nlbl.configure(bg=bg, fg=theme.accent)
                else:
                    bg = theme.bg3
                    nlbl.configure(bg=bg, fg=theme.fg)
                for w in (rw, tf, dlbl):
                    w.configure(bg=bg)
                # Update any link labels or other direct children of row
                for child in rw.winfo_children():
                    try:
                        child.configure(bg=bg)
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
            tk.Label(cat_frame, text=cat, bg=theme.bg, fg=theme.fg,
                     font=(UI_FONT, 12, "bold")).pack(side="left")

            for provider in providers:
                is_selected = (self._source_var.get() == provider.id)
                row_bg = theme.sel if is_selected else theme.bg3
                row = tk.Frame(body, bg=row_bg)
                row.pack(fill="x", padx=(16, 0), pady=2)

                text_frame = tk.Frame(row, bg=row_bg)
                text_frame.pack(side="left", fill="x", expand=True, padx=12, pady=8)
                name_lbl = tk.Label(text_frame, text=provider.name, bg=row_bg,
                         fg=theme.accent if is_selected else theme.fg,
                         font=(UI_FONT, 12, "bold"), anchor="w")
                name_lbl.pack(anchor="w")
                desc_lbl = tk.Label(text_frame, text=provider.description, bg=row_bg,
                         fg=theme.fg3, font=(UI_FONT, 12), anchor="w")
                desc_lbl.pack(anchor="w")

                # Website hyperlink (opens in browser, doesn't select row)
                if provider.website:
                    link_lbl = tk.Label(row, text="\u2197 Visit source", bg=row_bg,
                                        fg=theme.converted,
                                        font=(UI_FONT, 12, "underline"),
                                        cursor="hand2", padx=8)
                    link_lbl.pack(side="right", padx=(0, 8), pady=8)
                    link_lbl.bind("<Button-1>",
                                  lambda e, url=provider.website: webbrowser.open(url))

                self._source_rows[provider.id] = (row, text_frame, name_lbl, desc_lbl)

                # Click anywhere on row to select
                for widget in (row, text_frame, name_lbl, desc_lbl):
                    widget.bind("<Button-1>",
                                lambda e, pid=provider.id: _select_source(pid))

        self._bind_wizard_scroll(canvas)

    # ── Step 2: Browse & Select ──

    def _build_step_browse(self) -> None:
        theme = self.theme
        frame = self._content

        provider = self._get_provider(self._source_var.get())
        if not provider:
            tk.Label(frame, text="No source selected.", bg=theme.bg, fg=theme.error,
                     font=(UI_FONT, 13)).pack(pady=40)
            return

        # Header
        hdr = tk.Frame(frame, bg=theme.bg)
        hdr.pack(fill="x", padx=20, pady=(12, 4))
        tk.Label(hdr, text=f"Browsing: {provider.name}", bg=theme.bg, fg=theme.fg,
                 font=(UI_FONT, 14, "bold")).pack(side="left")

        # Status var — displayed inside the profile list pane
        self._browse_status = tk.StringVar(value="Fetching catalog...")

        # Filter row
        filter_row = tk.Frame(frame, bg=theme.bg)
        filter_row.pack(fill="x", padx=20, pady=(8, 4))

        tk.Label(filter_row, text="Material:", bg=theme.bg, fg=theme.fg2,
                 font=(UI_FONT, 12)).pack(side="left", padx=(0, 4))
        self._mat_combo = ttk.Combobox(filter_row, textvariable=self._filter_material,
                                       values=["All"], state="readonly", width=10,
                                       style="Dark.TCombobox")
        self._mat_combo.pack(side="left", padx=(0, 12))

        tk.Label(filter_row, text="Brand:", bg=theme.bg, fg=theme.fg2,
                 font=(UI_FONT, 12)).pack(side="left", padx=(0, 4))
        self._brand_combo = ttk.Combobox(filter_row, textvariable=self._filter_brand,
                                         values=["All"], state="readonly", width=12,
                                         style="Dark.TCombobox")
        self._brand_combo.pack(side="left", padx=(0, 12))

        tk.Label(filter_row, text="Slicer:", bg=theme.bg, fg=theme.fg2,
                 font=(UI_FONT, 12)).pack(side="left", padx=(0, 4))
        self._slicer_combo = ttk.Combobox(filter_row, textvariable=self._filter_slicer,
                                          values=["All"], state="readonly", width=12,
                                          style="Dark.TCombobox")
        self._slicer_combo.pack(side="left", padx=(0, 12))

        tk.Label(filter_row, text="Machine:", bg=theme.bg, fg=theme.fg2,
                 font=(UI_FONT, 12)).pack(side="left", padx=(0, 4))
        self._machine_combo = ttk.Combobox(filter_row, textvariable=self._filter_machine,
                                            values=["All"], state="readonly", width=14,
                                            style="Dark.TCombobox")
        self._machine_combo.pack(side="left")

        # Bind filter changes
        self._filter_material.trace_add("write", lambda *a: self._apply_filters())
        self._filter_brand.trace_add("write", lambda *a: self._apply_filters())
        self._filter_slicer.trace_add("write", lambda *a: self._apply_filters())
        self._filter_machine.trace_add("write", lambda *a: self._apply_filters())

        # Profile list area (scrollable)
        list_container = tk.Frame(frame, bg=theme.bg3,
                                  highlightbackground=theme.border, highlightthickness=1)
        list_container.pack(fill="both", expand=True, padx=20, pady=(4, 8))

        # Status bar inside list_container (bottom of the pane)
        self._list_status_label = tk.Label(
            list_container, textvariable=self._browse_status,
            bg=theme.bg3, fg=theme.fg2, font=(UI_FONT, 12),
            anchor="w", padx=8, pady=4)
        self._list_status_label.pack(fill="x", side="bottom")

        self._browse_canvas = tk.Canvas(list_container, bg=theme.bg3, highlightthickness=0)
        self._browse_scrollbar = ttk.Scrollbar(list_container, orient="vertical",
                                                command=self._browse_canvas.yview)
        self._browse_body = tk.Frame(self._browse_canvas, bg=theme.bg3)
        self._browse_body.bind("<Configure>",
                               lambda e: self._browse_canvas.configure(
                                   scrollregion=self._browse_canvas.bbox("all")))
        self._browse_cw = self._browse_canvas.create_window(
            (0, 0), window=self._browse_body, anchor="nw")
        self._browse_canvas.configure(yscrollcommand=self._browse_scrollbar.set)
        self._browse_canvas.pack(side="left", fill="both", expand=True)
        self._browse_scrollbar.pack(side="right", fill="y")
        self._browse_canvas.bind("<Configure>",
                                  lambda e: self._browse_canvas.itemconfig(
                                      self._browse_cw, width=e.width))

        # Show initial loading message inside the browse body too
        self._show_pane_status("Fetching catalog...")

        # Fetch catalog in background thread
        self._catalog = []
        self._check_vars = {}

        self._fetch_done = False

        def _status_update(msg: str) -> None:
            def _update(m: str = msg) -> None:
                self._browse_status.set(m)
                if not self._fetch_done:
                    self._show_pane_status(m)
            self.after(0, _update)

        def _fetch() -> None:
            try:
                catalog = provider.fetch_catalog(status_fn=_status_update)
                if self._fetch_done or self._cancelled:
                    return  # Watchdog already fired or user cancelled
                self._fetch_done = True
                self.after(0, lambda: self._on_catalog_loaded(catalog))
            except urllib.error.HTTPError as ex:
                if self._fetch_done or self._cancelled:
                    return
                self._fetch_done = True
                if ex.code == 403:
                    msg = "GitHub API rate limit exceeded — try again in a few minutes"
                elif ex.code == 404:
                    msg = "Source not found (404) — URL may have changed"
                else:
                    msg = f"HTTP error {ex.code}: {ex.reason}"
                self.after(0, lambda m=msg: self._on_catalog_error(m))
            except urllib.error.URLError as ex:
                if self._fetch_done or self._cancelled:
                    return
                self._fetch_done = True
                msg = f"Network error: {ex.reason}"
                self.after(0, lambda m=msg: self._on_catalog_error(m))
            except BaseException as ex:
                if self._fetch_done or self._cancelled:
                    return
                self._fetch_done = True
                msg = f"{type(ex).__name__}: {ex}"
                self.after(0, lambda m=msg: self._on_catalog_error(m))

        threading.Thread(target=_fetch, daemon=True).start()

        # Watchdog: if fetch hasn't completed in 20s, show timeout error
        def _watchdog() -> None:
            if not self._fetch_done and not self._cancelled:
                self._fetch_done = True  # Prevent race with late-arriving fetch result
                self._on_catalog_error(
                    "Request timed out — check your internet connection "
                    "or try a different source.")
        self.after(20000, _watchdog)

    def _show_pane_status(self, msg: str, icon: Optional[str] = None) -> None:
        theme = self.theme
        for w in self._browse_body.winfo_children():
            w.destroy()
        wrapper = tk.Frame(self._browse_body, bg=theme.bg3)
        wrapper.pack(fill="x", padx=20, pady=30)
        display = f"{icon}  {msg}" if icon else msg
        tk.Label(wrapper, text=display, bg=theme.bg3, fg=theme.fg2,
                 font=(UI_FONT, 12), wraplength=500, justify="center").pack(anchor="center")

    def _on_catalog_loaded(self, catalog: list[OnlineProfileEntry]) -> None:
        self._catalog = catalog
        if not catalog:
            self._browse_status.set("No profiles found from this source.")
            self._show_pane_status("No profiles found from this source.")
            return

        # Populate filter dropdowns
        materials = sorted(set(e.material for e in catalog if e.material))
        brands = sorted(set(e.brand for e in catalog if e.brand))
        slicers = sorted(set(e.slicer for e in catalog if e.slicer))
        machines = sorted(set(e.printer for e in catalog if e.printer))

        self._mat_combo["values"] = ["All"] + materials
        self._brand_combo["values"] = ["All"] + brands
        self._slicer_combo["values"] = ["All"] + slicers
        self._machine_combo["values"] = ["All"] + machines

        # Restore last filters from prefs
        last_mat = self._prefs.get("last_material", "All")
        last_brand = self._prefs.get("last_brand", "All")
        last_slicer = self._prefs.get("last_slicer", "All")
        last_machine = self._prefs.get("last_machine", "All")
        if last_mat in (["All"] + materials):
            self._filter_material.set(last_mat)
        if last_brand in (["All"] + brands):
            self._filter_brand.set(last_brand)
        if last_slicer in (["All"] + slicers):
            self._filter_slicer.set(last_slicer)
        if last_machine in (["All"] + machines):
            self._filter_machine.set(last_machine)

        self._browse_status.set(f"{len(catalog)} profiles available")
        self._apply_filters()

    def _on_catalog_error(self, err: str) -> None:
        self._browse_status.set(f"\u26a0 {err}")
        # Also show in the list body so it's unmissable
        theme = self.theme
        for w in self._browse_body.winfo_children():
            w.destroy()
        err_frame = tk.Frame(self._browse_body, bg=theme.bg3)
        err_frame.pack(fill="x", padx=12, pady=20)
        tk.Label(err_frame, text="\u26a0 Failed to load profiles", bg=theme.bg3,
                 fg=theme.warning, font=(UI_FONT, 13, "bold")).pack(anchor="w")
        tk.Label(err_frame, text=err, bg=theme.bg3, fg=theme.fg2,
                 font=(UI_FONT, 12), wraplength=600, justify="left").pack(
                     anchor="w", pady=(6, 0))

    def _apply_filters(self) -> None:
        mat = self._filter_material.get()
        brand = self._filter_brand.get()
        slicer = self._filter_slicer.get()
        machine = self._filter_machine.get()

        filtered = self._catalog
        if mat != "All":
            filtered = [e for e in filtered if e.material == mat]
        if brand != "All":
            filtered = [e for e in filtered if e.brand == brand]
        if slicer != "All":
            filtered = [e for e in filtered if e.slicer == slicer]
        if machine != "All":
            filtered = [e for e in filtered if e.printer == machine]

        self._filtered_catalog = filtered
        self._render_browse_list(filtered)

    def _render_browse_list(self, entries: list[OnlineProfileEntry]) -> None:
        theme = self.theme
        for w in self._browse_body.winfo_children():
            w.destroy()
        self._check_vars = {}

        if not entries:
            tk.Label(self._browse_body, text="No profiles match the current filters.",
                     bg=theme.bg3, fg=theme.fg3, font=(UI_FONT, 12),
                     pady=20).pack()
            return

        for i, entry in enumerate(entries):
            bg = theme.bg3 if i % 2 == 0 else theme.param_bg
            row = tk.Frame(self._browse_body, bg=bg)
            row.pack(fill="x")

            var = tk.BooleanVar(value=entry.selected)
            self._check_vars[id(entry)] = (var, entry)

            cb = tk.Checkbutton(row, variable=var, bg=bg, fg=theme.fg,
                                selectcolor=theme.bg4,
                                activebackground=bg, activeforeground=theme.fg,
                                highlightthickness=0,
                                command=lambda e=entry, v=var: setattr(e, 'selected', v.get()))
            cb.pack(side="left", padx=(8, 4), pady=4)

            # Name and description
            text_frame = tk.Frame(row, bg=bg)
            text_frame.pack(side="left", fill="x", expand=True, pady=4)
            tk.Label(text_frame, text=entry.name, bg=bg, fg=theme.fg,
                     font=(UI_FONT, 12, "bold"), anchor="w").pack(anchor="w")
            detail_parts = []
            if entry.material:
                detail_parts.append(entry.material)
            if entry.brand:
                detail_parts.append(entry.brand)
            if entry.slicer:
                detail_parts.append(entry.slicer)
            if detail_parts:
                tk.Label(text_frame, text=" \u2022 ".join(detail_parts), bg=bg,
                         fg=theme.fg3, font=(UI_FONT, 12), anchor="w").pack(anchor="w")

        self._bind_wizard_scroll(self._browse_canvas)

    # ── Step 3: Confirm & Import ──

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

        tk.Label(frame, text="Confirm & Import", bg=theme.bg, fg=theme.fg,
                 font=(UI_FONT, 14, "bold")).pack(anchor="w", padx=20, pady=(16, 6))

        # Summary
        summary_frame = tk.Frame(frame, bg=theme.bg3,
                                 highlightbackground=theme.border, highlightthickness=1)
        summary_frame.pack(fill="x", padx=20, pady=(0, 6))

        provider = self._get_provider(self._source_var.get())
        src_name = provider.name if provider else "Unknown"

        tk.Label(summary_frame, text=f"Source: {src_name}", bg=theme.bg3, fg=theme.fg2,
                 font=(UI_FONT, 12), anchor="w", padx=12).pack(anchor="w", pady=(8, 2))
        tk.Label(summary_frame, text=f"Profiles to import: {len(final)}", bg=theme.bg3,
                 fg=theme.fg, font=(UI_FONT, 12, "bold"), anchor="w",
                 padx=12).pack(anchor="w", pady=(2, 2))

        tk.Frame(summary_frame, bg=theme.bg3, height=8).pack()

        # ── Save-to checkboxes ──
        target_frame = tk.Frame(frame, bg=theme.bg)
        target_frame.pack(fill="x", padx=20, pady=(4, 6))

        tk.Label(target_frame, text="Save to:", bg=theme.bg, fg=theme.fg,
                 font=(UI_FONT, 12, "bold")).pack(anchor="w")

        # Build target options as checkboxes
        self._save_targets = []  # list of (BooleanVar, label, path)

        # "Load into app" is always on (not a checkbox — just a note)
        tk.Label(target_frame, text="\u2713  Load into app (always)",
                 bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12),
                 padx=4).pack(anchor="w", pady=(4, 2))

        slicer_targets = self._detect_slicer_filament_dirs()
        # Restore last-checked targets from prefs
        last_checked = set(self._prefs.get("last_targets", []))

        for label, path in slicer_targets:
            var = tk.BooleanVar(value=(label in last_checked))
            cb_row = tk.Frame(target_frame, bg=theme.bg)
            cb_row.pack(anchor="w", padx=4)
            tk.Checkbutton(cb_row, text=label, variable=var,
                           bg=theme.bg, fg=theme.fg, selectcolor=theme.bg3,
                           activebackground=theme.bg, activeforeground=theme.fg,
                           font=(UI_FONT, 12)).pack(side="left")
            tk.Label(cb_row, text=path, bg=theme.bg, fg=theme.fg3,
                     font=(UI_FONT, 12)).pack(side="left", padx=(6, 0))
            self._save_targets.append((var, label, path))

        # Custom folder option
        self._custom_dir_var = tk.BooleanVar(value=False)
        self._custom_dir_path = None
        custom_row = tk.Frame(target_frame, bg=theme.bg)
        custom_row.pack(anchor="w", padx=4, pady=(2, 0))
        tk.Checkbutton(custom_row, text="Custom folder:",
                       variable=self._custom_dir_var,
                       bg=theme.bg, fg=theme.fg, selectcolor=theme.bg3,
                       activebackground=theme.bg, activeforeground=theme.fg,
                       font=(UI_FONT, 12)).pack(side="left")
        self._custom_dir_label = tk.Label(custom_row, text="(none selected)",
                                           bg=theme.bg, fg=theme.fg3,
                                           font=(UI_FONT, 12))
        self._custom_dir_label.pack(side="left", padx=(4, 0))
        make_btn(custom_row, "Browse...", self._on_browse_target,
                  bg=theme.bg4, fg=theme.btn_fg,
                  font=(UI_FONT, 12), padx=6, pady=2).pack(side="left", padx=(6, 0))

        # ── Profile list ──
        list_frame = tk.Frame(frame, bg=theme.bg)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(4, 6))

        scroll_frame = ScrollableFrame(list_frame, bg=theme.bg3,
                                        highlight_border=theme.border)
        scroll_frame.pack(fill="both", expand=True)
        body = scroll_frame.body
        canvas = scroll_frame.canvas

        for i, entry in enumerate(final):
            bg = theme.bg3 if i % 2 == 0 else theme.param_bg
            row = tk.Frame(body, bg=bg)
            row.pack(fill="x")

            tk.Label(row, text="\u2713", bg=bg, fg=theme.success,
                     font=(UI_FONT, 12), padx=8).pack(side="left")
            tk.Label(row, text=entry.name, bg=bg, fg=theme.fg,
                     font=(UI_FONT, 12), anchor="w", padx=4, pady=4).pack(
                         side="left", fill="x", expand=True)
        # Download status area (at bottom of content)
        self._import_status.set("")
        tk.Label(frame, textvariable=self._import_status, bg=theme.bg, fg=theme.fg3,
                 font=(UI_FONT, 12)).pack(anchor="w", padx=20, pady=(0, 4))

        self._bind_wizard_scroll(canvas)

    # ── Navigation ──

    def _on_next(self) -> None:
        step = self._current_step

        if step == 0:
            # Validate source selected
            pid = self._source_var.get()
            if not pid:
                messagebox.showwarning("No Source", "Select a profile source to continue.",
                                       parent=self)
                return
            self._selected_provider = self._get_provider(pid)
            self._prefs["last_provider"] = pid
            self._show_step(1)

        elif step == 1:
            # Save filter prefs
            self._prefs["last_material"] = self._filter_material.get()
            self._prefs["last_brand"] = self._filter_brand.get()
            self._prefs["last_slicer"] = self._filter_slicer.get()
            self._prefs["last_machine"] = self._filter_machine.get()
            # Check at least one selected
            selected = [e for e in self._catalog if e.selected]
            if not selected:
                messagebox.showwarning("No Profiles",
                                       "Check at least one profile to continue.", parent=self)
                return
            self._selected_entries = selected
            self._show_step(2)

        elif step == 2:
            # Do the import
            self._do_import()

    def _on_back(self) -> None:
        if self._current_step > 0:
            self._show_step(self._current_step - 1)

    def _on_cancel(self) -> None:
        self._cancelled = True
        save_online_prefs(self._prefs)
        self.destroy()

    def _get_provider(self, provider_id: str) -> Optional[Any]:
        for p in ALL_PROVIDERS:
            if p.id == provider_id:
                return p
        return None

    # ── Import Execution ──

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
        self._import_status.set(f"Downloading {len(entries)} profile(s)...")
        self._btn_next.configure(text="  Importing...  ")

        # Disable nav buttons during download
        self._btn_next._inner_label.unbind("<Button-1>")
        self._btn_back._inner_label.unbind("<Button-1>")

        def _download() -> None:
            results = []
            errors = []
            saved_dirs = set()
            for i, entry in enumerate(entries):
                if self._cancelled:
                    return
                self.after(0, lambda i=i, n=entry.name: self._import_status.set(
                    f"Downloading {i+1}/{len(entries)}: {n}"))
                try:
                    data, fname = provider.download_profile(entry)
                    if data and fname:
                        fname = os.path.basename(fname)
                        if not fname:
                            fname = entry.name.replace(" ", "_").replace("/", "-") + ".json"

                        # Save to each checked target directory
                        primary_path = None
                        for tdir in target_dirs:
                            os.makedirs(tdir, exist_ok=True)
                            dest = os.path.join(tdir, fname)
                            with open(dest, "wb") as f:
                                f.write(data)
                            saved_dirs.add(tdir)
                            if primary_path is None:
                                primary_path = dest

                        if primary_path:
                            # Load into app from the first saved location
                            results.append((primary_path, None, provider.name))
                        else:
                            # No target dirs checked — save to temp for app-only
                            with tempfile.TemporaryDirectory(prefix="ppc_import_") as tmp_dir:
                                tmp_path = os.path.join(tmp_dir, fname)
                                with open(tmp_path, "wb") as f:
                                    f.write(data)
                                results.append((tmp_path, None, provider.name))
                except Exception as ex:
                    errors.append(f"{entry.name}: {ex}")

            self.after(0, lambda: self._on_download_complete(
                results, errors, list(saved_dirs)))

        threading.Thread(target=_download, daemon=True).start()

    def _on_download_complete(
        self,
        results: list[tuple[str, Optional[str], str]],
        errors: list[str],
        saved_dirs: list[str],
    ) -> None:
        save_online_prefs(self._prefs)

        if errors:
            err_msg = "\n".join(errors[:5])
            if len(errors) > 5:
                err_msg += f"\n... and {len(errors) - 5} more"
            messagebox.showwarning("Some Downloads Failed",
                                   f"Downloaded {len(results)}, failed {len(errors)}:\n\n{err_msg}",
                                   parent=self)

        if results:
            self._load_callback(results)
            if saved_dirs:
                dir_list = "\n".join(saved_dirs)
                messagebox.showinfo(
                    "Import Complete",
                    f"Imported {len(results)} profile(s).\n"
                    f"Saved to {len(saved_dirs)} location{'s' if len(saved_dirs) != 1 else ''}:\n"
                    f"{dir_list}",
                    parent=self)
            else:
                messagebox.showinfo(
                    "Import Complete",
                    f"Loaded {len(results)} profile(s) into the app.",
                    parent=self)

        self.destroy()


class BatchRenameDialog(tk.Toplevel):
    """Dialog for batch renaming selected profiles with find/replace or pattern builder."""

    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        profiles: list[Profile],
        on_complete: Optional[Callable] = None,
    ) -> None:
        super().__init__(parent)
        self.theme = theme
        self.profiles = profiles
        self.on_complete = on_complete

        self.title("Batch Rename")
        self.configure(bg=theme.bg)
        self.resizable(True, True)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 60, parent.winfo_rooty() + 40))

        # Snapshot all token values NOW so they survive name changes
        self._available_tokens = [
            ("name", "Profile name"),
            ("brand", "Brand / manufacturer"),
            ("material", "Material type"),
            ("printer", "Printer model"),
            ("nozzle", "Nozzle size"),
            ("type", "Profile type"),
            ("layer_height", "Layer height"),
            ("filename", "Original filename"),
        ]
        self._field_snapshot = {}
        for p in profiles:
            snap = {}
            for tok, _ in self._available_tokens:
                snap[tok] = self._profile_field(p, tok)
            self._field_snapshot[id(p)] = snap

        self._build()

    def _profile_field(self, profile: Profile, field: str) -> str:
        if field == "name":
            return profile.name
        elif field == "filename":
            return os.path.splitext(os.path.basename(profile.source_path or ""))[0]
        else:
            val = profile.data.get(field)
            return str(val) if val is not None else ""

    def _build(self) -> None:
        theme = self.theme

        tk.Label(self, text=f"Rename {len(self.profiles)} selected profiles",
                 bg=theme.bg, fg=theme.fg,
                 font=(UI_FONT, 13, "bold")).pack(padx=16, pady=(12, 6), anchor="w")

        # ── Mode tabs ──
        tab_frame = tk.Frame(self, bg=theme.bg)
        tab_frame.pack(fill="x", padx=16)
        self._mode_var = tk.StringVar(value="simple")

        self._simple_tab_btn = tk.Label(tab_frame, text="  Find / Replace  ", bg=theme.sel,
                                  fg=theme.fg, font=(UI_FONT, 12, "bold"),
                                  padx=8, pady=4, cursor="hand2")
        self._simple_tab_btn.pack(side="left", padx=(0, 2))
        self._pattern_tab_btn = tk.Label(tab_frame, text="  Pattern Builder  ", bg=theme.bg4,
                                   fg=theme.fg3, font=(UI_FONT, 12),
                                   padx=8, pady=4, cursor="hand2")
        self._pattern_tab_btn.pack(side="left")

        # Container for swappable tab content — sits between tabs and preview
        self._content_holder = tk.Frame(self, bg=theme.bg)
        self._content_holder.pack(fill="x", padx=16, pady=(6, 0))

        # --- Simple mode widgets ---
        self._simple_frame = tk.Frame(self._content_holder, bg=theme.bg)

        self._simple_mode_var = tk.StringVar(value="replace")
        smodes = tk.Frame(self._simple_frame, bg=theme.bg)
        smodes.pack(fill="x", pady=(2, 0))
        for val, label in [("replace", "Find and replace"),
                           ("prefix", "Add prefix"),
                           ("suffix", "Add suffix"),
                           ("remove", "Remove text")]:
            tk.Radiobutton(smodes, text=label, variable=self._simple_mode_var, value=val,
                           bg=theme.bg, fg=theme.fg, selectcolor=theme.bg4,
                           activebackground=theme.bg, activeforeground=theme.fg,
                           font=(UI_FONT, 12)).pack(anchor="w", pady=1)

        sinput = tk.Frame(self._simple_frame, bg=theme.bg)
        sinput.pack(fill="x", pady=(6, 0))
        sinput.columnconfigure(1, weight=1)

        tk.Label(sinput, text="Find:", bg=theme.bg, fg=theme.fg2,
                 font=(UI_FONT, 12)).grid(row=0, column=0, sticky="w", pady=2)
        self._find_var = tk.StringVar()
        find_entry = tk.Entry(sinput, textvariable=self._find_var, bg=theme.bg3, fg=theme.fg,
                              font=(UI_FONT, 12), insertbackground=theme.fg,
                              highlightbackground=theme.border, highlightthickness=1)
        find_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)

        self._replace_lbl = tk.Label(sinput, text="Replace:", bg=theme.bg, fg=theme.fg2,
                               font=(UI_FONT, 12))
        self._replace_var = tk.StringVar()
        self._replace_entry = tk.Entry(sinput, textvariable=self._replace_var, bg=theme.bg3, fg=theme.fg,
                                 font=(UI_FONT, 12), insertbackground=theme.fg,
                                 highlightbackground=theme.border, highlightthickness=1)

        def _update_simple_fields(*_) -> None:
            m = self._simple_mode_var.get()
            if m == "replace":
                self._replace_lbl.grid(row=1, column=0, sticky="w", pady=2)
                self._replace_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=2)
            else:
                self._replace_lbl.grid_forget()
                self._replace_entry.grid_forget()
            self._update_preview()

        self._simple_mode_var.trace_add("write", _update_simple_fields)
        self._find_var.trace_add("write", lambda *a: self._update_preview())
        self._replace_var.trace_add("write", lambda *a: self._update_preview())

        def _simple_rename(p: Profile) -> str:
            m = self._simple_mode_var.get()
            search_text = self._find_var.get()
            if not search_text:
                return p.name
            if m == "prefix":
                return search_text + p.name
            elif m == "suffix":
                return p.name + search_text
            elif m == "replace":
                return p.name.replace(search_text, self._replace_var.get())
            elif m == "remove":
                return p.name.replace(search_text, "")
            return p.name

        self._simple_rename = _simple_rename

        # --- Pattern mode widgets ---
        self._pattern_frame = tk.Frame(self._content_holder, bg=theme.bg)

        tk.Label(self._pattern_frame, text="Click tokens to build a naming pattern:",
                 bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12, "italic")).pack(
                     anchor="w", pady=(2, 4))

        self._pattern_var = tk.StringVar(value="{brand} - {material} - {name}")

        # Token buttons — use wrapping grid so they don't overflow
        token_row1 = tk.Frame(self._pattern_frame, bg=theme.bg)
        token_row1.pack(fill="x", pady=(0, 2))
        token_row2 = tk.Frame(self._pattern_frame, bg=theme.bg)
        token_row2.pack(fill="x", pady=(0, 4))

        def _insert_token(token: str) -> None:
            self._pattern_entry.insert("insert", "{" + token + "}")
            self._update_preview()

        for i, (tok, tip) in enumerate(self._available_tokens):
            parent_row = token_row1 if i < 4 else token_row2
            make_btn(parent_row, "{" + tok + "}",
                      lambda t=tok: _insert_token(t),
                      bg=theme.bg4, fg=theme.accent,
                      font=(UI_FONT, 12), padx=4, pady=2).pack(
                          side="left", padx=(0, 4))

        # Separator buttons
        sep_frame = tk.Frame(self._pattern_frame, bg=theme.bg)
        sep_frame.pack(fill="x", pady=(0, 4))
        tk.Label(sep_frame, text="Separators:", bg=theme.bg, fg=theme.fg3,
                 font=(UI_FONT, 12)).pack(side="left", padx=(0, 6))
        for label, val in [(" - ", " - "), (" _ ", " _ "), (" @ ", " @ "),
                           (" . ", "."), ("space", " ")]:
            make_btn(sep_frame, label,
                      lambda v=val: (self._pattern_entry.insert("insert", v), self._update_preview()),
                      bg=theme.bg4, fg=theme.fg2,
                      font=(UI_FONT, 12), padx=4, pady=2).pack(side="left", padx=(0, 3))

        # Editable pattern field
        pf_row = tk.Frame(self._pattern_frame, bg=theme.bg)
        pf_row.pack(fill="x", pady=(2, 0))
        tk.Label(pf_row, text="Pattern:", bg=theme.bg, fg=theme.fg2,
                 font=(UI_FONT, 12)).pack(side="left", padx=(0, 8))
        self._pattern_entry = tk.Entry(pf_row, textvariable=self._pattern_var, bg=theme.bg3, fg=theme.fg,
                                 font=(UI_FONT, 12), insertbackground=theme.fg,
                                 highlightbackground=theme.accent, highlightthickness=1)
        self._pattern_entry.pack(side="left", fill="x", expand=True)
        self._pattern_var.trace_add("write", lambda *a: self._update_preview())

        def _pattern_rename(p: Profile) -> str:
            tmpl = self._pattern_var.get()
            if not tmpl:
                return p.name
            snap = self._field_snapshot.get(id(p), {})
            result = tmpl
            for tok, _ in self._available_tokens:
                placeholder = "{" + tok + "}"
                if placeholder in result:
                    val = snap.get(tok, "")
                    result = result.replace(placeholder, val if val else "")
            for sep in (" - ", " _ ", " / "):
                while sep + sep[1:] in result:
                    result = result.replace(sep + sep[1:], sep)
            result = result.strip(" -_/")
            return result if result else p.name

        self._pattern_rename = _pattern_rename

        # --- Tab switching ---
        def _switch_tab(tab: str) -> None:
            self._mode_var.set(tab)
            for child in self._content_holder.winfo_children():
                child.pack_forget()
            if tab == "simple":
                self._simple_frame.pack(fill="x")
                self._simple_tab_btn.configure(bg=theme.sel, fg=theme.fg,
                                         font=(UI_FONT, 12, "bold"))
                self._pattern_tab_btn.configure(bg=theme.bg4, fg=theme.fg3,
                                          font=(UI_FONT, 12))
                find_entry.focus_set()
            else:
                self._pattern_frame.pack(fill="x")
                self._pattern_tab_btn.configure(bg=theme.sel, fg=theme.fg,
                                          font=(UI_FONT, 12, "bold"))
                self._simple_tab_btn.configure(bg=theme.bg4, fg=theme.fg3,
                                         font=(UI_FONT, 12))
                self._pattern_entry.focus_set()
            self._update_preview()

        self._simple_tab_btn.bind("<Button-1>", lambda e: _switch_tab("simple"))
        self._pattern_tab_btn.bind("<Button-1>", lambda e: _switch_tab("pattern"))

        # --- Preview area ---
        tk.Label(self, text="Preview:", bg=theme.bg, fg=theme.fg2,
                 font=(UI_FONT, 12)).pack(padx=16, pady=(10, 2), anchor="w")
        preview_frame = tk.Frame(self, bg=theme.bg3, highlightbackground=theme.border,
                                  highlightthickness=1)
        preview_frame.pack(fill="both", expand=True, padx=16)
        self._preview_text = tk.Text(preview_frame, bg=theme.bg3, fg=theme.fg,
                               font=(UI_FONT, 12), height=min(6, len(self.profiles)),
                               wrap="none", relief="flat", bd=4)
        self._preview_text.tag_configure("arrow", foreground=theme.fg3)
        self._preview_text.tag_configure("changed", foreground=theme.accent)
        preview_sb = ttk.Scrollbar(preview_frame, orient="vertical",
                                    command=self._preview_text.yview)
        self._preview_text.configure(yscrollcommand=preview_sb.set)
        self._preview_text.pack(side="left", fill="both", expand=True)
        preview_sb.pack(side="right", fill="y")
        self._preview_text.configure(state="disabled")

        def _compute_name(p: Profile) -> str:
            if self._mode_var.get() == "simple":
                raw = self._simple_rename(p)
            else:
                raw = self._pattern_rename(p)
            return Profile.sanitize_name(raw)

        self._compute_name = _compute_name

        # --- Action buttons ---
        btn_frame = tk.Frame(self, bg=theme.bg)
        btn_frame.pack(fill="x", padx=16, pady=(8, 12))

        def _apply() -> None:
            renamed = 0
            for p in self.profiles:
                new_name = Profile.sanitize_name(self._compute_name(p))
                if new_name and new_name != p.name:
                    old_name = p.name
                    snapshot = {"name": old_name, "_modified": p.modified}
                    p.data["name"] = new_name
                    p.log_change("Renamed", f"{old_name} \u2192 {new_name}",
                                 snapshot=snapshot)
                    renamed += 1
            self.destroy()
            if self.on_complete:
                self.on_complete(renamed)

        make_btn(btn_frame, "  Rename All  ", _apply,
                  bg=theme.accent2, fg=theme.accent_fg,
                  font=(UI_FONT, 12, "bold"), padx=12, pady=5).pack(
                      side="right", padx=(6, 0))
        make_btn(btn_frame, "  Cancel  ", self.destroy,
                  bg=theme.bg4, fg=theme.fg2,
                  font=(UI_FONT, 12), padx=12, pady=5).pack(side="right")

        # Show initial tab — this packs content and triggers first preview
        _switch_tab("simple")
        _update_simple_fields()

    def _update_preview(self) -> None:
        self._preview_text.configure(state="normal")
        self._preview_text.delete("1.0", "end")
        for i, p in enumerate(self.profiles[:30]):
            new = self._compute_name(p)
            if i > 0:
                self._preview_text.insert("end", "\n")
            if new != p.name:
                self._preview_text.insert("end", p.name)
                self._preview_text.insert("end", "  \u2192  ", "arrow")
                self._preview_text.insert("end", new, "changed")
            else:
                self._preview_text.insert("end", f"{p.name}  (unchanged)")
        if len(self.profiles) > 30:
            self._preview_text.insert("end", f"\n... and {len(self.profiles) - 30} more")
        self._preview_text.configure(state="disabled")
