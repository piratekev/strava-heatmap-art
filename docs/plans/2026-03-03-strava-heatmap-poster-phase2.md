# Strava Heatmap Poster Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve the poster with a square canvas, density-adaptive color ramp, Mapbox tile background, and typography overlay.

**Architecture:** Incremental additions to the existing pipeline — `config.py` gets new constants, `renderer.py` gains auto-fit bounds + color ramp + dual-sigma bloom, two new modules `src/tiles.py` and `src/typography.py` are wired together in `export.py`.

**Tech Stack:** Python 3.14, existing deps (numpy, opencv, Pillow, scipy), Mapbox Static Tiles API, Montserrat TTF via Google Fonts GitHub

---

### Task 1: Square canvas + config updates

**Files:**
- Modify: `config.py`
- Modify: `.env.example`
- Modify: `tests/test_renderer.py`

**Step 1: Update `config.py`**

```python
# San Francisco bounding box
SF_BOUNDS = {
    "lat_min": 37.6999,
    "lat_max": 37.8324,
    "lng_min": -122.5270,
    "lng_max": -122.3480,
}

# Print canvas: 18x18" @ 300 DPI (square)
CANVAS_WIDTH_PX = 5400
CANVAS_HEIGHT_PX = 5400
PRINT_DPI = 300

# Density color ramp: (normalized_value, [R, G, B])
# Edit stops here to change the palette — no code changes needed
ROUTE_COLOR_RAMP = [
    (0.0, [255, 200,  80]),   # low density  → warm gold
    (0.5, [255, 240, 180]),   # mid density  → white-gold
    (1.0, [200, 230, 255]),   # high density → blue-white
]

# Background color
BG_COLOR = [10, 15, 30]

# Strava API
STRAVA_BASE_URL = "https://www.strava.com/api/v3"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_ACTIVITIES_PER_PAGE = 200

# Cache paths
CACHE_DIR = "data"
ACTIVITIES_CACHE_FILE = "data/activities.json"
CACHE_META_FILE = "data/cache_meta.json"

# Output
OUTPUT_DIR = "output"

# Mapbox
MAP_TILE_ZOOM = 13
MAP_TILE_OPACITY = 0.15
MAP_TILE_CACHE = "data/map_tile.png"
MAP_FONT_PATH = "data/fonts/Montserrat-Light.ttf"
MAP_FONT_URL = "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Light.ttf"
```

**Step 2: Add `MAPBOX_TOKEN` to `.env.example`**

```
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
STRAVA_ACCESS_TOKEN=your_access_token
STRAVA_REFRESH_TOKEN=your_refresh_token
MAPBOX_TOKEN=your_mapbox_token
```

**Step 3: Update the renderer fixture and affected tests in `tests/test_renderer.py`**

The fixture changes from 540×720 to **540×540** (1/10 scale of new square canvas). Update every hardcoded pixel coordinate:

```python
@pytest.fixture
def renderer():
    return StravaRenderer(width=540, height=540)  # 1/10 scale for tests


def test_project_sf_center_to_canvas_center(renderer):
    center_lat = (SF_BOUNDS["lat_min"] + SF_BOUNDS["lat_max"]) / 2
    center_lng = (SF_BOUNDS["lng_min"] + SF_BOUNDS["lng_max"]) / 2
    x, y = renderer.project(center_lat, center_lng)
    assert abs(x - 270) < 30
    assert abs(y - 270) < 30  # was 360


def test_project_top_left_corner(renderer):
    x, y = renderer.project(SF_BOUNDS["lat_min"], SF_BOUNDS["lng_min"])
    assert x < 100
    assert y > 490  # was 620 — near bottom of 540px canvas


def test_canvas_initialized_to_zero(renderer):
    assert renderer.canvas.shape == (540, 540)  # was (720, 540)
    assert renderer.canvas.dtype == np.float32
    assert renderer.canvas.max() == 0.0


def test_full_resolution_canvas():
    r = StravaRenderer()
    assert r.canvas.shape == (CANVAS_HEIGHT_PX, CANVAS_WIDTH_PX)  # (5400, 5400)


def test_to_image_returns_rgb_array(renderer):
    renderer.rasterize_run([(37.76, -122.47), (37.77, -122.44)])
    img = renderer.to_image()
    assert img.shape == (540, 540, 3)  # was (720, 540, 3)
    assert img.dtype == np.uint8


def test_vignette_darkens_corners_vs_center(renderer):
    renderer.canvas[:] = 5.0
    img = renderer.to_image(bloom=False, vignette=True, grain=False)
    center = int(img[270, 270].mean())  # was [360, 270]
    corner = int(img[10, 10].mean())
    assert corner < center
```

**Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all 26 tests PASS (shape and coordinate assertions now match square canvas).

**Step 5: Commit**

```bash
git add config.py .env.example tests/test_renderer.py
git commit -m "feat: square 18x18 canvas, color ramp config, Mapbox config constants"
```

---

### Task 2: Auto-fit bounds

**Files:**
- Modify: `src/renderer.py`
- Modify: `tests/test_renderer.py`

**Step 1: Write the failing tests**

Add to `tests/test_renderer.py`:

```python
def test_set_bounds_updates_projection():
    """After set_bounds(), project() maps run extent to canvas edges."""
    r = StravaRenderer(width=540, height=540)
    runs = [{"coords": [(37.70, -122.50), (37.80, -122.40)]}]
    r.set_bounds(runs, padding=0.0)
    # SW corner should project near bottom-left
    x, y = r.project(37.70, -122.50)
    assert x < 10
    assert y > 530
    # NE corner should project near top-right
    x, y = r.project(37.80, -122.40)
    assert x > 530
    assert y < 10


def test_set_bounds_adds_padding():
    """Padding pushes route extents inward from canvas edges."""
    r = StravaRenderer(width=540, height=540)
    runs = [{"coords": [(37.70, -122.50), (37.80, -122.40)]}]
    r.set_bounds(runs, padding=0.1)
    x, y = r.project(37.70, -122.50)
    assert x > 20   # inset from left edge due to padding
    assert y < 520  # inset from bottom edge due to padding


def test_set_bounds_defaults_to_sf_bounds():
    """Renderer without set_bounds() uses SF_BOUNDS (existing behaviour)."""
    r = StravaRenderer(width=540, height=540)
    center_lat = (SF_BOUNDS["lat_min"] + SF_BOUNDS["lat_max"]) / 2
    center_lng = (SF_BOUNDS["lng_min"] + SF_BOUNDS["lng_max"]) / 2
    x, y = r.project(center_lat, center_lng)
    assert abs(x - 270) < 30
    assert abs(y - 270) < 30
```

**Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_renderer.py::test_set_bounds_updates_projection -v
```

Expected: `AttributeError: 'StravaRenderer' object has no attribute 'set_bounds'`

**Step 3: Implement `set_bounds()` in `src/renderer.py`**

Replace the import and `__init__` / `project()` methods:

```python
from config import SF_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, ROUTE_COLOR_RAMP, BG_COLOR


class StravaRenderer:
    def __init__(self, width=CANVAS_WIDTH_PX, height=CANVAS_HEIGHT_PX):
        self.width = width
        self.height = height
        self.canvas = np.zeros((height, width), dtype=np.float32)
        self.bounds = SF_BOUNDS.copy()  # default; overridden by set_bounds()

    def set_bounds(self, runs, padding=0.05):
        """Compute lat/lng extent from run coords and store with padding."""
        all_lats = [lat for run in runs for lat, lng in run["coords"]]
        all_lngs = [lng for run in runs for lat, lng in run["coords"]]
        lat_min, lat_max = min(all_lats), max(all_lats)
        lng_min, lng_max = min(all_lngs), max(all_lngs)
        lat_pad = (lat_max - lat_min) * padding
        lng_pad = (lng_max - lng_min) * padding
        self.bounds = {
            "lat_min": lat_min - lat_pad,
            "lat_max": lat_max + lat_pad,
            "lng_min": lng_min - lng_pad,
            "lng_max": lng_max + lng_pad,
        }

    def project(self, lat, lng):
        """Map (lat, lng) to (x, y) pixel coordinates using current bounds."""
        x = int((lng - self.bounds["lng_min"]) /
                (self.bounds["lng_max"] - self.bounds["lng_min"]) * (self.width - 1))
        y = int((self.bounds["lat_max"] - lat) /
                (self.bounds["lat_max"] - self.bounds["lat_min"]) * (self.height - 1))
        return x, y
```

**Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests PASS.

**Step 5: Commit**

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "feat: auto-fit bounds with padding, set_bounds() replaces static SF_BOUNDS in projection"
```

---

### Task 3: 2px lines + density color ramp

**Files:**
- Modify: `src/renderer.py`
- Modify: `tests/test_renderer.py`

**Step 1: Write the failing tests**

Add to `tests/test_renderer.py`:

```python
def test_color_ramp_low_density_is_gold(renderer):
    """A single-pass pixel should be closer to warm gold than blue."""
    renderer.rasterize_run([(37.76, -122.47), (37.77, -122.44)])
    img = renderer.to_image(bloom=False, vignette=False, grain=False)
    # Find the brightest pixel
    brightness = img.mean(axis=2)
    y, x = np.unravel_index(brightness.argmax(), brightness.shape)
    r, g, b = img[y, x]
    # Gold: R > B. Blue-white: B > R. Low density → gold.
    assert int(r) >= int(b)


def test_color_ramp_high_density_shifts_toward_blue(renderer):
    """Many overlapping runs should shift color toward blue-white."""
    coords = [(37.76, -122.47), (37.77, -122.44)]
    for _ in range(50):
        renderer.rasterize_run(coords)
    img = renderer.to_image(bloom=False, vignette=False, grain=False)
    brightness = img.mean(axis=2)
    y, x = np.unravel_index(brightness.argmax(), brightness.shape)
    r, g, b = img[y, x]
    # High density → blue-white: B should be significant
    assert int(b) > 150
```

**Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_renderer.py::test_color_ramp_low_density_is_gold -v
```

Expected: FAIL — `to_image()` still uses single ROUTE_COLOR.

**Step 3: Update `src/renderer.py`**

Remove the `BG_COLOR` and `ROUTE_COLOR` class attributes. Replace the color-blending section of `to_image()` with ramp interpolation. Update `rasterize_run()` thickness to 2:

```python
import numpy as np
import cv2
import os
from PIL import Image
from scipy.ndimage import gaussian_filter
from config import SF_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, ROUTE_COLOR_RAMP, BG_COLOR


def _ramp_colors(norm, ramp):
    """Vectorized color ramp: for each pixel in norm [0,1], return interpolated RGB."""
    result = np.zeros((*norm.shape, 3), dtype=np.float32)
    for i in range(len(ramp) - 1):
        t0, c0 = ramp[i]
        t1, c1 = ramp[i + 1]
        in_seg = (norm >= t0) & (norm <= t1) if i == len(ramp) - 2 else (norm >= t0) & (norm < t1)
        alpha = np.where(in_seg, (norm - t0) / (t1 - t0), 0.0)
        for c in range(3):
            route_c = c0[c] * (1 - alpha) + c1[c] * alpha
            result[:, :, c] += np.where(in_seg, route_c, 0.0)
    return result


class StravaRenderer:
    def __init__(self, width=CANVAS_WIDTH_PX, height=CANVAS_HEIGHT_PX):
        self.width = width
        self.height = height
        self.canvas = np.zeros((height, width), dtype=np.float32)
        self.bounds = SF_BOUNDS.copy()

    # ... set_bounds(), project() unchanged ...

    def rasterize_run(self, coords, weight=1.0):
        """Draw anti-aliased route onto the density canvas."""
        if len(coords) < 2:
            return
        points = [self.project(lat, lng) for lat, lng in coords]
        buf = np.zeros((self.height, self.width), dtype=np.float32)
        for i in range(len(points) - 1):
            cv2.line(buf, points[i], points[i + 1],
                     color=weight, thickness=2, lineType=cv2.LINE_AA)
        self.canvas += buf

    def to_image(self, bloom=True, bloom_sigma_tight=4.0, bloom_sigma_wide=16.0,
                 bloom_strength=0.6, vignette=True, vignette_strength=0.5,
                 grain=True, grain_amount=0.025):
        """Normalize density canvas, apply color ramp and effects. Returns HxWx3 uint8."""
        bg = np.array(BG_COLOR, dtype=np.float32)
        max_val = self.canvas.max()
        if max_val == 0:
            norm = self.canvas.copy()
        else:
            norm = np.log1p(self.canvas) / np.log1p(max_val)

        if bloom:
            tight = gaussian_filter(norm, sigma=bloom_sigma_tight)
            wide = gaussian_filter(norm, sigma=bloom_sigma_wide)
            bloom_layer = tight * 0.4 + wide * 0.6
            norm = 1 - (1 - norm) * (1 - bloom_layer * bloom_strength)

        route_colors = _ramp_colors(norm, ROUTE_COLOR_RAMP)
        rgb = np.zeros((self.height, self.width, 3), dtype=np.float32)
        for c in range(3):
            rgb[:, :, c] = bg[c] * (1 - norm) + route_colors[:, :, c] * norm

        if vignette:
            mask = self._make_vignette(strength=vignette_strength)
            rgb *= mask[:, :, np.newaxis]

        if grain:
            noise = np.random.normal(0, grain_amount * 255, rgb.shape).astype(np.float32)
            rgb += noise

        return np.clip(rgb, 0, 255).astype(np.uint8)
```

Note: `_make_vignette()`, `rasterize_all()`, and `save()` are unchanged.

**Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests PASS including the two new color ramp tests.

Note: `test_to_image_background_is_dark` checks `img.mean() < 20`. With bloom defaults enabled, the wide sigma (16px) on an empty canvas returns all zeros, so background stays dark — should still pass. If it fails, call `to_image(bloom=False)` in that test.

**Step 5: Commit**

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "feat: 2px line weight, density color ramp (gold→white-gold→blue-white), dual-sigma bloom"
```

---

### Task 4: Mapbox tile background

**Files:**
- Create: `src/tiles.py`
- Create: `tests/test_tiles.py`

**Step 1: Write the failing tests**

Create `tests/test_tiles.py`:

```python
import json
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image
from src.tiles import lat_lng_to_tile, fetch_map_tile


def test_lat_lng_to_tile_sf_center():
    """SF center at zoom 13 should produce tile within expected range."""
    x, y = lat_lng_to_tile(37.77, -122.42, zoom=13)
    # Rough expected tile for SF at zoom 13
    assert 1307 <= x <= 1310
    assert 3165 <= y <= 3168


def test_lat_lng_to_tile_zoom_doubles_range():
    """Each zoom increment doubles tile coordinates."""
    x0, y0 = lat_lng_to_tile(37.77, -122.42, zoom=12)
    x1, y1 = lat_lng_to_tile(37.77, -122.42, zoom=13)
    assert x1 == x0 * 2 or x1 == x0 * 2 + 1
    assert y1 == y0 * 2 or y1 == y0 * 2 + 1


def test_fetch_map_tile_returns_rgb_image(tmp_path):
    """fetch_map_tile returns a PIL Image in RGB mode."""
    bounds = {
        "lat_min": 37.75, "lat_max": 37.79,
        "lng_min": -122.45, "lng_max": -122.40,
    }
    # Create a fake 512x512 tile PNG
    fake_tile = Image.new("RGB", (512, 512), color=(20, 20, 30))
    import io
    tile_bytes = io.BytesIO()
    fake_tile.save(tile_bytes, format="PNG")
    tile_bytes.seek(0)

    mock_resp = MagicMock()
    mock_resp.content = tile_bytes.read()
    mock_resp.raise_for_status = MagicMock()

    cache_path = str(tmp_path / "tile.png")
    with patch("requests.get", return_value=mock_resp):
        img = fetch_map_tile(bounds, zoom=13, token="fake", cache_path=cache_path,
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
            zoom=13, token="fake", cache_path=cache_path, target_size=(540, 540)
        )
        mock_get.assert_not_called()

    assert img.size == (540, 540)
```

**Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_tiles.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.tiles'`

**Step 3: Implement `src/tiles.py`**

```python
import math
import os
import requests
from PIL import Image
import io


def lat_lng_to_tile(lat, lng, zoom):
    """Convert lat/lng to Mapbox tile (x, y) at given zoom."""
    n = 2 ** zoom
    x = int((lng + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.asinh(math.tan(lat_rad)) / math.pi) / 2 * n)
    return x, y


def fetch_map_tile(bounds, zoom, token, cache_path, target_size,
                   style="mapbox/dark-v11", tile_size=512):
    """
    Fetch Mapbox tiles covering bounds, stitch, resize to target_size.
    Caches result to cache_path — subsequent calls return cached image.
    """
    if os.path.exists(cache_path):
        img = Image.open(cache_path).convert("RGB")
        return img.resize(target_size, Image.LANCZOS)

    x_min, y_max = lat_lng_to_tile(bounds["lat_min"], bounds["lng_min"], zoom)
    x_max, y_min = lat_lng_to_tile(bounds["lat_max"], bounds["lng_max"], zoom)

    cols = x_max - x_min + 1
    rows = y_max - y_min + 1
    stitched = Image.new("RGB", (cols * tile_size, rows * tile_size))

    base_url = f"https://api.mapbox.com/styles/v1/{style}/tiles/{tile_size}"
    for tx in range(x_min, x_max + 1):
        for ty in range(y_min, y_max + 1):
            url = f"{base_url}/{zoom}/{tx}/{ty}?access_token={token}"
            resp = requests.get(url)
            resp.raise_for_status()
            tile_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            px = (tx - x_min) * tile_size
            py = (ty - y_min) * tile_size
            stitched.paste(tile_img, (px, py))

    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    stitched.save(cache_path)

    return stitched.resize(target_size, Image.LANCZOS)
```

**Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_tiles.py -v
```

Expected: all 4 PASSED.

**Step 5: Commit**

```bash
git add src/tiles.py tests/test_tiles.py
git commit -m "feat: Mapbox tile fetcher with stitch and cache"
```

---

### Task 5: Typography overlay

**Files:**
- Create: `src/typography.py`
- Create: `tests/test_typography.py`

**Step 1: Write the failing tests**

Create `tests/test_typography.py`:

```python
import numpy as np
import pytest
from unittest.mock import patch
from PIL import Image, ImageFont
from src.typography import render_typography, _download_font


def _make_runs(n=10, year_start=2021, year_end=2024):
    """Build minimal sf_runs list for typography tests."""
    runs = []
    for i in range(n):
        year = year_start + (i % (year_end - year_start + 1))
        runs.append({
            "start_date": f"{year}-06-15T08:00:00Z",
            "distance": 10000.0,  # 10km = ~6.2 miles each
        })
    return runs


def test_render_typography_changes_pixels(tmp_path):
    """render_typography should modify the image (some pixels change)."""
    font_path = str(tmp_path / "font.ttf")
    img = Image.new("RGB", (540, 540), color=(10, 15, 30))
    before = np.array(img).copy()

    # Use a default PIL font (no file needed) for the test
    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        result = render_typography(img, _make_runs(), font_path=font_path)

    after = np.array(result)
    assert not np.array_equal(before, after)


def test_render_typography_text_in_bottom_right(tmp_path):
    """Text should appear in the bottom-right quadrant."""
    font_path = str(tmp_path / "font.ttf")
    img = Image.new("RGB", (540, 540), color=(10, 15, 30))
    before = np.array(img).copy()

    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        result = render_typography(img, _make_runs(), font_path=font_path)

    after = np.array(result)
    diff = (after.astype(int) - before.astype(int)).sum(axis=2)
    # Bottom-right quadrant should have more changed pixels than top-left
    h, w = diff.shape
    bottom_right = diff[h//2:, w//2:].sum()
    top_left = diff[:h//2, :w//2].sum()
    assert bottom_right > top_left


def test_render_typography_shows_miles(tmp_path):
    """Distance should be in miles, not km."""
    font_path = str(tmp_path / "font.ttf")
    # 10 runs × 10km = ~62.1 miles
    runs = _make_runs(n=10)

    captured = {}
    original_load = __import__('src.typography', fromlist=['_load_font'])._load_font

    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        with patch("PIL.ImageDraw.ImageDraw.text") as mock_text:
            img = Image.new("RGB", (540, 540), color=(10, 15, 30))
            render_typography(img, runs, font_path=font_path)
            all_text = " ".join(str(call) for call in mock_text.call_args_list)
            assert "mi" in all_text


def test_render_typography_year_range_from_sf_runs(tmp_path):
    """Year range derived from SF runs, not all activities."""
    font_path = str(tmp_path / "font.ttf")
    runs = _make_runs(year_start=2021, year_end=2024)

    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        with patch("PIL.ImageDraw.ImageDraw.text") as mock_text:
            img = Image.new("RGB", (540, 540), color=(10, 15, 30))
            render_typography(img, runs, font_path=font_path)
            all_text = " ".join(str(call) for call in mock_text.call_args_list)
            assert "2021" in all_text
            assert "2024" in all_text
```

**Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_typography.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.typography'`

**Step 3: Implement `src/typography.py`**

```python
import os
import urllib.request
from PIL import Image, ImageDraw, ImageFont


METERS_PER_MILE = 1609.344


def _download_font(font_path, url):
    """Download font TTF to font_path if not already cached."""
    os.makedirs(os.path.dirname(font_path), exist_ok=True)
    if not os.path.exists(font_path):
        print(f"Downloading font to {font_path}...")
        urllib.request.urlretrieve(url, font_path)


def _load_font(font_path, size):
    """Load Montserrat TTF at given size, fall back to PIL default."""
    try:
        return ImageFont.truetype(font_path, size)
    except (OSError, IOError):
        return ImageFont.load_default()


def render_typography(img, sf_runs, font_path,
                      margin=60, text_color=(255, 240, 180),
                      large_size=48, small_size=36):
    """
    Render year range, run count, and distance onto img (PIL Image).
    Text is right-aligned in the bottom-right corner.
    Returns the modified image.
    """
    years = sorted({r["start_date"][:4] for r in sf_runs})
    year_range = f"{years[0]} – {years[-1]}" if len(years) > 1 else years[0]
    total_runs = f"{len(sf_runs):,} runs"
    total_miles = sum(r["distance"] for r in sf_runs) / METERS_PER_MILE
    total_dist = f"{total_miles:,.0f} mi"

    draw = ImageDraw.Draw(img)
    font_large = _load_font(font_path, large_size)
    font_small = _load_font(font_path, small_size)

    w, h = img.size
    shadow = (0, 0, 0)
    shadow_offset = 2

    lines = [
        (year_range, font_large),
        (total_runs, font_small),
        (total_dist, font_small),
    ]

    # Lay out bottom to top
    y = h - margin
    for text, font in reversed(lines):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = w - margin - text_w
        y -= text_h
        # Shadow
        draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow)
        # Text
        draw.text((x, y), text, font=font, fill=text_color)
        y -= 12  # line gap

    return img
```

**Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_typography.py -v
```

Expected: all 4 PASSED.

**Step 5: Commit**

```bash
git add src/typography.py tests/test_typography.py
git commit -m "feat: typography overlay — year range, run count, distance in miles"
```

---

### Task 6: Wire up export.py

**Files:**
- Modify: `export.py`

No new tests needed — this is a thin CLI integration of already-tested modules.

**Step 1: Rewrite `export.py`**

```python
#!/usr/bin/env python3
"""
Generate and save the SF running heatmap poster.

Usage:
    python export.py                 # full 300 DPI render
    python export.py --preview       # 1/10 scale for quick iteration
    python export.py --fetch         # fetch new activities first
    python export.py --no-map        # skip Mapbox background tile
    python export.py --no-bloom --no-grain
"""
import argparse
import json
import os
from datetime import datetime
from dotenv import load_dotenv

from src.fetcher import StravaClient, fetch_activities
from src.processor import filter_sf_runs, decode_runs
from src.renderer import StravaRenderer
from src.tiles import fetch_map_tile
from src.typography import render_typography, _download_font
from config import (
    CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, OUTPUT_DIR,
    MAP_TILE_ZOOM, MAP_TILE_OPACITY, MAP_TILE_CACHE,
    MAP_FONT_PATH, MAP_FONT_URL,
)
from PIL import Image
import numpy as np


def composite_map_background(tile_img, canvas_size, opacity, bg_color):
    """Blend Mapbox tile onto solid background at given opacity."""
    bg = Image.new("RGB", canvas_size, tuple(int(c) for c in bg_color))
    tile = tile_img.resize(canvas_size, Image.LANCZOS)
    return Image.blend(bg, tile, alpha=opacity)


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Generate SF running heatmap poster")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--preview", action="store_true", help="1/10 scale for speed")
    parser.add_argument("--no-bloom", dest="bloom", action="store_false", default=True)
    parser.add_argument("--no-vignette", dest="vignette", action="store_false", default=True)
    parser.add_argument("--no-grain", dest="grain", action="store_false", default=True)
    parser.add_argument("--no-map", dest="use_map", action="store_false", default=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if args.fetch:
        print("Fetching activities from Strava...")
        client = StravaClient.from_env()
        fetch_activities(client)

    with open("data/activities.json") as f:
        activities = json.load(f)

    sf_runs = filter_sf_runs(activities)
    runs = decode_runs(sf_runs)
    print(f"Rendering {len(runs)} SF runs...")

    scale = 0.1 if args.preview else 1.0
    w = int(CANVAS_WIDTH_PX * scale)
    h = int(CANVAS_HEIGHT_PX * scale)

    renderer = StravaRenderer(width=w, height=h)
    renderer.set_bounds(runs, padding=0.05)
    renderer.rasterize_all(runs)

    img_array = renderer.to_image(
        bloom=args.bloom, vignette=args.vignette, grain=args.grain
    )
    img = Image.fromarray(img_array, mode="RGB")

    # Composite Mapbox tile background
    if args.use_map:
        mapbox_token = os.environ.get("MAPBOX_TOKEN")
        if mapbox_token:
            from config import BG_COLOR
            cache = MAP_TILE_CACHE if not args.preview else MAP_TILE_CACHE.replace(".png", "-preview.png")
            try:
                tile = fetch_map_tile(
                    bounds=renderer.bounds,
                    zoom=MAP_TILE_ZOOM if not args.preview else MAP_TILE_ZOOM - 2,
                    token=mapbox_token,
                    cache_path=cache,
                    target_size=(w, h),
                )
                bg = composite_map_background(tile, (w, h), MAP_TILE_OPACITY, BG_COLOR)
                # Composite: use bg as base, blend routes on top
                bg_arr = np.array(bg, dtype=np.float32)
                route_arr = img_array.astype(np.float32)
                # Screen blend: preserve route glow, let map show through darks
                result = 255 - ((255 - bg_arr) * (255 - route_arr) / 255)
                img = Image.fromarray(np.clip(result, 0, 255).astype(np.uint8), mode="RGB")
            except Exception as e:
                print(f"Map tile skipped: {e}")
        else:
            print("MAPBOX_TOKEN not set — skipping map background")

    # Typography
    _download_font(MAP_FONT_PATH, MAP_FONT_URL)
    img = render_typography(img, sf_runs, font_path=MAP_FONT_PATH)

    # Save
    if args.output:
        out_path = args.output
    else:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = "-preview" if args.preview else ""
        out_path = os.path.join(OUTPUT_DIR, f"poster{suffix}-{ts}.png")

    dpi = 30 if args.preview else 300
    img.save(out_path, dpi=(dpi, dpi))
    print(f"Done. {out_path}")


if __name__ == "__main__":
    main()
```

**Step 2: Run full test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests PASS.

**Step 3: Run a preview render to visually verify**

```bash
.venv/bin/python export.py --preview
```

Expected: `output/poster-preview-TIMESTAMP.png` created. Open and verify:
- Routes fill the square canvas with padding on all sides
- Color shifts from gold (lightly-run streets) toward blue-white (Embarcadero, GGP)
- Mapbox dark basemap visible subtly underneath
- Year range / run count / distance in miles visible in bottom right

**Step 4: Commit**

```bash
git add export.py
git commit -m "feat: wire up auto-fit bounds, tiles, typography in export pipeline"
```

---

### Task 7: Run full test suite + final render

**Step 1: Run all tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests PASS.

**Step 2: Generate the full 300 DPI poster**

```bash
.venv/bin/python export.py
```

Expected: `output/poster-TIMESTAMP.png` at 5400×5400px.

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete Phase 2 — square canvas, color ramp, Mapbox tiles, typography"
```
