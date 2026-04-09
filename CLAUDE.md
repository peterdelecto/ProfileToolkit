# Project Instructions

## Project Facts
- Stack: Python 3.10+, Tkinter GUI, custom theming (no PyQt/Electron)
- Entry: `ProfileToolkit.py` | Build: `python3 build.py` (PyInstaller) | Test: `pytest tests/`
- Deps: `pyproject.toml` via pip | Size: 16 source files
- Key modules: `profile_toolkit/` — app.py, panels.py, widgets.py, theme.py, constants.py, models.py

## Response Contract
- Responses under 150 tokens unless asked for more.
- Code over prose. Show the fix, not a paragraph about it.
- After edits: one line saying what changed. After commands: one line summary.
- When sharing files: link and stop.
- Delta only: return ONLY changed parts, prefixed with what changed in <10 words.

## Mode Detection
- Code request → code only
- Bug → minimal patch only
- Analysis → 5 bullets max
- Verification → VALID/INVALID + one line

## Scope Defaults
- Bug → fix only, no refactoring. Feature → minimal implementation, no gold-plating.
- Prefer modifying existing files over creating new ones.
- Treat given constraints as immutable.
- Section ordering MUST match FILAMENT_LAYOUT in constants.py — never reorder.
- Contrast rules non-negotiable: WCAG AA 4.5:1 minimum. Use theme.py tokens only.
- `_bind_scroll(widget, canvas)` on EVERY widget in scrollable bodies.

## Tool Discipline
- Check context before reading any file.
- Use Grep with targeted patterns, not whole-file reads.
- Read with offset/limit — never >300 lines. panels.py is 3200+ lines.
- Stop after 3 tool calls without progress. Ask the user.
- Do NOT pre-load files, git history, or run broad searches "just in case."

## Compaction
Preserve: code changes, test results, decisions, file paths.
Discard: exploration steps, dead-ends, intermediate reads.
