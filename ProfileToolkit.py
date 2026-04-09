#!/usr/bin/env python3
"""
Profile Toolkit v2.2.0
===============================
Cross-platform GUI for unlocking/converting 3D printer slicer profiles.
Mirrors BambuStudio's exact UI layout. OrcaSlicer-inspired teal theme.

No external dependencies — Python standard library + tkinter.

This file is a thin entry point. All code lives in the profile_toolkit/ package.
"""

from profile_toolkit.app import run

if __name__ == "__main__":
    run()
