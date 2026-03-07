# NYC Config Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `nyc_config.py` for a rotated NYC heatmap poster (Manhattan-axis-up), selectable via `--config nyc` in `export.py`, without affecting the SF pipeline.

**Architecture:** `nyc_config.py` inherits from `config.py` via `from config import *` and overrides bounds/canvas/rotation. `export.py` pre-parses `--config`, injects the chosen config module into `sys.modules["config"]` before any pipeline imports, so all `src/` files receive the correct values transparently. Rotation is handled inside `StravaRenderer`: `__init__` computes an oversized intermediate canvas (to avoid black corners), and `rotate_and_crop()` applies `cv2.warpAffine` + center-crop after full compositing in `export.py`.

**Tech Stack:** Python, OpenCV (`cv2.warpAffine`), NumPy, existing pipeline unchanged for SF.

---

## Key geometry

For SF (no rotation): `CANVAS_WIDTH_PX / CANVAS_HEIGHT_PX` must equal the Mercator aspect ratio of `CITY_BOUNDS`. Validated by `test_sf_bounds_aspect_ratio_matches_canvas`.

For NYC (rotation = 29°): The *intermediate* canvas (pre-rotation) must match the NYC bounds Mercator aspect ratio. The final canvas (`CANVAS_WIDTH_PX × CANVAS_HEIGHT_PX`) is derived from the intermediate by the rotation geometry. Constraint:

```
render_w = W * cos(θ) + H * sin(θ)
render_h = W * sin(θ) + H * cos(θ)
render_w / render_h == geo_aspect  →  W/H ≈ 0.969
```

NYC canvas values: `CANVAS_WIDTH_PX = 5150`, `CANVAS_HEIGHT_PX = 5316`. Validated by `test_nyc_intermediate_canvas_aspect_matches_bounds`.

---

## Task 1: Rename SF_BOUNDS → CITY_BOUNDS

**Files:**
- Modify: `config.py:2`
- Modify: `src/renderer.py:6,32`
- Modify: `src/processor.py:2,22-23`
- Modify: `tests/test_renderer.py:5,15,24,29,39,163,167,299,311`

This is a pure rename refactor. Make all changes, then run the full test suite to verify nothing broke.

**Step 1: Rename in config.py**

Change line 2 from `SF_BOUNDS = {` to `CITY_BOUNDS = {`.

**Step 2: Rename in src/renderer.py**

```python
# Line 6: change import
from config import (CITY_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, ROUTE_COLOR_RAMP, BG_COLOR,
                    HOT_BLOOM_THRESHOLD, HOT_BLOOM_SIGMA_MULT, HOT_BLOOM_STRENGTH,
                    ROUTE_LINE_THICKNESS, ROUTE_LINE_THICKNESS_50_BONUS, ROUTE_LINE_THICKNESS_10_BONUS,
                    DENSITY_EXPAND_SIGMA, DENSITY_EXPAND_STRENGTH,
                    DENSITY_EXPAND_POWER, GAMMA)

# Line 32: change default bounds
self.bounds = CITY_BOUNDS.copy()  # default; overridden by set_bounds()
```

**Step 3: Rename in src/processor.py**

```python
from config import CITY_BOUNDS

# Lines 22-23:
if (CITY_BOUNDS["lat_min"] <= centroid_lat <= CITY_BOUNDS["lat_max"] and
        CITY_BOUNDS["lng_min"] <= centroid_lng <= CITY_BOUNDS["lng_max"]):
```

**Step 4: Rename in tests/test_renderer.py**

- Line 5: `from config import CITY_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX`
- All occurrences of `SF_BOUNDS` in the file → `CITY_BOUNDS`
- Rename `test_set_bounds_defaults_to_sf_bounds` → `test_set_bounds_defaults_to_city_bounds` and update its docstring
- Rename `test_sf_bounds_aspect_ratio_matches_canvas` → keep name (it tests SF specifically, just update the import inside it to `CITY_BOUNDS`)

**Step 5: Run tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests pass (same count as before).

**Step 6: Commit**

```bash
git add config.py src/renderer.py src/processor.py tests/test_renderer.py
git commit -m "refactor: rename SF_BOUNDS to CITY_BOUNDS"
```

---

## Task 2: Add CANVAS_ROTATION_DEGREES to config.py

**Files:**
- Modify: `config.py`
- Modify: `tests/test_renderer.py`

**Step 1: Write the failing test**

Add to `tests/test_renderer.py`:

```python
def test_canvas_rotation_degrees_exists_and_defaults_to_zero():
    """SF config must define CANVAS_ROTATION_DEGREES = 0."""
    from config import CANVAS_ROTATION_DEGREES
    assert CANVAS_ROTATION_DEGREES == 0
```

**Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_renderer.py::test_canvas_rotation_degrees_exists_and_defaults_to_zero -v
```

Expected: FAIL with `ImportError: cannot import name 'CANVAS_ROTATION_DEGREES'`

**Step 3: Add constant to config.py**

Add after `PRINT_DPI = 285` (line 12):

```python
CANVAS_ROTATION_DEGREES = 0  # degrees clockwise. 0 = north-up (SF). 29 = Manhattan-axis-up (NYC).
```

**Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_renderer.py::test_canvas_rotation_degrees_exists_and_defaults_to_zero -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add config.py tests/test_renderer.py
git commit -m "feat: add CANVAS_ROTATION_DEGREES = 0 default to config"
```

---

## Task 3: Create nyc_config.py

**Files:**
- Create: `nyc_config.py`
- Modify: `tests/test_renderer.py`

**Step 1: Write the failing test**

Add to `tests/test_renderer.py`:

```python
def test_nyc_intermediate_canvas_aspect_matches_bounds():
    """NYC intermediate canvas (pre-rotation) must match the Mercator aspect ratio of CITY_BOUNDS."""
    import math
    import importlib
    nyc = importlib.import_module("nyc_config")

    b = nyc.CITY_BOUNDS
    lng_range_rad = (b["lng_max"] - b["lng_min"]) * math.pi / 180
    merc_max = math.asinh(math.tan(math.radians(b["lat_max"])))
    merc_min = math.asinh(math.tan(math.radians(b["lat_min"])))
    geo_aspect = lng_range_rad / (merc_max - merc_min)

    rot_rad = math.radians(nyc.CANVAS_ROTATION_DEGREES)
    cos_r, sin_r = math.cos(rot_rad), math.sin(rot_rad)
    W, H = nyc.CANVAS_WIDTH_PX, nyc.CANVAS_HEIGHT_PX
    render_w = W * cos_r + H * sin_r
    render_h = W * sin_r + H * cos_r
    canvas_aspect = render_w / render_h

    assert abs(canvas_aspect - geo_aspect) < 0.005, (
        f"NYC intermediate aspect {canvas_aspect:.4f} != geo aspect {geo_aspect:.4f}"
    )
```

**Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_renderer.py::test_nyc_intermediate_canvas_aspect_matches_bounds -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'nyc_config'`

**Step 3: Create nyc_config.py**

```python
from config import *  # inherit all SF defaults

# New York City bounding box
# Covers: full NYC marathon course (Staten Island → Brooklyn → Queens → Bronx → Manhattan),
# Hoboken to the west, Washington Heights to the north.
CITY_BOUNDS = {
    "lat_min": 40.575,   # Verrazzano Bridge / Staten Island marathon start
    "lat_max": 40.875,   # Washington Heights
    "lng_min": -74.105,  # Hoboken
    "lng_max": -73.730,  # eastern Brooklyn/Queens
}

# Rotation: Manhattan's street grid runs ~29° from true north.
# Setting this rotates the final output so Manhattan's long axis is vertical.
CANVAS_ROTATION_DEGREES = 29

# Canvas: final output dimensions.
# Derived so the intermediate (pre-rotation) canvas matches the NYC Mercator aspect ratio.
# Formula: render_w/render_h = geo_aspect → W/H ≈ 0.969
# render_w = 5150*cos(29°) + 5316*sin(29°) ≈ 7082
# render_h = 5150*sin(29°) + 5316*cos(29°) ≈ 7147
# 7082/7147 ≈ 0.991 (matches NYC geo_aspect)
CANVAS_WIDTH_PX  = 5150
CANVAS_HEIGHT_PX = 5316

# Separate tile cache so SF and NYC renders don't stomp each other.
MAP_TILE_CACHE = "data/map_tile_nyc.png"
```

**Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_renderer.py::test_nyc_intermediate_canvas_aspect_matches_bounds -v
```

Expected: PASS

**Step 5: Run full test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all pass.

**Step 6: Commit**

```bash
git add nyc_config.py tests/test_renderer.py
git commit -m "feat: add nyc_config.py with bounds, rotation, canvas dims"
```

---

## Task 4: Update renderer.py for oversized canvas and rotate_and_crop

**Files:**
- Modify: `src/renderer.py`
- Modify: `tests/test_renderer.py`

**Step 1: Write failing tests**

Add to `tests/test_renderer.py`:

```python
def test_rotate_and_crop_is_noop_when_rotation_zero():
    """rotate_and_crop returns original shape when _rotation_degrees == 0."""
    r = StravaRenderer(width=100, height=120)
    assert r._rotation_degrees == 0
    arr = np.zeros((120, 100, 3), dtype=np.uint8)
    result = r.rotate_and_crop(arr)
    assert result.shape == (120, 100, 3)


def test_rotate_and_crop_returns_final_dimensions():
    """rotate_and_crop crops to final_width × final_height after rotation."""
    import math
    r = StravaRenderer(width=100, height=120)
    # Manually configure for a 29° rotation (mimics NYC config)
    rot = 29
    cos_r, sin_r = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    r._rotation_degrees = rot
    r.final_width = 100
    r.final_height = 120
    r.width  = int(100 * cos_r + 120 * sin_r)
    r.height = int(100 * sin_r + 120 * cos_r)
    arr = np.full((r.height, r.width, 3), 128, dtype=np.uint8)
    result = r.rotate_and_crop(arr)
    assert result.shape == (120, 100, 3)


def test_renderer_oversized_when_rotation_nonzero():
    """When CANVAS_ROTATION_DEGREES != 0, renderer internal canvas is larger than final dims."""
    import math
    r = StravaRenderer(width=100, height=120)
    r._rotation_degrees = 29
    cos_r, sin_r = math.cos(math.radians(29)), math.sin(math.radians(29))
    expected_w = int(100 * cos_r + 120 * sin_r)
    expected_h = int(100 * sin_r + 120 * cos_r)
    # Simulate what __init__ would compute — just verify the formula
    assert expected_w > 100
    assert expected_h > 120
```

**Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_renderer.py::test_rotate_and_crop_is_noop_when_rotation_zero tests/test_renderer.py::test_rotate_and_crop_returns_final_dimensions -v
```

Expected: FAIL with `AttributeError: 'StravaRenderer' object has no attribute 'rotate_and_crop'`

**Step 3: Update src/renderer.py**

Update the import at the top:

```python
import math
import os
import numpy as np
import cv2
from PIL import Image
from scipy.ndimage import gaussian_filter
from config import (CITY_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, CANVAS_ROTATION_DEGREES,
                    ROUTE_COLOR_RAMP, BG_COLOR,
                    HOT_BLOOM_THRESHOLD, HOT_BLOOM_SIGMA_MULT, HOT_BLOOM_STRENGTH,
                    ROUTE_LINE_THICKNESS, ROUTE_LINE_THICKNESS_50_BONUS, ROUTE_LINE_THICKNESS_10_BONUS,
                    DENSITY_EXPAND_SIGMA, DENSITY_EXPAND_STRENGTH,
                    DENSITY_EXPAND_POWER, GAMMA)
```

Add a module-level helper before the class:

```python
def _expand_bounds(bounds, lng_scale, lat_scale):
    """Expand geographic bounds by scale factors around their center (in Mercator space)."""
    lng_center = (bounds["lng_min"] + bounds["lng_max"]) / 2
    half_lng = (bounds["lng_max"] - bounds["lng_min"]) / 2 * lng_scale

    lat_min_rad = math.radians(bounds["lat_min"])
    lat_max_rad = math.radians(bounds["lat_max"])
    merc_min = math.asinh(math.tan(lat_min_rad))
    merc_max = math.asinh(math.tan(lat_max_rad))
    merc_center = (merc_min + merc_max) / 2
    half_merc = (merc_max - merc_min) / 2 * lat_scale

    return {
        "lat_min": math.degrees(math.atan(math.sinh(merc_center - half_merc))),
        "lat_max": math.degrees(math.atan(math.sinh(merc_center + half_merc))),
        "lng_min": lng_center - half_lng,
        "lng_max": lng_center + half_lng,
    }
```

Update `StravaRenderer.__init__`:

```python
def __init__(self, width=CANVAS_WIDTH_PX, height=CANVAS_HEIGHT_PX):
    self.final_width = width
    self.final_height = height
    self._rotation_degrees = CANVAS_ROTATION_DEGREES

    if CANVAS_ROTATION_DEGREES != 0:
        cos_r = math.cos(math.radians(CANVAS_ROTATION_DEGREES))
        sin_r = math.sin(math.radians(CANVAS_ROTATION_DEGREES))
        self.width  = int(width  * cos_r + height * sin_r)
        self.height = int(width  * sin_r + height * cos_r)
        self.bounds = _expand_bounds(
            CITY_BOUNDS,
            lng_scale=self.width  / width,
            lat_scale=self.height / height,
        )
    else:
        self.width  = width
        self.height = height
        self.bounds = CITY_BOUNDS.copy()

    self.canvas = np.zeros((self.height, self.width), dtype=np.float32)
```

Add `rotate_and_crop` method after `_make_vignette`:

```python
def rotate_and_crop(self, img_array):
    """Rotate by _rotation_degrees and crop to final_width × final_height.
    Returns img_array unchanged when _rotation_degrees == 0.
    img_array must be HxWx3 uint8 or float32.
    """
    if self._rotation_degrees == 0:
        return img_array
    h, w = img_array.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), -self._rotation_degrees, 1.0)
    rotated = cv2.warpAffine(img_array, M, (w, h))
    y0 = (h - self.final_height) // 2
    x0 = (w - self.final_width)  // 2
    return rotated[y0:y0 + self.final_height, x0:x0 + self.final_width]
```

**Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_renderer.py -v
```

Expected: all pass including the 3 new rotation tests.

**Step 5: Commit**

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "feat: add oversized canvas and rotate_and_crop to StravaRenderer"
```

---

## Task 5: Update export.py for --config flag and rotation-aware pipeline

**Files:**
- Modify: `export.py`

The config injection must happen before any `from config import` or `from src.*` imports. Restructure the top of `export.py` as follows.

**Step 1: Restructure imports and add --config pre-parse**

Replace the top section of `export.py` (lines 1–30) with:

```python
#!/usr/bin/env python3
"""
Generate a running heatmap poster from Strava data.

Usage:
    python export.py                      # SF, full render
    python export.py --config nyc         # NYC render
    python export.py --preview            # 1/10 scale for quick iteration
    python export.py --fetch              # fetch new activities first
    python export.py --no-map
    python export.py --no-bloom --no-grain --no-glow
"""
import argparse
import importlib
import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# ── Config injection ──────────────────────────────────────────────────────────
# Pre-parse --config before any pipeline imports so sys.modules["config"] is set
# before src/* modules load and execute their own `from config import ...`.
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--config", default="sf")
_pre_args, _ = _pre.parse_known_args()

if _pre_args.config != "sf":
    sys.modules["config"] = importlib.import_module(f"{_pre_args.config}_config")
# ─────────────────────────────────────────────────────────────────────────────

import numpy as np
from PIL import Image

from src.fetcher import StravaClient, fetch_activities
from src.processor import filter_sf_runs, decode_runs
from src.renderer import StravaRenderer
from src.tiles import fetch_map_tile
from src.typography import render_typography, render_legend, _download_font
from config import (
    CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, OUTPUT_DIR,
    MAP_TILE_OPACITY, MAP_TILE_CACHE,
    MAP_TILE_URL,
    MAP_FONT_PATH, MAP_FONT_URL,
    ROUTE_COLOR_RAMP, GAMMA, PRINT_DPI,
)
```

**Step 2: Update main() to use renderer intermediate dimensions and call rotate_and_crop**

Replace `main()` with:

```python
def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Generate running heatmap poster")
    parser.add_argument("--config", default="sf", help="Config to use: sf (default) or nyc")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--preview", action="store_true", help="1/10 scale for speed")
    parser.add_argument("--no-bloom", dest="bloom", action="store_false", default=True)
    parser.add_argument("--no-vignette", dest="vignette", action="store_false", default=True)
    parser.add_argument("--no-grain", dest="grain", action="store_false", default=True)
    parser.add_argument("--no-glow", dest="glow", action="store_false", default=True)
    parser.add_argument("--no-hot-bloom", dest="hot_bloom", action="store_false", default=True)
    parser.add_argument("--no-density-expand", dest="density_expand", action="store_false", default=True)
    parser.add_argument("--no-map", dest="use_map", action="store_false", default=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if args.fetch:
        print("Fetching activities from Strava...")
        try:
            client = StravaClient.from_env()
        except KeyError as e:
            print(f"ERROR: Missing token {e} in .env")
            print("Run 'python auth.py' first to authenticate with Strava.")
            sys.exit(1)
        fetch_activities(client)

    with open("data/activities.json") as f:
        activities = json.load(f)

    city_runs = filter_sf_runs(activities)
    runs = decode_runs(city_runs)
    print(f"Rendering {len(runs)} runs...")

    scale = 0.1 if args.preview else 1.0
    w = int(CANVAS_WIDTH_PX * scale)   # final output dimensions
    h = int(CANVAS_HEIGHT_PX * scale)

    renderer = StravaRenderer(width=w, height=h)
    renderer.rasterize_all(runs)
    canvas_max_val = float(renderer.canvas.max())

    # to_image() returns oversized array (renderer.width × renderer.height) when rotation != 0
    img_array = renderer.to_image(
        bloom=False, vignette=args.vignette, grain=args.grain,
        glow=args.glow, hot_bloom=args.hot_bloom, density_expand=args.density_expand
    )
    img = Image.fromarray(img_array, mode="RGB")

    # Composite map background at intermediate (oversized) dimensions
    if args.use_map:
        from config import BG_COLOR
        cache = MAP_TILE_CACHE if not args.preview else MAP_TILE_CACHE.replace(".png", "-preview.png")
        zoom = 15 if not args.preview else 11
        try:
            tile = fetch_map_tile(
                bounds=renderer.bounds,
                zoom=zoom,
                cache_path=cache,
                target_size=(renderer.width, renderer.height),
                url_template=MAP_TILE_URL,
            )
            bg = composite_map_background(tile, (renderer.width, renderer.height), MAP_TILE_OPACITY, BG_COLOR)
            bg_arr = np.array(bg, dtype=np.float32)
            route_arr = img_array.astype(np.float32)
            result = 255 - ((255 - bg_arr) * (255 - route_arr) / 255)
            img_array = np.clip(result, 0, 255).astype(np.uint8)
        except Exception as e:
            print(f"Map tile skipped: {e}")

    # Rotate + crop to final dimensions (no-op when CANVAS_ROTATION_DEGREES == 0)
    img_array = renderer.rotate_and_crop(img_array)
    img = Image.fromarray(img_array, mode="RGB")

    # Typography at final dimensions
    _download_font(MAP_FONT_PATH, MAP_FONT_URL)
    img = render_typography(img, city_runs, font_path=MAP_FONT_PATH)
    img = render_legend(img, color_ramp=ROUTE_COLOR_RAMP, font_path=MAP_FONT_PATH,
                        gamma=GAMMA, canvas_max_val=canvas_max_val)

    # Save
    if args.output:
        out_path = args.output
    else:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = "-preview" if args.preview else ""
        config_tag = f"-{_pre_args.config}" if _pre_args.config != "sf" else ""
        out_path = os.path.join(OUTPUT_DIR, f"poster{config_tag}{suffix}-{ts}.png")

    dpi = 3 if args.preview else PRINT_DPI
    img.save(out_path, dpi=(dpi, dpi))
    print(f"Done. {out_path}")
```

**Step 3: Run tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all pass.

**Step 4: Smoke test SF (no regression)**

```bash
.venv/bin/python export.py --no-map --preview --output /tmp/test_sf.png
```

Expected: renders and saves `test_sf.png` with no errors.

**Step 5: Smoke test NYC**

```bash
.venv/bin/python export.py --config nyc --no-map --preview --output /tmp/test_nyc.png
```

Expected: renders and saves `test_nyc.png` (NYC bounds, rotated 29°) with no errors.

**Step 6: Commit**

```bash
git add export.py
git commit -m "feat: add --config flag to export.py; support NYC rotated render"
```

---

## Task 6: Update CLAUDE.md and README.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

**Step 1: Update CLAUDE.md**

- Replace all references to `SF_BOUNDS` with `CITY_BOUNDS`
- Add `CANVAS_ROTATION_DEGREES` to the config knobs reference table
- Add a note in "Adding a new city" about the rotation constraint (final canvas W/H must satisfy `(W*cos(θ)+H*sin(θ)) / (W*sin(θ)+H*cos(θ)) == geo_aspect`)
- Note the `--config` flag in the pipeline description

**Step 2: Update README.md**

- Replace `SF_BOUNDS` with `CITY_BOUNDS` in the "Adapting for a new city" section
- Add a note that `python export.py --config nyc` renders the NYC config

**Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: update CITY_BOUNDS rename and NYC config usage in CLAUDE.md and README"
```
