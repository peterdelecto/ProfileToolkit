"""CompareDialog — side-by-side parameter comparison popup."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Any, Optional

from .constants import (
    FILAMENT_LAYOUT,
    _IDENTITY_KEYS,
    _DLG_COMPARE_WIDTH,
    _DLG_COMPARE_HEIGHT,
    _DLG_COMPARE_MIN_WIDTH,
    _DLG_COMPARE_MIN_HEIGHT,
    _VALUE_TRUNCATE_SHORT,
    UI_FONT,
    ENUM_VALUES,
)
from .theme import Theme
from .models import Profile
from .utils import bind_scroll, get_enum_human_label
from .widgets import ScrollableFrame, make_btn

logger = logging.getLogger(__name__)


class CompareDialog(tk.Toplevel):
    """Side-by-side comparison of two profiles, grouped by section."""

    def __init__(
        self, parent: tk.Widget, theme: Theme, profile_a: Profile, profile_b: Profile
    ) -> None:
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
        tk.Label(
            header_frame,
            text=profile_a.name,
            bg=theme.bg,
            fg=theme.accent,
            font=(UI_FONT, 13, "bold"),
        ).pack(side="left")
        # Centered "vs"
        tk.Label(
            header_frame, text="  vs  ", bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12)
        ).pack(side="left")
        # Right name
        tk.Label(
            header_frame,
            text=profile_b.name,
            bg=theme.bg,
            fg=theme.warning,
            font=(UI_FONT, 13, "bold"),
        ).pack(side="left")

        # ── Find differences and group by section ──
        data_a = profile_a.resolved_data or profile_a.data
        data_b = profile_b.resolved_data or profile_b.data
        all_keys = set(data_a.keys()) | set(data_b.keys())
        all_keys -= _IDENTITY_KEYS
        diffs = {}
        for k in all_keys:
            value_a = data_a.get(k)
            value_b = data_b.get(k)
            if value_a != value_b:
                diffs[k] = (value_a, value_b)

        # Build section lookup from layout
        layout = FILAMENT_LAYOUT
        key_to_label = {}
        key_to_group = {}  # key -> "Tab > Section"
        for tab_name, sections in layout.items():
            for sec_name, params in sections.items():
                for entry in params:
                    json_key, ui_label = entry[0], entry[1]
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
        tk.Label(
            self,
            text=f"{diff_count} parameter{'s' if diff_count != 1 else ''} differ",
            bg=theme.bg,
            fg=theme.fg2,
            font=(UI_FONT, 12),
        ).pack(anchor="w", padx=16, pady=(0, 6))

        # ── Column headers (fixed above scroll) ──
        col_hdr = tk.Frame(self, bg=theme.bg4)
        col_hdr.pack(fill="x", padx=16)
        tk.Label(
            col_hdr,
            text="Parameter",
            bg=theme.bg4,
            fg=theme.fg,
            font=(UI_FONT, 12, "bold"),
            anchor="w",
            padx=8,
            pady=4,
        ).pack(side="left", fill="x", expand=True)
        tk.Label(
            col_hdr,
            text="Left",
            bg=theme.bg4,
            fg=theme.accent,
            font=(UI_FONT, 12, "bold"),
            width=18,
            anchor="w",
            padx=4,
            pady=4,
        ).pack(side="left")
        tk.Label(
            col_hdr,
            text="Right",
            bg=theme.bg4,
            fg=theme.warning,
            font=(UI_FONT, 12, "bold"),
            width=18,
            anchor="w",
            padx=4,
            pady=4,
        ).pack(side="left")
        tk.Label(
            col_hdr,
            text="Change",
            bg=theme.bg4,
            fg=theme.fg2,
            font=(UI_FONT, 12, "bold"),
            width=8,
            anchor="w",
            padx=4,
            pady=4,
        ).pack(side="left")

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
            tk.Label(
                sec_hdr,
                text=group_name,
                bg=theme.bg2,
                fg=theme.fg,
                font=(UI_FONT, 12, "bold"),
                padx=4,
            ).pack(side="left")

            for key in keys:
                value_a, value_b = diffs[key]
                bg = theme.bg2 if row_idx % 2 == 0 else theme.bg3
                row = tk.Frame(body, bg=bg)
                row.pack(fill="x")

                label = key_to_label.get(key, key)
                value_a_text = self._format_value(value_a, key=key)
                value_b_text = self._format_value(value_b, key=key)
                delta = self._delta(value_a, value_b)

                tk.Label(
                    row,
                    text=label,
                    bg=bg,
                    fg=theme.fg,
                    font=(UI_FONT, 12),
                    anchor="w",
                    padx=10,
                    pady=3,
                ).pack(side="left", fill="x", expand=True)
                # Left value
                value_a_color = theme.accent if value_a is not None else theme.fg3
                tk.Label(
                    row,
                    text=value_a_text,
                    bg=bg,
                    fg=value_a_color,
                    font=(UI_FONT, 12),
                    width=18,
                    anchor="w",
                    padx=4,
                ).pack(side="left")
                # Right value
                value_b_color = theme.warning if value_b is not None else theme.fg3
                tk.Label(
                    row,
                    text=value_b_text,
                    bg=bg,
                    fg=value_b_color,
                    font=(UI_FONT, 12),
                    width=18,
                    anchor="w",
                    padx=4,
                ).pack(side="left")
                # Delta
                delta_fg = theme.modified if delta != "\u2014" else theme.fg3
                tk.Label(
                    row,
                    text=delta,
                    bg=bg,
                    fg=delta_fg,
                    font=(UI_FONT, 12),
                    width=8,
                    anchor="w",
                    padx=4,
                ).pack(side="left")
                row_idx += 1

        if not diffs:
            tk.Label(
                body,
                text="These profiles are identical.",
                bg=theme.bg2,
                fg=theme.fg2,
                font=(UI_FONT, 13),
                pady=30,
            ).pack()

        _bind_scroll_recursive(body)

    def _format_value(self, value: Any, key: Optional[str] = None) -> str:
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
        return (
            s[:_VALUE_TRUNCATE_SHORT] + "..." if len(s) > _VALUE_TRUNCATE_SHORT else s
        )

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
            logger.debug(
                "Could not compute delta for %r vs %r: %s", value_a, value_b, e
            )
            return "—"
