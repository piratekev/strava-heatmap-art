# Strava Art — Developer Reference

This file is for Claude and developers who need to understand the codebase quickly.

## What it does

Fetches a user's Strava running activities, filters them to a geographic bounding box, and renders a print-quality heatmap poster. The output is a high-DPI PNG with glowing neon routes on a dark map background.

**Pipeline:**
```
auth.py          → writes tokens to .env (run once)
export.py        → orchestrates everything (--config sf|nyc selects city)
  src/fetcher.py → fetch & cache activities from Strava API
  src/processor.py → filter by city bounds + decode polylines
  src/renderer.py  → rasterize routes → post-process (bloom, grain, glow)
  src/tiles.py     → fetch & cache OpenStreetMap background tiles
  src/typography.py → render stats text + color legend
```

## File map

| File | Purpose |
|---|---|
| `config.py` | All tunable constants — canvas size, bounds, colors, effects |
| `auth.py` | One-time OAuth flow — writes tokens to `.env` |
| `export.py` | CLI entry point — wires pipeline together |
| `src/fetcher.py` | `StravaClient` + `fetch_activities()` with incremental cache |
| `src/processor.py` | `filter_sf_runs()` centroid filter + `decode_runs()` polyline decoder |
| `src/renderer.py` | `StravaRenderer`: rasterize → density expand → hot bloom → color map |
| `src/tiles.py` | Fetch and stitch CARTO map tiles |
| `src/typography.py` | Render year range / run count / distance / elevation + color legend |

## Adding a new city

The easiest approach is to create a `<city>_config.py` that inherits from `config.py` via `from config import *` and overrides the relevant values. Pass `--config <city>` to `export.py` to use it.

Four values to set in your city config:

**1. `CITY_BOUNDS`** — update the four lat/lng values to your city's bounding box. Use [bboxfinder.com](http://bboxfinder.com).

**2. Canvas dimensions** — the canvas pixel ratio must match the Mercator aspect ratio of the bounds or the map distorts. Formula (no rotation):

```python
import math
lng_range = (lng_max - lng_min) * math.pi / 180
merc_range = math.asinh(math.tan(math.radians(lat_max))) - math.asinh(math.tan(math.radians(lat_min)))
aspect = lng_range / merc_range  # width / height
```

Set `CANVAS_WIDTH_PX` and `CANVAS_HEIGHT_PX` so `WIDTH / HEIGHT ≈ aspect`. The test `test_sf_bounds_aspect_ratio_matches_canvas` in `tests/test_renderer.py` validates this — update the expected ratio if you change cities.

**With rotation** (`CANVAS_ROTATION_DEGREES != 0`): the *intermediate* (pre-rotation) canvas must match the geo aspect, not the final canvas. The constraint becomes:

```
render_w = W * cos(θ) + H * sin(θ)
render_h = W * sin(θ) + H * cos(θ)
render_w / render_h == geo_aspect
```

Solve for `W/H` and pick pixel dimensions accordingly. See `test_nyc_intermediate_canvas_aspect_matches_bounds`.

**3. Activity filter** — `src/processor.py:filter_sf_runs()` uses `CITY_BOUNDS` directly; no code change needed. The function name still says "sf" — rename it if you care.

**4. Map tiles** — `src/tiles.py` derives tile coordinates from the renderer bounds (`renderer.bounds`), which come from `CITY_BOUNDS`. No change needed.

## Config knobs reference

### Canvas & bounds
- `CITY_BOUNDS` — geographic bounding box. All projection math derives from this.
- `CANVAS_WIDTH_PX` / `CANVAS_HEIGHT_PX` — output canvas in pixels. Must match Mercator aspect ratio of `CITY_BOUNDS` (or satisfy the rotation constraint when `CANVAS_ROTATION_DEGREES != 0`).
- `CANVAS_ROTATION_DEGREES` — degrees clockwise to rotate the final output. `0` = north-up (SF default). `29` = Manhattan-axis-up (NYC). When non-zero, renderer uses an oversized intermediate canvas and `rotate_and_crop()` is called in `export.py` after compositing.
- `PRINT_DPI` — DPI tag written to the PNG (affects print size, not pixel count).

### Color
- `ROUTE_COLOR_RAMP` — list of `(t, [R, G, B])` stops. `t` is a normalized density value [0, 1] after log1p compression and gamma. With `GAMMA=0.4`, a single-run route lands around `t ≈ 0.45`, so set the first stop there to control the lowest visible color.
- `BG_COLOR` — background RGB.

### Line drawing
- `GAMMA` — applied as `norm = norm ** GAMMA` before color mapping. Values < 1 lift dim routes; values > 1 suppress them. Affects effective range of `HOT_BLOOM_THRESHOLD`.
- `ROUTE_LINE_THICKNESS` — base stroke width. Thicker lines need a wider `HOT_BLOOM_SIGMA_MULT` to maintain glow proportion.
- `ROUTE_LINE_THICKNESS_50_BONUS` / `ROUTE_LINE_THICKNESS_10_BONUS` — extra stroke for top 50%/10% density routes. Only the highest applicable bonus fires (non-stacking).

### Density expand (thickens heavy corridors)
- `DENSITY_EXPAND_SIGMA` — Gaussian spread (px). Larger = blurrier thickening.
- `DENSITY_EXPAND_STRENGTH` — screen-blend intensity of the expanded layer.
- `DENSITY_EXPAND_POWER` — exponent applied to norm before expanding; concentrates effect on peaks.

### Hot bloom (glow on peak-density routes)
- `HOT_BLOOM_THRESHOLD` — density cutoff (post-gamma) to trigger hot bloom. With `GAMMA=0.4`, keep this at 0.75+ to avoid bloom firing on medium routes.
- `HOT_BLOOM_SIGMA_MULT` — width of bloom Gaussian as a multiplier of `bloom_sigma_wide` in renderer.
- `HOT_BLOOM_STRENGTH` — screen-blend intensity of the bloom layer.

### Map
- `MAP_TILE_ZOOM` — tile zoom level. 16 = default (~600 tiles). 17 = sharper (~2400 tiles, slow first download). Note: `export.py` currently hardcodes zoom 15 (full render) and 11 (preview) — editing this config value has no effect unless you also update `export.py`.
- `MAP_TILE_OPACITY` — how much the street grid shows through (0 = invisible, 1 = full).

## Key implementation notes

**Float32 accumulation** (`src/renderer.py`): `cv2.line` on a float32 canvas clips values to [0, 1]. Routes drawn repeatedly would plateau. Fix: each run is drawn onto a zeroed temp buffer, then *added* to the main canvas (`canvas += buf`). This allows values > 1, which encode density. The canvas is only normalized to [0, 1] when converting to image.

**Bloom is disabled in `export.py`**: The `--no-bloom` flag in `export.py` always passes `bloom=False` to `to_image()`. Regular bloom was removed as it caused halos on single isolated pixels. `hot_bloom` is kept — it fires only above `HOT_BLOOM_THRESHOLD`.

**Density expand pass order** in `renderer.to_image()`: rasterize → log1p normalize → gamma → density expand (Gaussian thickening) → hot bloom → color map → grain → vignette. Density expand runs after gamma on the gamma-corrected normalized canvas.

**Token refresh** (`src/fetcher.py:_update_env_tokens`): when the access token expires mid-fetch, `StravaClient.refresh_access_token()` POSTs to Strava and writes the new tokens back to `.env` in-place. It only updates existing lines — auth.py must have written them first.

## Environment

- Python 3.14 (Homebrew), `.venv/` virtual environment
- Run tests: `.venv/bin/pytest tests/ -v`
- Worktrees: `.worktrees/` (project-local, in `.gitignore`)
