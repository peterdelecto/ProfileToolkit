#!/bin/bash
# Generate .icns from AppIcon.svg
# Requires: sips (built into macOS) + iconutil (built into macOS)
# Optional: rsvg-convert (brew install librsvg) for SVG->PNG

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SVG="$SCRIPT_DIR/AppIcon.svg"
ICONSET="$SCRIPT_DIR/AppIcon.iconset"
ICNS="$SCRIPT_DIR/AppIcon.icns"

echo "Generating .icns from $SVG..."

mkdir -p "$ICONSET"

# Convert SVG to a large PNG first
if command -v rsvg-convert &> /dev/null; then
    rsvg-convert -w 1024 -h 1024 "$SVG" -o "$SCRIPT_DIR/_icon_1024.png"
elif command -v sips &> /dev/null; then
    # sips can't read SVG natively; try Python as fallback
    python3 -c "
import subprocess, sys
# Use built-in macOS qlmanage as a quick converter
subprocess.run(['qlmanage', '-t', '-s', '1024', '-o', '$SCRIPT_DIR', '$SVG'],
               capture_output=True)
import glob, shutil
pngs = glob.glob('$SCRIPT_DIR/AppIcon.svg.png')
if pngs:
    shutil.move(pngs[0], '$SCRIPT_DIR/_icon_1024.png')
else:
    print('Could not convert SVG. Install librsvg: brew install librsvg')
    sys.exit(1)
" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "ERROR: Could not convert SVG to PNG."
        echo "Install librsvg: brew install librsvg"
        exit 1
    fi
else
    echo "ERROR: No SVG conversion tool found."
    echo "Install librsvg: brew install librsvg"
    exit 1
fi

BASE="$SCRIPT_DIR/_icon_1024.png"

if [ ! -f "$BASE" ]; then
    echo "ERROR: Failed to create base PNG."
    exit 1
fi

# Generate all required sizes for .iconset
sips -z 16 16     "$BASE" --out "$ICONSET/icon_16x16.png"      > /dev/null 2>&1
sips -z 32 32     "$BASE" --out "$ICONSET/icon_16x16@2x.png"   > /dev/null 2>&1
sips -z 32 32     "$BASE" --out "$ICONSET/icon_32x32.png"      > /dev/null 2>&1
sips -z 64 64     "$BASE" --out "$ICONSET/icon_32x32@2x.png"   > /dev/null 2>&1
sips -z 128 128   "$BASE" --out "$ICONSET/icon_128x128.png"    > /dev/null 2>&1
sips -z 256 256   "$BASE" --out "$ICONSET/icon_128x128@2x.png" > /dev/null 2>&1
sips -z 256 256   "$BASE" --out "$ICONSET/icon_256x256.png"    > /dev/null 2>&1
sips -z 512 512   "$BASE" --out "$ICONSET/icon_256x256@2x.png" > /dev/null 2>&1
sips -z 512 512   "$BASE" --out "$ICONSET/icon_512x512.png"    > /dev/null 2>&1
sips -z 1024 1024 "$BASE" --out "$ICONSET/icon_512x512@2x.png" > /dev/null 2>&1

# Build .icns
iconutil -c icns "$ICONSET" -o "$ICNS"

if [ -f "$ICNS" ]; then
    echo "SUCCESS: $ICNS"
    # Copy to .app bundle if it exists
    APP_RESOURCES="$SCRIPT_DIR/../Profile Toolkit.app/Contents/Resources"
    if [ -d "$APP_RESOURCES" ]; then
        cp "$ICNS" "$APP_RESOURCES/AppIcon.icns"
        echo "Copied to .app bundle."
    fi
else
    echo "ERROR: iconutil failed."
fi

# Cleanup
rm -f "$BASE"
rm -rf "$ICONSET"
