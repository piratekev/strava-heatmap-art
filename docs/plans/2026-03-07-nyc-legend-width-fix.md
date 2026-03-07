# NYC Legend Width Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the NYC legend bar being too small in the full render by removing the erroneous `TYPOGRAPHY_SCALE` multiplier from the `bar_width` calculation.

**Architecture:** Two-line fix across two files. `bar_width` in `render_legend` should not apply `scale` (TYPOGRAPHY_SCALE) because it is already proportional to canvas width `w`. Update `nyc_config.py` to set `LEGEND_WIDTH_SCALE = 1.0` since `scale` was previously handling part of the sizing. Update the one test that mirrors the old formula.

**Tech Stack:** Python, Pillow, pytest

---

### Task 1: Update the bar_width formula and nyc_config, with tests

**Files:**
- Modify: `src/typography.py:108`
- Modify: `nyc_config.py:45-46`
- Modify: `tests/test_typography.py:235`

---

**Step 1: Write the failing test**

Add this test to `tests/test_typography.py` (after the existing legend tests):

```python
def test_render_legend_bar_width_not_shrunk_by_typography_scale(tmp_path):
    """bar_width must not be further shrunk when scale (TYPOGRAPHY_SCALE) < 1.

    A city config with TYPOGRAPHY_SCALE=0.7 should produce the same bar-width
    *proportion* (bar_width / canvas_width) as scale=1.0, since bar_width is
    already derived from canvas width w.
    """
    font_path = str(tmp_path / "f.ttf")

    def bar_proportion(scale_val):
        W = 400
        img = Image.new("RGB", (W, 500), color=(0, 0, 0))
        before = np.array(img).copy()
        with patch("src.typography._load_font", return_value=ImageFont.load_default()):
            render_legend(img, color_ramp=_RAMP, font_path=font_path, scale=scale_val)
        after = np.array(img)
        diff = np.abs(after.astype(int) - before.astype(int)).sum(axis=2)
        # Count columns in the center half that changed — proxy for bar width
        h, w = diff.shape
        center_cols = diff[h // 3: 2 * h // 3, :]
        changed_cols = np.where(center_cols.sum(axis=0) > 0)[0]
        if len(changed_cols) == 0:
            return 0.0
        return (changed_cols[-1] - changed_cols[0]) / W

    prop_full  = bar_proportion(scale_val=1.0)
    prop_nyc   = bar_proportion(scale_val=0.7)

    # Proportions should be within 5% of each other (not 30% smaller as before)
    assert abs(prop_full - prop_nyc) < 0.05, (
        f"scale=1.0 → {prop_full:.2f}, scale=0.7 → {prop_nyc:.2f}; "
        f"bar_width must not shrink with TYPOGRAPHY_SCALE"
    )
```

**Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_typography.py::test_render_legend_bar_width_not_shrunk_by_typography_scale -v
```

Expected: FAIL (the proportions differ by ~30%)

---

**Step 3: Fix `src/typography.py` — remove `scale` from `bar_width`**

In `render_legend` at line 108, change:
```python
# Before
bar_width  = int(max(120, w * 3 // 8) * scale * width_scale)

# After
bar_width  = int(max(120, w * 3 // 8) * width_scale)
```

**Step 4: Run new test to verify it passes**

```bash
.venv/bin/pytest tests/test_typography.py::test_render_legend_bar_width_not_shrunk_by_typography_scale -v
```

Expected: PASS

---

**Step 5: Fix the mirrored formula in the existing test**

In `tests/test_typography.py` at line 235, the helper `left_bar_color` computes `bar_width` to locate the bar on the pixel array. Update it to match the new formula:

```python
# Before (line 235)
bar_width = max(120, w * 3 // 8)

# After (no change needed — scale was never applied here; this line is already correct)
```

Wait — double check: line 235 reads `bar_width = max(120, w * 3 // 8)`. It does NOT include `* scale`, so it already matches the new formula. No edit needed.

**Step 6: Run the full typography test suite**

```bash
.venv/bin/pytest tests/test_typography.py -v
```

Expected: All 16 tests PASS (15 existing + 1 new).

---

**Step 7: Update `nyc_config.py`**

Change `LEGEND_WIDTH_SCALE` from `0.8` to `1.0`:

```python
# Before
LEGEND_WIDTH_SCALE = .8

# After
LEGEND_WIDTH_SCALE = 1.0
```

This targets ~37.5% of canvas width in both preview and full render, matching the visual appearance the NYC preview had before.

**Step 8: Run full test suite to confirm nothing regressed**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All tests PASS.

---

**Step 9: Commit**

```bash
git add src/typography.py nyc_config.py tests/test_typography.py
git commit -m "fix: remove TYPOGRAPHY_SCALE from legend bar_width; update nyc LEGEND_WIDTH_SCALE"
```
