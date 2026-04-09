"""
Icon loader for Tkinter — loads PNG icons at the requested size.

Usage in your app:
    from resources.icons.icon_loader import IconSet

    icons = IconSet(size=24)                    # load all 24x24 PNGs
    label = tk.Label(parent, image=icons.printer, bg=theme.bg)

    # Or load individual icons:
    icons = IconSet(size=32)
    btn_cfg = dict(image=icons.save, compound="left")

Available icons:
    icons.printer    — 3D printer
    icons.filament   — filament spool
    icons.process    — stacked layers (process/slicing)
    icons.save       — floppy disk
    icons.search     — magnifying glass
    icons.hourglass  — hourglass timer
    icons.compare    — side-by-side compare
    icons.gear       — settings gear
    icons.clear      — X in circle (clear/reset)
"""

import os
import tkinter as tk
from pathlib import Path

_ICON_DIR = Path(__file__).parent
_ICON_NAMES = ("printer", "filament", "process", "save", "search", "hourglass", "compare", "gear", "clear")


class IconSet:
    """Load a set of PNG icons at a given size.

    Keep a reference to this object (or its attributes) for as long as
    the images are displayed — Tkinter's PhotoImage is garbage-collected
    when the Python reference goes away.
    """

    def __init__(self, size: int = 24, base_dir: str | Path | None = None):
        import sys
        if getattr(sys, 'frozen', False):
            base = Path(sys._MEIPASS) / 'resources' / 'icons'
        else:
            base = Path(base_dir) if base_dir else _ICON_DIR
        folder = base / f"{size}x{size}"

        if not folder.is_dir():
            available = sorted(
                int(d.name.split("x")[0])
                for d in base.iterdir()
                if d.is_dir() and "x" in d.name
            )
            raise FileNotFoundError(
                f"No icons at size {size}. Available: {available}. "
                f"Run generate_pngs.py --sizes {size}"
            )

        self._images: dict[str, tk.PhotoImage] = {}
        for name in _ICON_NAMES:
            png = folder / f"{name}.png"
            if png.exists():
                img = tk.PhotoImage(file=str(png))
                self._images[name] = img
                setattr(self, name, img)

    def get(self, name: str) -> tk.PhotoImage | None:
        """Get an icon by name, or None if not found."""
        return self._images.get(name)

    def names(self) -> list[str]:
        """Return list of loaded icon names."""
        return list(self._images.keys())
