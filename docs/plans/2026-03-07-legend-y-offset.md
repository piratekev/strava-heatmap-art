# Legend Y Offset Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `LEGEND_Y_OFFSET` config knob to shift the legend bar up or down. SF defaults to 0 (no change). NYC starts at 40 (lower).

**Architecture:** One new param `y_offset` in `render_legend`, applied to `bar_top` after centering. Wired through config and export.py.

**Tech Stack:** Python, Pillow, pytest

---

### Task 1: Add y_offset param to render_legend and wire through config

**Files:**
- Modify: `src/typography.py:85`
- Modify: `config.py`
- Modify: `nyc_config.py`
- Modify: `export.py`
- Modify: `tests/test_typography.py`

---

**Step 1: Write the failing test**

Add to `tests/test_typography.py`:

```python
def test_render_legend_y_offset_shifts_position(tmp_path):
    """Positive y_offset must move the legend bar downward (larger y coordinate)."""
    font_path = str(tmp_path / "f.ttf")

    def legend_mid_y(offset):
        img = Image.new("RGB", (540, 540), color=(0, 0, 0))
        before = np.array(img).copy()
        with patch("src.typography._load_font", return_value=ImageFont.load_default()):
            render_legend(img, color_ramp=_RAMP, font_path=font_path, y_offset=offset)
        after = np.array(img)
        diff = np.abs(after.astype(int) - before.astype(int)).sum(axis=2)
        rows = np.where(diff.sum(axis=1) > 0)[0]
        return rows.mean() if len(rows) else 0

    mid_zero     = legend_mid_y(0)
    mid_positive = legend_mid_y(40)
    mid_negative = legend_mid_y(-40)

    assert mid_positive > mid_zero,   "positive y_offset must lower the legend"
    assert mid_negative < mid_zero,   "negative y_offset must raise the legend"
```

**Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_typography.py::test_render_legend_y_offset_shifts_position -v
```

Expected: FAIL with `TypeError: render_legend() got an unexpected keyword argument 'y_offset'`

---

**Step 3: Add `y_offset` param to `render_legend`**

In `src/typography.py`, change the `render_legend` signature to add `y_offset=0`:

```python
def render_legend(img, color_ramp, font_path,
                  text_color=(255, 255, 255), gamma=GAMMA, canvas_max_val=None,
                  scale=1.0, position="center", width_scale=1.0,
                  text_width_scale=1.0, show_elevation=True, y_offset=0):
```

Apply `y_offset` after computing `bar_top`. Change:
```python
bar_top    = block_mid_y - legend_h // 2
bar_bottom = bar_top + bar_height
```
To:
```python
bar_top    = block_mid_y - legend_h // 2 + y_offset
bar_bottom = bar_top + bar_height
```

---

**Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_typography.py::test_render_legend_y_offset_shifts_position -v
```

Expected: PASS

---

**Step 5: Run full typography suite**

```bash
.venv/bin/pytest tests/test_typography.py -v
```

Expected: All tests PASS.

---

**Step 6: Add `LEGEND_Y_OFFSET` to config files**

In `config.py`, add after `LEGEND_WIDTH_SCALE`:
```python
# Vertical pixel offset for the legend bar (positive = lower, negative = higher).
# 0 = default (centered on text block). Adjust per city config for fine-tuning.
LEGEND_Y_OFFSET = 0
```

In `nyc_config.py`, add at the end:
```python
LEGEND_Y_OFFSET = 40
```

---

**Step 7: Wire through export.py**

Add `LEGEND_Y_OFFSET` to the import block in `export.py`:
```python
from config import (
    CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, OUTPUT_DIR,
    MAP_TILE_OPACITY, MAP_TILE_CACHE,
    MAP_TILE_URL,
    MAP_FONT_PATH, MAP_FONT_URL,
    ROUTE_COLOR_RAMP, GAMMA, PRINT_DPI,
    TYPOGRAPHY_SCALE, TYPOGRAPHY_WIDTH_SCALE, TYPOGRAPHY_X_OFFSET,
    LEGEND_POSITION, LEGEND_WIDTH_SCALE,
    SHOW_ELEVATION, LEGEND_Y_OFFSET,
)
```

Pass `y_offset=LEGEND_Y_OFFSET` to `render_legend`:
```python
img = render_legend(img, color_ramp=ROUTE_COLOR_RAMP, font_path=MAP_FONT_PATH,
                    gamma=GAMMA, canvas_max_val=canvas_max_val,
                    scale=TYPOGRAPHY_SCALE, position=LEGEND_POSITION,
                    width_scale=LEGEND_WIDTH_SCALE,
                    text_width_scale=TYPOGRAPHY_WIDTH_SCALE,
                    show_elevation=SHOW_ELEVATION,
                    y_offset=LEGEND_Y_OFFSET)
```

---

**Step 8: Run full test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All tests PASS.

---

**Step 9: Commit**

```bash
git add src/typography.py config.py nyc_config.py export.py tests/test_typography.py
git commit -m "feat: add LEGEND_Y_OFFSET config knob for vertical legend positioning"
```
