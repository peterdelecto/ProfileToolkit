# Profile Toolkit

A desktop app for managing 3D printer slicer profiles. Import, inspect, edit, compare, convert, and export filament and process profiles across BambuStudio, OrcaSlicer, and PrusaSlicer.

Built with Python + tkinter. No internet connection required to use local profiles.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)

---

## Screenshots

**Filament profile browser — filter by printer, brand, material, or status**
![Filament tab](screenshots/Filament.png)

**Side-by-side comparison with diff filtering and value copy**
![Compare tab](screenshots/Compare.png)

**Cross-slicer conversion with missing key review**
![Convert tab](screenshots/Convert.png)

**Smart recommendations — flags values outside typical ranges for a given material**
![Recommendations](screenshots/Recommendation.png)

**Online profile import — browse and download from Polymaker, Prusa, colorFabb, and more**
![Online import step 1](screenshots/Import%20from%20Online%201.png)
![Online import step 2](screenshots/Import%20from%20Online%202.png)

---

## Features

**Familiar layout** — Parameters are displayed using BambuStudio's tab and section structure, so nothing is out of place if you're already used to the slicer.

**Filament & process profiles** — Each profile type has its own dedicated tab and layout.

**Filter and search** — The profile list supports text search plus dropdown filters by printer, brand, material, or status (Unlocked / Printer-Locked / Universal).

**Edit inline** — Modify values directly with type-aware validation. Full undo support and change history per profile.

**Batch rename** — Find/replace and pattern tokens across multiple profiles at once.

**Compare side-by-side** — Diff two profiles with view modes: all params, diffs only, or missing keys. Copy values between profiles with undo.

**Convert across slicers** — Map parameters between PrusaSlicer and BambuStudio/OrcaSlicer. Review unmapped keys and fill defaults before exporting.

**Smart recommendations** — Flags values outside typical ranges for a given material across 50+ parameters, with suggested corrections.

**Unlock profiles** — Remove printer-compatibility locks so profiles work across any machine.

**Import from anywhere** — Load JSON, INI, and .3MF files. Pull system presets from installed slicers. Browse and download from online sources: Polymaker, colorFabb, Prusa, OrcaSlicer, BambuStudio, and community databases.

**Export everywhere** — Save as JSON or INI. Install directly into a slicer's preset directory. All exports include full resolved parameters.

---

## Quick Start

```bash
python3 ProfileToolkit.py
```

Requires Python 3.10+ with tkinter.

| Platform | Install tkinter |
|----------|----------------|
| macOS | `brew install python-tk` |
| Ubuntu/Debian | `sudo apt install python3-tk` |
| Windows | Included with the standard Python installer from python.org |

---

## Building a Standalone App

```bash
python3 build.py
```

Produces a self-contained app for the current platform:

| Platform | Output |
|----------|--------|
| macOS | `dist/Profile Toolkit.app` — drag to Applications, or zip to share |
| Windows | `dist/Profile Toolkit/Profile Toolkit.exe` — zip the folder to share |
| Linux | `dist/profile-toolkit/profile-toolkit` — tar/zip the folder to share |

PyInstaller is installed automatically if not present.

---

## Supported Slicers

Auto-detects installed slicers and their profile directories:

- **BambuStudio**
- **OrcaSlicer**
- **PrusaSlicer**

---

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
  about_dialog.py              About dialog
  batch_rename_dialog.py       Batch rename with pattern tokens
  recommendations_dialog.py    Parameter recommendations
  online_import_wizard.py      Online profile browser
  prusa_bundle_wizard.py       PrusaSlicer bundle importer
  providers_pkg/               Online profile source providers
resources/                     App icons (PNG, ICO, ICNS)
screenshots/                   UI screenshots
tests/                         pytest test suites
```

---

## License

MIT
