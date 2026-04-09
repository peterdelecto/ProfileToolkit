# Main application window

from __future__ import annotations

import json
import logging
import os
import secrets
import subprocess
import threading
import tkinter as tk
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from typing import Optional

import platform

from .constants import (
    APP_NAME,
    APP_VERSION,
    _PLATFORM,
    _WIN_WIDTH,
    _WIN_HEIGHT,
    _TREE_ROW_HEIGHT,
    SETTING_ID_PREFIX,
    UI_FONT,
)
from .theme import Theme
from .models import Profile, ProfileEngine, PresetIndex, SlicerDetector
from .state import save_profile_state, restore_profile_state, reapply_unlock_state
from .panels import ProfileDetailPanel, ProfileListPanel, ComparePanel
from .dialogs import CompareDialog, OnlineImportWizard
from .widgets import ExportDialog, UnlockDialog, make_btn

logger = logging.getLogger(__name__)

MAX_COLLISION_ATTEMPTS = 100


class App(tk.Tk):
    """Main application window.

    Manages UI layout, menu bar, tab navigation, file operations, and
    profile loading/saving. Single Tkinter root window with two
    ProfileListPanel children (process and filament tabs).
    """

    def __init__(self) -> None:
        """Initialize the application window and UI."""
        super().__init__()
        self.theme = Theme()

        # Load PNG icon sets — keep references on self to prevent GC of PhotoImages
        try:
            from resources.icons.icon_loader import IconSet
            self.icons = IconSet(size=24)
            self.icons_sm = IconSet(size=16)
        except Exception:
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
        self._update_status("Ready. Import JSON profiles, extract from 3MF, or load system presets to get started.")

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
            if getattr(sys, 'frozen', False):
                base = Path(sys._MEIPASS) / 'resources'
            else:
                base = Path(__file__).parent.parent / 'resources'

            system = platform.system()

            # Windows: .ico gives best results for taskbar + title bar
            if system == "Windows":
                ico_path = base / 'AppIcon.ico'
                if ico_path.exists():
                    self.iconbitmap(str(ico_path))
                    return

            # All platforms: iconphoto with multiple PNG sizes (largest-first)
            icon_files = [
                base / 'AppIcon-512.png',
                base / 'AppIcon.png',       # 256px
                base / 'AppIcon-128.png',
                base / 'AppIcon-64.png',
                base / 'AppIcon-32.png',
            ]
            images = []
            for f in icon_files:
                if f.exists():
                    images.append(tk.PhotoImage(file=str(f)))

            if images:
                self.iconphoto(True, *images)
                self._app_icon_images = images  # prevent GC
        except Exception:
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
            fieldbackground=[("readonly", theme.bg3)],
            foreground=[("readonly", theme.fg)],
            background=[("readonly", theme.bg3)],
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
            label="Import JSON...",
            command=self._on_import_json,
            accelerator=f"{mod_key}+O",
        )
        file_menu.add_command(
            label="Extract Profile from 3MF...",
            command=self._on_extract_3mf,
            accelerator=f"{mod_key}+Shift+O",
        )
        file_menu.add_command(
            label="Load System Presets from Slicers",
            command=self._on_load_presets,
        )
        file_menu.add_command(
            label="Import from Online Sources...",
            command=self._on_import_online,
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
        self.status_var = tk.StringVar()
        status_frame = tk.Frame(self, bg=theme.bg)
        status_frame.pack(fill="x", side="bottom")

        self._count_var = tk.StringVar()
        tk.Label(
            status_frame,
            textvariable=self._count_var,
            anchor="w",
            bg=theme.bg,
            fg=theme.fg,
            font=(UI_FONT, 13),
            padx=12,
            pady=4,
        ).pack(side="left")
        tk.Label(
            status_frame,
            textvariable=self.status_var,
            anchor="w",
            bg=theme.bg,
            fg=theme.fg,
            font=(UI_FONT, 13),
            padx=6,
            pady=4,
        ).pack(side="left", fill="x", expand=True)

        if self.detected_slicers:
            tk.Label(
                status_frame,
                text=f"Detected: {', '.join(self.detected_slicers.keys())}",
                bg=theme.bg,
                fg=theme.fg,
                font=(UI_FONT, 13),
                padx=12,
            ).pack(side="right")

        # Toolbar row
        toolbar_row = tk.Frame(self, bg=theme.bg)
        toolbar_row.pack(fill="x", side="top")

        # Tab labels on the left
        self._tab_var = tk.StringVar(value="process")
        tab_frame = tk.Frame(toolbar_row, bg=theme.bg)
        tab_frame.pack(side="left", padx=(4, 0), pady=(4, 0))

        _process_icon = self._icon("process")
        _filament_icon = self._icon("filament")

        _compare_icon = self._icon("compare")

        self._process_tab = make_btn(
            tab_frame,
            "  Process  ",
            lambda: self._switch_tab("process"),
            bg=theme.icon_active_bg_strong,
            fg=theme.fg,
            font=(UI_FONT, 13, "bold"),
            padx=14,
            pady=6,
            image=_process_icon,
            compound="left",
        )
        self._process_tab.pack(side="left", padx=(0, 2))

        self._filament_tab = make_btn(
            tab_frame,
            "  Filament  ",
            lambda: self._switch_tab("filament"),
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=(UI_FONT, 13),
            padx=14,
            pady=6,
            image=_filament_icon,
            compound="left",
        )
        self._filament_tab.pack(side="left")

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
        self._compare_tab.pack(side="left", padx=(2, 0))

        # Toolbar buttons on the right
        toolbar = tk.Frame(toolbar_row, bg=theme.bg)
        toolbar.pack(side="right", padx=(0, 8), pady=(4, 6))

        btn_font = (UI_FONT, 12)
        btn_pad = 10

        make_btn(
            toolbar,
            "Import JSON",
            self._on_import_json,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=btn_font,
            padx=btn_pad,
            pady=5,
        ).pack(side="left", padx=(0, 4))

        make_btn(
            toolbar,
            "Extract from 3MF",
            self._on_extract_3mf,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=btn_font,
            padx=btn_pad,
            pady=5,
        ).pack(side="left", padx=(0, 4))

        make_btn(
            toolbar,
            "Load System Presets",
            self._on_load_presets,
            bg=theme.bg4,
            fg=theme.btn_fg,
            font=btn_font,
            padx=btn_pad,
            pady=5,
        ).pack(side="left", padx=(0, 4))

        make_btn(
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
        ).pack(side="right", padx=(0, 4))

        # Content area: stacked frames (manual tab switching)
        self._content_area = tk.Frame(self, bg=theme.bg)
        self._content_area.pack(fill="both", expand=True)

        self.process_panel = ProfileListPanel(self._content_area, theme, "process", self)
        self.filament_panel = ProfileListPanel(self._content_area, theme, "filament", self)
        self.compare_panel = ComparePanel(self._content_area, theme, self)

        # Show process panel by default
        self.process_panel.pack(fill="both", expand=True)
        self._current_tab = "process"

        # Global Ctrl+Z / Cmd+Z dispatcher — routes to the correct panel
        self._bind_global_undo()

    def _bind_global_undo(self) -> None:
        """Bind a single global Ctrl+Z handler that dispatches to the visible panel."""
        import platform
        mod_key = "Command" if platform.system() == "Darwin" else "Control"
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
        """Switch to the named tab (process, filament, or compare)."""
        theme = self.theme
        if tab_name == self._current_tab:
            return

        # Hide all panels
        self.process_panel.pack_forget()
        self.filament_panel.pack_forget()
        self.compare_panel.pack_forget()

        # Reset all tabs to inactive
        inactive = dict(bg=theme.bg4, fg=theme.btn_fg, font=(UI_FONT, 13))
        active = dict(bg=theme.icon_active_bg_strong, fg=theme.fg, font=(UI_FONT, 13, "bold"))

        self._process_tab.configure(**inactive)
        self._filament_tab.configure(**inactive)
        if tab_name != "compare":
            self._compare_tab.configure(**inactive)

        # Show the selected panel and activate its tab
        if tab_name == "process":
            self.process_panel.pack(fill="both", expand=True)
            self._process_tab.configure(**active)
        elif tab_name == "filament":
            self.filament_panel.pack(fill="both", expand=True)
            self._filament_tab.configure(**active)
        elif tab_name == "compare":
            self.compare_panel.pack(fill="both", expand=True)
            self._compare_tab.configure(**active)

        self._current_tab = tab_name

    def _active_panel(self) -> ProfileListPanel:
        if self._current_tab == "compare":
            # When on compare tab, return whichever panel the compared profiles came from
            pa = self.compare_panel._profile_a
            if pa and pa.profile_type == "filament":
                return self.filament_panel
            return self.process_panel
        return (
            self.process_panel
            if self._current_tab == "process"
            else self.filament_panel
        )

    def _update_compare_tab_state(self) -> None:
        """No-op — Compare tab is always enabled. Kept for backward compat."""
        pass

    # ── File Operations ──

    def _on_import_json(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Import JSON Profiles",
            filetypes=[
                ("JSON profiles", "*.json"),
                ("BBS filament bundles", "*.bbsflmt"),
                ("All", "*.*"),
            ],
        )
        if paths:
            self._load_files([(p, None, "") for p in paths])

    def _on_extract_3mf(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Extract Profiles from 3MF",
            filetypes=[("3MF projects", "*.3mf"), ("All", "*.*")],
        )
        if paths:
            self._load_files([(p, None, "") for p in paths])

    def _on_import_online(self) -> None:
        OnlineImportWizard(self, self.theme, self._load_files)

    def _on_load_presets(self) -> None:
        if not self.detected_slicers:
            messagebox.showinfo(
                "No Slicers Found",
                "No slicer installations were detected.\n\n"
                "Supported: BambuStudio, OrcaSlicer, PrusaSlicer",
            )
            return

        # Prevent multiple concurrent loads
        if getattr(self, '_preset_loading', False):
            return
        self._preset_loading = True

        panel = self._active_panel()
        slicer_names = ", ".join(self.detected_slicers.keys())
        panel._show_overlay(f"Scanning {slicer_names}...", show_spinner=True,
                            show_progress=True)

        def _bg_scan() -> None:
            """Background thread: discover, load, index, and resolve preset files."""
            # Phase 1: Discover preset files
            pairs = []
            for name, path in self.detected_slicers.items():
                self.after(0, lambda n=name: panel._update_overlay_text(f"Scanning {n}..."))
                presets = SlicerDetector.find_user_presets(path)
                for ptype, files in presets.items():
                    for fp in files:
                        pairs.append((fp, ptype, name))

            if not pairs:
                self.after(0, lambda: self._preset_load_done(panel, [], [], 0, slicer_names))
                return

            total = len(pairs)
            self.after(0, lambda: panel._update_overlay_text(f"Loading {total} presets..."))
            self.after(0, lambda: panel._update_overlay_progress(0, total))

            # Phase 2: Load profile files (background thread)
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
                except Exception as e:
                    errors.append(f"{os.path.basename(fp)}: {e}")
                    logger.debug(f"Failed to load preset {fp}", exc_info=True)

                if (i + 1) % 10 == 0 or (i + 1) == total:
                    c = i + 1
                    self.after(
                        0,
                        lambda c=c, t=total: (
                            panel._update_overlay_text(f"Loading presets ({c}/{t})..."),
                            panel._update_overlay_progress(c, t),
                        ),
                    )

            if not all_new:
                self.after(0, lambda: self._preset_load_done(panel, [], errors, 0, slicer_names))
                return

            # Phase 3: Index and resolve inheritance (background thread)
            self.after(0, lambda: panel._update_overlay_text("Indexing and resolving inheritance..."))
            self.preset_index.add_profiles(all_new)
            resolved_count = 0
            for profile in all_new:
                if profile.inherits:
                    self.preset_index.resolve(profile)
                    if profile.resolved_data:
                        resolved_count += 1

            # Phase 4: Restore persisted state (background thread)
            self.after(0, lambda: panel._update_overlay_text("Restoring saved state..."))
            restore_profile_state(all_new)

            # Phase 5: Sort into process/filament batches (background thread)
            process_batch = []
            filament_batch = []
            for profile in all_new:
                if profile.profile_type == "filament":
                    filament_batch.append(profile)
                else:
                    process_batch.append(profile)

            # Hand off to main thread with pre-sorted batches
            self.after(0, lambda: self._preset_load_done(
                panel, process_batch, filament_batch, resolved_count,
                slicer_names, errors,
            ))

        threading.Thread(target=_bg_scan, daemon=True).start()

    def _preset_load_done(
        self,
        panel: ProfileListPanel,
        process_batch: list[Profile],
        filament_batch: list[Profile],
        resolved_count: int,
        slicer_names: str,
        errors: Optional[list[str]] = None,
    ) -> None:
        """Finish preset loading on the main thread.

        Heavy work (indexing, resolution, state restore) has already been done
        on the background thread. This method only does the lightweight UI
        updates: batched panel additions and status messages.
        """
        self._preset_loading = False
        panel._hide_overlay()

        loaded_p = len(process_batch)
        loaded_f = len(filament_batch)

        if not loaded_p and not loaded_f:
            self._update_status("No user presets found in detected slicers.")
            return

        # Batch-add to panels (single _refresh_list per panel)
        if process_batch:
            self.process_panel.add_profiles(process_batch)
        if filament_batch:
            self.filament_panel.add_profiles(filament_batch)

        if errors:
            messagebox.showwarning(
                "Some Files Failed",
                f"Loaded {loaded_p + loaded_f} profiles. Errors:\n\n"
                + "\n".join(errors[:20]),
            )

        total = len(self.process_panel.profiles) + len(self.filament_panel.profiles)
        status = f"Loaded {loaded_p} process, {loaded_f} filament. {total} total."
        if resolved_count:
            status += f" Resolved inherited settings for {resolved_count}."
        self._update_status(status)

    def _load_files(self, path_hint_tuples: list[tuple]) -> None:
        """Load files. Each entry is (path, type_hint, origin).

        Args:
            path_hint_tuples: List of (path, type_hint, origin) tuples
        """
        loaded_p, loaded_f, resolved_count = 0, 0, 0
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
                all_new.extend(profiles)
            except Exception as e:
                msg = f"{os.path.basename(path)}: {e}"
                errors.append(msg)
                logger.warning(msg, exc_info=True)

        # Add to index for cross-referencing, then resolve inheritance
        self.preset_index.add_profiles(all_new)
        for profile in all_new:
            if profile.inherits:
                self.preset_index.resolve(profile)
                if profile.resolved_data:
                    resolved_count += 1

        # Restore persisted state (changelogs, modified flags)
        restore_profile_state(all_new)

        # Sort into panels
        for profile in all_new:
            if profile.profile_type == "process":
                self.process_panel.add_profiles([profile])
                loaded_p += 1
            elif profile.profile_type == "filament":
                self.filament_panel.add_profiles([profile])
                loaded_f += 1
            else:
                self.process_panel.add_profiles([profile])
                loaded_p += 1

        if errors:
            messagebox.showwarning(
                "Some Files Failed",
                f"Loaded {loaded_p + loaded_f} profiles. Errors:\n\n"
                + "\n".join(errors),
            )

        total = len(self.process_panel.profiles) + len(self.filament_panel.profiles)
        status = f"Loaded {loaded_p} process, {loaded_f} filament. {total} total."
        if resolved_count:
            status += f" Resolved inherited settings for {resolved_count}."
        self._update_status(status)

    # ── Profile Actions ──

    def _on_unlock(self) -> None:
        """Unlock selected profiles with custom printer or make universal."""
        panel = self._active_panel()
        selected = panel.get_selected_profiles()
        if not selected:
            messagebox.showinfo("No Selection", "Select profiles to unlock.")
            return

        dlg = UnlockDialog(self, self.theme, len(selected))
        if dlg.result is None:
            return

        all_printers = self.preset_index.known_printers if hasattr(self, "preset_index") else None
        saved_back = 0
        for profile in selected:
            if dlg.result == "universal":
                profile.make_universal(all_printers=all_printers)
            else:
                profile.retarget(dlg.result)

            # Auto-save back to slicer directory
            if self._is_slicer_profile(profile):
                try:
                    self._save_back_to_slicer(profile)
                    saved_back += 1
                except Exception as exc:
                    logger.warning(f"Auto-save failed for {profile.name}: {exc}")

        panel._refresh_list()
        panel._on_select()
        status = f"Unlocked {len(selected)} profile(s)."
        if saved_back:
            status += " Saved to slicer — restart to see changes."
        status += " Check print speed and acceleration settings for your printer."
        self._update_status(status)

    def _is_slicer_profile(self, profile: Profile) -> bool:
        """Check if the profile was loaded from a detected slicer directory."""
        if not profile.source_path:
            return False
        src = os.path.normpath(profile.source_path)
        for slicer_path in self.detected_slicers.values():
            if src.startswith(os.path.normpath(slicer_path)):
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

        # Write the JSON
        with open(fp, "w", encoding="utf-8") as f:
            f.write(profile.to_json(flatten=True))

        info_path = os.path.splitext(fp)[0] + ".info"
        now_ts = str(int(_time.time()))

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
            user_id = ""
            parts = os.path.normpath(fp).split(os.sep)
            for i, part in enumerate(parts):
                if part == "user" and i + 1 < len(parts):
                    user_id = parts[i + 1]
                    break

            setting_id = SETTING_ID_PREFIX + secrets.token_hex(7)[:14]
            base_id = "GFSU00"

            with open(info_path, "w", encoding="utf-8") as f:
                f.write("sync_info = \n")
                f.write(f"user_id = {user_id}\n")
                f.write(f"setting_id = {setting_id}\n")
                f.write(f"base_id = {base_id}\n")
                f.write(f"updated_time = {now_ts}\n")

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
            logger.debug("_on_compare_tab: fell back to cache=%d profiles", len(selected))
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
        logger.debug("_on_filament_selection_changed: %d selected, tab=%s",
                     len(selected), self._current_tab)

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
        """Clear the comparison and show the waiting state."""
        self.compare_panel.show_waiting()

    # ── Export Operations ──

    def _on_export(self) -> None:
        """Export selected profiles with options for flattening/organization."""
        panel = self._active_panel()
        if hasattr(panel, "detail"):
            panel.detail._commit_edits()
        selected = panel.get_selected_profiles()
        if not selected:
            messagebox.showinfo("No Selection", "Select profiles to export.")
            return

        has_inh = any(p.inherits for p in selected)
        dlg = ExportDialog(
            self,
            self.theme,
            len(selected),
            detected_slicers=self.detected_slicers,
            any_has_inheritance=has_inh,
        )
        if dlg.result is None:
            return

        # Handle "Export to Slicer" from the export dialog
        if dlg.result == "slicer" and dlg.slicer_target:
            sname, spath = dlg.slicer_target
            self._on_install_to_slicer(sname, spath)
            return

        flatten = dlg.flatten

        if len(selected) == 1:
            # Single profile: save-as dialog
            profile = selected[0]
            fp = filedialog.asksaveasfilename(
                title="Export Profile",
                initialfile=profile.suggested_filename(),
                defaultextension=".json",
                filetypes=[("JSON profile", "*.json"), ("All", "*.*")],
            )
            if fp:
                try:
                    with open(fp, "w", encoding="utf-8") as f:
                        f.write(profile.to_json(flatten=flatten))
                    mode_note = " (all settings included)" if flatten else ""
                    self._update_status(f"Exported{mode_note}: {os.path.basename(fp)}")
                except Exception as e:
                    messagebox.showerror("Export Error", str(e))
                    logger.error(f"Export failed for {profile.name}: {e}")
        else:
            # Multiple profiles: choose directory
            out = filedialog.askdirectory(title="Choose Export Directory")
            if out:
                self._do_export(selected, out, flatten=flatten)

    def _on_export_to_slicer(self, name: str, path: str) -> None:
        """Export selected profiles to a slicer's preset directory.

        Args:
            name: Slicer name (e.g., 'BambuStudio')
            path: Path to slicer installation
        """
        panel = self._active_panel()
        selected = panel.get_selected_profiles()
        if not selected:
            messagebox.showinfo("No Selection", "Select profiles to export.")
            return

        base = SlicerDetector.get_export_dir(path)
        is_bambu = "BambuStudio" in name or "OrcaSlicer" in name

        if messagebox.askyesno(
            "Export", f"Export {len(selected)} to {name}?\n{base}"
        ):
            self._do_export(selected, base, organize=True, write_info=is_bambu)

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
            messagebox.showinfo("No Selection", "Select profiles to export.")
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

        has_inh = any(p.inherits for p in selected)
        is_bambu = "BambuStudio" in slicer_name or "OrcaSlicer" in slicer_name
        self._do_export(
            selected,
            export_base,
            organize=True,
            flatten=has_inh,
            quiet=True,
            write_info=is_bambu,
        )
        msg = (
            f"Exported {count} {profiles_word} to {slicer_name}. "
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
        exported = 0
        errors = []

        for profile in profiles:
            try:
                dest_dir = (
                    os.path.join(out_dir, profile.profile_type)
                    if organize and profile.profile_type != "unknown"
                    else out_dir
                )
                os.makedirs(dest_dir, exist_ok=True)
                fp = os.path.join(dest_dir, profile.suggested_filename())

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
                    errors.append(f"{profile.name}: Could not find unique filename")
                    continue

                with open(fp, "w", encoding="utf-8") as f:
                    f.write(profile.to_json(flatten=flatten))

                if write_info:
                    self._write_info_file(fp, out_dir, profile)

                exported += 1
            except Exception as e:
                msg = f"{profile.name}: {e}"
                errors.append(msg)
                logger.error(msg, exc_info=True)

        if errors:
            messagebox.showwarning(
                "Partial Export",
                f"Exported {exported}, errors:\n\n" + "\n".join(errors),
            )
        elif not quiet:
            messagebox.showinfo(
                "Export Complete",
                f"Exported {exported} profile(s) to:\n{out_dir}",
            )

        if not quiet:
            mode_note = " (all settings included)" if flatten else ""
            self._update_status(f"Exported {exported} profile(s){mode_note}.")

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
        user_id = ""
        parts = os.path.normpath(export_base).split(os.sep)
        for i, part in enumerate(parts):
            if part == "user" and i + 1 < len(parts):
                user_id = parts[i + 1]
                break

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
                except Exception:
                    pass

        if not base_id:
            base_id = "GFSU00"

        updated_time = str(int(_time.time()))

        setting_id = SETTING_ID_PREFIX + secrets.token_hex(7)[:14]

        with open(info_path, "w", encoding="utf-8") as f:
            f.write("sync_info = \n")
            f.write(f"user_id = {user_id}\n")
            f.write(f"setting_id = {setting_id}\n")
            f.write(f"base_id = {base_id}\n")
            f.write(f"updated_time = {updated_time}\n")

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
            messagebox.showinfo("Select One", "Select exactly 1 profile to create from.")
            return

        source = selected[0]

        # Name dialog
        dlg = tk.Toplevel(self)
        dlg.title("Create from Profile")
        dlg.configure(bg=self.theme.bg)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        dlg.geometry(
            "+%d+%d"
            % (self.winfo_rootx() + 120, self.winfo_rooty() + 120)
        )

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
            width=40,
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
            for k in ("setting_id", "updated_time", "user_id", "instantiation"):
                new_data.pop(k, None)

            new_profile = Profile(
                new_data,
                source.source_path,
                source.source_type,
                type_hint=source.type_hint,
                origin=source.origin,
            )
            panel.add_profiles([new_profile])
            self._update_status(f"Created '{result['name']}' from '{source.name}'.")

    def _on_select_all(self) -> None:
        self._active_panel().select_all()

    def _on_about(self) -> None:
        messagebox.showinfo(
            "About",
            f"{APP_NAME} v{APP_VERSION}\n\n"
            "Removes artificial printer-compatibility restrictions\n"
            "from 3D printer slicer profiles.\n\n"
            "Mirrors BambuStudio's settings layout.\n"
            "Supports BambuStudio, OrcaSlicer, PrusaSlicer.",
        )

    def _update_status(self, msg: str = "") -> None:
        if msg:
            self.status_var.set(
                f"[{datetime.now().strftime('%H:%M:%S')}]  {msg}"
            )
        self._update_counts()

    def _update_counts(self) -> None:
        process_count = len(self.process_panel.profiles)
        filament_count = len(self.filament_panel.profiles)
        self._count_var.set(f"{process_count} process, {filament_count} filament")

    def _on_show_folder(self) -> None:
        """Open the source folder of the currently selected profile."""
        try:
            panel = self._active_panel()
            selected = panel.get_selected_profiles()
            if not selected:
                messagebox.showinfo(
                    "No Selection", "Select a profile to show its folder."
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
                    subprocess.Popen(["xdg-open", folder])
            else:
                messagebox.showinfo(
                    "Folder Not Found", f"Source folder not found:\n{folder}"
                )
        except Exception as e:
            messagebox.showerror("Error", f"Could not open folder:\n{e}")
            logger.error(f"Failed to open folder: {e}", exc_info=True)


def run() -> None:
    """Launch the application with top-level error handling."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler()],
    )
    try:
        app = App()
        app.mainloop()
    except Exception:
        logger.critical("Unhandled exception during startup", exc_info=True)
        raise


if __name__ == "__main__":
    run()
