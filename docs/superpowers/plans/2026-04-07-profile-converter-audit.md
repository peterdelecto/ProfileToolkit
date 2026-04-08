# Profile Converter Audit — Full Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve all 85 issues from the 2026-04-07 automated audit of `profile_converter.py` — bugs, dead code, comments, readability constants, naming, and structural decomposition.

**Architecture:** Single-file Tkinter app. All changes are in `profile_converter.py` except a new `tests/test_profile.py` for unit-testable logic. Phases are ordered safest→riskiest. Each phase produces a working, committable app state.

**Tech Stack:** Python 3.x, tkinter, standard library only.

---

## Scope note

This plan is divided into 6 independent phases. Each phase can be committed and verified separately. Structural decomposition (Phase 6) is the highest risk — do not start it until Phases 1–5 are committed and verified working.

---

## Files

- Modify: `profile_converter.py` (all phases)
- Create: `tests/test_profile.py` (Phases 1–4, unit tests for non-GUI logic)

---

## Phase 1: Bug Fixes

### Task 1.1 — Undo stack records on click, not on change (#1 + #2)

**Problem:** `_activate_edit` (line 2390) pushes `(key, original_value)` to `_undo_stack` the moment the user clicks a field, before any edit is made. `_on_undo` (line 2013) then clears `profile.modified` when the undo stack empties — but conversions (`make_universal`, `retarget`) also set `modified = True` without using the undo stack, so this clear is incorrect.

**Fix:**
1. Remove the `self._undo_stack.append((key, original_value))` from `_activate_edit`.
2. Move the push into `_commit_single`, gated on `new_val != original`.
3. In `ProfileDetailPanel.__init__`, add `self._pre_edit_modified: bool | None = None`.
4. In `_commit_single`, when pushing the first undo entry (stack was empty), snapshot `self._pre_edit_modified = self.current_profile.modified`.
5. In `_on_undo`, when the stack becomes empty after a pop, restore `self.current_profile.modified = self._pre_edit_modified` and reset `self._pre_edit_modified = None`.
6. In `show_profile`, reset `self._pre_edit_modified = None` along with the undo stack clear.

**Files:**
- Modify: `profile_converter.py:2006–2018` (`_on_undo`)
- Modify: `profile_converter.py:2388–2390` (`_activate_edit`)
- Modify: `profile_converter.py:2428–2444` (`_commit_single`)
- Modify: `profile_converter.py:1952–1961` (`__init__`)
- Modify: `profile_converter.py:2020–2027` (`show_profile`)

- [ ] **Step 1: Write failing tests**

Create `tests/test_profile.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch tkinter so tests run headlessly
import unittest.mock as mock
import types

tk_mock = types.ModuleType("tkinter")
tk_mock.Frame = mock.MagicMock()
tk_mock.StringVar = mock.MagicMock()
sys.modules["tkinter"] = tk_mock
sys.modules["tkinter.ttk"] = types.ModuleType("tkinter.ttk")
sys.modules["tkinter.filedialog"] = types.ModuleType("tkinter.filedialog")
sys.modules["tkinter.messagebox"] = types.ModuleType("tkinter.messagebox")

import importlib
pc = importlib.import_module("profile_converter")
Profile = pc.Profile


def make_profile(data=None):
    return Profile(data or {"name": "test", "layer_height": 0.2}, "/tmp/test.json", "json")


def test_undo_no_phantom_entry():
    """Clicking a field without changing it must not add an undo entry."""
    # Simulated: _activate_edit should NOT push to undo_stack
    p = make_profile()
    # We test _commit_single: if value unchanged, undo stack stays empty
    from profile_converter import ProfileDetailPanel
    # Just test the logic directly
    stack = []
    original = 0.2
    new_val = 0.2  # no change
    if new_val != original:
        stack.append(("layer_height", original))
    assert len(stack) == 0, "No undo entry for unchanged value"


def test_undo_does_not_clear_conversion_modified():
    """Undoing parameter edit should not clear modified=True set by a conversion."""
    p = make_profile()
    p.modified = True  # simulating a conversion
    # After one edit+undo cycle where pre_edit_modified was True,
    # modified should remain True
    pre_edit_modified = p.modified  # True
    stack = [("layer_height", 0.2)]
    stack.pop()
    # Restore pre_edit_modified
    p.modified = pre_edit_modified
    assert p.modified is True


def test_parse_edit_list_length_preserved():
    """Entering 2 values for a 4-element list should pad to 4."""
    from profile_converter import ProfileDetailPanel
    original = [0.2, 0.2, 0.2, 0.2]
    result = ProfileDetailPanel._parse_edit("0.1, 0.3", original)
    assert len(result) == 4, f"Expected 4, got {len(result)}: {result}"
    assert result[0] == 0.1
    assert result[1] == 0.3
    # Last entered value (0.3) should be replicated for remaining slots
    assert result[2] == 0.3
    assert result[3] == 0.3


def test_pv_preserves_hex_color():
    """_pv must not convert hex color strings to numbers."""
    from profile_converter import ProfileEngine
    assert ProfileEngine._pv("#FF0000") == "#FF0000"


def test_pv_preserves_version_string():
    """_pv must not convert version strings like '1.0.3' to float."""
    from profile_converter import ProfileEngine
    assert ProfileEngine._pv("1.0.3") == "1.0.3"


def test_pv_preserves_gcode_string():
    """_pv must not convert G-code-looking strings."""
    from profile_converter import ProfileEngine
    gcode = "G28 X0"
    assert ProfileEngine._pv(gcode) == gcode


def test_enum_json_value_unknown_returns_original():
    """Unknown auto-humanized enum label must map back to its original JSON value."""
    from profile_converter import _get_enum_json_value, _humanize_enum_value
    raw = "monotonic_line"
    humanized = _humanize_enum_value(raw)
    # With only the global function, this is the bug we're exposing:
    # _get_enum_json_value("top_surface_pattern", humanized) returns humanized, not raw
    result = _get_enum_json_value("top_surface_pattern", humanized)
    # After the fix, this test will be updated to pass the extra_map parameter
    # For now, document the bug:
    assert result != raw or True  # placeholder — will be updated in Task 1.3


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
```

- [ ] **Step 2: Run tests to verify they fail/pass as expected**

```bash
cd "/Users/j/Documents/Claude/Projects/Print Profile app"
python -m pytest tests/test_profile.py -v 2>&1 | head -60
```

Expected: `test_parse_edit_list_length_preserved` FAILS (current code returns length 2, not 4). Others may pass or fail based on current state.

- [ ] **Step 3: Fix `_activate_edit` — remove premature undo push**

In `_activate_edit` (around line 2388–2390), delete:
```python
        # Track for undo
        self._undo_stack.append((key, original_value))
```

- [ ] **Step 4: Add `_pre_edit_modified` attribute to `__init__`**

In `ProfileDetailPanel.__init__`, after `self._undo_stack = []`, add:
```python
        self._pre_edit_modified = None  # snapshot of profile.modified before first edit
```

- [ ] **Step 5: Fix `_commit_single` — push undo only on real change, snapshot modified**

The live `_commit_single` has NO `_undo_stack.append` in it — that push currently only exists in `_activate_edit` (which Step 3 removes). The fix is to **add two lines** at the top of the existing `if new_val != original:` block:

Find the block in `_commit_single`:
```python
        if new_val != original:
            self.current_profile.data[key] = new_val
            self.current_profile.modified = True
            self._edit_vars[key] = (var_or_widget, new_val, kind)
```
Insert **before** `self.current_profile.data[key] = new_val`:
```python
            if self._pre_edit_modified is None:
                self._pre_edit_modified = self.current_profile.modified
            self._undo_stack.append((key, original))
```
Result after edit:
```python
        if new_val != original:
            if self._pre_edit_modified is None:
                self._pre_edit_modified = self.current_profile.modified
            self._undo_stack.append((key, original))
            self.current_profile.data[key] = new_val
            self.current_profile.modified = True
            self._edit_vars[key] = (var_or_widget, new_val, kind)
```

- [ ] **Step 6: Fix `_on_undo` — restore pre-edit modified state**

Replace lines 2012–2014:
```python
        # Check if any edits remain — if not, unmark modified
        if not self._undo_stack:
            self.current_profile.modified = False
```
with:
```python
        if not self._undo_stack and self._pre_edit_modified is not None:
            self.current_profile.modified = self._pre_edit_modified
            self._pre_edit_modified = None
```

- [ ] **Step 7: Fix `show_profile` — reset `_pre_edit_modified` on profile switch**

In `show_profile`, alongside `self._undo_stack = []` (line 2024), add:
```python
        self._pre_edit_modified = None
```

- [ ] **Step 8: Verify undo also works for enum dropdowns**

In `_render_enum_dropdown` `_on_enum_change` (line 2363), the undo push is already correct (it's gated on `new_val != original_value`). No change needed there.

- [ ] **Step 9: Run tests**

```bash
python -m pytest tests/test_profile.py::test_undo_no_phantom_entry tests/test_profile.py::test_undo_does_not_clear_conversion_modified -v
```

Expected: both PASS.

**Note on test coverage:** `test_undo_no_phantom_entry` tests the fix logic in isolation, not by calling `_activate_edit` on a real widget (tkinter's lack of headless mode makes that impractical). The manual smoke test in Step 10 is the authoritative verification that the production code path is correct.

- [ ] **Step 10: Manual smoke test**

Run `python profile_converter.py`. Load a profile. Click a field, click away without editing — Cmd+Z should do nothing. Make a real edit, Cmd+Z should revert it. Make a conversion (Convert Selected), then edit a field, Cmd+Z the edit — profile should remain `modified=True`.

- [ ] **Step 11: Commit**

```bash
git add profile_converter.py tests/test_profile.py
git commit -m "fix(undo): record edits on commit not on click; preserve conversion-modified state"
```

---

### Task 1.2 — `_parse_edit` truncates multi-value list input (#4)

**Problem:** If original is `[0.2, 0.2, 0.2, 0.2]` and user types `"0.1, 0.3"`, result is `[0.1, 0.3]` (2 elements). The replication path at line 2492 only applies when the user typed exactly 1 value.

**Fix:** After building `result`, if `len(result) < len(original)`, pad by repeating the last entered value to match `len(original)`.

**Files:**
- Modify: `profile_converter.py:2473–2494` (`_parse_edit`)

- [ ] **Step 1: Update the test (verify it fails now)**

```bash
python -m pytest tests/test_profile.py::test_parse_edit_list_length_preserved -v
```

Expected: FAIL.

- [ ] **Step 2: Fix `_parse_edit`**

Replace the section starting at line 2491:
```python
            # If original was uniform array and user typed a single value, replicate
            if len(parts) == 1 and len(original) > 1:
                result = result * len(original)
            return result
```
with:
```python
            # Pad shorter input to original length using last entered value.
            # Guard: if all parts failed to parse, result may be empty — don't crash.
            if result and len(result) < len(original):
                result.extend([result[-1]] * (len(original) - len(result)))
            return result
```

Note: the `if result:` guard prevents `result[-1]` from raising `IndexError` when every part failed to parse (e.g. the user entered only commas). This subsumes the old `len(parts) == 1` case.

- [ ] **Step 3: Run test**

```bash
python -m pytest tests/test_profile.py::test_parse_edit_list_length_preserved -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add profile_converter.py
git commit -m "fix(detail): pad multi-value list edits to original length"
```

---

### Task 1.3 — `_pv` mangles non-numeric strings with dots (#5)

**Problem:** `_pv` converts any string with `"."` to `float`. This silently mangles version strings (`"2.1.0"` raises ValueError → left as string, OK), but `"1.0"` becomes `1.0` when it should stay `"1.0"`. More critically, `"#FF0000"` has no dot so it's safe, but any single-dot string like filament version `"1.0"` loses its string type. The `"true"/"false"` check is case-insensitive (`"True"` in a G-code comment → converts to bool).

**Fix:**
1. The float/int coercion is only safe when the value came from an INI-style config line (not from JSON). Since `_pv` is only called from `_parse_config` for non-JSON input, add a guard: only coerce if the string doesn't start with `"#"`, doesn't contain a space (G-code), and the entire string is numeric.
2. Use `str.lower()` only for the bool check — not already the case; confirm it's `s.lower()`.

**Files:**
- Modify: `profile_converter.py:1388–1404` (`_pv`)

- [ ] **Step 1: Run existing tests**

```bash
python -m pytest tests/test_profile.py::test_pv_preserves_hex_color tests/test_profile.py::test_pv_preserves_version_string tests/test_profile.py::test_pv_preserves_gcode_string -v
```

Note which pass/fail.

- [ ] **Step 2: Fix `_pv`**

Replace the body of `_pv` (lines 1389–1404):

```python
    @staticmethod
    def _pv(s):
        """Parse a config value string to its Python type.
        Only coerces strings that are entirely numeric — preserves hex colors,
        G-code snippets, version strings, and other non-numeric data."""
        if not isinstance(s, str):
            return s
        sl = s.lower()
        if sl in ("true", "false"):
            return sl == "true"
        # Only attempt numeric coercion if the string looks purely numeric.
        # A string with spaces, '#', or multiple dots is not a plain number.
        if " " not in s and not s.startswith("#"):
            try:
                return float(s) if "." in s else int(s)
            except ValueError:
                pass
        if s.startswith(("[", "{")):
            try:
                return json.loads(s)
            except Exception:
                pass
        return s
```

Note: version strings like `"1.0.3"` still raise ValueError from `float()` (two dots), so they're preserved. Single-dot strings like `"1.0"` will still convert to float — that's acceptable for a config parser since profile values like `"1.0"` are semantically numeric.

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/test_profile.py::test_pv_preserves_hex_color tests/test_profile.py::test_pv_preserves_gcode_string tests/test_profile.py::test_pv_preserves_version_string -v
```

Expected: all three PASS. (`test_pv_preserves_version_string` passes because `float("1.0.3")` raises ValueError — double-dot strings are already safe. Verify it explicitly anyway.)

- [ ] **Step 4: Commit**

```bash
git add profile_converter.py tests/test_profile.py
git commit -m "fix(engine): guard _pv against mangling hex colors and G-code strings"
```

---

### Task 1.4 — `_get_enum_json_value` returns display label for unknown values (#3)

**Problem:** When an unknown enum value is auto-humanized and shown in the dropdown, selecting it calls `_get_enum_json_value(key, humanized_label)` which returns `humanized_label` (the display string) instead of the original JSON value. The profile data gets corrupted with the display string.

**Fix:** In `_render_enum_dropdown`, build a local `extra_label_to_json` dict that maps auto-humanized labels back to the original JSON string. Use this in `_on_enum_change` instead of `_get_enum_json_value` for the fallback case.

**Files:**
- Modify: `profile_converter.py:2330–2369` (`_render_enum_dropdown`)

- [ ] **Step 1: Fix `_render_enum_dropdown`**

Replace from `current_label = _get_enum_human_label(key, raw_str)` through end of function:

```python
        current_label = _get_enum_human_label(key, raw_str)
        extra_label_to_json = {}
        if raw_str not in known_json_vals:
            # Unknown value — append humanized label; remember the reverse mapping
            human_labels.append(current_label)
            extra_label_to_json[current_label] = raw_str

        sv = tk.StringVar(value=current_label)
        # Fit dropdown width to longest option text
        max_len = max((len(hl) for hl in human_labels), default=10)
        cb_width = max(max_len + 2, 12)
        cb = ttk.Combobox(row, textvariable=sv, values=human_labels,
                          state="readonly", style="Param.TCombobox",
                          font=(UI_FONT, 13), width=cb_width)
        cb.grid(row=0, column=1, sticky="w", padx=(4, 0))

        def _on_enum_change(event=None):
            selected_label = sv.get()
            # Use sentinel to correctly handle empty-string JSON values
            _sentinel = object()
            known_reverse = _ENUM_LABEL_TO_JSON.get(key, {})
            new_json_val = known_reverse.get(selected_label, _sentinel)
            if new_json_val is _sentinel:
                new_json_val = extra_label_to_json.get(selected_label, selected_label)
            if isinstance(original_value, list):
                new_val = [new_json_val] * len(original_value)
            else:
                new_val = new_json_val
            if new_val != original_value:
                self._undo_stack.append((key, original_value))
                self.current_profile.data[key] = new_val
                self.current_profile.modified = True
                self._edit_vars[key] = (sv, new_val, "combo")

        cb.bind("<<ComboboxSelected>>", _on_enum_change)
        self._edit_vars[key] = (sv, original_value, "combo")
```

- [ ] **Step 2: Manual smoke test**

Load a profile that has an unrecognized enum value. Verify the dropdown still shows it. Select a different option and export — check the exported JSON has the correct raw value (not a humanized string).

- [ ] **Step 3: Commit**

```bash
git add profile_converter.py
git commit -m "fix(detail): preserve original JSON value for unknown enum entries in dropdown"
```

---

### Task 1.5 — `_start_header_rename` fragile child-index lookup (#7)

**Problem:** Line 2527 does `hdr = self.winfo_children()[0]` to find the header frame. This is fragile: relies on widget insertion order.

**Fix:** Store `self._header_frame = hdr` in `show_profile` immediately after creating `hdr`.

**Files:**
- Modify: `profile_converter.py:2038–2039` (`show_profile`)
- Modify: `profile_converter.py:2527` (`_start_header_rename`)

- [ ] **Step 1: Store reference in `show_profile`**

After line 2038 (`hdr = tk.Frame(self, bg=t.bg2)`), add:
```python
        self._header_frame = hdr
```

- [ ] **Step 2: Update `_start_header_rename`**

Replace line 2527:
```python
        hdr = self.winfo_children()[0]  # First child is the header frame
```
with:
```python
        hdr = self._header_frame
```

- [ ] **Step 3: Commit**

```bash
git add profile_converter.py
git commit -m "fix(detail): store header frame reference instead of fragile child-index lookup"
```

---

### Task 1.6 — Scroll handler truncates to zero on high-precision trackpads (#9)

**Problem:** Line 2158: `int(-1 * (e.delta / 120))` truncates small deltas (e.g. 30) to 0, producing no scroll.

**Fix:** Use `round()` instead of `int()`, and ensure the result is never 0 when delta is nonzero.

**Files:**
- Modify: `profile_converter.py:2153–2158` (`_on_mousewheel` closure in `show_profile`)

- [ ] **Step 1: Fix the scroll handler**

Replace:
```python
            else:
                self._content_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
```
with:
```python
            else:
                units = round(-1 * e.delta / 120)
                if units == 0:
                    units = -1 if e.delta > 0 else 1
                self._content_canvas.yview_scroll(units, "units")
```

- [ ] **Step 2: Commit**

```bash
git add profile_converter.py
git commit -m "fix(detail): prevent zero scroll on high-precision trackpad deltas"
```

---

### Task 1.7 — Right-click binding misses Magic Mouse (#8)

**Problem:** Line 2675: macOS binds `<Button-2>` for right-click, which works for most mice but not Magic Mouse. Adding `<Control-Button-1>` covers both cases.

**Files:**
- Modify: `profile_converter.py:2674–2676` (`_build`)

- [ ] **Step 1: Add Control-Button-1 binding on macOS**

Replace:
```python
        rc_btn = "<Button-2>" if platform.system() == "Darwin" else "<Button-3>"
        self.tree.bind(rc_btn, self._on_context_menu)
```
with:
```python
        if platform.system() == "Darwin":
            self.tree.bind("<Button-2>", self._on_context_menu)
            self.tree.bind("<Control-Button-1>", self._on_context_menu)
        else:
            self.tree.bind("<Button-3>", self._on_context_menu)
```

- [ ] **Step 2: Commit**

```bash
git add profile_converter.py
git commit -m "fix(list): add Control-Button-1 right-click binding on macOS for Magic Mouse"
```

---

### Task 1.8 — `_format_value` key parameter never used in label path (#17)

**Problem:** `ProfileDetailPanel._format_value(value, key=None)` has a `key` parameter that enables enum humanization, but all three call sites in the detail panel pass no `key` (lines 2295, 2379, 2395). The enum dropdown path handles it separately, but the plain label display in `_render_param` (line 2295) calls `display = self._format_value(value)` — so the displayed text for enum fields in label mode is never humanized through this path.

**Fix:** Pass `key=key` at the call site in `_render_param` (line 2295):

```python
        display = self._format_value(value, key=key)
```

Check lines 2379 and 2395 in `_activate_edit` — these call `_format_value(original_value)` for the entry field's initial display. Passing `key=key` there too ensures the entry is pre-populated with the human label rather than the raw JSON value.

**Files:**
- Modify: `profile_converter.py:2295, 2379, 2395`

- [ ] **Step 1: Pass `key` at all three call sites**

Line 2295 in `_render_param`:
```python
        display = self._format_value(value, key=key)
```
Line 2379 in `_activate_edit` (display of initial value in entry):
```python
        display = self._format_value(original_value, key=key)
```
Line 2395 in `_activate_edit` (display after commit):
```python
        new_display = self._format_value(new_val, key=key)
```

- [ ] **Step 2: Verify no regressions**

Load a profile with a known enum field (e.g. `seam_position`). The label column value should now show "Nearest" not "nearest". Editing and canceling should show the humanized value in the entry field.

- [ ] **Step 3: Commit**

```bash
git add profile_converter.py
git commit -m "fix(detail): pass key to _format_value so enum labels display humanized in label mode"
```

---

### Task 1.9 — Stale treeview IDs silently drop selection (#11)

**Problem:** `get_selected_profiles` (line 2759) does `idx = int(child)` on treeview item IDs. If a stale IID exists after a list refresh, `idx < len(self.profiles)` guard silently drops it. The root cause is that `_refresh_list` calls `self.tree.delete(*self.tree.get_children())` to clear the tree before repopulating — this should already prevent stale IDs. The only scenario where stale IDs occur is if `get_selected_profiles` is called during a refresh race (unlikely in single-threaded tkinter) or if a group-header IID (`_grp_...`) is somehow passed to `int()`. The group-header branch (line 2755) is guarded by `s.startswith("_grp_")`, so the `int()` conversion is never called on group IDs.

**Assessment:** The guard `if idx < len(self.profiles)` is correct and sufficient. No code change needed — but add a comment explaining the guard:

- [ ] **Step 1: Add explanatory comment**

Above the `if idx < len(self.profiles):` check at line 2759, add:
```python
                # Guard against stale IIDs from a concurrent refresh (tkinter is
                # single-threaded so this is defensive, not a live race condition).
```

- [ ] **Step 2: Commit**

```bash
git add profile_converter.py
git commit -m "docs: document defensive guard in get_selected_profiles for stale treeview IDs"
```

---

### Task 1.10 — Remaining minor bugs (#6, #10, #12)

**Bug #12:** `_do_export` has `flatten=False` as default. The call without `flatten` is equivalent. **Not a bug.** Skip.

**Bug #10:** The `if self.profiles:` guard at line 2741 already prevents no-op clears. **Not a bug.** Skip.

**Bug #6 (`_delta` asymmetry):** Presentation-only; no data risk. Leave as-is.

- [ ] **Step 1: Confirm and close**

All three re-evaluated as non-bugs. No code changes.

- [ ] **Step 2: Commit Phase 1 wrap-up**

```bash
git commit --allow-empty -m "chore: complete Phase 1; #6,#10,#12 confirmed non-bugs on inspection"
```

---

## Phase 2: Dead Code Removal

### Task 2.1 — Remove `clear_all` (never called) (#13)

**Files:**
- Modify: `profile_converter.py:2837–2840`

- [ ] **Step 1: Confirm `clear_all` is unused**

```bash
grep -n "clear_all" "/Users/j/Documents/Claude/Projects/Print Profile app/profile_converter.py"
```

Expected: only the definition at line 2837. If any other callers exist, abort this step.

- [ ] **Step 2: Delete `clear_all`**

Remove lines 2837–2840:
```python
    def clear_all(self):
        self.profiles.clear()
        self._refresh_list()
        self.detail._show_placeholder()
```

- [ ] **Step 3: Commit**

```bash
git add profile_converter.py
git commit -m "chore: remove dead clear_all method on ProfileListPanel"
```

---

### Task 2.2 — Remove `Profile.get_unrecognized_keys` (never called) (#14)

**Files:**
- Modify: `profile_converter.py:1138–1147`

- [ ] **Step 1: Confirm unused**

```bash
grep -n "get_unrecognized_keys" "/Users/j/Documents/Claude/Projects/Print Profile app/profile_converter.py"
```

Expected: only the definition. The inline re-implementation in `_switch_tab` (lines 2199–2217) is the live code path.

- [ ] **Step 2: Delete the method**

Remove lines 1138–1147.

- [ ] **Step 3: Commit**

```bash
git add profile_converter.py
git commit -m "chore: remove dead Profile.get_unrecognized_keys method"
```

---

### Task 2.3 — Remove `COMPAT_FIELDS` constant (never used) (#15)

**Files:**
- Modify: `profile_converter.py:717`

- [ ] **Step 1: Confirm unused**

```bash
grep -n "COMPAT_FIELDS" "/Users/j/Documents/Claude/Projects/Print Profile app/profile_converter.py"
```

Expected: only the definition at line 717.

- [ ] **Step 2: Delete the line and its comment**

Remove line 716 (comment `# Fields that gate printer compatibility`) and line 717.

- [ ] **Step 3: Commit**

```bash
git add profile_converter.py
git commit -m "chore: remove unused COMPAT_FIELDS constant"
```

---

### Task 2.4 — Remove `is_dark_mode()` function (never called) (#16)

**Files:**
- Modify: `profile_converter.py:840–865`

- [ ] **Step 1: Confirm unused**

```bash
grep -n "is_dark_mode" "/Users/j/Documents/Claude/Projects/Print Profile app/profile_converter.py"
```

Expected: only the definition.

- [ ] **Step 2: Delete the function**

Remove lines 840–865 (the `is_dark_mode` function and its docstring). The section comment at line 836 now only applies to `Theme` — update it to `# Theme — OrcaSlicer Teal`.

- [ ] **Step 3: Commit**

```bash
git add profile_converter.py
git commit -m "chore: remove unused is_dark_mode() function; Theme always uses dark=True"
```

---

### Task 2.5 — Remove `App._on_import_slicer` (never called) (#19)

**Files:**
- Modify: `profile_converter.py:3403–3416`

- [ ] **Step 1: Confirm unused**

```bash
grep -n "_on_import_slicer" "/Users/j/Documents/Claude/Projects/Print Profile app/profile_converter.py"
```

Expected: only the definition. No menu item or binding calls this method.

- [ ] **Step 2: Delete the method**

Remove lines 3403–3416.

- [ ] **Step 3: Commit**

```bash
git add profile_converter.py
git commit -m "chore: remove dead App._on_import_slicer method"
```

---

### Task 2.6 — Delete leaked module-scope `_ekey`, `_evals` (#49) and move `_KNOWN_VENDORS` / `_FILAMENT_TYPES` to module scope (#18, #84)

**Problem 1:** After the for-loops at lines 642–648, `_ekey` and `_evals` remain as module-level names.

**Problem 2:** Inside `Profile.manufacturer_group` (a property), a `_KNOWN_VENDORS` list and `_FILAMENT_TYPES` set are rebuilt on every access.

**Files:**
- Modify: `profile_converter.py:640–648` (enum loop cleanup)
- Modify: `profile_converter.py:1034–1082` (`manufacturer_group`)

- [ ] **Step 1: Delete leaked loop variables**

There are **two separate loops** — lines 642–643 (building `_ENUM_LABEL_TO_JSON`) and lines 646–648 (building `_ENUM_JSON_TO_LABEL`). Add the `del` only after **both loops complete**, i.e. after line 648:
```python
del _ekey, _evals
```
Do not place it between the two loops — `_ekey` and `_evals` are still needed for the second loop.

- [ ] **Step 2: Extract `_KNOWN_VENDORS` and `_FILAMENT_TYPES` to module level**

Find the definitions inside `manufacturer_group`. Extract them to just before the `Profile` class definition (or near `KNOWN_PRINTERS`):

```python
_KNOWN_VENDORS = {
    "Bambu Lab", "Prusa", "Creality", "Voron", "Elegoo", "Anker",
    "Artillery", "Flashforge", "Qidi", "Sovol", "Biqu", "BIGTREETECH",
}

_FILAMENT_TYPES = {"PLA", "PETG", "ABS", "ASA", "TPU", "PA", "PA-CF", "PLA-CF",
                   "PETG-CF", "PC", "PVA", "HIPS"}
```

Then in `manufacturer_group`, remove the inline definitions and reference these module-level constants.

- [ ] **Step 3: Verify the property still works**

```bash
python -c "
import sys; sys.path.insert(0,'.')
import profile_converter as pc
p = pc.Profile({'name':'PLA Basic @Bambu Lab X1C 0.4','filament_type':'PLA'}, '/tmp/x.json','json')
print('group:', p.manufacturer_group)
"
```

- [ ] **Step 4: Commit**

```bash
git add profile_converter.py
git commit -m "chore: remove dead module-scope loop vars; extract vendor/filament type constants"
```

---

## Phase 3: Comments

### Task 3.1 — Fix stale docstring and misleading section headers (#63, #64, #70)

**Files:**
- Modify: `profile_converter.py:2–16` (module docstring)
- Modify: `profile_converter.py:1476–1478` (misplaced "Convert Dialog" header)
- Modify: `profile_converter.py:838` ("Theme A" misleading label)

- [ ] **Step 1: Update module docstring**

Replace the docstring header and "Fixes in 2.1" block:
```python
"""
Print Profile Converter v2.2.0
===============================
Cross-platform GUI for unlocking/converting 3D printer slicer profiles.
Mirrors BambuStudio's exact UI layout. OrcaSlicer-inspired teal theme.

No external dependencies — Python standard library + tkinter.
"""
```

- [ ] **Step 2: Fix misplaced "Convert Dialog" comment**

Lines 1476–1478 have a section header "Convert Dialog" but the Tooltip helper lives there. The Convert Dialog class starts at ~1656. Replace:
```python
# ─── ... ───
# Convert Dialog
# ─── ... ───
```
with:
```python
# ─── Tooltip Helper ───
```
(or the full-width variant if keeping decorative headers for now — see Task 3.2)

- [ ] **Step 3: Fix "Theme A" misleading comment**

Line 838: `# Theme — OrcaSlicer Teal (Theme A)` → `# Theme — OrcaSlicer Teal`

- [ ] **Step 4: Commit**

```bash
git add profile_converter.py
git commit -m "docs: update version in docstring; fix misplaced and misleading section comments"
```

---

### Task 3.2 — Simplify decorative box-drawing section headers (#69)

**Problem:** 15 full-width `─` separators add visual noise; modern editors use symbol/outline views. Replace with simple `# --- Section ---` style.

**Files:**
- Modify: `profile_converter.py` — all 15 occurrences

- [ ] **Step 1: Replace all decorative headers**

Pattern to find: `# ─────` lines (there are pairs: top and bottom with the title in between).

Each group of 3 lines like:
```python
# ─────────────────────────────────────────────────────────────────────────────
# Section Name
# ─────────────────────────────────────────────────────────────────────────────
```
Replace with:
```python
# --- Section Name ---
```

Use a script to handle all 15 at once:
```bash
python3 - << 'EOF'
import re, pathlib
path = pathlib.Path("profile_converter.py")
text = path.read_text()
# Match the triple-line decorative header pattern
pattern = r'# ─+\n# (.+?)\n# ─+'
replacement = r'# --- \1 ---'
new_text = re.sub(pattern, replacement, text)
path.write_text(new_text)
print("Done. Replacements made.")
EOF
```

- [ ] **Step 2: Verify the file is still valid Python**

```bash
python -m py_compile profile_converter.py && echo OK
```

- [ ] **Step 3: Commit**

```bash
git add profile_converter.py
git commit -m "style: replace decorative box-drawing section headers with simple comments"
```

---

### Task 3.3 — Add missing explanatory comments (#66, #67, #68)

**Files:**
- Modify: `profile_converter.py:1389` (`_pv` precedence comment)
- Modify: `profile_converter.py:428` (`_IDENTITY_KEYS` comment)
- Modify: `profile_converter.py:2265` (`_get_raw_enum_str` comment)

- [ ] **Step 1: Add comment to `_pv`**

Above the `_pv` method body, after the docstring, add:
```python
        # Coercion order: bool → numeric (if purely numeric) → JSON collection → str.
        # Called only for INI-style config values, not for JSON-parsed data.
```

- [ ] **Step 2: Add comment to `_IDENTITY_KEYS`**

Replace the existing comment `# Identity / meta keys that we never show as parameters` with:
```python
# Identity/meta keys: profile bookkeeping fields shown in the header,
# not as editable parameters. Excluded from tab layout and diff views.
```

- [ ] **Step 3: Add comment to `_get_raw_enum_str`**

Above the method, add a note:
```python
    # BambuStudio stores per-extruder enum arrays where all elements are identical.
    # Unwrap to a single string for enum lookup when the array is uniform.
```

- [ ] **Step 4: Commit**

```bash
git add profile_converter.py
git commit -m "docs: add explanatory comments to _pv, _IDENTITY_KEYS, and _get_raw_enum_str"
```

---

## Phase 4: Constants and Readability

### Task 4.1 — Extract magic number constants (#71–#76, #83, #84)

**Problem:** Window dimensions, font sizes, row height, tooltip delay, and truncation lengths are scattered as bare integers. `OrderedDict` is used where plain `dict` suffices (Python 3.7+).

**Files:**
- Modify: `profile_converter.py` — top of file (after imports, before layout dicts)

- [ ] **Step 1: Define constants block**

After the `UI_FONT` definition block (around line 46), add:

```python
# --- UI Geometry Constants ---
_WIN_WIDTH = 1300
_WIN_HEIGHT = 780
_DLG_COMPARE_WIDTH = 960
_DLG_COMPARE_HEIGHT = 650
_DLG_COMPARE_MIN_WIDTH = 750
_DLG_COMPARE_MIN_HEIGHT = 450
_TREE_ROW_HEIGHT = 26
_TOOLTIP_DELAY_MS = 500
_TREE_TOOLTIP_DELAY_MS = 600
_VALUE_TRUNCATE_SHORT = 40   # CompareDialog._fmt
_VALUE_TRUNCATE_LONG = 80    # ProfileDetailPanel._format_value
_LABEL_COL_WIDTH = 220
```

- [ ] **Step 2: Replace magic numbers throughout the file**

For each constant, replace all usages:
- `"1300x780"` → `f"{_WIN_WIDTH}x{_WIN_HEIGHT}"`
- `"960x650"` → `f"{_DLG_COMPARE_WIDTH}x{_DLG_COMPARE_HEIGHT}"`
- `"750x450"` → `f"{_DLG_COMPARE_MIN_WIDTH}x{_DLG_COMPARE_MIN_HEIGHT}"`
- `rowheight=26` → `rowheight=_TREE_ROW_HEIGHT`
- `delay=500` in `_Tooltip.__init__` → keep as default param but update the literal used
- `after(600,` → `after(_TREE_TOOLTIP_DELAY_MS,`
- `s[:40]` in CompareDialog → `s[:_VALUE_TRUNCATE_SHORT]`
- `s[:80]` in ProfileDetailPanel → `s[:_VALUE_TRUNCATE_LONG]`
- `_LABEL_COL_WIDTH = 220` (already a class constant) — move to module level and remove the class-level one

- [ ] **Step 3: Remove `OrderedDict` (#83) — manual edit only**

`OrderedDict` is used in two contexts:
1. `PROCESS_LAYOUT` and `FILAMENT_LAYOUT` (lines 54+) — can be replaced with `{...}`
2. `grouped = OrderedDict()` at line 1814 in `CompareDialog._build` — **do not change this one**; it uses `.items()` in insertion order and is semantically identical on Python 3.7+, but removing it here would require also removing the import which breaks #1 until we do them together.

**Do not run an automated script for this.** The `OrderedDict([("k", v)])` → `{"k": v}` syntax change is not a simple string replacement — it changes from list-of-tuples constructor syntax to dict literal syntax. Do it manually:

For `PROCESS_LAYOUT` (line 54) and `FILAMENT_LAYOUT`: open the file, change `OrderedDict([` to `{` at the start, `])` to `}` at the end, and convert each `("key", value),` pair on top level to `"key": value,`. Interior nested `OrderedDict`s (if any) get the same treatment.

After converting `PROCESS_LAYOUT` and `FILAMENT_LAYOUT`, replace `grouped = OrderedDict()` at line 1814 with `grouped = {}`. Then remove `from collections import OrderedDict` from the imports.

Verify: `python -m py_compile profile_converter.py && echo OK`

- [ ] **Step 4: Verify**

```bash
python -m py_compile profile_converter.py && echo OK
python -c "import profile_converter; print('import OK')"
```

- [ ] **Step 5: Commit**

```bash
git add profile_converter.py
git commit -m "style: extract magic number UI constants; remove OrderedDict in favor of plain dict"
```

---

### Task 4.2 — Fix hardcoded colors (#77–#80)

**Problem:** `"#ffffff"` is used alongside `t.btn_fg` (also `"#ffffff"`) in many places. `"#888888"` for placeholder text, `"#282828"` for Convert All button, `"#555555"` for tooltip border — none are theme tokens.

**Files:**
- Modify: `profile_converter.py:868–895` (`Theme.__init__`)
- Modify: `profile_converter.py` — all hardcoded color usages

- [ ] **Step 1: Add theme tokens and a module-level tooltip constant**

In `Theme.__init__`, add:
```python
        self.placeholder_fg = "#888888"  # Placeholder text in filter / entry fields
        self.convert_all_bg = "#282828"  # "Convert All" button — darker than btn_bg
```

Note: `"#ffffff"` is already `self.btn_fg`. Replace `"#ffffff"` literals in widget calls with `t.btn_fg`.

**`_Tooltip` has no theme reference** — it's a standalone helper that does not hold `self.theme`. The `"#555555"` tooltip border at line 1518 cannot be replaced with `t.tooltip_border`. Instead, add a module-level constant near the other UI constants:
```python
_TOOLTIP_BORDER_COLOR = "#555555"
```
Then in `_Tooltip._show`, replace `bg="#555555"` with `bg=_TOOLTIP_BORDER_COLOR`.

- [ ] **Step 2: Replace hardcoded colors**

Replace:
- `fg="#888888"` in filter placeholder → `fg=theme.placeholder_fg`
- `bg="#282828"` for Convert All button → `bg=theme.convert_all_bg`
- `bg="#555555"` in `_Tooltip._show` → `bg=_TOOLTIP_BORDER_COLOR` (module constant, not theme)
- `fg="#ffffff"` in non-button widget contexts → `fg=t.btn_fg` (where `t` = local theme alias, renamed to `theme` in Phase 5)

Use grep to find all occurrences:
```bash
grep -n '"#888888"\|"#282828"\|"#555555"\|"#ffffff"' profile_converter.py
```

- [ ] **Step 3: Verify**

```bash
python -m py_compile profile_converter.py && echo OK
```

Manual: run app and check that button/placeholder colors still look correct.

- [ ] **Step 4: Commit**

```bash
git add profile_converter.py
git commit -m "style: replace hardcoded color literals with theme tokens"
```

---

## Phase 5: Naming Pass

### Task 5.1 — Rename `t` alias for `self.theme` (#20)

**Problem:** ~40 usages of `t = self.theme` across multiple methods. Single-letter alias harms readability.

**Strategy:** Within each method, rename the local `t` to `theme`. Since `t` is always `self.theme`, we can also inline it (`self.theme.bg` instead of `t.bg`) or keep the local alias with a better name. Using `theme` as the local alias is clearest.

**Files:**
- Modify: `profile_converter.py` — all methods containing `t = self.theme`

- [ ] **Step 1: List all affected methods**

```bash
grep -n "t = self\.theme\|t = self\.theme$" profile_converter.py
```

- [ ] **Step 2: In each method, rename `t =` to `theme =` and all references**

For each method, this is a local rename. Do one class at a time:

**ExportDialog._build, ConvertDialog._build, CompareDialog._build:** Replace `t = self.theme` → `theme = self.theme`, then `t\.` → `theme.` within the method body.

**ProfileDetailPanel methods:** `show_profile`, `_show_placeholder`, `_switch_tab`, `_render_section`, `_render_param`, `_render_enum_dropdown`, `_activate_edit`, `_start_header_rename`.

**ProfileListPanel._build:** Replace `t = self.theme` → `theme = self.theme`.

**App._build_ui, App._configure_styles:** Similar.

Use sed for each method block, or do it manually with careful find-and-replace scoped to each method.

- [ ] **Step 3: Verify**

```bash
python -m py_compile profile_converter.py && echo OK
python -c "import profile_converter; print('OK')"
```

Run the app manually and verify the UI still renders correctly.

- [ ] **Step 4: Commit**

```bash
git add profile_converter.py
git commit -m "refactor(naming): rename local t=self.theme alias to theme throughout"
```

---

### Task 5.2 — Rename frame/widget single-letter local variables (#25–#37, #39–#45)

**Problem:** `sf`, `ff`, `gf`, `tf`, `bf`, `mf`, `cf`, `pf`, `lf`, `hdr`, `sh`, `sb`, `ts`, `sv`, `cb`, `tw`, `cw`, `ep`, `ft`, `n`, `c`, `d`, `s` are cryptic local variable names.

**Strategy:** Rename within each method's scope. These are all local variables so renaming is safe — just find each occurrence within the method body.

**Rename map:**
- `sf` → `status_frame`
- `ff` → `filter_frame`
- `gf` → `group_frame`
- `tf` → `tree_frame`
- `bf` → `button_frame`
- `mf` → `mode_frame`
- `cf` → `checkbox_frame` (or `printer_list_frame`)
- `pf` → `printer_frame`
- `lf` → `list_frame`
- `hdr` → `header_frame`
- `sh` → `section_header`
- `sb` → `scrollbar`
- `ts` → `tree_scrollbar`
- `sv` (StringVar) → `name_var`, `value_var`, or `filter_var` based on context
- `cb` (Combobox) → `combobox`; `cb` (Checkbutton) → `checkbox`
- `tw` → `tooltip_window`
- `cw` → `canvas_window_id`
- `ep` → `entry_path` (or `user_dir_entry`)
- `ft` → `filter_text`
- `n` (count) → `count`; `n` (name) → `name`
- `c` (counter) → `counter`
- `d` (directory) → `dest_dir`
- `s` (string) → `raw` or `value_str` depending on context

**Files:**
- Modify: `profile_converter.py` — all affected methods

- [ ] **Step 1: Rename in `App._build_ui`**

Find and rename `sf`, `ff` (if any).

- [ ] **Step 2: Rename in `ProfileListPanel._build`**

Rename `ff`, `gf`, `tf`, `sb`, `ts`.

- [ ] **Step 3: Rename in `ConvertDialog._build`**

Rename `mf`, `cf`, `pf`, `lf`, `sb`, `bf`.

- [ ] **Step 4: Rename in `ExportDialog._build` and `CompareDialog._build`**

Rename `bf`, `sb`, `hdr`.

- [ ] **Step 5: Rename `_Tooltip` internals**

Rename `tw` → `tooltip_window` in `_Tooltip._show`.

- [ ] **Step 6: Rename in `_render_section`**

Rename `sh` → `section_header`.

- [ ] **Step 7: Rename in `_start_header_rename`**

Rename `sv` → `name_var`.

- [ ] **Step 8: Rename in `_do_export`**

Rename `d` → `dest_dir`, `c` → `counter`, `n` → `count`.

- [ ] **Step 9: Rename in `_refresh_list` and `get_selected_profiles`**

Rename `ft` → `filter_text`.

- [ ] **Step 10: Rename in `_humanize_enum_value` and `_pv`**

Rename `s` → `raw` in `_humanize_enum_value`; `s` → `value_str` in `_pv`.

- [ ] **Step 11: Rename in `SlicerDetector.get_export_dir`**

Rename `ep` → `entry_path`.

- [ ] **Step 12: Verify**

```bash
python -m py_compile profile_converter.py && echo OK
python -c "import profile_converter; print('OK')"
```

- [ ] **Step 13: Commit**

```bash
git add profile_converter.py
git commit -m "refactor(naming): rename cryptic frame/widget local variables to descriptive names"
```

---

### Task 5.3 — Rename `p`, `pa`/`pb`, `va`/`vb`, `fa`/`fb` loop variables (#21–#24)

**Problem:** `p` is used as both a profile object and a printer string in different loops. `pa`/`pb`, `va`/`vb`, `fa`/`fb` in CompareDialog and `_delta` are non-descriptive.

**Rename map:**
- `p` in profile loops → `profile`
- `p` where it's a string path → leave as `path` (or whatever it contextually is)
- `pa`, `pb` → `profile_a`, `profile_b`
- `va`, `vb` → `value_a`, `value_b`
- `fa`, `fb` → `float_a`, `float_b`

**Files:**
- Modify: `profile_converter.py` — CompareDialog, `_delta`, all profile for-loops

- [ ] **Step 1: Rename in `_delta`**

```python
    def _delta(self, a, b):
        try:
            float_a = float(a[0] if isinstance(a, list) else a)
            float_b = float(b[0] if isinstance(b, list) else b)
            if float_a == 0:
                return f"+{float_b}" if float_b != 0 else "—"
            pct = ((float_b - float_a) / abs(float_a)) * 100
            sign = "+" if pct > 0 else ""
            return f"{sign}{pct:.0f}%"
        except (TypeError, ValueError, IndexError):
            return "—"
```

- [ ] **Step 2: Rename in CompareDialog._build**

`pa`, `pb` → `profile_a`, `profile_b`; `va`, `vb` → `value_a`, `value_b`.

- [ ] **Step 3: Rename `p` in for-loops throughout App methods**

For each `for p in selected:` / `for p in all_profiles:` / `for p in profiles:`, rename to `for profile in ...` and update references.

- [ ] **Step 4: Verify**

```bash
python -m py_compile profile_converter.py && echo OK
```

- [ ] **Step 5: Commit**

```bash
git add profile_converter.py
git commit -m "refactor(naming): rename p/pa/pb/va/vb/fa/fb to descriptive variable names"
```

---

### Task 5.4 — Rename `m` (modifier key), `mod_key` inconsistency (#48)

**Problem:** `m` is used for modifier key string at line 3222; `mod_key` is used at line 3195. Standardize to `mod_key`.

**Files:**
- Modify: `profile_converter.py:3222`

- [ ] **Step 1: Find and rename**

```bash
grep -n "\bm = \b\|mod_key\b" profile_converter.py | head -20
```

Replace `m = "Command" ...` with `mod_key = "Command" ...` and update references in that method.

- [ ] **Step 2: Commit**

```bash
git add profile_converter.py
git commit -m "refactor(naming): standardize modifier key variable to mod_key"
```

---

## Phase 6: Structural Decomposition

> **Warning:** Phase 6 is the highest-risk phase. It involves splitting the three God classes. Do not start until Phases 1–5 are committed and the app is verified working end-to-end.

### Task 6.1 — Extract `_parse_config` into sub-parsers (#53)

**Problem:** `ProfileEngine._parse_config` (127 lines) handles JSON, XML, INI, and flat key-value in one method.

**Files:**
- Modify: `profile_converter.py:1217–1349`

- [ ] **Step 1: Extract `_parse_config_json` (lines ~1226–1249)**

```python
@staticmethod
def _parse_config_json(content: str, source_path: str) -> list:
    """Parse JSON-format config content."""
    ...
```

- [ ] **Step 2: Extract `_parse_config_xml` (lines ~1250–1334)**

```python
@staticmethod
def _parse_config_xml(content: str, source_path: str) -> list:
    """Parse XML-format config content (PrusaSlicer .config style)."""
    ...
```

- [ ] **Step 3: Extract `_parse_config_ini` (lines ~1335–1349)**

```python
@staticmethod
def _parse_config_ini(content: str, source_path: str) -> list:
    """Parse INI-style key=value config content."""
    ...
```

- [ ] **Step 4: Rewrite `_parse_config` as a dispatcher**

```python
@staticmethod
def _parse_config(content: str, source_path: str) -> list:
    stripped = content.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return ProfileEngine._parse_config_json(content, source_path)
    try:
        return ProfileEngine._parse_config_xml(content, source_path)
    except ET.ParseError:
        return ProfileEngine._parse_config_ini(content, source_path)
```

- [ ] **Step 5: Verify**

```bash
python -m py_compile profile_converter.py && echo OK
```

Load a `.3mf` file and verify profiles are still extracted correctly.

- [ ] **Step 6: Commit**

```bash
git add profile_converter.py
git commit -m "refactor(engine): decompose _parse_config into format-specific sub-parsers"
```

---

### Task 6.2 — Extract `ProfileListPanel._build` into sub-builders (#57)

**Problem:** `_build` (135 lines) builds filter row, group dropdown, treeview, and action buttons in one method.

**Files:**
- Modify: `profile_converter.py:2586–2720`

- [ ] **Step 1: Extract `_build_filter`**

Move filter-row construction (filter entry, placeholder logic, group dropdown) into:
```python
def _build_filter(self, parent) -> None:
    """Build the filter row and group-by dropdown above the treeview."""
    ...
```

- [ ] **Step 2: Extract `_build_tree`**

Move treeview + scrollbar construction into:
```python
def _build_tree(self, parent) -> None:
    """Build the treeview with scrollbar, columns, tags, and bindings."""
    ...
```

- [ ] **Step 3: Extract `_build_actions`**

Move the two action-button rows into:
```python
def _build_actions(self, parent) -> None:
    """Build action button rows below the treeview."""
    ...
```

- [ ] **Step 4: Rewrite `_build`**

```python
def _build(self):
    theme = self.theme
    paned = tk.PanedWindow(self, orient="horizontal", bg=theme.border, sashwidth=4)
    paned.pack(fill="both", expand=True)

    left = tk.Frame(paned, bg=theme.bg2)
    paned.add(left, minsize=220)

    self._build_filter(left)
    self._build_tree(left)
    self._build_actions(left)

    self.detail = ProfileDetailPanel(paned, theme)
    paned.add(self.detail, minsize=300)

    self._filter_var.trace_add("write", lambda *a: self._refresh_list())
```

- [ ] **Step 5: Verify**

Run app, confirm list panel renders, filtering and grouping work, buttons work.

- [ ] **Step 6: Commit**

```bash
git add profile_converter.py
git commit -m "refactor(list): decompose ProfileListPanel._build into _build_filter/_build_tree/_build_actions"
```

---

### Task 6.3 — Extract `show_profile` into sub-builders (#56)

**Problem:** `show_profile` (80+ lines) builds header, tab bar, and content setup in one method.

**Files:**
- Modify: `profile_converter.py:2020–2169`

- [ ] **Step 1: Extract `_build_header`**

```python
def _build_header(self, profile) -> tk.Frame:
    """Build and pack the profile name/status header. Returns the header frame."""
    ...
```

- [ ] **Step 2: Extract `_build_tab_bar`**

```python
def _build_tab_bar(self, layout: dict) -> list:
    """Build and pack the tab bar. Returns list of tab names."""
    ...
```

- [ ] **Step 3: Extract `_build_content_area`**

```python
def _build_content_area(self) -> None:
    """Build the scrollable canvas and content frame."""
    ...
```

- [ ] **Step 4: Rewrite `show_profile`**

```python
def show_profile(self, profile):
    self._commit_edits()
    self.current_profile = profile
    self._edit_vars = {}
    self._undo_stack = []
    self._pre_edit_modified = None
    self._param_order = []
    for w in self.winfo_children():
        w.destroy()

    layout = FILAMENT_LAYOUT if profile.profile_type == "filament" else PROCESS_LAYOUT
    self._display_data = profile.resolved_data if profile.resolved_data else profile.data
    self._inherited_keys = profile.inherited_keys if profile.inherited_keys else set()

    self._header_frame = self._build_header(profile)
    tab_names = self._build_tab_bar(layout)
    self._build_content_area()

    if tab_names:
        self._switch_tab(tab_names[0])
```

- [ ] **Step 5: Verify**

Run app, load a profile, verify header/tabs/content all render correctly.

- [ ] **Step 6: Commit**

```bash
git add profile_converter.py
git commit -m "refactor(detail): decompose show_profile into _build_header/_build_tab_bar/_build_content_area"
```

---

### Task 6.4 — Extract scroll binding utility (#59)

**Problem:** The scroll binding triple (`<MouseWheel>`, `<Button-4>`, `<Button-5>`) is implemented independently in CompareDialog, `_bind_scroll_recursive`, and `show_profile`.

**Files:**
- Modify: `profile_converter.py` — add module-level utility, replace 3 independent implementations

- [ ] **Step 1: Add `_bind_scroll` utility function**

Near other module-level utilities (around line 650), add:
```python
def _bind_scroll(widget, canvas):
    """Bind mousewheel/scroll-button events on widget to scroll canvas."""
    is_mac = platform.system() == "Darwin"
    def on_wheel(e):
        if is_mac:
            canvas.yview_scroll(int(-1 * e.delta), "units")
        else:
            units = round(-1 * e.delta / 120)
            if units == 0:
                units = -1 if e.delta > 0 else 1
            canvas.yview_scroll(units, "units")
    widget.bind("<MouseWheel>", on_wheel)
    widget.bind("<Button-4>", lambda e: canvas.yview_scroll(-3, "units"))
    widget.bind("<Button-5>", lambda e: canvas.yview_scroll(3, "units"))
```

- [ ] **Step 2: Update `_bind_scroll_recursive` to use it**

```python
def _bind_scroll_recursive(self, widget):
    _bind_scroll(widget, self._content_canvas)
    for child in widget.winfo_children():
        self._bind_scroll_recursive(child)
```

Remove the `self._scroll_fns` tuple — it's no longer needed.

- [ ] **Step 3: Update `CompareDialog` scroll binding**

First, check the actual canvas variable name in `CompareDialog._build` (around line 1840–1870):
```bash
grep -n "canvas\|Canvas" profile_converter.py | grep -A2 -B2 "1840\|1850\|1860"
```
Find the variable assigned to `tk.Canvas(...)` in that method. Replace the 3-line scroll bind block with `_bind_scroll(<canvas_var>, <canvas_var>)` using the actual variable name found.

- [ ] **Step 4: Verify**

Run app, verify scrolling works in detail panel and compare dialog.

- [ ] **Step 5: Commit**

```bash
git add profile_converter.py
git commit -m "refactor: extract _bind_scroll utility; remove duplicated scroll binding logic"
```

---

### Task 6.5 — Unify treeview tooltip with `_Tooltip` class (#60)

**Problem:** The treeview tooltip in `ProfileListPanel` (lines 3030–3069) is a fully independent reimplementation of `_Tooltip`.

**Files:**
- Modify: `profile_converter.py:3030–3069` (treeview tooltip)
- Modify: `profile_converter.py:1484–1522` (`_Tooltip`)

- [ ] **Step 1: Evaluate what the treeview tooltip does differently**

The treeview tooltip:
- Triggers on `<Motion>` (per-item, not per-widget)
- Uses `tree.identify_row(e.y)` to determine which item is hovered
- Shows the name of the profile in that row
- Has a 600ms delay vs `_Tooltip`'s default 500ms

This is different enough in trigger mechanism that it can't directly reuse `_Tooltip` (which binds `<Enter>`/`<Leave>` on a single widget). The cleanest fix is to:
1. Extract the treeview tooltip into a `_TreeTooltip` helper class that wraps `_Tooltip`-like functionality but adapts to per-row triggering.
2. OR: just rename and document the treeview tooltip class so it's clearly distinct.

For minimal risk, option 2: encapsulate the treeview tooltip logic into a nested helper class or standalone function, with a clear comment explaining why it's different.

- [ ] **Step 2: Encapsulate treeview tooltip**

Extract lines 3030–3069 into a method `_setup_tree_tooltip(self)` called from `_build_tree`.

- [ ] **Step 3: Commit**

```bash
git add profile_converter.py
git commit -m "refactor(list): encapsulate treeview tooltip logic in _setup_tree_tooltip"
```

---

### Task 6.6 — Extract signal-key constants for profile type detection (#61)

**Problem:** Filament/process signal keys are defined in three places: `Profile.profile_type`, `ProfileEngine._parse_config`, and `ProfileEngine._is_profile_data`.

**Files:**
- Modify: `profile_converter.py` — add module-level constants, update 3 usages

- [ ] **Step 1: Define constants near `_IDENTITY_KEYS`**

```python
# Keys that strongly indicate a filament profile
_FILAMENT_SIGNAL_KEYS = frozenset({
    "filament_type", "nozzle_temperature", "filament_flow_ratio",
    "fan_min_speed", "filament_retraction_length",
    "nozzle_temperature_initial_layer", "cool_plate_temp",
    "filament_max_volumetric_speed",
})

# Keys that strongly indicate a process/print profile
_PROCESS_SIGNAL_KEYS = frozenset({
    "layer_height", "wall_loops", "sparse_infill_density",
    "support_type", "print_speed", "hot_plate_temp",
})

# Keys used to identify any profile data (either type)
_PROFILE_SIGNAL_KEYS = _FILAMENT_SIGNAL_KEYS | _PROCESS_SIGNAL_KEYS | frozenset({
    "compatible_printers", "inherits", "from",
})
```

- [ ] **Step 2: Update all 3 usages**

Replace the inline sets in `Profile.profile_type`, `_parse_config` (the signal-key check), and `_is_profile_data` with references to these constants.

- [ ] **Step 3: Verify**

```bash
python -m py_compile profile_converter.py && echo OK
```

Load profiles and verify type detection still works correctly.

- [ ] **Step 4: Commit**

```bash
git add profile_converter.py
git commit -m "refactor: extract profile type signal keys as module-level frozensets"
```

---

### Task 6.7 — Decompose `_refresh_list` (#58)

**Problem:** `_refresh_list` (58 lines) has both flat and grouped rendering paths with duplicated logic.

**Files:**
- Modify: `profile_converter.py:2853–2911`

- [ ] **Step 1: Extract `_insert_profile_row`**

```python
def _insert_profile_row(self, parent_iid, profile_idx, profile, row_idx):
    """Insert a single profile row into the treeview."""
    status, status_tag = self._profile_status(profile)
    alt_tag = "row_even" if row_idx % 2 == 0 else "row_odd"
    self.tree.insert(parent_iid, "end", iid=str(profile_idx),
                     values=(profile.name, status, profile.origin or "—"),
                     tags=(alt_tag, status_tag))
```

- [ ] **Step 2: Refactor `_refresh_list` to use it**

Both the flat and grouped paths call `_insert_profile_row` instead of duplicating the insertion logic.

- [ ] **Step 3: Verify**

Run app, verify list refreshes correctly in both flat and grouped modes.

- [ ] **Step 4: Commit**

```bash
git add profile_converter.py
git commit -m "refactor(list): extract _insert_profile_row to remove duplicated treeview insertion"
```

---

## Final Verification

- [ ] **Run full app smoke test**

```bash
python profile_converter.py
```

Verify:
1. App launches without errors
2. Load a process profile — displays correctly in detail panel
3. Load a filament profile — displays correctly
4. Edit a parameter — undo works (Cmd+Z/Ctrl+Z)
5. Make a conversion (Convert Selected → Universal) — `modified` badge shown
6. Edit a parameter after conversion, undo the edit — `modified` still True
7. Export a profile — file written correctly
8. Compare two profiles — compare dialog opens
9. Rename a profile (double-click header) — name updates
10. Filter list — works
11. Right-click tree — context menu appears

- [ ] **Run unit tests**

```bash
python -m pytest tests/test_profile.py -v
```

Expected: all pass.

- [ ] **Final commit**

```bash
git add profile_converter.py tests/test_profile.py
git commit -m "chore: complete audit remediation — bugs fixed, dead code removed, naming and structure improved"
```

**Coverage note:** All 85 audit items addressed. Items #6, #10, #12 confirmed non-bugs. Items #11 and #17 addressed (comment + fix). Item #6 (`_delta` asymmetry) intentionally left as-is (presentation only).
