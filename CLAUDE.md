# Strava Art — Developer Reference

This file is for Claude and developers who need to understand the codebase quickly.

## What it does

Fetches a user's Strava running activities, filters them to a geographic bounding box, and renders either a print-quality heatmap poster (PNG) or an animated timelapse MP4.

**Poster pipeline (`render.py`):**
```
auth.py          → writes tokens to .env (run once)
render.py        → orchestrates everything (--config sf|nyc selects city)
  src/fetcher.py → fetch & cache activities from Strava API
  src/processor.py → filter by city bounds + decode polylines
  src/renderer.py  → rasterize routes → post-process (bloom, grain, glow)
  src/tiles.py     → fetch & cache OpenStreetMap background tiles
  src/typography.py → render stats text + color legend
```

**Animation pipeline (`animate.py`):**
```
animate.py       → orchestrates animation (--config, --preview, --fetch, --output)
  src/animator.py  → cursor advance, canvas accumulation, dot rendering, ffmpeg pipe
  src/renderer.py  → pre-pass rasterization + canvas_to_rgb (reused)
  src/tiles.py     → map tile (reused)
  src/typography.py → live stats overlay (reused)
```

## File map

| File | Purpose |
|---|---|
| `config.py` | All tunable constants — canvas size, bounds, colors, effects, animation |
| `auth.py` | One-time OAuth flow — writes tokens to `.env` |
| `render.py` | Poster CLI — renders static print-quality PNG |
| `animate.py` | Animation CLI — renders MP4 timelapse |
| `src/fetcher.py` | `StravaClient` + `fetch_activities()` with incremental cache |
| `src/processor.py` | `filter_sf_runs()` centroid filter + `decode_runs()` polyline decoder |
| `src/renderer.py` | `StravaRenderer`: rasterize → density expand → hot bloom → color map |
| `src/animator.py` | Animation logic: cursor, accumulation, dot, ffmpeg pipe |
| `src/tiles.py` | Fetch and stitch CARTO map tiles |
| `src/typography.py` | Render year range / run count / distance / elevation + color legend |

## Adding a new city

The easiest approach is to create a `<city>_config.py` that inherits from `config.py` via `from config import *` and overrides the relevant values. Pass `--config <city>` to `render.py` or `animate.py` to use it.

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

**Note:** `animate.py` does not support `CANVAS_ROTATION_DEGREES != 0` — it will exit with an error if rotation is set. Animation is SF-only for now.

## Config knobs reference

### Canvas & bounds
- `CITY_BOUNDS` — geographic bounding box. All projection math derives from this.
- `CANVAS_WIDTH_PX` / `CANVAS_HEIGHT_PX` — final output canvas in pixels. When rotation is 0, must match Mercator aspect ratio of `CITY_BOUNDS`. When rotation != 0, this is the post-crop size; aspect ratio is enforced on the intermediate canvas instead.
- `CANVAS_ROTATION_DEGREES` — degrees counterclockwise to rotate the final output (cv2 convention). `0` = north-up (SF default). `29` = Manhattan-axis-up (NYC). When non-zero, renderer uses an oversized intermediate canvas and `rotate_and_crop()` is called in `render.py` after compositing.
- `CANVAS_RENDER_WIDTH` / `CANVAS_RENDER_HEIGHT` — intermediate (pre-rotation) canvas dimensions. `None` = use `CANVAS_WIDTH_PX` / `CANVAS_HEIGHT_PX` (no rotation). When set, the geo aspect ratio constraint applies to these dimensions, not the final canvas.
- `CANVAS_CROP_X` / `CANVAS_CROP_Y` — top-left pixel of the crop in the rotated intermediate canvas. `None` = centered crop. Set in city configs for non-centered framing (e.g. NYC trims more from the right than the left).
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

### Typography & legend
- `TYPOGRAPHY_SCALE` — overall size multiplier for all text and legend elements. `1.0` = SF default. Set smaller (e.g. `0.7`) for city configs with different canvas proportions.
- `TYPOGRAPHY_WIDTH_SCALE` — additional font-size multiplier applied on top of `TYPOGRAPHY_SCALE`. Narrows the text block without changing vertical spacing.
- `TYPOGRAPHY_X_OFFSET` — horizontal pixel offset for the text block in final canvas coordinates. Positive = toward right edge, negative = toward left. Scaled by the preview factor in `render.py` so it behaves correctly at both preview and full resolution.
- `LEGEND_POSITION` — horizontal placement of the color legend bar: `"center"` (default, centered on canvas) or `"left"` (margin-aligned to left edge).
- `LEGEND_WIDTH_SCALE` — additional width multiplier for the legend bar, applied on top of `TYPOGRAPHY_SCALE`. `1.0` = no change. `0.8` = 20% narrower.

### Map
- `MAP_TILE_ZOOM` — tile zoom level. 16 = default (~600 tiles). 17 = sharper (~2400 tiles, slow first download). Note: `render.py` currently hardcodes zoom 15 (full render) and 11 (preview) — editing this config value has no effect unless you also update `render.py`.
- `MAP_TILE_OPACITY` — how much the street grid shows through (0 = invisible, 1 = full).

### Animation
- `ANIMATION_FPS` — output frame rate. 60 = default.
- `ANIMATION_DRAWING_SPEED` — pixels/frame for middle runs (the fast constant-speed section). Tune to hit your target duration.
- `ANIMATION_DRAWING_SPEED_SLOW` — pixels/frame for the first and last run. Creates a slow-draw-in / slow-draw-out effect.
- `ANIMATION_SPEED_RAMP_RUNS` — number of runs over which speed linearly ramps from slow → fast after run 1 (and back before the last run).
- `ANIMATION_DOT_RADIUS` — cursor dot radius in pixels at `ANIMATION_OUTPUT_RESOLUTION`.
- `ANIMATION_DOT_BLUR` — Gaussian sigma for the dot halo. 0 = hard edge.
- `ANIMATION_DOT_BRIGHTNESS` — multiplier applied to the dot layer after blur. > 1 saturates the core white.
- `ANIMATION_HOLD_SECONDS` — seconds to hold on the final completed frame after the dot fades out.
- `ANIMATION_OUTPUT_RESOLUTION` — `(width, height)` of the MP4. Default `(1080, 1350)` = Instagram 4:5 portrait. `--preview` halves this.

## Key implementation notes

**Float32 accumulation** (`src/renderer.py`): `cv2.line` on a float32 canvas clips values to [0, 1]. Routes drawn repeatedly would plateau. Fix: each run is drawn onto a zeroed temp buffer, then *added* to the main canvas (`canvas += buf`). This allows values > 1, which encode density. The canvas is only normalized to [0, 1] when converting to image.

**Bloom is disabled in `render.py`**: The `--no-bloom` flag always passes `bloom=False` to `to_image()`. Regular bloom was removed as it caused halos on single isolated pixels. `hot_bloom` is kept — it fires only above `HOT_BLOOM_THRESHOLD`.

**Density expand pass order** in `renderer.to_image()`: rasterize → log1p normalize → gamma → density expand (Gaussian thickening) → hot bloom → color map → grain → vignette. Density expand runs after gamma on the gamma-corrected normalized canvas.

**Animation two-pass normalization** (`src/animator.py`): a pre-pass rasterizes all runs to compute `final_log_max = log1p(full_canvas).max()`. Each animation frame normalizes with this fixed anchor (`norm = log1p(canvas) / final_log_max`) so early dim frames and the completed final frame share the same color scale — the final frame matches the static poster exactly.

**Animation cursor**: `advance_cursor()` moves a cursor along pixel-space polylines by a pixel budget per frame, returning drawn sub-segments for rasterization and the new cursor position for dot placement. The last run decelerates over the final `out_w // 4` pixels (linear ramp to 1 px/frame), then the dot fades over 0.5 s before the hold frames begin.

**Token refresh** (`src/fetcher.py:_update_env_tokens`): when the access token expires mid-fetch, `StravaClient.refresh_access_token()` POSTs to Strava and writes the new tokens back to `.env` in-place. It only updates existing lines — auth.py must have written them first.

## Environment

- Python 3.14 (Homebrew), `.venv/` virtual environment
- Run tests: `.venv/bin/pytest tests/ -v`
- Worktrees: `.worktrees/` (project-local, in `.gitignore`)
