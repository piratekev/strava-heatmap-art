# NYC Legend Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three NYC-specific legend issues: preview bar too wide, legend misaligned with text center, and elevation always shown.

**Architecture:** Add `show_elevation` and `text_width_scale` params to `render_typography` and `render_legend`. Remove the `max(120, ...)` floor from `bar_width`. Add `SHOW_ELEVATION` config knob. All new params default to current SF behavior — SF is unaffected.

**Tech Stack:** Python, Pillow, pytest

---

### Task 1: Add `show_elevation` to `render_typography`

**Files:**
- Modify: `src/typography.py:38-82`
- Modify: `tests/test_typography.py`

**Step 1: Write the failing test**

Add to `tests/test_typography.py`:

```python
def test_render_typography_hides_elevation_when_disabled(tmp_path):
    """When show_elevation=False, elevation text must not appear."""
    font_path = str(tmp_path / "f.ttf")
    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        with patch("PIL.ImageDraw.ImageDraw.text") as mock_text:
            img = Image.new("RGB", (540, 540), color=(0, 0, 0))
            render_typography(img, _make_runs(n=10), font_path=font_path, show_elevation=False)
            all_text = " ".join(str(c) for c in mock_text.call_args_list)
            assert "ft" not in all_text
            assert "↑" not in all_text


def test_render_typography_shows_elevation_by_default(tmp_path):
    """show_elevation defaults to True — elevation must appear without passing the param."""
    font_path = str(tmp_path / "f.ttf")
    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        with patch("PIL.ImageDraw.ImageDraw.text") as mock_text:
            img = Image.new("RGB", (540, 540), color=(0, 0, 0))
            render_typography(img, _make_runs(n=10), font_path=font_path)
            all_text = " ".join(str(c) for c in mock_text.call_args_list)
            assert "ft" in all_text
```

**Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_typography.py::test_render_typography_hides_elevation_when_disabled tests/test_typography.py::test_render_typography_shows_elevation_by_default -v
```

Expected: FAIL with `TypeError: render_typography() got an unexpected keyword argument 'show_elevation'`

**Step 3: Implement**

In `src/typography.py`, change `render_typography` signature and body:

```python
def render_typography(img, sf_runs, font_path,
                      text_color=(255, 255, 255), scale=1.0, width_scale=1.0,
                      x_offset=0, show_elevation=True):
```

Change the lines list from:
```python
lines = [
    (year_range, font),
    (total_runs,  font),
    (total_dist,  font),
    (total_elev,  font),
]
```
To:
```python
lines = [
    (year_range, font),
    (total_runs,  font),
    (total_dist,  font),
]
if show_elevation:
    lines.append((total_elev, font))
```

**Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_typography.py::test_render_typography_hides_elevation_when_disabled tests/test_typography.py::test_render_typography_shows_elevation_by_default -v
```

Expected: PASS

**Step 5: Run full typography suite**

```bash
.venv/bin/pytest tests/test_typography.py -v
```

Expected: All tests PASS.

**Step 6: Commit**

```bash
git add src/typography.py tests/test_typography.py
git commit -m "feat: add show_elevation param to render_typography"
```

---

### Task 2: Fix `render_legend` — bar_width floor, text_width_scale, show_elevation

**Files:**
- Modify: `src/typography.py:85-172`
- Modify: `tests/test_typography.py`

**Step 1: Write failing tests**

Add to `tests/test_typography.py`:

```python
def test_render_legend_bar_width_proportional_at_small_canvas(tmp_path):
    """bar_width must be proportional to canvas width even at small (preview) sizes.

    Previously max(120, w * 3 // 8) caused the floor to dominate at small w,
    making preview bar disproportionately wide. Now it should be ~37.5% at any size.
    """
    font_path = str(tmp_path / "f.ttf")

    def bar_proportion(canvas_w):
        img = Image.new("RGB", (canvas_w, 500), color=(0, 0, 0))
        before = np.array(img).copy()
        with patch("src.typography._load_font", return_value=ImageFont.load_default()):
            render_legend(img, color_ramp=_RAMP, font_path=font_path)
        after = np.array(img)
        diff = np.abs(after.astype(int) - before.astype(int)).sum(axis=2)
        h, w = diff.shape
        center_row = diff[h // 2, :]
        changed = np.where(center_row > 0)[0]
        if len(changed) == 0:
            return 0.0
        return (changed[-1] - changed[0] + 1) / canvas_w

    prop_large = bar_proportion(1740)
    prop_small = bar_proportion(174)
    # Both should be close to 37.5%; definitely not 2x different
    assert abs(prop_large - prop_small) < 0.15, (
        f"large={prop_large:.2f}, small={prop_small:.2f}; bar must scale proportionally"
    )


def test_render_legend_centers_on_3line_block_when_elevation_hidden(tmp_path):
    """When show_elevation=False the legend must center on the 3-line block,
    not the 4-line block. Legend midpoint should be lower than when elevation is shown."""
    font_path = str(tmp_path / "f.ttf")

    def legend_mid_y(show_elev):
        img = Image.new("RGB", (540, 540), color=(0, 0, 0))
        before = np.array(img).copy()
        with patch("src.typography._load_font", return_value=ImageFont.load_default()):
            render_legend(img, color_ramp=_RAMP, font_path=font_path, show_elevation=show_elev)
        after = np.array(img)
        diff = np.abs(after.astype(int) - before.astype(int)).sum(axis=2)
        rows = np.where(diff.sum(axis=1) > 0)[0]
        return rows.mean() if len(rows) else 0

    mid_4line = legend_mid_y(show_elev=True)
    mid_3line = legend_mid_y(show_elev=False)
    # 3-line block is shorter so text starts higher; legend center should be higher (smaller y)
    assert mid_3line < mid_4line, (
        f"3-line legend mid {mid_3line:.0f} should be above 4-line mid {mid_4line:.0f}"
    )


def test_render_legend_text_width_scale_affects_vertical_centering(tmp_path):
    """text_width_scale must be used in block height estimation.
    A smaller text_width_scale (narrower/shorter font) shifts block_top down,
    moving legend center lower than with text_width_scale=1.0."""
    font_path = str(tmp_path / "f.ttf")

    def legend_mid_y(twscale):
        img = Image.new("RGB", (540, 540), color=(0, 0, 0))
        before = np.array(img).copy()
        with patch("src.typography._load_font", return_value=ImageFont.load_default()):
            render_legend(img, color_ramp=_RAMP, font_path=font_path, text_width_scale=twscale)
        after = np.array(img)
        diff = np.abs(after.astype(int) - before.astype(int)).sum(axis=2)
        rows = np.where(diff.sum(axis=1) > 0)[0]
        return rows.mean() if len(rows) else 0

    mid_full = legend_mid_y(1.0)
    mid_nyc  = legend_mid_y(0.7)
    # Smaller text → block_top moves down → legend center moves down (larger y)
    assert mid_nyc > mid_full, (
        f"text_width_scale=0.7 legend mid {mid_nyc:.0f} should be below scale=1.0 mid {mid_full:.0f}"
    )
```

**Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_typography.py::test_render_legend_bar_width_proportional_at_small_canvas tests/test_typography.py::test_render_legend_centers_on_3line_block_when_elevation_hidden tests/test_typography.py::test_render_legend_text_width_scale_affects_vertical_centering -v
```

Expected: FAIL (wrong bar proportions, missing params)

**Step 3: Implement changes in `render_legend`**

Change the function signature:
```python
def render_legend(img, color_ramp, font_path,
                  text_color=(255, 255, 255), gamma=GAMMA, canvas_max_val=None,
                  scale=1.0, position="center", width_scale=1.0,
                  text_width_scale=1.0, show_elevation=True):
```

Change `bar_width` (remove floor, remove `scale`):
```python
# Before
bar_width  = int(max(120, w * 3 // 8) * width_scale)
# After
bar_width  = int(w * 3 // 8 * width_scale)
```

Change `main_font_size` to use `text_width_scale`:
```python
# Before
main_font_size = int(max(10, h // 40) * scale)
# After
main_font_size = int(max(10, h // 40) * scale * text_width_scale)
```

Change block_top to use `num_lines`:
```python
# Before
block_top    = h - margin - 4 * main_font_size - 3 * main_line_gap
# After
num_lines    = 3 if not show_elevation else 4
block_top    = h - margin - num_lines * main_font_size - (num_lines - 1) * main_line_gap
```

**Step 4: Run new tests**

```bash
.venv/bin/pytest tests/test_typography.py::test_render_legend_bar_width_proportional_at_small_canvas tests/test_typography.py::test_render_legend_centers_on_3line_block_when_elevation_hidden tests/test_typography.py::test_render_legend_text_width_scale_affects_vertical_centering -v
```

Expected: PASS

**Step 5: Run full typography suite**

```bash
.venv/bin/pytest tests/test_typography.py -v
```

Expected: All tests PASS. Note: `test_render_legend_bar_width_not_shrunk_by_typography_scale` (added in the previous fix) should still pass since we're not re-introducing scale into bar_width.

**Step 6: Commit**

```bash
git add src/typography.py tests/test_typography.py
git commit -m "feat: fix render_legend bar_width floor, add text_width_scale and show_elevation params"
```

---

### Task 3: Add `SHOW_ELEVATION` to config and wire up export.py

**Files:**
- Modify: `config.py`
- Modify: `nyc_config.py`
- Modify: `export.py`

**Step 1: Add config knob**

In `config.py`, add after `LEGEND_WIDTH_SCALE`:
```python
# Show or hide elevation gain in the typography block.
# True = show (SF default). False = hide (e.g. NYC).
SHOW_ELEVATION = True
```

In `nyc_config.py`, add after `TYPOGRAPHY_X_OFFSET`:
```python
SHOW_ELEVATION = False
```

**Step 2: Wire up export.py**

In `export.py`, add `SHOW_ELEVATION` and `TYPOGRAPHY_WIDTH_SCALE` to the import from config (TYPOGRAPHY_WIDTH_SCALE is already imported — just add SHOW_ELEVATION):

```python
from config import (
    CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, OUTPUT_DIR,
    MAP_TILE_OPACITY, MAP_TILE_CACHE,
    MAP_TILE_URL,
    MAP_FONT_PATH, MAP_FONT_URL,
    ROUTE_COLOR_RAMP, GAMMA, PRINT_DPI,
    TYPOGRAPHY_SCALE, TYPOGRAPHY_WIDTH_SCALE, TYPOGRAPHY_X_OFFSET,
    LEGEND_POSITION, LEGEND_WIDTH_SCALE,
    SHOW_ELEVATION,
)
```

Pass `show_elevation` to both render calls:
```python
img = render_typography(img, city_runs, font_path=MAP_FONT_PATH,
                        scale=TYPOGRAPHY_SCALE, width_scale=TYPOGRAPHY_WIDTH_SCALE,
                        x_offset=int(TYPOGRAPHY_X_OFFSET * scale),
                        show_elevation=SHOW_ELEVATION)
img = render_legend(img, color_ramp=ROUTE_COLOR_RAMP, font_path=MAP_FONT_PATH,
                    gamma=GAMMA, canvas_max_val=canvas_max_val,
                    scale=TYPOGRAPHY_SCALE, position=LEGEND_POSITION,
                    width_scale=LEGEND_WIDTH_SCALE,
                    text_width_scale=TYPOGRAPHY_WIDTH_SCALE,
                    show_elevation=SHOW_ELEVATION)
```

**Step 3: Run full test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All tests PASS.

**Step 4: Commit**

```bash
git add config.py nyc_config.py export.py
git commit -m "feat: add SHOW_ELEVATION config; pass text_width_scale and show_elevation to render_legend"
```
