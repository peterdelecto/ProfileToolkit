"""About dialog — app icon, version, source links, repo links."""

import platform
import sys
import tkinter as tk
import webbrowser
from pathlib import Path

from profile_toolkit.constants import APP_NAME, APP_VERSION, UI_FONT
from profile_toolkit.theme import Theme
from profile_toolkit.widgets import make_btn

# ── Source links shown in the dialog ──────────────────────────────────

_SOURCES = [
    # (section heading, [(label, url), ...])
    (
        "Reference Guides",
        [
            ("Ellis3DP Print Tuning Guide", "https://ellis3dp.com/Print-Tuning-Guide/"),
            (
                "TeachingTech Calibration",
                "https://teachingtechyt.github.io/calibration.html",
            ),
            ("Filament Cheat Sheet", "https://filamentcheatsheet.com/"),
            (
                "Simplify3D Materials Guide",
                "https://www.simplify3d.com/resources/materials-guide/",
            ),
        ],
    ),
    (
        "Slicer Wikis",
        [
            ("OrcaSlicer Wiki", "https://www.orcaslicer.com/wiki/"),
            ("Prusa Knowledge Base", "https://help.prusa3d.com/"),
            ("BambuLab Wiki", "https://wiki.bambulab.com/"),
            ("Polymaker Wiki", "https://wiki.polymaker.com/"),
        ],
    ),
    (
        "Research & Articles",
        [
            (
                "CNC Kitchen — Layer Height vs Strength",
                "https://www.cnckitchen.com/blog/the-influence-of-layer-height-on-the-strength-of-fdm-3d-prints",
            ),
            (
                "CNC Kitchen — Extrusion Temp & Adhesion",
                "https://www.cnckitchen.com/blog/the-influence-of-extrusion-temperature-on-layer-adhesion/",
            ),
        ],
    ),
    (
        "Profile Repositories",
        [
            (
                "BambuStudio Profiles",
                "https://github.com/bambulab/BambuStudio/tree/master/resources/profiles",
            ),
            (
                "OrcaSlicer Profiles",
                "https://github.com/OrcaSlicer/OrcaSlicer/tree/main/resources/profiles",
            ),
            (
                "PrusaSlicer Profiles",
                "https://github.com/prusa3d/PrusaSlicer/tree/master/resources/profiles",
            ),
            (
                "SimplyPrint Profiles DB",
                "https://github.com/SimplyPrint/slicer-profiles-db/tree/main/profiles",
            ),
            (
                "Polymaker Presets",
                "https://github.com/Polymaker3D/Polymaker-Preset/tree/main/preset",
            ),
            ("ColorFabb Profiles", "https://github.com/colorfabb/printer-profiles"),
        ],
    ),
    (
        "Community Profiles",
        [
            (
                "DRIgnazGortngschirl Presets",
                "https://github.com/DRIgnazGortngschirl/bambulab-studio-orca-slicer-presets",
            ),
            (
                "Santanachia Custom Filaments",
                "https://github.com/Santanachia/BambuStudio_CustomFilaments",
            ),
            (
                "dgauche Filament Library",
                "https://github.com/dgauche/BambuStudioFilamentLibrary",
            ),
        ],
    ),
]


def show_about(parent: tk.Tk, theme: Theme) -> None:
    """Open a themed About dialog."""
    dlg = tk.Toplevel(parent)
    dlg.title(f"About {APP_NAME}")
    dlg.configure(bg=theme.bg)
    dlg.resizable(False, True)
    dlg.transient(parent.winfo_toplevel())
    dlg.grab_set()
    # Position near parent
    dlg.geometry(
        "520x620+%d+%d" % (parent.winfo_rootx() + 120, parent.winfo_rooty() + 40)
    )
    dlg.minsize(440, 400)

    # ── Header: icon + name/version ───────────────────────────────────
    header = tk.Frame(dlg, bg=theme.bg)
    header.pack(fill="x", padx=24, pady=(24, 8))

    # Load 64px icon
    icon_img = _load_icon(64)
    if icon_img:
        icon_lbl = tk.Label(header, image=icon_img, bg=theme.bg)
        icon_lbl.image = icon_img  # prevent GC
        icon_lbl.pack(side="left", padx=(0, 16))

    title_frame = tk.Frame(header, bg=theme.bg)
    title_frame.pack(side="left", fill="y")
    tk.Label(
        title_frame,
        text=APP_NAME,
        font=(UI_FONT, 20, "bold"),
        fg=theme.fg,
        bg=theme.bg,
        anchor="w",
    ).pack(anchor="w")
    tk.Label(
        title_frame,
        text=f"Version {APP_VERSION}",
        font=(UI_FONT, 11),
        fg=theme.fg3,
        bg=theme.bg,
        anchor="w",
    ).pack(anchor="w")

    # ── Separator ─────────────────────────────────────────────────────
    tk.Frame(dlg, bg=theme.border, height=1).pack(fill="x", padx=24, pady=(12, 0))

    # ── Scrollable source-link body ───────────────────────────────────
    canvas = tk.Canvas(dlg, bg=theme.bg, highlightthickness=0, bd=0)
    scrollbar = tk.Scrollbar(dlg, orient="vertical", command=canvas.yview)
    body = tk.Frame(canvas, bg=theme.bg)

    body.bind(
        "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.create_window((0, 0), window=body, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True, padx=(24, 0), pady=(8, 0))

    # Mousewheel scrolling (dialog-scoped, not global bind_all)
    _is_mac = platform.system() == "Darwin"

    def _on_wheel(event):
        if _is_mac:
            canvas.yview_scroll(int(-1 * event.delta * 3), "units")
        else:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    canvas.bind("<MouseWheel>", _on_wheel)
    canvas.bind("<Button-4>", lambda e: canvas.yview_scroll(-3, "units"))
    canvas.bind("<Button-5>", lambda e: canvas.yview_scroll(3, "units"))
    dlg.protocol(
        "WM_DELETE_WINDOW",
        lambda: (dlg.grab_release(), dlg.destroy()),
    )

    from profile_toolkit.utils import bind_scroll

    for section_title, links in _SOURCES:
        sec_lbl = tk.Label(
            body,
            text=section_title,
            font=(UI_FONT, 10, "bold"),
            fg=theme.accent,
            bg=theme.bg,
            anchor="w",
        )
        sec_lbl.pack(anchor="w", pady=(12, 2))
        bind_scroll(sec_lbl, canvas)

        for label, url in links:
            link = tk.Label(
                body,
                text=f"  {label}",
                font=(UI_FONT, 9),
                fg=theme.success,
                bg=theme.bg,
                cursor="hand2",
                anchor="w",
            )
            link.pack(anchor="w", pady=1)
            link.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            link.bind("<Enter>", lambda e, w=link: w.configure(fg=theme.accent_hover))
            link.bind("<Leave>", lambda e, w=link: w.configure(fg=theme.success))
            bind_scroll(link, canvas)

    # ── Bottom separator + close button ───────────────────────────────
    bottom = tk.Frame(dlg, bg=theme.bg)
    bottom.pack(fill="x", side="bottom", padx=24, pady=(8, 16))
    tk.Frame(bottom, bg=theme.border, height=1).pack(fill="x", pady=(0, 12))

    close_btn = make_btn(
        bottom,
        "Close",
        lambda: (dlg.grab_release(), dlg.destroy()),
        bg=theme.accent,
        fg=theme.accent_fg,
        font=(UI_FONT, 10, "bold"),
        padx=20,
        pady=6,
    )
    close_btn.pack(anchor="e")

    dlg.focus_force()


def _load_icon(size: int) -> "tk.PhotoImage | None":
    """Load the app icon at *size* px, returning None on failure."""
    try:
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS) / "resources"
        else:
            base = Path(__file__).parent.parent / "resources"

        # Try exact-size first, then fall back to 128 → default 256
        candidates = [
            base / f"AppIcon-{size}.png",
            base / "AppIcon-128.png",
            base / "AppIcon.png",
        ]
        for p in candidates:
            if p.exists():
                return tk.PhotoImage(file=str(p))
    except (tk.TclError, OSError):
        pass
    return None
