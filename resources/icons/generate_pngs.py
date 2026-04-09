#!/usr/bin/env python3
"""Convert SVG icons to PNG at multiple sizes for Tkinter use.

Requires: pip install cairosvg pillow

Usage:
    python generate_pngs.py              # Generate all sizes
    python generate_pngs.py --sizes 16 24 32  # Specific sizes only
"""

import argparse
import os
import sys
from pathlib import Path

try:
    import cairosvg
except ImportError:
    print("ERROR: cairosvg not installed. Run: pip install cairosvg")
    sys.exit(1)

ICONS = ["printer", "filament", "process", "save", "search", "hourglass", "compare", "gear", "clear"]
DEFAULT_SIZES = [16, 20, 24, 32, 48, 64]


def generate(sizes=None):
    sizes = sizes or DEFAULT_SIZES
    script_dir = Path(__file__).parent

    for size in sizes:
        out_dir = script_dir / f"{size}x{size}"
        out_dir.mkdir(exist_ok=True)

        for name in ICONS:
            svg_path = script_dir / f"{name}.svg"
            if not svg_path.exists():
                print(f"  SKIP {name}.svg (not found)")
                continue

            png_path = out_dir / f"{name}.png"
            cairosvg.svg2png(
                url=str(svg_path),
                write_to=str(png_path),
                output_width=size,
                output_height=size,
            )
            print(f"  {png_path.relative_to(script_dir)}")

    print(f"\nDone — generated {len(sizes) * len(ICONS)} PNGs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate PNG icons from SVG sources")
    parser.add_argument(
        "--sizes", nargs="+", type=int, default=DEFAULT_SIZES,
        help=f"Icon sizes to generate (default: {DEFAULT_SIZES})"
    )
    args = parser.parse_args()
    generate(args.sizes)
