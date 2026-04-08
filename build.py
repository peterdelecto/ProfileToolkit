#!/usr/bin/env python3
"""
Build Script for Print Profile Converter
=========================================
Creates a standalone, distributable application bundle.

Usage:
    python3 build.py

This script:
  1. Installs PyInstaller if not present
  2. Builds a single-folder app bundle
  3. On macOS: creates a .app that opens from Finder
  4. On Windows: creates a .exe
  5. On Linux: creates a standalone binary

The resulting app requires NO Python installation on the target machine.

Requirements:
  - Python 3.8+ with tkinter (used only for building, not on target)
  - pip (for installing PyInstaller)
  - Internet connection (first run only, to download PyInstaller)
"""

import subprocess
import sys
import os
import platform
import shutil

APP_NAME = "Print Profile Converter"
SCRIPT = "profile_converter.py"
ICON_MAC = "resources/AppIcon.icns"
ICON_WIN = "resources/AppIcon.ico"

def run(cmd, check=True):
    """Run a command and print it."""
    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0 and check:
        print(f"ERROR: {result.stderr.strip()}")
        sys.exit(1)
    return result

def ensure_pyinstaller():
    """Install PyInstaller if not available."""
    try:
        import PyInstaller
        print(f"  PyInstaller {PyInstaller.__version__} found.")
    except ImportError:
        print("  Installing PyInstaller...")
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("  PyInstaller installed.")

def build_macos():
    """Build a macOS .app bundle."""
    print("\n--- Building macOS .app bundle ---\n")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",           # .app bundle, no terminal window
        "--onedir",             # Single directory (faster startup than onefile)
        "--noconfirm",          # Overwrite previous build
        "--clean",              # Clean build cache
        "--strip",              # Strip debug symbols
    ]

    # Add icon if available
    if os.path.exists(ICON_MAC):
        cmd.extend(["--icon", ICON_MAC])

    # macOS-specific: ensure high-DPI support
    cmd.extend(["--osx-bundle-identifier", "com.printprofileconverter.app"])

    cmd.append(SCRIPT)
    run(cmd)

    # The .app bundle is in dist/
    app_path = os.path.join("dist", f"{APP_NAME}.app")
    if os.path.exists(app_path):
        print(f"\n  SUCCESS: {app_path}")
        print(f"  Size: {get_dir_size(app_path):.1f} MB")
        print(f"\n  To install: drag '{APP_NAME}.app' to your Applications folder.")
        print(f"  To distribute: zip the .app and share it.")
    else:
        print("\n  ERROR: .app bundle not found in dist/")

def build_windows():
    """Build a Windows .exe."""
    print("\n--- Building Windows .exe ---\n")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",           # No console window
        "--onedir",
        "--noconfirm",
        "--clean",
    ]

    if os.path.exists(ICON_WIN):
        cmd.extend(["--icon", ICON_WIN])

    cmd.append(SCRIPT)
    run(cmd)

    exe_path = os.path.join("dist", APP_NAME, f"{APP_NAME}.exe")
    if os.path.exists(exe_path):
        print(f"\n  SUCCESS: {exe_path}")
        print(f"  Folder size: {get_dir_size(os.path.join('dist', APP_NAME)):.1f} MB")
        print(f"\n  To distribute: zip the '{APP_NAME}' folder and share it.")
    else:
        print("\n  ERROR: .exe not found in dist/")

def build_linux():
    """Build a Linux binary."""
    print("\n--- Building Linux binary ---\n")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME.lower().replace(" ", "-"),
        "--windowed",
        "--onedir",
        "--noconfirm",
        "--clean",
    ]

    cmd.append(SCRIPT)
    run(cmd)

    binary_name = APP_NAME.lower().replace(" ", "-")
    binary_path = os.path.join("dist", binary_name, binary_name)
    if os.path.exists(binary_path):
        print(f"\n  SUCCESS: {binary_path}")
        print(f"  Folder size: {get_dir_size(os.path.join('dist', binary_name)):.1f} MB")
        print(f"\n  To distribute: tar/zip the '{binary_name}' folder and share it.")
    else:
        print("\n  ERROR: binary not found in dist/")

def get_dir_size(path):
    """Get total size of a directory in MB."""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total += os.path.getsize(fp)
    return total / (1024 * 1024)

def main():
    print(f"{'=' * 50}")
    print(f"  Building {APP_NAME}")
    print(f"  Platform: {platform.system()} {platform.machine()}")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"{'=' * 50}")

    # Verify source exists
    if not os.path.exists(SCRIPT):
        print(f"\nERROR: {SCRIPT} not found. Run this from the project directory.")
        sys.exit(1)

    # Verify tkinter
    try:
        import tkinter
        print(f"  tkinter: OK")
    except ImportError:
        print("\nERROR: tkinter not found. Install it:")
        if platform.system() == "Darwin":
            print("  brew install python-tk")
        elif platform.system() == "Linux":
            print("  sudo apt install python3-tk")
        else:
            print("  Reinstall Python with tkinter support from python.org")
        sys.exit(1)

    # Install PyInstaller
    ensure_pyinstaller()

    # Build for current platform
    system = platform.system()
    if system == "Darwin":
        build_macos()
    elif system == "Windows":
        build_windows()
    elif system == "Linux":
        build_linux()
    else:
        print(f"\nUnsupported platform: {system}")
        sys.exit(1)

    print(f"\n{'=' * 50}")
    print("  Build complete!")
    print(f"{'=' * 50}\n")

if __name__ == "__main__":
    main()
