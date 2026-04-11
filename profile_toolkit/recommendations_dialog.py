"""RecommendationsDialog — material-aware parameter recommendations panel."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Callable, Optional

from .constants import (
    FILAMENT_LAYOUT,
    _IDENTITY_KEYS,
    _VALUE_TRUNCATE_SHORT,
    UI_FONT,
    RECOMMENDATIONS,
)
from .theme import Theme
from .models import Profile
from .utils import (
    bind_scroll,
    detect_material,
    get_recommendation,
    get_recommendation_info,
    check_value_range,
    get_enum_human_label,
)
from .widgets import ScrollableFrame, make_btn

logger = logging.getLogger(__name__)


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
        refresh_callback: Optional[Callable[[Profile], None]] = None,
    ) -> None:
        self.theme = theme
        self.profile = profile
        self.all_profiles = all_profiles or []
        self._refresh_callback = refresh_callback
        self._apply_vars = {}  # key -> BooleanVar for checkboxes

        display_data = profile.resolved_data if profile.resolved_data else profile.data
        material = detect_material(display_data)

        self.dlg = dlg = tk.Toplevel(parent)
        dlg.title(f"Recommended Values — {profile.name}")
        dlg.configure(bg=theme.bg)
        dlg.resizable(True, True)
        dlg.transient(parent.winfo_toplevel())
        dlg.grab_set()
        dlg.protocol("WM_DELETE_WINDOW", lambda: (dlg.grab_release(), dlg.destroy()))
        dlg.geometry(
            "720x560+%d+%d" % (parent.winfo_rootx() + 40, parent.winfo_rooty() + 40)
        )
        dlg.minsize(600, 400)

        # Header
        hdr = tk.Frame(dlg, bg=theme.bg)
        hdr.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(
            hdr,
            text="\u2699 Recommended Values",
            bg=theme.bg,
            fg=theme.fg,
            font=(UI_FONT, 16, "bold"),
        ).pack(side="left")
        mat_text = material if material != "General" else "Material not detected"
        tk.Label(
            hdr,
            text=f"  \u00b7  {mat_text}  \u00b7  {profile.name}",
            bg=theme.bg,
            fg=theme.fg2,
            font=(UI_FONT, 13),
        ).pack(side="left")

        # Compute stats (used by _render_rec_row below)
        stats = self._compute_stats(display_data, material)

        # (Outlier comparison removed — too noisy for end users)

        # Scrollable parameter list
        sf = ScrollableFrame(dlg, bg=theme.bg)
        sf.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        out_of_range = []
        layout = FILAMENT_LAYOUT
        for tab_name, sections in layout.items():
            for section_name, params in sections.items():
                for entry in params:
                    json_key, ui_label = entry[0], entry[1]
                    if json_key not in display_data:
                        continue
                    val = display_data[json_key]
                    status = check_value_range(json_key, val, material)
                    if status in ("low", "high"):
                        rec = get_recommendation(json_key, material)
                        inherited = bool(
                            getattr(self.profile, "inherited_keys", None)
                            and json_key in self.profile.inherited_keys
                        )
                        out_of_range.append(
                            (json_key, ui_label, val, status, rec, tab_name, inherited)
                        )

        if out_of_range:
            # Select All / Deselect All
            sel_frame = tk.Frame(sf.body, bg=theme.bg)
            sel_frame.pack(fill="x", pady=(4, 6))
            self._select_all_var = tk.BooleanVar(value=True)

            def _toggle_all() -> None:
                val = self._select_all_var.get()
                for v in self._apply_vars.values():
                    v.set(val)

            cb = tk.Checkbutton(
                sel_frame,
                text="Select All",
                variable=self._select_all_var,
                command=_toggle_all,
                bg=theme.bg,
                fg=theme.fg,
                selectcolor=theme.bg3,
                activebackground=theme.bg,
                activeforeground=theme.fg,
                font=(UI_FONT, 12),
            )
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
            for ci, (text, w) in enumerate(
                [
                    ("", 30),
                    ("Parameter", 180),
                    ("Current", 80),
                    ("", 30),
                    ("Recommended", 100),
                    ("Typical", 80),
                ]
            ):
                tk.Label(
                    hdr_row,
                    text=text,
                    bg=theme.bg3,
                    fg=theme.fg2,
                    font=(UI_FONT, 12, "bold"),
                    anchor="w",
                ).grid(row=0, column=ci, sticky="w", padx=4, pady=4)

            for (
                json_key,
                ui_label,
                val,
                status,
                rec,
                tab_name,
                inherited,
            ) in out_of_range:
                self._render_rec_row(
                    sf.body, json_key, ui_label, val, status, rec, tab_name, inherited
                )
        else:
            tk.Label(
                sf.body,
                text="All parameters are within recommended ranges.",
                bg=theme.bg,
                fg=theme.accent,
                font=(UI_FONT, 14, "bold"),
            ).pack(pady=30)

        sf.bind_scroll_recursive()

        # Bottom buttons
        btn_frame = tk.Frame(dlg, bg=theme.bg)
        btn_frame.pack(fill="x", padx=16, pady=(0, 12))
        if out_of_range:
            apply_btn = make_btn(
                btn_frame,
                "Apply Recommended Values",
                self._apply_typical,
                bg=theme.accent2,
                fg=theme.accent_fg,
                font=(UI_FONT, 12, "bold"),
                padx=16,
                pady=6,
            )
            apply_btn.pack(side="left", padx=(0, 8))
        make_btn(
            btn_frame,
            "Close",
            dlg.destroy,
            bg=theme.bg4,
            fg=theme.fg2,
            font=(UI_FONT, 12),
            padx=16,
            pady=6,
        ).pack(side="right")

    def _render_rec_row(
        self,
        parent: tk.Widget,
        key: str,
        label: str,
        value: Any,
        status: str,
        rec: Optional[dict],
        tab_name: str,
        inherited: bool = False,
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
        cb = tk.Checkbutton(
            row,
            variable=var,
            bg=theme.param_bg,
            selectcolor=theme.bg3,
            activebackground=theme.param_bg,
        )
        cb.grid(row=0, column=0, sticky="w", padx=4)

        # Parameter name
        tk.Label(
            row,
            text=label,
            bg=theme.param_bg,
            fg=theme.fg,
            font=(UI_FONT, 12, "bold"),
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=4)

        # Current value
        disp_val = value
        if isinstance(value, list):
            unique = list(dict.fromkeys(str(v) for v in value))
            disp_val = (
                unique[0] if len(unique) == 1 else ", ".join(str(v) for v in value)
            )
        val_frame = tk.Frame(row, bg=theme.param_bg)
        val_frame.grid(row=0, column=2, sticky="w", padx=4)
        tk.Label(
            val_frame,
            text=str(disp_val),
            bg=theme.param_bg,
            fg=theme.fg2,
            font=(UI_FONT, 12),
            anchor="w",
        ).pack(side="left")
        if inherited:
            tk.Label(
                val_frame,
                text="(from parent)",
                bg=theme.param_bg,
                fg=theme.fg3 if hasattr(theme, "fg3") else theme.fg2,
                font=(UI_FONT, 10),
                anchor="w",
            ).pack(side="left", padx=(4, 0))

        # Indicator arrow
        arrow = "\u25bc" if status == "low" else "\u25b2"
        arrow_fg = theme.info if status == "low" else theme.warning
        tk.Label(
            row, text=arrow, bg=theme.param_bg, fg=arrow_fg, font=(UI_FONT, 12, "bold")
        ).grid(row=0, column=3, sticky="w", padx=2)

        # Recommended range
        if rec:
            range_text = f"{rec.get('min', '?')} – {rec.get('max', '?')}"
            tk.Label(
                row,
                text=range_text,
                bg=theme.param_bg,
                fg=theme.fg2,
                font=(UI_FONT, 12),
                anchor="w",
            ).grid(row=0, column=4, sticky="w", padx=4)

            typical = rec.get("typical", "")
            tk.Label(
                row,
                text=str(typical),
                bg=theme.param_bg,
                fg=theme.accent,
                font=(UI_FONT, 12, "bold"),
                anchor="w",
            ).grid(row=0, column=5, sticky="w", padx=4)

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
            if isinstance(original, list):
                if not original:
                    new_val = typical
                else:
                    elem_type = type(original[0])
                    try:
                        if elem_type in (int, float):
                            coerced = elem_type(float(typical))
                        elif elem_type is str:
                            coerced = str(typical)
                        else:
                            coerced = typical
                        new_val = [coerced] * len(original)
                    except (ValueError, TypeError):
                        logger.debug(
                            "Cannot coerce typical %r to %s for key %s",
                            typical,
                            elem_type,
                            key,
                        )
                        continue
            elif isinstance(original, int):
                try:
                    new_val = int(float(typical))
                except (ValueError, TypeError):
                    new_val = typical
            elif isinstance(original, float):
                try:
                    new_val = float(typical)
                except (ValueError, TypeError):
                    new_val = typical
            else:
                new_val = typical
            if new_val != original:
                old_val = original
                self.profile.data[key] = new_val
                if getattr(self.profile, "resolved_data", None) is not None:
                    self.profile.resolved_data[key] = new_val
                self.profile.modified = True
                self.profile.log_change(
                    "Recommendation applied",
                    f"{key}: {original} \u2192 {new_val}",
                    snapshot={"key": key, "old": old_val},
                )
                applied += 1

        if applied:
            messagebox.showinfo(
                "Applied",
                f"Applied {applied} recommended typical value{'s' if applied != 1 else ''}.",
                parent=self.dlg,
            )
            # Refresh the detail panel
            self._refresh_detail()
        self.dlg.destroy()

    def _refresh_detail(self) -> None:
        if self._refresh_callback:
            try:
                self._refresh_callback(self.profile)
            except Exception as exc:
                logger.debug("Refresh callback failed: %s", exc)
            return
        try:
            parent = self.dlg.master
            while parent:
                # Import here to avoid circular dependency
                from .list_panel import ProfileListPanel

                if isinstance(parent, ProfileListPanel):
                    parent.detail.show_profile(self.profile)
                    parent._refresh_list()
                    return
                parent = getattr(parent, "master", None)
        except (tk.TclError, AttributeError) as exc:
            logger.debug("Could not refresh detail panel: %s", exc)

    def _compute_stats(self, data: dict, material: str) -> dict[str, int]:
        total = ok = low = high = 0
        # Only check keys defined in FILAMENT_LAYOUT (not metadata/identity keys)
        layout_keys = set()
        for sections in FILAMENT_LAYOUT.values():
            for params in sections.values():
                for entry in params:
                    layout_keys.add(entry[0])
        for key in layout_keys:
            if key not in data:
                continue
            status = check_value_range(key, data[key], material)
            if status is not None:
                total += 1
                if status == "ok":
                    ok += 1
                elif status == "low":
                    low += 1
                elif status == "high":
                    high += 1
        return {"total": total, "ok": ok, "low": low, "high": high}

    def _compute_loaded_profile_stats(
        self, data: dict, material: str
    ) -> Optional[dict]:
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
                for layout in (FILAMENT_LAYOUT,):
                    for sections in layout.values():
                        for params in sections.values():
                            for entry in params:
                                k, l = entry[0], entry[1]
                                if k == key:
                                    ui_label = l
                                    break
                outliers.append(ui_label)
        return {"outliers": outliers} if outliers else None
