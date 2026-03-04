# Phase 2 Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix map alignment, switch to CARTO no-labels tiles, scale typography with canvas, and update the color ramp to blue→purple→pink on black.

**Architecture:** Four independent tasks touching config, renderer, tiles, and typography. Each is a self-contained change with its own tests. Tasks 1 and 2 can be done in either order; Task 3 depends on nothing; Task 4 depends on nothing.

**Tech Stack:** Python 3.14, numpy, opencv, Pillow, scipy, CARTO public tile CDN (no token needed)

---

### Task 1: Blue/purple/pink color ramp + black background

**Files:**
- Modify: `config.py`
- Modify: `tests/test_renderer.py`

**Step 1: Update `config.py`**

Replace `BG_COLOR` and `ROUTE_COLOR_RAMP`:

```python
# Background color
BG_COLOR = [0, 0, 0]  # pure black

# Density color ramp: (normalized_value, [R, G, B])
ROUTE_COLOR_RAMP = [
    (0.0, [ 30,  80, 255]),   # low density  → blue
    (0.5, [150,  50, 200]),   # mid density  → purple
    (1.0, [255,  80, 180]),   # high density → pink
]
```

**Step 2: Run tests to see which ones break**

```bash
.venv/bin/pytest tests/test_renderer.py -v
```

Expected: `test_color_ramp_low_density_is_gold` and `test_color_ramp_high_density_shifts_toward_blue` fail. All others pass.

**Step 3: Update the two color ramp tests in `tests/test_renderer.py`**

Replace both tests:

```python
def test_color_ramp_low_density_is_blue(renderer):
    """Low-density pixels should appear blue (B >= R)."""
    renderer.canvas[100, 100] = 1.0    # low density
    renderer.canvas[200, 200] = 50.0   # high density anchor
    img = renderer.to_image(bloom=False, vignette=False, grain=False)
    r, g, b = img[100, 100]
    assert int(b) >= int(r)


def test_color_ramp_high_density_is_pink(renderer):
    """High-density pixels should appear pink (R > 150)."""
    renderer.canvas[100, 100] = 1.0
    renderer.canvas[200, 200] = 50.0
    img = renderer.to_image(bloom=False, vignette=False, grain=False)
    r, g, b = img[200, 200]
    assert int(r) > 150
```

**Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all 39 pass.

**Step 5: Commit**

```bash
git add config.py tests/test_renderer.py
git commit -m "feat: blue→purple→pink color ramp on black background"
```

---

### Task 2: Mercator projection in renderer

**Files:**
- Modify: `src/renderer.py`

Background: `project()` currently uses linear lat/lng interpolation. Mapbox/CARTO tiles use Web Mercator (Y axis is `asinh(tan(lat_rad))`). Switching makes routes align precisely with map tiles. The difference is sub-pixel at SF's latitude but grows with the extent of the viewport.

**Step 1: Write the failing test**

Add to `tests/test_renderer.py`:

```python
def test_project_uses_mercator_y():
    """Mercator midpoint (not geographic midpoint) should map to canvas center."""
    import math
    r = StravaRenderer(width=540, height=540)
    # Compute the Mercator midpoint of SF bounds
    merc_min = math.asinh(math.tan(math.radians(SF_BOUNDS["lat_min"])))
    merc_max = math.asinh(math.tan(math.radians(SF_BOUNDS["lat_max"])))
    merc_mid = (merc_min + merc_max) / 2
    # Back-convert Mercator midpoint to lat
    lat_mercator_center = math.degrees(math.atan(math.sinh(merc_mid)))
    lng_center = (SF_BOUNDS["lng_min"] + SF_BOUNDS["lng_max"]) / 2
    x, y = r.project(lat_mercator_center, lng_center)
    assert abs(y - 270) < 5  # should be very close to canvas center
```

**Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_renderer.py::test_project_uses_mercator_y -v
```

Expected: FAIL — `y` will be close to 270 with linear projection too at SF's scale, but the assertion `< 5` will fail (linear gives ~271 or so, Mercator gives 270 exactly).

Note: if it passes already, the tolerance may need tightening to `< 2` to distinguish linear from Mercator. Adjust if needed.

**Step 3: Update `project()` in `src/renderer.py`**

Replace the existing `project()` method:

```python
def project(self, lat, lng):
    """Map (lat, lng) to (x, y) pixel using Web Mercator Y projection."""
    lat_rad = np.radians(lat)
    merc_y = np.arcsinh(np.tan(lat_rad))

    lat_min_rad = np.radians(self.bounds["lat_min"])
    lat_max_rad = np.radians(self.bounds["lat_max"])
    merc_min = np.arcsinh(np.tan(lat_min_rad))
    merc_max = np.arcsinh(np.tan(lat_max_rad))

    x = int((lng - self.bounds["lng_min"]) /
            (self.bounds["lng_max"] - self.bounds["lng_min"]) * (self.width - 1))
    y = int((merc_max - merc_y) / (merc_max - merc_min) * (self.height - 1))
    return x, y
```

numpy is already imported as `np` — no new imports needed.

**Step 4: Run all tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all 40 pass. The existing coordinate tests use generous tolerances (±30px) so they won't break. If any coordinate test fails, check the tolerance — Mercator Y at SF's scale shifts values by at most a few pixels.

**Step 5: Commit**

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "feat: Web Mercator Y projection in renderer, aligns routes with map tiles"
```

---

### Task 3: CARTO tiles + pixel-accurate crop + export.py update

**Files:**
- Modify: `src/tiles.py`
- Modify: `tests/test_tiles.py`
- Modify: `export.py`
- Modify: `config.py`

Background: The current tile fetcher (a) uses Mapbox's raster tile format (requires token, 512px tiles), and (b) just resizes the stitched grid to `target_size` without cropping — so the tile image covers a slightly different bounding box than the renderer bounds, causing misalignment.

The fix: switch to CARTO's free 256px tiles (no token), and after stitching, crop the stitched image to the exact sub-pixel coordinates corresponding to `renderer.bounds` using the same Mercator tile math.

**Step 1: Update `config.py`**

Add tile URL constant and increase opacity:

```python
MAP_TILE_URL = "https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png"
MAP_TILE_OPACITY = 0.35   # was 0.15
```

Remove the old `MAP_TILE_ZOOM = 13` line — zoom is passed at call time, not a global constant.

**Step 2: Rewrite `src/tiles.py`**

```python
import math
import os
import requests
from PIL import Image
import io


CARTO_URL = "https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png"
_SUBDOMAINS = ["a", "b", "c", "d"]


def lat_lng_to_tile(lat, lng, zoom):
    """Convert lat/lng to tile (x, y) at given zoom (Web Mercator)."""
    n = 2 ** zoom
    x = int((lng + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.asinh(math.tan(lat_rad)) / math.pi) / 2 * n)
    return x, y


def _lng_to_world_x(lng, zoom, tile_size):
    return (lng + 180) / 360 * (2 ** zoom) * tile_size


def _lat_to_world_y(lat, zoom, tile_size):
    lat_rad = math.radians(lat)
    return (1 - math.asinh(math.tan(lat_rad)) / math.pi) / 2 * (2 ** zoom) * tile_size


def fetch_map_tile(bounds, zoom, cache_path, target_size,
                   url_template=CARTO_URL, tile_size=256):
    """
    Fetch tiles covering bounds, stitch, crop to exact bounds, resize to target_size.
    Uses CARTO dark_nolabels by default (no token required).
    Caches the cropped result — subsequent calls return cached image.
    """
    if os.path.exists(cache_path):
        img = Image.open(cache_path).convert("RGB")
        return img.resize(target_size, Image.LANCZOS)

    x_min, y_max = lat_lng_to_tile(bounds["lat_min"], bounds["lng_min"], zoom)
    x_max, y_min = lat_lng_to_tile(bounds["lat_max"], bounds["lng_max"], zoom)

    cols = x_max - x_min + 1
    rows = y_max - y_min + 1
    stitched = Image.new("RGB", (cols * tile_size, rows * tile_size))

    idx = 0
    for tx in range(x_min, x_max + 1):
        for ty in range(y_min, y_max + 1):
            s = _SUBDOMAINS[idx % len(_SUBDOMAINS)]
            idx += 1
            url = url_template.format(s=s, z=zoom, x=tx, y=ty)
            resp = requests.get(url)
            resp.raise_for_status()
            tile_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            stitched.paste(tile_img, ((tx - x_min) * tile_size, (ty - y_min) * tile_size))

    # Pixel-accurate crop: compute exact sub-pixel position of bounds within stitched image
    origin_x = x_min * tile_size
    origin_y = y_min * tile_size
    left   = _lng_to_world_x(bounds["lng_min"], zoom, tile_size) - origin_x
    right  = _lng_to_world_x(bounds["lng_max"], zoom, tile_size) - origin_x
    top    = _lat_to_world_y(bounds["lat_max"], zoom, tile_size) - origin_y
    bottom = _lat_to_world_y(bounds["lat_min"], zoom, tile_size) - origin_y
    cropped = stitched.crop((int(left), int(top), int(right), int(bottom)))

    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    cropped.save(cache_path)
    return cropped.resize(target_size, Image.LANCZOS)
```

**Step 3: Run existing tile tests to see what breaks**

```bash
.venv/bin/pytest tests/test_tiles.py -v
```

Expected: `test_fetch_map_tile_returns_rgb_image` and `test_fetch_map_tile_uses_cache` fail (wrong signature — `token` param removed).

**Step 4: Update `tests/test_tiles.py`**

Replace the two fetch tests (keep the two `lat_lng_to_tile` tests unchanged):

```python
def test_fetch_map_tile_returns_rgb_image(tmp_path):
    """fetch_map_tile returns a PIL Image in RGB mode."""
    bounds = {
        "lat_min": 37.75, "lat_max": 37.79,
        "lng_min": -122.45, "lng_max": -122.40,
    }
    fake_tile = Image.new("RGB", (256, 256), color=(20, 20, 30))
    import io
    tile_bytes = io.BytesIO()
    fake_tile.save(tile_bytes, format="PNG")
    tile_content = tile_bytes.getvalue()

    mock_resp = MagicMock()
    mock_resp.content = tile_content
    mock_resp.raise_for_status = MagicMock()

    cache_path = str(tmp_path / "tile.png")
    with patch("requests.get", return_value=mock_resp):
        img = fetch_map_tile(bounds, zoom=13, cache_path=cache_path,
                             target_size=(540, 540))

    assert img.mode == "RGB"
    assert img.size == (540, 540)


def test_fetch_map_tile_uses_cache(tmp_path):
    """Second call uses cached file, makes no HTTP requests."""
    cache_path = str(tmp_path / "tile.png")
    fake = Image.new("RGB", (540, 540), color=(10, 10, 20))
    fake.save(cache_path)

    with patch("requests.get") as mock_get:
        img = fetch_map_tile(
            bounds={"lat_min": 37.75, "lat_max": 37.79,
                    "lng_min": -122.45, "lng_max": -122.40},
            zoom=13, cache_path=cache_path, target_size=(540, 540)
        )
        mock_get.assert_not_called()

    assert img.size == (540, 540)
```

**Step 5: Update `export.py`**

In `main()`, replace the tile fetching block. Remove the `mapbox_token` guard entirely (CARTO needs no token). Keep the `--no-map` flag and the `try/except`:

```python
    # Composite map background
    if args.use_map:
        from config import BG_COLOR, MAP_TILE_URL
        cache = MAP_TILE_CACHE if not args.preview else MAP_TILE_CACHE.replace(".png", "-preview.png")
        zoom = 13 if not args.preview else 11
        try:
            tile = fetch_map_tile(
                bounds=renderer.bounds,
                zoom=zoom,
                cache_path=cache,
                target_size=(w, h),
                url_template=MAP_TILE_URL,
            )
            bg = composite_map_background(tile, (w, h), MAP_TILE_OPACITY, BG_COLOR)
            bg_arr = np.array(bg, dtype=np.float32)
            route_arr = img_array.astype(np.float32)
            result = 255 - ((255 - bg_arr) * (255 - route_arr) / 255)
            img = Image.fromarray(np.clip(result, 0, 255).astype(np.uint8), mode="RGB")
        except Exception as e:
            print(f"Map tile skipped: {e}")
```

Also update the import at the top of `export.py` — remove `MAP_TILE_ZOOM` from the config import, add `MAP_TILE_URL`:

```python
from config import (
    CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, OUTPUT_DIR,
    MAP_TILE_OPACITY, MAP_TILE_CACHE,
    MAP_TILE_URL,
    MAP_FONT_PATH, MAP_FONT_URL,
)
```

**Step 6: Run all tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all 40 pass.

**Step 7: Commit**

```bash
git add src/tiles.py tests/test_tiles.py export.py config.py
git commit -m "feat: CARTO dark no-labels tiles, pixel-accurate bounds crop, remove Mapbox dependency"
```

---

### Task 4: Typography scaling

**Files:**
- Modify: `src/typography.py`

Background: Font sizes are currently hardcoded at 48/36px. On a 5400×5400 poster those are tiny (0.16" tall). Sizes need to derive from `img.size` so they're readable at any resolution.

**Step 1: Write the failing test**

Add to `tests/test_typography.py`:

```python
def test_render_typography_scales_with_image_size(tmp_path):
    """Larger images should produce larger text (more changed pixels)."""
    font_path = str(tmp_path / "font.ttf")
    runs = _make_runs(n=5)

    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        small_img = Image.new("RGB", (200, 200), color=(0, 0, 0))
        render_typography(small_img, runs, font_path=font_path)
        small_changed = np.count_nonzero(np.array(small_img).sum(axis=2))

        large_img = Image.new("RGB", (800, 800), color=(0, 0, 0))
        render_typography(large_img, runs, font_path=font_path)
        large_changed = np.count_nonzero(np.array(large_img).sum(axis=2))

    assert large_changed > small_changed * 4
```

**Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_typography.py::test_render_typography_scales_with_image_size -v
```

Expected: FAIL — both images use the same hardcoded 48/36px fonts, so `large_changed` won't be 4× bigger.

**Step 3: Update `src/typography.py`**

Remove the `large_size` and `small_size` keyword args; derive all sizing from `img.size` internally:

```python
def render_typography(img, sf_runs, font_path,
                      text_color=(255, 240, 180)):
    """
    Render year range, run count, and distance onto img (PIL Image).
    Font sizes and margins scale automatically with image dimensions.
    Text is right-aligned in the bottom-right corner.
    Returns the modified image.
    """
    years = sorted({r["start_date"][:4] for r in sf_runs})
    year_range = f"{years[0]} \u2013 {years[-1]}" if len(years) > 1 else years[0]
    total_runs = f"{len(sf_runs):,} runs"
    total_miles = sum(r["distance"] for r in sf_runs) / METERS_PER_MILE
    total_dist = f"{total_miles:,.0f} mi"

    w, h = img.size
    large_size = max(12, h // 27)    # ~200px at 5400, 20px at 540
    small_size = max(10, h // 40)    # ~135px at 5400, 13px at 540
    margin = max(10, h // 25)        # ~216px at 5400, 22px at 540
    shadow_offset = max(2, h // 1800)

    draw = ImageDraw.Draw(img)
    font_large = _load_font(font_path, large_size)
    font_small = _load_font(font_path, small_size)

    shadow = (0, 0, 0)
    lines = [
        (year_range, font_large),
        (total_runs, font_small),
        (total_dist, font_small),
    ]

    y = h - margin
    for text, font in reversed(lines):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = w - margin - text_w
        y -= text_h
        draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow)
        draw.text((x, y), text, font=font, fill=text_color)
        y -= max(4, h // 450)  # line gap scales too

    return img
```

**Step 4: Run all tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all 41 pass.

Note: the existing typography tests all mock `_load_font` to return `ImageFont.load_default()`, which ignores the `size` arg — they won't break. The new scaling test works because PIL default font has some fixed small size, so the rendered text area grows with the image (more text pixels visible at larger canvas since we call `textbbox` relative to canvas size and layout bottom-to-top).

**Step 5: Commit**

```bash
git add src/typography.py tests/test_typography.py
git commit -m "feat: typography scales with canvas size — readable at 300 DPI print"
```

---

### Task 5: Full test suite + preview render

**Step 1: Run all tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: 41 passed.

**Step 2: Preview render**

```bash
python export.py --preview
```

Expected: `output/poster-preview-TIMESTAMP.png` at 540×540. Open and verify:
- Black background ✓
- Routes shift from blue (lightly-run streets) → purple → pink (busy corridors) ✓
- Map tile visible as subtle dark road grid (no labels) ✓
  *(if MAPBOX_TOKEN was the reason before — CARTO tiles work without any token)*
- Typography readable in bottom-right at preview scale ✓

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete Phase 2 fixes — CARTO tiles, Mercator projection, typography scaling, blue/purple/pink ramp"
```
