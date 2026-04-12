"""BatchRenameDialog — bulk rename profiles with pattern matching."""

from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Optional

from .constants import UI_FONT, _PLATFORM
from .theme import Theme
from .models import Profile
from .utils import bind_scroll, lighten_color
from .widgets import make_btn

logger = logging.getLogger(__name__)


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

    def destroy(self) -> None:
        for var, trace_id in getattr(self, "_trace_ids", []):
            try:
                var.trace_remove("write", trace_id)
            except (tk.TclError, ValueError):
                pass
        super().destroy()

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

        tk.Label(
            self,
            text=f"Rename {len(self.profiles)} selected profiles",
            bg=theme.bg,
            fg=theme.fg,
            font=(UI_FONT, 13, "bold"),
        ).pack(padx=16, pady=(12, 6), anchor="w")

        self._build_mode_tabs()
        self._build_simple_mode()
        self._build_pattern_mode()
        self._build_preview_section()
        self._build_action_buttons()

        # Show initial tab — this packs content and triggers first preview
        self._switch_tab("simple")
        self._update_simple_fields()

    def _build_mode_tabs(self) -> None:
        theme = self.theme
        tab_frame = tk.Frame(self, bg=theme.bg)
        tab_frame.pack(fill="x", padx=16)
        self._mode_var = tk.StringVar(value="simple")

        self._simple_tab_btn = tk.Label(
            tab_frame,
            text="  Find / Replace  ",
            bg=theme.sel,
            fg=theme.fg,
            font=(UI_FONT, 12, "bold"),
            padx=8,
            pady=4,
            cursor="pointinghand",
        )
        self._simple_tab_btn.pack(side="left", padx=(0, 2))
        self._pattern_tab_btn = tk.Label(
            tab_frame,
            text="  Name from Template  ",
            bg=theme.bg4,
            fg=theme.fg3,
            font=(UI_FONT, 12),
            padx=8,
            pady=4,
            cursor="pointinghand",
        )
        self._pattern_tab_btn.pack(side="left")

        # Container for swappable tab content — sits between tabs and preview
        self._content_holder = tk.Frame(self, bg=theme.bg)
        self._content_holder.pack(fill="x", padx=16, pady=(6, 0))

        self._simple_tab_btn.bind("<Button-1>", lambda e: self._switch_tab("simple"))
        self._pattern_tab_btn.bind("<Button-1>", lambda e: self._switch_tab("pattern"))

    def _build_simple_mode(self) -> None:
        theme = self.theme
        self._simple_frame = tk.Frame(self._content_holder, bg=theme.bg)

        self._simple_mode_var = tk.StringVar(value="replace")
        smodes = tk.Frame(self._simple_frame, bg=theme.bg)
        smodes.pack(fill="x", pady=(2, 0))
        for val, label in [
            ("replace", "Find and replace"),
            ("prefix", "Add prefix"),
            ("suffix", "Add suffix"),
            ("remove", "Remove text"),
        ]:
            tk.Radiobutton(
                smodes,
                text=label,
                variable=self._simple_mode_var,
                value=val,
                bg=theme.bg,
                fg=theme.fg,
                selectcolor=theme.bg4,
                activebackground=theme.bg,
                activeforeground=theme.fg,
                font=(UI_FONT, 12),
            ).pack(anchor="w", pady=1)

        sinput = tk.Frame(self._simple_frame, bg=theme.bg)
        sinput.pack(fill="x", pady=(6, 0))
        sinput.columnconfigure(1, weight=1)

        tk.Label(
            sinput, text="Find:", bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12)
        ).grid(row=0, column=0, sticky="w", pady=2)
        self._find_var = tk.StringVar()
        find_entry = tk.Entry(
            sinput,
            textvariable=self._find_var,
            bg=theme.bg3,
            fg=theme.fg,
            font=(UI_FONT, 12),
            insertbackground=theme.fg,
            highlightbackground=theme.border,
            highlightthickness=1,
        )
        find_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)

        self._replace_lbl = tk.Label(
            sinput, text="Replace:", bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12)
        )
        self._replace_var = tk.StringVar()
        self._replace_entry = tk.Entry(
            sinput,
            textvariable=self._replace_var,
            bg=theme.bg3,
            fg=theme.fg,
            font=(UI_FONT, 12),
            insertbackground=theme.fg,
            highlightbackground=theme.border,
            highlightthickness=1,
        )

        self._find_entry = find_entry
        self._trace_ids = getattr(self, "_trace_ids", [])
        self._trace_ids.append(
            (
                self._simple_mode_var,
                self._simple_mode_var.trace_add("write", self._update_simple_fields),
            )
        )
        self._trace_ids.append(
            (
                self._find_var,
                self._find_var.trace_add("write", lambda *a: self._update_preview()),
            )
        )
        self._trace_ids.append(
            (
                self._replace_var,
                self._replace_var.trace_add("write", lambda *a: self._update_preview()),
            )
        )

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

    def _build_pattern_mode(self) -> None:
        theme = self.theme
        self._pattern_frame = tk.Frame(self._content_holder, bg=theme.bg)

        tk.Label(
            self._pattern_frame,
            text="Click tokens to build a naming pattern:",
            bg=theme.bg,
            fg=theme.fg2,
            font=(UI_FONT, 12, "italic"),
        ).pack(anchor="w", pady=(2, 4))

        self._pattern_var = tk.StringVar(value="{brand} - {material} - {name}")

        self._build_pattern_tokens()
        self._build_pattern_separators()
        self._build_pattern_entry()
        self._trace_ids.append(
            (
                self._pattern_var,
                self._pattern_var.trace_add("write", lambda *a: self._update_preview()),
            )
        )

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

    def _build_pattern_tokens(self) -> None:
        theme = self.theme
        token_row1 = tk.Frame(self._pattern_frame, bg=theme.bg)
        token_row1.pack(fill="x", pady=(0, 2))
        token_row2 = tk.Frame(self._pattern_frame, bg=theme.bg)
        token_row2.pack(fill="x", pady=(0, 4))

        def _insert_token(token: str) -> None:
            self._pattern_entry.insert("insert", "{" + token + "}")
            self._update_preview()

        for i, (tok, tip) in enumerate(self._available_tokens):
            parent_row = token_row1 if i < 4 else token_row2
            make_btn(
                parent_row,
                "{" + tok + "}",
                lambda t=tok: _insert_token(t),
                bg=theme.bg4,
                fg=theme.accent,
                font=(UI_FONT, 12),
                padx=4,
                pady=2,
            ).pack(side="left", padx=(0, 4))

    def _build_pattern_separators(self) -> None:
        theme = self.theme
        sep_frame = tk.Frame(self._pattern_frame, bg=theme.bg)
        sep_frame.pack(fill="x", pady=(0, 4))
        tk.Label(
            sep_frame, text="Separators:", bg=theme.bg, fg=theme.fg3, font=(UI_FONT, 12)
        ).pack(side="left", padx=(0, 6))
        for label, val in [
            (" - ", " - "),
            (" _ ", " _ "),
            (" @ ", " @ "),
            (" . ", "."),
            ("space", " "),
        ]:
            make_btn(
                sep_frame,
                label,
                lambda v=val: (
                    self._pattern_entry.insert("insert", v),
                    self._update_preview(),
                ),
                bg=theme.bg4,
                fg=theme.fg2,
                font=(UI_FONT, 12),
                padx=4,
                pady=2,
            ).pack(side="left", padx=(0, 3))

    def _build_pattern_entry(self) -> None:
        theme = self.theme
        pf_row = tk.Frame(self._pattern_frame, bg=theme.bg)
        pf_row.pack(fill="x", pady=(2, 0))
        tk.Label(
            pf_row, text="Pattern:", bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12)
        ).pack(side="left", padx=(0, 8))
        self._pattern_entry = tk.Entry(
            pf_row,
            textvariable=self._pattern_var,
            bg=theme.bg3,
            fg=theme.fg,
            font=(UI_FONT, 12),
            insertbackground=theme.fg,
            highlightbackground=theme.accent,
            highlightthickness=1,
        )
        self._pattern_entry.pack(side="left", fill="x", expand=True)

    def _build_preview_section(self) -> None:
        theme = self.theme
        tk.Label(
            self, text="Preview:", bg=theme.bg, fg=theme.fg2, font=(UI_FONT, 12)
        ).pack(padx=16, pady=(10, 2), anchor="w")
        preview_frame = tk.Frame(
            self, bg=theme.bg3, highlightbackground=theme.border, highlightthickness=1
        )
        preview_frame.pack(fill="both", expand=True, padx=16)
        self._preview_text = tk.Text(
            preview_frame,
            bg=theme.bg3,
            fg=theme.fg,
            font=(UI_FONT, 12),
            height=min(6, len(self.profiles)),
            wrap="none",
            relief="flat",
            bd=4,
        )
        self._preview_text.tag_configure("arrow", foreground=theme.fg3)
        self._preview_text.tag_configure("changed", foreground=theme.accent)
        self._preview_text.tag_configure("collision", foreground=theme.error)
        self._has_collisions = False
        preview_sb = ttk.Scrollbar(
            preview_frame, orient="vertical", command=self._preview_text.yview
        )
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

    def _build_action_buttons(self) -> None:
        theme = self.theme
        btn_frame = tk.Frame(self, bg=theme.bg)
        btn_frame.pack(fill="x", padx=16, pady=(8, 12))

        def _apply() -> None:
            if self._has_collisions:
                from tkinter import messagebox

                if not messagebox.askokcancel(
                    "Duplicate Names",
                    "Some profiles will have duplicate names after renaming.\n"
                    "Continue anyway?",
                    parent=self,
                ):
                    return
            renamed = 0
            for p in self.profiles:
                new_name = Profile.sanitize_name(self._compute_name(p))
                if new_name and new_name != p.name:
                    old_name = p.name
                    snapshot = {"name": old_name, "_modified": p.modified}
                    p.data["name"] = new_name
                    p.modified = True
                    p.log_change(
                        "Renamed", f"{old_name} \u2192 {new_name}", snapshot=snapshot
                    )
                    renamed += 1
            self.destroy()
            if self.on_complete:
                self.on_complete()

        make_btn(
            btn_frame,
            "  Rename All  ",
            _apply,
            bg=theme.accent2,
            fg=theme.accent_fg,
            font=(UI_FONT, 12, "bold"),
            padx=12,
            pady=5,
        ).pack(side="right", padx=(6, 0))
        make_btn(
            btn_frame,
            "  Cancel  ",
            self.destroy,
            bg=theme.bg4,
            fg=theme.fg2,
            font=(UI_FONT, 12),
            padx=12,
            pady=5,
        ).pack(side="right")

    def _switch_tab(self, tab: str) -> None:
        theme = self.theme
        self._mode_var.set(tab)
        for child in self._content_holder.winfo_children():
            child.pack_forget()
        if tab == "simple":
            self._simple_frame.pack(fill="x")
            self._simple_tab_btn.configure(
                bg=theme.sel, fg=theme.fg, font=(UI_FONT, 12, "bold")
            )
            self._pattern_tab_btn.configure(
                bg=theme.bg4, fg=theme.fg3, font=(UI_FONT, 12)
            )
            self._find_entry.focus_set()
        else:
            self._pattern_frame.pack(fill="x")
            self._pattern_tab_btn.configure(
                bg=theme.sel, fg=theme.fg, font=(UI_FONT, 12, "bold")
            )
            self._simple_tab_btn.configure(
                bg=theme.bg4, fg=theme.fg3, font=(UI_FONT, 12)
            )
            self._pattern_entry.focus_set()
        self._update_preview()

    def _update_simple_fields(self, *_) -> None:
        m = self._simple_mode_var.get()
        if m == "replace":
            self._replace_lbl.grid(row=1, column=0, sticky="w", pady=2)
            self._replace_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=2)
        else:
            self._replace_lbl.grid_forget()
            self._replace_entry.grid_forget()
        self._update_preview()

    def _update_preview(self) -> None:
        self._preview_text.configure(state="normal")
        self._preview_text.delete("1.0", "end")

        # Compute all new names and detect duplicates
        new_names = [self._compute_name(p) for p in self.profiles]
        seen: dict[str, int] = {}
        duplicates: set[str] = set()
        for nm in new_names:
            seen[nm] = seen.get(nm, 0) + 1
        for nm, count in seen.items():
            if count > 1:
                duplicates.add(nm)
        self._has_collisions = bool(duplicates)

        for i, p in enumerate(self.profiles[:30]):
            new = new_names[i]
            if i > 0:
                self._preview_text.insert("end", "\n")
            if new != p.name:
                self._preview_text.insert("end", p.name)
                self._preview_text.insert("end", "  \u2192  ", "arrow")
                tag = "collision" if new in duplicates else "changed"
                self._preview_text.insert("end", new, tag)
                if new in duplicates:
                    self._preview_text.insert("end", "  \u26a0 duplicate", "collision")
            else:
                self._preview_text.insert("end", f"{p.name}  (unchanged)")
        # Count hidden collisions beyond the preview limit
        hidden_collisions = sum(1 for nm in new_names[30:] if nm in duplicates)
        if len(self.profiles) > 30:
            suffix = f"\n... and {len(self.profiles) - 30} more"
            if hidden_collisions:
                suffix += f" ({hidden_collisions} with duplicate names)"
            self._preview_text.insert("end", suffix)
        self._preview_text.configure(state="disabled")
