# Main application window

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import subprocess
import threading
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from typing import Optional

import zipfile

from .constants import (
    APP_NAME,
    APP_VERSION,
    _PLATFORM,
    _WIN_WIDTH,
    _WIN_HEIGHT,
    _TREE_ROW_HEIGHT,
    SETTING_ID_PREFIX,
    UI_FONT,
    MAX_COLLISION_ATTEMPTS,
    PRESET_SCAN_TIMEOUT_S,
    _ENTRY_CHARS,
)

_INSTANCE_LOCK_PORT = 47391
from .theme import Theme
from .models import (
    Profile,
    ProfileEngine,
    PresetIndex,
    SlicerDetector,
    BundleDetectedError,
    UnsupportedFormatError,
)
from .state import (
    restore_profile_state,
    cleanup_stale_state,
)
from .panels import ProfileDetailPanel, ProfileListPanel, ComparePanel
from .dialogs import OnlineImportWizard, PrusaBundleWizard
from .utils import user_error
from .widgets import ExportDialog, Tooltip, UnlockDialog, make_btn

logger = logging.getLogger(__name__)


class App(tk.Tk):
    """Main application window.

    Manages UI layout, menu bar, tab navigation, file operations, and
    profile loading/saving. Single Tkinter root window with two
    ProfileListPanel children (process and filament tabs).
    """

    @staticmethod
    def _extract_user_id(source_path: str) -> str:
        """Extract user_id from directory structure: .../user/<user_id>/...

        Args:
            source_path: File or directory path containing "user/<user_id>/"

        Returns:
            The user_id if found, otherwise empty string
        """
        parts = os.path.normpath(source_path).split(os.sep)
        for i, part in enumerate(parts):
            if part == "user" and i + 1 < len(parts):
                return parts[i + 1]
        return ""

    def __init__(self) -> None:
        """Initialize the application window and UI."""
        super().__init__()
        self.theme = Theme()
        self._preset_lock = threading.Lock()

        # Load PNG icon sets — keep references on self to prevent GC of PhotoImages
        try:
            from resources.icons.icon_loader import IconSet

            self.icons = IconSet(size=24)
            self.icons_sm = IconSet(size=16)
        except (ImportError, FileNotFoundError, OSError):
            logger.warning("Failed to load icon sets; icons will be unavailable")
            self.icons = None
            self.icons_sm = None

        self.detected_slicers = SlicerDetector.find_all()
        self.preset_index = PresetIndex()
        self._filament_selection: list = []  # Cached filament panel selection
        self._preset_loading = False

        # Build preset index from all detected slicers
        for name, path in self.detected_slicers.items():
            self.preset_index.build(path, name)

        self.title(APP_NAME)
        self.geometry(f"{_WIN_WIDTH}x{_WIN_HEIGHT}")
        self.configure(bg=self.theme.bg)

        # Set window icon (taskbar / title bar)
        self._set_window_icon()

        self._configure_styles()
        self._build_menu()
        self._build_ui()
        self._update_status("Ready")

        # Set minimum size after UI is built and mapped
        self.update_idletasks()
        self.minsize(1020, 620)

    def _icon(self, name: str, small: bool = False) -> Optional[tk.PhotoImage]:
        source = self.icons_sm if small else self.icons
        return getattr(source, name, None) if source else None

    def _set_window_icon(self) -> None:
        """Set the application window icon for taskbar, title bar, and dock.

        Platform-specific handling:
          macOS:   Uses .icns via tk.call('wm', 'iconphoto') + PhotoImage fallback
          Windows: Uses .ico via iconbitmap() for sharp taskbar/title bar icons
          Linux:   Uses iconphoto() with multiple PNG sizes (freedesktop.org)
        """
        import sys

        try:
            if getattr(sys, "frozen", False):
                base = Path(sys._MEIPASS) / "resources"
            else:
                base = Path(__file__).parent.parent / "resources"

            # Windows: .ico gives best results for taskbar + title bar
            if _PLATFORM == "Windows":
                ico_path = base / "AppIcon.ico"
                if ico_path.exists():
                    self.iconbitmap(str(ico_path))
                    return

            # All platforms: iconphoto with multiple PNG sizes (largest-first)
            icon_files = [
                base / "AppIcon-512.png",
                base / "AppIcon.png",  # 256px
                base / "AppIcon-128.png",
                base / "AppIcon-64.png",
                base / "AppIcon-32.png",
            ]
            images = []
            for f in icon_files:
                if f.exists():
                    images.append(tk.PhotoImage(file=str(f)))

            if images:
                self.iconphoto(True, *images)
                self._app_icon_images = images  # prevent GC
        except (tk.TclError, OSError):
            logger.debug("Could not set window icon", exc_info=True)

    def _configure_styles(self) -> None:
        """Configure ttk style theme for the application.

        Sets colors, fonts, and appearance for all themed widgets
        (Treeview, Combobox, Notebook tabs).
        """
        theme = self.theme
        style = ttk.Style(self)
        available = style.theme_names()
        if "clam" in available:
            style.theme_use("clam")

        # Base widget styles
        style.configure(".", background=theme.bg, foreground=theme.fg)
        style.configure("TFrame", background=theme.bg)
        style.configure("TLabel", background=theme.bg, foreground=theme.fg)

        # Treeview (profile list)
        style.configure(
            "Treeview",
            background=theme.bg2,
            foreground=theme.fg,
            fieldbackground=theme.bg2,
            rowheight=_TREE_ROW_HEIGHT,
            font=(UI_FONT, 12),
        )
        style.map(
            "Treeview",
            background=[("selected", theme.sel)],
            foreground=[("selected", theme.fg)],
        )

        # Treeview headings
        style.configure(
            "Treeview.Heading",
            background=theme.bg4,
            foreground=theme.fg,
            font=(UI_FONT, 12, "bold"),
            relief="flat",
            padding=(6, 4),
        )
        style.map("Treeview.Heading", background=[("active", theme.bg3)])

        # Combobox for enum parameter dropdowns
        style.configure(
            "Param.TCombobox",
            fieldbackground=theme.bg3,
            background=theme.bg3,
            foreground=theme.fg,
            arrowcolor=theme.fg2,
            borderwidth=1,
            relief="flat",
        )
        style.map(
            "Param.TCombobox",
            fieldbackground=[("disabled", theme.bg3), ("readonly", theme.bg3)],
            foreground=[("disabled", theme.fg3), ("readonly", theme.fg)],
            background=[("disabled", theme.bg3), ("readonly", theme.bg3)],
        )

        # Combobox dropdown list
        self.option_add("*TCombobox*Listbox.background", theme.bg3)
        self.option_add("*TCombobox*Listbox.foreground", theme.fg)
        self.option_add("*TCombobox*Listbox.selectBackground", theme.accent2)
        self.option_add("*TCombobox*Listbox.selectForeground", theme.accent_fg)
        self.option_add("*TCombobox*Listbox.font", (UI_FONT, 13))

        # Notebook (tabs)
        style.configure("TNotebook", background=theme.bg, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=theme.bg4,
            foreground=theme.fg2,
            padding=(18, 8),
            font=(UI_FONT, 12),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", theme.accent2)],
            foreground=[("selected", theme.accent_fg)],
            padding=[("selected", (18, 8))],
        )

    def _build_menu(self) -> None:
        """Build the application menu bar (File, Edit, Help).

        Configures File menu with import/export operations, Edit menu
        with selection, and Help menu with about dialog. Binds keyboard
        shortcuts across all platforms.
        """
        menubar = tk.Menu(self, bg=self.theme.bg3, fg=self.theme.fg)
        file_menu = tk.Menu(menubar, tearoff=0, bg=self.theme.bg3, fg=self.theme.fg)
        mod_key = "Cmd" if _PLATFORM == "Darwin" else "Ctrl"

        file_menu.add_command(
            label="Import from Files\u2026",
            command=self._on_import_json,
            accelerator=f"{mod_key}+O",
        )
        file_menu.add_command(
            label="Import from 3MF Project\u2026",
            command=self._on_extract_3mf,
            accelerator=f"{mod_key}+Shift+O",
        )
        file_menu.add_command(
            label="Import from Online Sources\u2026",
            command=self._on_import_online,
        )
        file_menu.add_command(
            label="Import from Installed Slicers",
            command=self._on_load_presets,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Export Selected...",
            command=self._on_export,
            accelerator=f"{mod_key}+E",
        )

        # Export to Slicer submenu (if slicers detected)
        if self.detected_slicers:
            exp = tk.Menu(file_menu, tearoff=0, bg=self.theme.bg3, fg=self.theme.fg)
            for name, path in self.detected_slicers.items():
                exp.add_command(
                    label=f"Export to {name}...",
                    command=lambda p=path, n=name: self._on_export_to_slicer(n, p),
                )
            file_menu.add_cascade(label="Export to Slicer", menu=exp)

        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0, bg=self.theme.bg3, fg=self.theme.fg)
        edit_menu.add_command(
            label="Select All",
            command=self._on_select_all,
            accelerator=f"{mod_key}+A",
        )
        menubar.add_cascade(label="Edit", menu=edit_menu)

        help_menu = tk.Menu(menubar, tearoff=0, bg=self.theme.bg3, fg=self.theme.fg)
        help_menu.add_command(label="About", command=self._on_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

        # Bind keyboard shortcuts
        mod_key_internal = "Command" if _PLATFORM == "Darwin" else "Control"
        self.bind(f"<{mod_key_internal}-o>", lambda e: self._on_import_json())
        self.bind(f"<{mod_key_internal}-Shift-o>", lambda e: self._on_extract_3mf())
        self.bind(f"<{mod_key_internal}-Shift-O>", lambda e: self._on_extract_3mf())
        self.bind(f"<{mod_key_internal}-e>", lambda e: self._on_export())
        self.bind(f"<{mod_key_internal}-a>", lambda e: self._on_select_all())

    def _build_ui(self) -> None:
        """Build the main UI layout.

        Constructs status bar, toolbar with tab buttons, and content area
        with two stacked ProfileListPanel instances (process/filament).
        """
        theme = self.theme

        # Status bar (pack first so it stays at bottom)
        status_frame = tk.Frame(self, bg=theme.bg)
        status_frame.pack(fill="x", side="bottom")

        self._status_label = tk.Label(
            status_frame,
            text="",
            bg=theme.bg,
            fg=theme.fg3,
            font=(UI_FONT, 12),
            padx=12,
        )
        self._status_label.pack(side="left")

        self._count_label = tk.Label(
            status_frame,
            text="",
            bg=theme.bg,
            fg=theme.fg3,
            font=(UI_FONT, 12),
            padx=12,
        )
        self._count_label.pack(side="right")

        if self.detected_slicers:
            tk.Label(
                status_frame,
                text=f"Detected: {', '.join(self.detected_slicers.keys())}",
                bg=theme.bg,
                fg=theme.fg,
                font=(UI_FONT, 12),
                padx=12,
            ).pack(side="right")

        # Toolbar row
        toolbar_row = tk.Frame(self, bg=theme.bg)
        toolbar_row.pack(fill="x", side="top")

        # Tab labels on the left
        self._tab_var = tk.StringVar(value="filament")
        tab_frame = tk.Frame(toolbar_row, bg=theme.bg)
        tab_frame.pack(side="left", padx=(4, 0), pady=(4, 0))

        _filament_icon = self._icon("filament")

        _convert_icon = self._icon("convert")
        _compare_icon = self._icon("compare")

        self._filament_tab = make_btn(
            tab_frame,
            "  Filament  ",
            lambda: self._switch_tab("filament"),
            bg=theme.icon_active_bg_strong,
            fg=theme.fg,
            font=(UI_FONT, 13, "bold"),
            padx=14,
            pady=6,
            image=_filament_icon,
            compound="left",
        )
        self._filament_tab.pack(side="left", padx=(0, 10))

        self._convert_tab = make_btn(
            tab_frame,
            "  Convert  ",
            lambda: self._on_convert_tab(),
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 13),
            padx=14,
            pady=6,
            image=_convert_icon,
            compound="left",
        )
        self._convert_tab.pack(side="left", padx=(0, 10))

        self._compare_tab = make_btn(
            tab_frame,
            "  Compare Filament  ",
            lambda: self._on_compare_tab(),
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 13),
            padx=14,
            pady=6,
            image=_compare_icon,
            compound="left",
        )
        self._compare_tab.pack(side="left")

        # Toolbar buttons on the right
        toolbar = tk.Frame(toolbar_row, bg=theme.bg)
        toolbar.pack(side="right", padx=(0, 8), pady=(4, 6))

        btn_font = (UI_FONT, 12)
        btn_pad = 10

        make_btn(
            toolbar,
            "Import from Files",
            self._on_import_json,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=btn_font,
            padx=btn_pad,
            pady=5,
        ).pack(side="left", padx=(0, 4))

        make_btn(
            toolbar,
            "Import from 3MF",
            self._on_extract_3mf,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=btn_font,
            padx=btn_pad,
            pady=5,
        ).pack(side="left", padx=(0, 4))

        make_btn(
            toolbar,
            "Import from Slicers",
            self._on_load_presets,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=btn_font,
            padx=btn_pad,
            pady=5,
        ).pack(side="left", padx=(0, 4))

        export_btn = make_btn(
            toolbar,
            "Export",
            self._on_export,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=btn_font,
            padx=btn_pad,
            pady=5,
            image=self._icon("save"),
            compound="left",
        )
        export_btn.pack(side="right", padx=(0, 4))
        Tooltip(export_btn, "Export selected profiles to file or slicer", theme=theme)

        # Content area: stacked frames (manual tab switching)
        self._content_area = tk.Frame(self, bg=theme.bg)
        self._content_area.pack(fill="both", expand=True)

        self.filament_panel = ProfileListPanel(
            self._content_area, theme, "filament", self
        )
        self.compare_panel = ComparePanel(self._content_area, theme, self)

        # Show filament panel by default
        self.filament_panel.pack(fill="both", expand=True)
        self._current_tab = "filament"

        # Global Ctrl+Z / Cmd+Z dispatcher — routes to the correct panel
        self._bind_global_undo()

    def _bind_global_undo(self) -> None:
        """Bind a single global Ctrl+Z handler that dispatches to the visible panel."""
        mod_key = "Command" if _PLATFORM == "Darwin" else "Control"
        self.winfo_toplevel().bind(f"<{mod_key}-z>", self._global_undo)

    def _global_undo(self, event: Optional[tk.Event] = None) -> str:
        """Route Ctrl+Z to ComparePanel (if visible) or DetailPanel."""
        if self._current_tab == "compare":
            return self.compare_panel._on_undo(event) or "break"
        else:
            panel = self._active_panel()
            if hasattr(panel, "detail"):
                return panel.detail._on_undo(event) or "break"
        return "break"

    def _switch_tab(self, tab_name: str) -> None:
        """Switch to the named tab (filament, compare, or convert).

        Filament and Convert share the same filament_panel — only the right
        pane is swapped via set_mode().  Avoid pack_forget/pack when switching
        between them to preserve sash position and tree state.
        """
        theme = self.theme
        if tab_name == self._current_tab:
            return

        prev = self._current_tab
        # Determine if the underlying panel changes
        prev_uses_filament = prev in ("filament", "convert")
        next_uses_filament = tab_name in ("filament", "convert")

        # Unbind compare shortcuts when leaving compare tab
        if prev == "compare":
            self.compare_panel._unbind_shortcuts()

        # Only pack_forget panels that are actually being replaced
        if not (prev_uses_filament and next_uses_filament):
            self.filament_panel.pack_forget()
            self.compare_panel.pack_forget()

        # Reset all tab button styles to inactive
        inactive = dict(bg=theme.bg4, fg=theme.btn_fg, font=(UI_FONT, 13))
        active = dict(
            bg=theme.icon_active_bg_strong, fg=theme.fg, font=(UI_FONT, 13, "bold")
        )

        self._filament_tab.configure(**inactive)
        self._convert_tab.configure(**inactive)
        self._compare_tab.configure(**inactive)

        # Show the selected panel and activate its tab
        if tab_name == "filament":
            self.filament_panel.set_mode("detail")
            if not prev_uses_filament:
                self.filament_panel.pack(fill="both", expand=True)
            self._filament_tab.configure(**active)
        elif tab_name == "convert":
            self.filament_panel.set_mode("convert")
            if not prev_uses_filament:
                self.filament_panel.pack(fill="both", expand=True)
            self._convert_tab.configure(**active)
        elif tab_name == "compare":
            self.compare_panel.pack(fill="both", expand=True)
            self._compare_tab.configure(**active)

        self._current_tab = tab_name

    def _active_panel(self) -> ProfileListPanel:
        # Compare tab handles its own state via compare_panel; menu actions
        # always target the filament panel, which is the only list panel.
        return self.filament_panel

    # --- File Operations ---

    def _on_import_json(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Import from Files",
            filetypes=[
                ("JSON profiles", "*.json"),
                ("Prusa profiles", "*.ini"),
                ("BBS filament bundles", "*.bbsflmt"),
                ("All", "*.*"),
            ],
        )
        if not paths:
            return
        # Check for Prusa factory bundles and route through wizard
        bundle_paths = [p for p in paths if ProfileEngine.is_prusa_bundle(p)]
        normal_paths = [p for p in paths if p not in bundle_paths]

        if normal_paths:
            self._load_files([(p, None, "") for p in normal_paths])

        for bp in bundle_paths:
            wizard = PrusaBundleWizard(self, self.theme, bp)
            if wizard.result:
                cached = wizard.parsed_sections
                self._update_status("Resolving Prusa profiles...")
                self.update_idletasks()
                profiles = ProfileEngine.load_bundle_filaments(
                    bp, wizard.result, sections=cached
                )
                if profiles:
                    with self._preset_lock:
                        self.preset_index.add_profiles(profiles)
                        resolved = 0
                        for i, p in enumerate(profiles):
                            if p.inherits:
                                self.preset_index.resolve(p)
                                if p.resolved_data:
                                    resolved += 1
                            if i % 5 == 0:
                                self._update_status(
                                    f"Resolving Prusa profiles... ({i}/{len(profiles)})"
                                )
                                self.update_idletasks()
                    self.filament_panel.add_profiles(profiles)
                    total = len(self.filament_panel.profiles)
                    status = f"Imported {len(profiles)} Prusa factory profiles. {total} total."
                    if resolved:
                        status += f" Resolved {resolved} inherited."
                    self._update_status(status)

    def _on_extract_3mf(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Import from 3MF Project",
            filetypes=[("3MF projects", "*.3mf"), ("All", "*.*")],
        )
        if not paths:
            return
        before = len(self.filament_panel.profiles)
        self._load_files([(p, None, "") for p in paths])
        after = len(self.filament_panel.profiles)
        if after == before:
            messagebox.showinfo(
                "No Filament Profiles Found",
                "No filament profiles were found in the selected 3MF file(s).",
            )

    def _safe_after(self, ms: int, func: callable) -> None:
        """Schedule a callback only if the window still exists (prevents TclError on exit)."""
        try:
            if self.winfo_exists():
                self.after(ms, func)
        except tk.TclError:
            pass

    def _on_import_online(self) -> None:
        OnlineImportWizard(self, self.theme, self._load_files)

    def _on_load_presets(self) -> None:
        if not self.detected_slicers:
            messagebox.showinfo(
                "No Slicers Found",
                "No slicer installations were detected.\n\n"
                "Supported: BambuStudio, OrcaSlicer, PrusaSlicer\n\n"
                "Use File > Import to load profiles manually.",
            )
            return

        # Prevent multiple concurrent loads
        with self._preset_lock:
            if getattr(self, "_preset_loading", False):
                return
            self._preset_loading = True

        panel = self._active_panel()
        slicer_names = ", ".join(self.detected_slicers.keys())
        panel._show_overlay(
            f"Scanning {slicer_names}...", show_spinner=True, show_progress=True
        )

        def _bg_scan() -> None:
            """Background thread: discover, load, index, and resolve preset files."""
            try:
                pairs = self._resolve_preset_paths(panel, slicer_names)
                if not pairs:
                    self._safe_after(
                        0, lambda: self._preset_load_done(panel, [], 0, slicer_names)
                    )
                    return

                all_new, errors = self._load_preset_files(panel, pairs)
                if not all_new:
                    self._safe_after(
                        0,
                        lambda: self._preset_load_done(
                            panel, [], 0, slicer_names, errors
                        ),
                    )
                    return

                resolved_count = self._index_and_resolve_presets(panel, all_new)
                # NOTE: restore_profile_state moved to _preset_load_done (main thread)
                # to avoid mutating Profile objects concurrently with UI updates.
                filament_batch, skipped_process = self._batch_presets_by_type(all_new)

                # Hand off to main thread with pre-sorted batches
                self._safe_after(
                    0,
                    lambda: self._preset_load_done(
                        panel,
                        filament_batch,
                        skipped_process,
                        slicer_names,
                        errors,
                    ),
                )
            except Exception as e:
                logger.error("Preset loading failed: %s", e, exc_info=True)
                try:
                    self._safe_after(
                        0,
                        lambda: self._preset_load_done(
                            panel, [], 0, slicer_names, [f"Internal error: {e}"]
                        ),
                    )
                except Exception:
                    # _safe_after itself failed (widget destroyed) — reset flag directly
                    logger.debug("Could not signal main thread after preset scan error")
                    with self._preset_lock:
                        self._preset_loading = False

        threading.Thread(target=_bg_scan, daemon=True).start()

        def _bg_timeout():
            with self._preset_lock:
                if self._preset_loading:
                    self._preset_loading = False
                    self._safe_after(
                        0,
                        lambda: (
                            panel._hide_overlay(),
                            self._update_status(
                                "Loading timed out. Try again, or import manually via File > Import."
                            ),
                        ),
                    )

        self._bg_timer = threading.Timer(PRESET_SCAN_TIMEOUT_S, _bg_timeout)
        self._bg_timer.start()

    def _resolve_preset_paths(
        self, panel: ProfileListPanel, slicer_names: str
    ) -> list[tuple[str, str, str]]:
        """Phase 1: Discover preset file paths from all detected slicers."""
        pairs = []
        for name, path in self.detected_slicers.items():
            self._safe_after(
                0, lambda n=name: panel._update_overlay_text(f"Scanning {n}...")
            )
            presets = SlicerDetector.find_user_presets(path)
            for profile_type, files in presets.items():
                for fp in files:
                    pairs.append((fp, profile_type, name))
        return pairs

    def _load_preset_files(
        self, panel: ProfileListPanel, pairs: list[tuple[str, str, str]]
    ) -> tuple[list[Profile], list[str]]:
        """Phase 2: Load profile files from discovered paths."""
        total = len(pairs)
        self._safe_after(
            0, lambda: panel._update_overlay_text(f"Loading {total} presets...")
        )
        self._safe_after(0, lambda: panel._update_overlay_progress(0, total))

        all_new = []
        errors = []
        for i, item in enumerate(pairs):
            fp, type_hint, origin = item
            try:
                profiles = ProfileEngine.load_file(fp, type_hint)
                for p in profiles:
                    if origin:
                        p.origin = origin
                all_new.extend(profiles)
            except (
                OSError,
                json.JSONDecodeError,
                ValueError,
                zipfile.BadZipFile,
                BundleDetectedError,
                UnsupportedFormatError,
            ) as e:
                errors.append(f"{os.path.basename(fp)}: {e}")
                logger.debug(f"Failed to load preset {fp}", exc_info=True)

            if (i + 1) % 10 == 0 or (i + 1) == total:
                c = i + 1
                self._safe_after(
                    0,
                    lambda c=c, t=total: (
                        panel._update_overlay_text(f"Loading presets ({c}/{t})..."),
                        panel._update_overlay_progress(c, t),
                    ),
                )
        return all_new, errors

    def _index_and_resolve_presets(
        self, panel: ProfileListPanel, all_new: list[Profile]
    ) -> int:
        """Phase 3: Index and resolve inheritance for loaded profiles."""
        self._safe_after(
            0,
            lambda: panel._update_overlay_text("Indexing and resolving inheritance..."),
        )
        with self._preset_lock:
            self.preset_index.add_profiles(all_new)
            resolved_count = 0
            for profile in all_new:
                if profile.inherits:
                    self.preset_index.resolve(profile)
                    if profile.resolved_data:
                        resolved_count += 1
            return resolved_count

    def _batch_presets_by_type(
        self, all_new: list[Profile]
    ) -> tuple[list[Profile], int]:
        """Filter to filament profiles only."""
        filament_batch = [p for p in all_new if p.profile_type == "filament"]
        skipped = len(all_new) - len(filament_batch)
        return filament_batch, skipped

    def _preset_load_done(
        self,
        panel: ProfileListPanel,
        filament_batch: list[Profile],
        skipped: int,
        slicer_names: str,
        errors: Optional[list[str]] = None,
    ) -> None:
        """Finish preset loading on the main thread.

        Heavy work (indexing, resolution, state restore) has already been done
        on the background thread. This method only does the lightweight UI
        updates: batched panel additions and status messages.
        """
        with self._preset_lock:
            self._preset_loading = False
        if hasattr(self, "_bg_timer") and self._bg_timer:
            self._bg_timer.cancel()
            self._bg_timer = None
        panel._hide_overlay()

        # Restore persisted state on the main thread (safe to mutate profiles here)
        if filament_batch:
            restore_profile_state(filament_batch)

        loaded_f = len(filament_batch)

        if not loaded_f:
            self._update_status("No filament presets found in detected slicers.")
            return

        if filament_batch:
            self.filament_panel.add_profiles(filament_batch)

        if errors:
            error_list = errors[:20]
            if len(errors) > 20:
                error_list = list(error_list) + [f"... and {len(errors) - 20} more"]
            messagebox.showwarning(
                "Some Files Failed",
                f"Loaded {loaded_f} profiles. Errors:\n\n" + "\n".join(error_list),
            )

        total = len(self.filament_panel.profiles)
        status = f"Loaded {loaded_f} filament profiles. {total} total."
        # Surface unresolved inheritance and collision warnings
        warnings_parts = []
        if self.preset_index.unresolved_profiles:
            n = len(self.preset_index.unresolved_profiles)
            warnings_parts.append(
                f"{n} profiles may have missing values \u2014 their parent presets weren't found."
            )
        if self.preset_index.collisions > 0:
            warnings_parts.append(
                f"{self.preset_index.collisions} user presets override factory defaults with the same name."
            )
        if warnings_parts:
            status += " \u26a0 " + " ".join(warnings_parts)

        self._update_status(status)

    def _load_files(self, path_hint_tuples: list[tuple]) -> None:
        """Load files. Each entry is (path, type_hint, origin).

        Args:
            path_hint_tuples: List of (path, type_hint, origin) tuples
        """
        self._filament_selection = []
        loaded_f, resolved_count = 0, 0
        errors = []
        all_new = []

        for item in path_hint_tuples:
            path = item[0]
            type_hint = item[1] if len(item) > 1 else None
            origin = item[2] if len(item) > 2 else ""

            try:
                profiles = ProfileEngine.load_file(path, type_hint)
                for profile in profiles:
                    if origin:
                        profile.origin = origin
                    logger.info(
                        "Loaded profile '%s' from %s: %d keys, type=%s",
                        profile.name,
                        os.path.basename(path),
                        len(profile.data),
                        profile.profile_type,
                    )
                all_new.extend(profiles)
            except (
                OSError,
                json.JSONDecodeError,
                ValueError,
                zipfile.BadZipFile,
                BundleDetectedError,
                UnsupportedFormatError,
            ) as e:
                msg = f"{os.path.basename(path)}: {e}"
                errors.append(msg)
                logger.warning(msg, exc_info=True)

        # Add to index for cross-referencing, then resolve inheritance
        with self._preset_lock:
            self.preset_index.add_profiles(all_new)
            for profile in all_new:
                if profile.inherits:
                    self.preset_index.resolve(profile)
                    if profile.resolved_data:
                        resolved_count += 1

        # Restore persisted state (changelogs, modified flags)
        restore_profile_state(all_new)

        # Filter to filament profiles
        filament_batch = [p for p in all_new if p.profile_type == "filament"]
        loaded_f = len(filament_batch)
        if filament_batch:
            self.filament_panel.add_profiles(filament_batch)

        if errors:
            error_list = errors[:20]
            if len(errors) > 20:
                error_list.append(f"... and {len(errors) - 20} more")
            messagebox.showwarning(
                "Some Files Failed",
                f"Loaded {loaded_f} profiles. {len(errors)} error(s):\n\n"
                + "\n".join(error_list),
            )

        total = len(self.filament_panel.profiles)
        status = f"Loaded {loaded_f} filament profiles. {total} total."
        self._update_status(status)

    # --- Profile Actions ---

    def _on_unlock(self) -> None:
        """Unlock selected profiles with custom printer or make universal."""
        panel = self._active_panel()
        selected = panel.get_selected_profiles()
        if not selected:
            messagebox.showinfo(
                "No Selection", "Select one or more profiles in the list first."
            )
            return

        dlg = UnlockDialog(self, self.theme, len(selected))
        if dlg.result is None:
            return

        saved_back = 0
        for profile in selected:
            if dlg.result == "universal":
                profile.make_universal()
            else:
                profile.retarget(dlg.result)

        # Confirm before auto-saving to slicer
        slicer_profiles = [p for p in selected if self._is_slicer_profile(p)]
        if slicer_profiles:
            names = "\n".join(f"  \u2022 {p.name}" for p in slicer_profiles[:10])
            if len(slicer_profiles) > 10:
                names += f"\n  ... and {len(slicer_profiles) - 10} more"
            if not messagebox.askyesno(
                "Save to Slicer?",
                f"Save changes to {len(slicer_profiles)} {'profile' if len(slicer_profiles) == 1 else 'profiles'} in your slicer directory?\n\n{names}",
                parent=self,
            ):
                slicer_profiles = []

        for profile in slicer_profiles:
            try:
                self._save_back_to_slicer(profile)
                saved_back += 1
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(f"Auto-save failed for {profile.name}: {exc}")

        panel._refresh_list()
        panel._on_select()
        if dlg.result == "universal":
            n = len(selected)
            status = f"Made {n} {'profile' if n == 1 else 'profiles'} universal."
        else:
            n = len(selected)
            targets = (
                ", ".join(dlg.result) if isinstance(dlg.result, list) else dlg.result
            )
            status = (
                f"{n} {'profile' if n == 1 else 'profiles'} assigned to: {targets}."
            )
        if saved_back:
            status += " Saved to slicer — restart to see changes."
        self._update_status(status)
        if dlg.result == "universal":
            messagebox.showwarning(
                "Review Speed Settings",
                "These profiles may have speed and acceleration values "
                "tuned for a different printer.\n\n"
                "Review the Speed tab before printing.",
                parent=self,
            )

    def _is_slicer_profile(self, profile: Profile) -> bool:
        """Check if the profile was loaded from a detected slicer directory."""
        if not profile.source_path:
            return False
        src = os.path.normpath(profile.source_path)
        for slicer_path in self.detected_slicers.values():
            prefix = os.path.normpath(slicer_path)
            if src.startswith(prefix + os.sep) or src == prefix:
                return True
        return False

    def _save_back_to_slicer(self, profile: Profile) -> None:
        """Write the modified profile back to its source file in the slicer directory.

        Also ensures a .info metadata file exists alongside the JSON.
        BambuStudio creates one for every user profile and relies on it.

        Args:
            profile: Profile to save back
        """
        import time as _time

        fp = profile.source_path
        if not fp or not os.path.isfile(fp):
            return

        # Path traversal guard: ensure target is within a known slicer directory
        norm_fp = os.path.normpath(os.path.realpath(fp))
        if not any(
            norm_fp.startswith(os.path.normpath(os.path.realpath(sp)))
            for sp in self.detected_slicers.values()
        ):
            logger.warning("Refusing to save outside slicer directory: %s", fp)
            return

        # Write the JSON
        try:
            with open(fp, "w", encoding="utf-8") as f:
                f.write(profile.to_json(flatten=True))
        except OSError as e:
            messagebox.showerror(
                "Save Failed",
                user_error(
                    "Could not save to slicer directory.",
                    e,
                    "Make sure the slicer is not running.",
                ),
            )
            return

        info_path = os.path.splitext(fp)[0] + ".info"
        now_ts = str(int(_time.time()))

        try:
            if os.path.isfile(info_path):
                # Preserve existing metadata, just bump the timestamp
                lines = []
                with open(info_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("updated_time"):
                            lines.append(f"updated_time = {now_ts}\n")
                        else:
                            lines.append(line)
                with open(info_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
            else:
                # Create a new .info file — derive fields from context
                user_id = self._extract_user_id(fp)

                setting_id = SETTING_ID_PREFIX + secrets.token_hex(7)[:14]
                base_id = "GFSU00"

                with open(info_path, "w", encoding="utf-8") as f:
                    f.write("sync_info = \n")
                    f.write(f"user_id = {user_id}\n")
                    f.write(f"setting_id = {setting_id}\n")
                    f.write(f"base_id = {base_id}\n")
                    f.write(f"updated_time = {now_ts}\n")
        except OSError as e:
            logger.warning("Could not write .info file %s: %s", info_path, e)

    def _on_compare_tab(self) -> None:
        """Handle Compare Filament tab click.

        If 2 filament profiles are selected → switch to compare tab and load.
        Otherwise → switch to compare tab showing the waiting/prompt state.
        The ComparePanel will listen for selection changes via _on_filament_selection_changed.
        """
        # Try live tree selection first, fall back to cached selection
        selected = self.filament_panel.get_selected_profiles()
        logger.debug("_on_compare_tab: live selection=%d profiles", len(selected))
        if len(selected) != 2:
            selected = self._filament_selection
            logger.debug(
                "_on_compare_tab: fell back to cache=%d profiles", len(selected)
            )
        if len(selected) == 2:
            self.compare_panel.load(selected[0], selected[1])
        elif not self.compare_panel.is_waiting():
            self.compare_panel.show_waiting()
        # Always switch to compare tab
        if self._current_tab != "compare":
            self._switch_tab("compare")

    def _on_filament_selection_changed(self) -> None:
        """Called by filament_panel._on_select when selection changes.

        Reactively updates the Compare tab:
        - If Compare tab is active (waiting or showing): auto-load when 2 selected,
          show waiting when selection drops below 2.
        - If on Filament tab: cache the selection so Compare tab can pick it up
          immediately when activated (no stale state).
        """
        selected = self.filament_panel.get_selected_profiles()
        # Cache the current filament selection for cross-tab access
        self._filament_selection = selected
        logger.debug(
            "_on_filament_selection_changed: %d selected, tab=%s",
            len(selected),
            self._current_tab,
        )

        if self._current_tab == "compare":
            if len(selected) == 2:
                self.compare_panel.load(selected[0], selected[1])
            elif not self.compare_panel.is_waiting():
                # Selection dropped below 2 while viewing comparison — reset
                self.compare_panel.show_waiting()

    def _launch_compare(self, a: Profile, b: Profile) -> None:
        """Load two profiles into the ComparePanel and switch to it."""
        logger.info("_launch_compare: %s vs %s", a.name, b.name)
        self.compare_panel.load(a, b)
        if self._current_tab != "compare":
            self._switch_tab("compare")

    def _close_compare(self) -> None:
        """Clear the comparison and return to the filament list."""
        self.compare_panel.show_waiting()
        self._switch_tab("filament")

    def _on_convert_tab(self) -> None:
        """Handle Convert tab click — switches filament_panel to convert mode."""
        if self._current_tab != "convert":
            self._switch_tab("convert")

    # --- Conversion ---

    def _on_convert_profile(self, profile: "Profile", target: str) -> None:
        """Convert a profile to a different slicer format, add as a copy, and select it."""
        from .constants import SLICER_SHORT_LABELS, FILAMENT_LAYOUT

        short = SLICER_SHORT_LABELS.get(target, target)
        new_profile, dropped, missing, conv_warnings = profile.convert_to(target)

        # Rename copy to indicate conversion
        new_profile.data["name"] = f"{new_profile.name} ({short})"

        # Build JSON key → UI label lookup from layout
        key_labels = {}
        for tab_sections in FILAMENT_LAYOUT.values():
            for params in tab_sections.values():
                for entry in params:
                    key_labels[entry[0]] = entry[1]

        # Build summary dialog
        lines = [f"Converted '{profile.name}' to {short} format."]
        if dropped:
            lines.append(f"{len(dropped)} parameters dropped (no equivalent).")
        if missing:
            lines.append(
                f"{len(missing)} parameters need review \u2014 highlighted in the detail view."
            )
        gcode_keys = [k for k in new_profile.data if "gcode" in k.lower()]
        if gcode_keys:
            lines.append("G-code fields may need manual review.")

        # Add to list and select the new profile
        panel = self._active_panel()
        panel.profiles.append(new_profile)
        panel._refresh_list()

        # Find the new profile's iid by matching the object
        for iid in panel.tree.get_children():
            idx = int(iid)
            if idx < len(panel.profiles) and panel.profiles[idx] is new_profile:
                panel.tree.selection_set(iid)
                panel.tree.see(iid)
                panel._on_select()
                break

        messagebox.showinfo("Profile Converted", "\n".join(lines), parent=self)
        self._update_status(f"Converted to {short}: {new_profile.name}")

    # --- Export Operations ---

    def _warn_missing_conversion_keys(self, profiles: list) -> bool:
        """Check if any profiles have missing conversion keys. If so, warn the user.

        Returns True if the user wants to proceed anyway, False to cancel.
        """
        from .constants import FILAMENT_LAYOUT, SLICER_SHORT_LABELS

        # Collect profiles with missing keys
        problems = []
        for p in profiles:
            if p._missing_conversion_keys:
                problems.append(p)

        if not problems:
            return True

        # Build key→label lookup
        key_labels = {}
        for tab_sections in FILAMENT_LAYOUT.values():
            for params in tab_sections.values():
                for entry in params:
                    key_labels[entry[0]] = entry[1]

        lines = []
        for p in problems:
            slicer = SLICER_SHORT_LABELS.get(p.origin, p.origin or "target slicer")
            lines.append(
                f'"{p.name}" is missing {len(p._missing_conversion_keys)} '
                f"parameter(s) expected by {slicer}:"
            )
            for k in sorted(p._missing_conversion_keys):
                label = key_labels.get(k, k.replace("_", " ").capitalize())
                lines.append(f"    \u2022 {label}")
            lines.append("")

        lines.append("The exported profile may not work correctly in the slicer.")
        lines.append("\nExport anyway?")

        return messagebox.askyesno(
            "Missing Parameters",
            "\n".join(lines),
            icon="warning",
            parent=self,
        )

    def _on_export(self) -> None:
        """Export selected profiles with options for flattening/organization."""
        panel = self._active_panel()
        if hasattr(panel, "detail"):
            panel.detail._commit_edits()
        selected = panel.get_selected_profiles()
        if not selected:
            messagebox.showinfo(
                "No Selection",
                "Select profiles to export. Click one or more profiles in the list, then try again.",
            )
            return

        if not self._warn_missing_conversion_keys(selected):
            return

        # Auto-detect format from profile origin (Prusa → INI, others → JSON)
        default_fmt = "json"
        if selected and any(
            getattr(p, "origin", "").lower().startswith("prusa") for p in selected
        ):
            default_fmt = "ini"
        dlg = ExportDialog(
            self,
            self.theme,
            len(selected),
            detected_slicers=self.detected_slicers,
            default_format=default_fmt,
        )
        if dlg.result is None:
            return

        # Handle "Export to Slicer" from the export dialog
        if dlg.result == "slicer" and dlg.slicer_target:
            sname, spath = dlg.slicer_target
            self._on_install_to_slicer(sname, spath)
            return

        fmt = dlg.export_format

        if len(selected) == 1:
            # Single profile: save-as dialog
            profile = selected[0]
            if fmt == "ini":
                ext, ftype = ".ini", [("INI profile", "*.ini"), ("All", "*.*")]
            else:
                ext, ftype = ".json", [("JSON profile", "*.json"), ("All", "*.*")]
            fp = filedialog.asksaveasfilename(
                title="Export Profile",
                initialfile=profile.suggested_filename(fmt=fmt),
                defaultextension=ext,
                filetypes=ftype,
            )
            if fp:
                try:
                    if fmt == "ini" and hasattr(profile, "to_prusa_ini"):
                        content = profile.to_prusa_ini()
                    elif fmt == "ini":
                        content = profile.to_ini(flatten=True)
                    else:
                        content = profile.to_json(flatten=True)
                    with open(fp, "w", encoding="utf-8") as f:
                        f.write(content)
                    # Write .info for Bambu slicer compatibility
                    if fmt == "json" and hasattr(self, "_write_info_file"):
                        self._write_info_file(fp, os.path.dirname(fp), profile)
                    self._update_status(f"Exported: {os.path.basename(fp)}")
                except (OSError, json.JSONDecodeError) as e:
                    messagebox.showerror(
                        "Export Error",
                        user_error(
                            "Could not save the file.",
                            e,
                            "Check that the destination is writable.",
                        ),
                    )
                    logger.error(f"Export failed for {profile.name}: {e}")
        else:
            # Multiple profiles: choose directory
            out = filedialog.askdirectory(title="Choose Export Directory")
            if out:
                self._do_export(selected, out, flatten=True, fmt=fmt)

    def _on_export_to_slicer(self, name: str, path: str) -> None:
        """Export selected profiles to a slicer's preset directory.

        Args:
            name: Slicer name (e.g., 'BambuStudio')
            path: Path to slicer installation
        """
        panel = self._active_panel()
        if hasattr(panel, "detail"):
            panel.detail._commit_edits()
        selected = panel.get_selected_profiles()
        if not selected:
            messagebox.showinfo(
                "No Selection",
                "Select profiles to export. Click one or more profiles in the list, then try again.",
            )
            return

        base = SlicerDetector.get_export_dir(path)
        is_bambu = "BambuStudio" in name or "OrcaSlicer" in name
        fmt = "json" if is_bambu else "ini"

        if messagebox.askyesno(
            "Export",
            f"Export {len(selected)} profiles to {name}?\n\nDestination: {base}\n\nRestart {name} to see changes.",
        ):
            self._do_export(
                selected,
                base,
                organize=True,
                flatten=True,
                write_info=is_bambu,
                fmt=fmt,
            )

    def _on_install_to_slicer(self, slicer_name: str, slicer_path: str) -> None:
        """Export selected profiles directly into a slicer's user preset directory.

        Args:
            slicer_name: Name of slicer
            slicer_path: Path to slicer installation
        """
        panel = self._active_panel()
        if hasattr(panel, "detail"):
            panel.detail._commit_edits()
        selected = panel.get_selected_profiles()
        if not selected:
            messagebox.showinfo(
                "No Selection",
                "Select profiles to export. Click one or more profiles in the list, then try again.",
            )
            return

        if not self._warn_missing_conversion_keys(selected):
            return

        export_base = SlicerDetector.get_export_dir(slicer_path)
        count = len(selected)
        profiles_word = "profile" if count == 1 else "profiles"

        # Build descriptive summary
        names = [profile.name for profile in selected[:3]]
        summary = ", ".join(names)
        if count > 3:
            summary += f", and {count - 3} more"

        if not messagebox.askyesno(
            f"Export to {slicer_name}",
            f"Export {count} {profiles_word} to {slicer_name}?\n\n"
            f"{summary}\n\n"
            f"Destination: {export_base}\n\n"
            f"Profiles will be organized into subfolders by type\n"
            f"(process/, filament/) and will appear in {slicer_name}\n"
            f"after restarting it.",
        ):
            return

        is_bambu = "BambuStudio" in slicer_name or "OrcaSlicer" in slicer_name
        fmt = "json" if is_bambu else "ini"
        exported, errors = self._export_profiles_batch(
            selected,
            export_base,
            organize=True,
            flatten=True,
            write_info=is_bambu,
            fmt=fmt,
        )
        self._show_export_result(exported, errors, export_base, quiet=True)
        profiles_word = "profile" if exported == 1 else "profiles"
        if errors:
            msg = (
                f"Exported {exported} of {count} {profiles_word} to {slicer_name} "
                f"({len(errors)} failed). Restart {slicer_name} to see them."
            )
        else:
            msg = (
                f"Exported {exported} {profiles_word} to {slicer_name}. "
                f"Restart {slicer_name} to see them."
            )
        self._update_status(msg)
        messagebox.showinfo(f"Exported to {slicer_name}", msg)

    def _do_export(
        self,
        profiles: list[Profile],
        out_dir: str,
        organize: bool = False,
        flatten: bool = False,
        quiet: bool = False,
        write_info: bool = False,
        fmt: str = "json",
    ) -> None:
        """Export multiple profiles to a directory.

        Args:
            profiles: List of Profile objects to export
            out_dir: Output directory path
            organize: If True, organize into profile_type subdirectories
            flatten: If True, include all inherited settings
            quiet: If True, suppress success messagebox
            write_info: If True, write .info metadata files (BambuStudio/OrcaSlicer)
        """
        exported, errors = self._export_profiles_batch(
            profiles, out_dir, organize, flatten, write_info, fmt
        )
        self._show_export_result(exported, errors, out_dir, quiet)

    def _export_profiles_batch(
        self,
        profiles: list[Profile],
        out_dir: str,
        organize: bool,
        flatten: bool,
        write_info: bool,
        fmt: str = "json",
    ) -> tuple[int, list[str]]:
        """Export profiles and collect success/error counts."""
        exported = 0
        errors = []

        for profile in profiles:
            try:
                fp = self._resolve_export_path(profile, out_dir, organize, fmt=fmt)
                content = (
                    profile.to_ini(flatten=flatten)
                    if fmt == "ini"
                    else profile.to_json(flatten=flatten)
                )
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(content)

                if write_info:
                    self._write_info_file(fp, out_dir, profile)

                exported += 1
            except (OSError, json.JSONDecodeError) as e:
                msg = f"{profile.name}: {e}"
                errors.append(msg)
                logger.error(msg, exc_info=True)

        return exported, errors

    def _resolve_export_path(
        self, profile: Profile, out_dir: str, organize: bool, fmt: str = "json"
    ) -> str:
        """Resolve destination directory and filename with collision handling."""
        safe_type = re.sub(r"[^\w\-]", "_", profile.profile_type)
        dest_dir = (
            os.path.join(out_dir, safe_type)
            if organize and profile.profile_type != "unknown"
            else out_dir
        )
        os.makedirs(dest_dir, exist_ok=True)
        fp = os.path.join(dest_dir, profile.suggested_filename(fmt=fmt))

        # cap iterations to avoid infinite loop on name collisions
        counter = 1
        base, ext = os.path.splitext(fp)
        while os.path.exists(fp) and counter <= MAX_COLLISION_ATTEMPTS:
            fp = f"{base}_{counter}{ext}"
            counter += 1

        if counter > MAX_COLLISION_ATTEMPTS:
            logger.warning(
                f"Max collision attempts reached for {profile.name}; "
                f"skipping to avoid infinite loop"
            )
            raise OSError(f"Could not find unique filename for {profile.name}")

        return fp

    def _show_export_result(
        self,
        exported: int,
        errors: list[str],
        out_dir: str,
        quiet: bool,
    ) -> None:
        """Display export results and update status."""
        if errors:
            total = exported + len(errors)
            messagebox.showwarning(
                "Partial Export",
                f"Exported {exported} of {total} profiles.\n\n" + "\n".join(errors),
            )
        elif not quiet:
            messagebox.showinfo(
                "Export Complete",
                f"Exported {exported} {'profile' if exported == 1 else 'profiles'} to:\n{out_dir}",
            )

        if not quiet:
            self._update_status(
                f"Exported {exported} {'profile' if exported == 1 else 'profiles'}."
            )

    @staticmethod
    def _write_info_file(
        json_path: str,
        export_base: str,
        profile: Profile,
    ) -> None:
        """Write a BambuStudio/OrcaSlicer .info metadata file.

        BambuStudio uses .info files to track profile identity, ownership,
        and sync state. Without one the profile may be ignored.

        Format (INI-style, no section headers):
            sync_info = <empty or 'update'>
            user_id = <numeric user id from export directory>
            setting_id = <unique id>
            base_id = <parent system profile id, or GFSU00 as fallback>
            updated_time = <unix timestamp>

        Args:
            json_path: Path to the exported .json file
            export_base: Base export directory path
            profile: Profile instance
        """
        import time as _time

        info_path = os.path.splitext(json_path)[0] + ".info"

        # Derive user_id from directory structure: .../user/<user_id>/filament/
        user_id = App._extract_user_id(export_base)

        # base_id: try to read from source .info if known
        base_id = ""
        if profile.source_path:
            source_info = os.path.splitext(profile.source_path)[0] + ".info"
            if os.path.isfile(source_info):
                try:
                    with open(source_info, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("base_id"):
                                base_id = line.split("=", 1)[1].strip()
                                break
                except (OSError, KeyError, ValueError):
                    pass

        if not base_id:
            base_id = "GFSU00"

        updated_time = str(int(_time.time()))

        setting_id = SETTING_ID_PREFIX + secrets.token_hex(7)[:14]

        try:
            with open(info_path, "w", encoding="utf-8") as f:
                f.write("sync_info = \n")
                f.write(f"user_id = {user_id}\n")
                f.write(f"setting_id = {setting_id}\n")
                f.write(f"base_id = {base_id}\n")
                f.write(f"updated_time = {updated_time}\n")
        except OSError as e:
            logger.warning("Could not write .info file %s: %s", info_path, e)

    def _on_clear_list(self) -> None:
        panel = self._active_panel()
        if not panel.profiles:
            return
        count = len(panel.profiles)
        if not messagebox.askyesno(
            "Clear List",
            f"Remove all {count} {'profile' if count == 1 else 'profiles'} from the list?",
            parent=self,
        ):
            return
        panel.profiles.clear()
        self._filament_selection = []
        panel._refresh_list()
        panel.detail._show_placeholder()

    def _on_remove(self) -> None:
        self._active_panel().remove_selected()

    def _on_create_from_profile(self) -> None:
        """Create a new profile based on the selected one.

        Opens a dialog to choose a name for the copy, then duplicates
        the source profile's data and removes identity keys.
        """
        panel = self._active_panel()
        selected = panel.get_selected_profiles()
        if len(selected) != 1:
            messagebox.showinfo(
                "Select One", "Select exactly 1 profile to create from."
            )
            return

        source = selected[0]

        # Name dialog
        dlg = tk.Toplevel(self)
        dlg.title("Create from Profile")
        dlg.configure(bg=self.theme.bg)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        dlg.geometry("+%d+%d" % (self.winfo_rootx() + 120, self.winfo_rooty() + 120))

        theme = self.theme
        tk.Label(
            dlg,
            text="New profile name:",
            bg=theme.bg,
            fg=theme.fg,
            font=(UI_FONT, 12),
        ).pack(padx=16, pady=(12, 4), anchor="w")

        name_var = tk.StringVar(value=f"{source.name} (copy)")
        entry = tk.Entry(
            dlg,
            textvariable=name_var,
            bg=theme.bg3,
            fg=theme.fg,
            font=(UI_FONT, 12),
            insertbackground=theme.fg,
            highlightbackground=theme.accent,
            highlightthickness=1,
            width=_ENTRY_CHARS,
        )
        entry.pack(padx=16, pady=(0, 8))
        entry.select_range(0, "end")
        entry.focus_set()

        result = {"name": None}

        def on_ok(event: Optional[tk.Event] = None) -> None:
            """Handle OK button."""
            n = Profile.sanitize_name(name_var.get())
            if n:
                result["name"] = n
                dlg.destroy()

        def on_cancel(event: Optional[tk.Event] = None) -> None:
            """Handle Cancel button."""
            dlg.destroy()

        btn_row = tk.Frame(dlg, bg=theme.bg)
        btn_row.pack(fill="x", padx=16, pady=(0, 12))
        make_btn(
            btn_row,
            "Create",
            on_ok,
            bg=theme.accent2,
            fg=theme.accent_fg,
            font=(UI_FONT, 12, "bold"),
            padx=12,
            pady=4,
        ).pack(side="right")
        make_btn(
            btn_row,
            "Cancel",
            on_cancel,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 12),
            padx=8,
            pady=4,
        ).pack(side="right", padx=(0, 4))

        entry.bind("<Return>", on_ok)
        entry.bind("<Escape>", on_cancel)
        dlg.wait_window()

        if result["name"]:
            # Deep copy the source profile's data
            new_data = deepcopy(
                source.resolved_data if source.resolved_data else source.data
            )
            new_data["name"] = result["name"]

            # Remove identity keys
            for k in (
                "setting_id",
                "updated_time",
                "user_id",
                "instantiation",
                "profile_id",
                "filament_id",
                "inherits",
            ):
                new_data.pop(k, None)

            new_profile = Profile(
                new_data,
                None,
                source.source_type,
                type_hint=source.type_hint,
                origin=source.origin,
            )
            new_profile.modified = True
            panel.add_profiles([new_profile])
            self._update_status(f"Created '{result['name']}' from '{source.name}'.")

    def _on_select_all(self) -> None:
        self._active_panel().select_all()

    def _on_about(self) -> None:
        messagebox.showinfo(
            "About",
            f"{APP_NAME} v{APP_VERSION}\n\n"
            "Make any filament profile work with any printer.\n"
            "Convert profiles between BambuStudio, OrcaSlicer,\n"
            "and PrusaSlicer.",
        )

    def _update_status(self, msg: str = "") -> None:
        """Update status bar text."""
        try:
            self._status_label.configure(text=msg)
        except (tk.TclError, AttributeError):
            pass

    def _update_counts(self) -> None:
        """Update profile count display."""
        try:
            profiles = (
                getattr(self, "filament_panel", None)
                and self.filament_panel.profiles
                or []
            )
            count = len(profiles)
            self._count_label.configure(text=f"{count} profiles")
        except (tk.TclError, AttributeError):
            pass

    def _show_temp_status(self, msg: str, duration: int = 4000) -> None:
        """Show a temporary status message that auto-clears."""
        self._update_status(msg)
        if msg:
            self._safe_after(duration, lambda: self._update_status(""))

    def _on_show_folder(self) -> None:
        """Open the source folder of the currently selected profile."""
        try:
            panel = self._active_panel()
            selected = panel.get_selected_profiles()
            if not selected:
                messagebox.showinfo(
                    "No Selection",
                    "Select a profile to show its folder. Click a profile in the list, then try again.",
                )
                return

            profile = selected[0]
            if not profile.source_path:
                messagebox.showinfo(
                    "No Source File",
                    "This profile was loaded from an online source\n"
                    "and has no local file on disk.",
                )
                return

            folder = os.path.dirname(os.path.abspath(profile.source_path))
            if os.path.isdir(folder):
                # fire-and-forget subprocess is fine here for opening file managers
                if _PLATFORM == "Darwin":
                    subprocess.Popen(["open", "--", folder])
                elif _PLATFORM == "Windows":
                    subprocess.Popen(["explorer", os.path.normpath(folder)])
                else:
                    subprocess.Popen(["xdg-open", "--", folder])
            else:
                messagebox.showinfo(
                    "Folder Not Found", f"Source folder not found:\n{folder}"
                )
        except (OSError, FileNotFoundError) as e:
            messagebox.showerror("Error", f"Could not open folder:\n{e}")
            logger.error(f"Failed to open folder: {e}", exc_info=True)


def _set_macos_app_name() -> None:
    """Set the process name shown in the macOS menu bar."""
    import platform

    if platform.system() != "Darwin":
        return
    try:
        from Foundation import NSBundle

        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info:
            info["CFBundleName"] = APP_NAME
    except ImportError:
        pass


def _acquire_instance_lock() -> "socket.socket | None":
    """Return a bound socket acting as an instance lock, or None if already running."""
    import socket as _socket

    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 0)
    try:
        sock.bind(("127.0.0.1", _INSTANCE_LOCK_PORT))
        return sock
    except OSError:
        sock.close()
        return None


def run() -> None:
    """Launch the application with top-level error handling."""
    lock = _acquire_instance_lock()
    if lock is None:
        import tkinter as _tk
        import tkinter.messagebox as _mb

        _root = _tk.Tk()
        _root.withdraw()
        _mb.showwarning(
            "Already Running",
            "ProfileToolkit is already open.\nCheck your taskbar or dock.",
        )
        _root.destroy()
        return

    _set_macos_app_name()
    # Clean up stale state files from profiles that no longer exist on disk
    try:
        cleanup_stale_state(max_age_days=90)
    except Exception:
        logging.getLogger(__name__).debug("Stale state cleanup failed", exc_info=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler()],
    )
    try:
        app = App()
        app.mainloop()
    except KeyboardInterrupt:
        pass
    except (tk.TclError, RuntimeError):
        logger.critical("Unhandled exception during startup", exc_info=True)
        raise
    finally:
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    run()
