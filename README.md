# Profile Toolkit

Cross-platform desktop app for managing 3D printer slicer profiles. Import, inspect, edit, compare, convert, and export profiles across BambuStudio, OrcaSlicer, and PrusaSlicer.

Built with Python + tkinter. No external dependencies required.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

**Import from anywhere** -- Load JSON, INI, and .3MF files. Pull system presets from installed slicers. Browse and download from online profile databases (Polymaker, colorFabb, Prusa, OrcaSlicer, BambuStudio, and community sources).

**Familiar layout** -- Parameters displayed using BambuStudio's tab and section structure. Filament and process profiles each have their own layout.

**Edit inline** -- Modify values directly with type-aware validation. Batch rename with find/replace and pattern tokens. Full undo support and change history.

**Compare side-by-side** -- Diff two or more profiles with filtering (all, diffs only, missing). Copy values between profiles with undo.

**Convert across slicers** -- Map parameters between PrusaSlicer and BambuStudio/OrcaSlicer. Review missing keys and fill defaults before exporting.

**Smart recommendations** -- Flag values outside typical ranges for a given material across 50+ parameters.

**Unlock profiles** -- Remove printer-compatibility locks so profiles work across any machine.

**Export everywhere** -- Save as JSON or INI. Install directly into a slicer's preset directory. All exports include full resolved parameters.

## Quick Start

```bash
python3 ProfileToolkit.py
```

Requires Python 3.10+ with tkinter.

- **macOS**: `brew install python-tk`
- **Ubuntu/Debian**: `sudo apt install python3-tk`

## Building a Standalone App

```bash
python3 build.py
```

Produces:
- **macOS**: `dist/Profile Toolkit.app`
- **Windows**: `dist/Profile Toolkit/Profile Toolkit.exe`
- **Linux**: `dist/profile-toolkit/profile-toolkit`

PyInstaller is installed automatically if not present.

## Project Structure

```
ProfileToolkit.py              Entry point
build.py                       PyInstaller build script
profile_toolkit/
  app.py                       Main window, menus, tabs
  models.py                    Profile, ProfileEngine, PresetIndex, SlicerDetector
  constants.py                 Layout definitions, conversion mappings
  theme.py                     Dark theme with WCAG AA colors
  widgets.py                   Tooltip, ScrollableFrame, ExportDialog
  state.py                     Persistence layer
  detail_panel.py              Profile editing panel
  list_panel.py                Profile list with filtering/sorting
  compare_panel.py             Side-by-side comparison
  convert_panel.py             Cross-slicer conversion
  batch_rename_dialog.py       Batch rename with patterns
  recommendations_dialog.py    Parameter recommendations
  online_import_wizard.py      Online profile browser
  prusa_bundle_wizard.py       PrusaSlicer bundle importer
  providers_pkg/               Online profile source providers
resources/                     App icons (PNG, ICO, ICNS)
tests/
  test_profile.py
```

## Supported Slicers

Auto-detects installed slicers and their profile directories:

- BambuStudio
- OrcaSlicer
- PrusaSlicer

## License

MIT
