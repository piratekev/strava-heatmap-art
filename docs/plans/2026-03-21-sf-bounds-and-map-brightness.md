# SF Bounds Extension + Map Brightness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the SF canvas 40px west + 50px south (maintaining 4:5 print ratio), and add a MAP_TILE_BRIGHTNESS config knob to lift map tile visibility for both cities.

**Architecture:** Two independent config changes. Bounds/canvas is SF-only (config.py). Brightness is a new config value wired through export.py, defaulting to 1.3.

**Tech Stack:** Python, Pillow (ImageEnhance), pytest

---

### Task 1: Extend SF canvas and bounds

**Files:**
- Modify: `config.py`
- Modify: `tests/test_renderer.py` (aspect ratio test)

---

**Step 1: Read the current aspect ratio test**

Open `tests/test_renderer.py` and find `test_sf_bounds_aspect_ratio_matches_canvas`. Note the expected ratio value — it will need updating after the bounds change.

Run it first to confirm it currently passes:
```bash
.venv/bin/pytest tests/test_renderer.py::test_sf_bounds_aspect_ratio_matches_canvas -v
```
Expected: PASS

---

**Step 2: Update `config.py`**

Change canvas dimensions:
```python
CANVAS_WIDTH_PX  = 4720   # was 4680 — +40px west
CANVAS_HEIGHT_PX = 5900   # was 5850 — +50px south (maintains 4:5 ratio)
```

Extend bounds:
```python
CITY_BOUNDS = {
    "lat_min": 37.7057,     # was 37.7068 — extended south ~50px
    "lat_max": 37.8392,     # unchanged
    "lng_min": -122.5163,   # was -122.5152 — extended west 40px (+40 × 0.00002863°/px)
    "lng_max": -122.3812,   # unchanged
}
```

Update the DPI comment: 4720px at 16" wide = 295 DPI:
```python
# Print canvas: 16x20" aspect ratio (4:5) — prints at ~295 DPI
```

---

**Step 3: Verify the aspect ratio**

Run this in the Python REPL to confirm the new bounds produce aspect ≈ 0.8:
```python
import math
lat_min, lat_max = 37.7057, 37.8392
lng_min, lng_max = -122.5163, -122.3812
lng_range = (lng_max - lng_min) * math.pi / 180
merc_range = math.asinh(math.tan(math.radians(lat_max))) - math.asinh(math.tan(math.radians(lat_min)))
aspect = lng_range / merc_range
print(f"geo aspect: {aspect:.4f}, canvas: {4720/5900:.4f}")
```

Expected: both values close to 0.8. If the geo aspect differs from canvas by more than 0.003, adjust `lat_min` up or down by 0.0001° until they match.

---

**Step 4: Update the aspect ratio test**

In `tests/test_renderer.py`, find `test_sf_bounds_aspect_ratio_matches_canvas` and update the expected ratio to match the computed geo aspect from Step 3. The test likely has a line like:
```python
assert abs(aspect - expected) < 0.003
```
or compares to a hardcoded value. Update it to the new computed value.

---

**Step 5: Run the aspect ratio test**

```bash
.venv/bin/pytest tests/test_renderer.py::test_sf_bounds_aspect_ratio_matches_canvas -v
```
Expected: PASS

---

**Step 6: Run full test suite**

```bash
.venv/bin/pytest tests/ -v
```
Expected: All tests PASS.

---

**Step 7: Commit**

```bash
git add config.py tests/test_renderer.py
git commit -m "feat: extend SF canvas 40px west + 50px south; maintain 4:5 print ratio"
```

---

### Task 2: Add MAP_TILE_BRIGHTNESS config

**Files:**
- Modify: `config.py`
- Modify: `export.py`
- Modify: `tests/test_renderer.py` or `tests/test_tiles.py` (add brightness test)

---

**Step 1: Write the failing test**

Find the test file that covers the export compositing pipeline, or add to `tests/test_renderer.py`. Add:

```python
def test_map_tile_brightness_lightens_background():
    """MAP_TILE_BRIGHTNESS > 1.0 must produce a brighter composite than 1.0."""
    from PIL import Image, ImageEnhance
    import numpy as np

    tile = Image.new("RGB", (100, 100), color=(50, 50, 80))  # dark map tile

    def apply_brightness(factor):
        t = ImageEnhance.Brightness(tile).enhance(factor)
        return np.array(t).mean()

    assert apply_brightness(1.3) > apply_brightness(1.0)
    assert apply_brightness(1.0) > apply_brightness(0.7)
```

Run it:
```bash
.venv/bin/pytest tests/ -k "test_map_tile_brightness" -v
```
Expected: PASS immediately (this tests PIL behavior, no code change needed yet — confirms the approach works).

---

**Step 2: Add `MAP_TILE_BRIGHTNESS` to `config.py`**

Add after `MAP_TILE_OPACITY`:
```python
# Brightness multiplier applied to the map tile before compositing.
# 1.0 = no change. > 1.0 = brighter streets/water. Start at 1.3 and iterate.
MAP_TILE_BRIGHTNESS = 1.3
```

---

**Step 3: Wire through `export.py`**

Add `MAP_TILE_BRIGHTNESS` to the import block:
```python
from config import (
    CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, OUTPUT_DIR,
    MAP_TILE_OPACITY, MAP_TILE_CACHE, MAP_TILE_BRIGHTNESS,
    MAP_TILE_URL,
    MAP_FONT_PATH, MAP_FONT_URL,
    ROUTE_COLOR_RAMP, GAMMA, PRINT_DPI,
    TYPOGRAPHY_SCALE, TYPOGRAPHY_WIDTH_SCALE, TYPOGRAPHY_X_OFFSET,
    LEGEND_POSITION, LEGEND_WIDTH_SCALE,
    SHOW_ELEVATION, LEGEND_Y_OFFSET,
)
```

In the map tile compositing block, apply brightness to the tile after fetching, before compositing. Find this section:
```python
tile = fetch_map_tile(...)
bg = composite_map_background(tile, ...)
```

Change to:
```python
from PIL import ImageEnhance
tile = fetch_map_tile(...)
if MAP_TILE_BRIGHTNESS != 1.0:
    tile = ImageEnhance.Brightness(tile).enhance(MAP_TILE_BRIGHTNESS)
bg = composite_map_background(tile, ...)
```

---

**Step 4: Run full test suite**

```bash
.venv/bin/pytest tests/ -v
```
Expected: All tests PASS.

---

**Step 5: Commit**

```bash
git add config.py export.py
git commit -m "feat: add MAP_TILE_BRIGHTNESS config to control map tile lightness"
```

---

## Iteration note

`MAP_TILE_BRIGHTNESS = 1.3` is a starting point. Run a preview render to check:
```bash
python export.py --preview
```
Adjust `MAP_TILE_BRIGHTNESS` in `config.py` up or down until streets and water are visible without overpowering the routes. Typical useful range: 1.2–2.0.
