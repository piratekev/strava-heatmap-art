# Strava Art — Developer Reference

This file is for Claude and developers who need to understand the codebase quickly.

## What it does

Fetches Strava or Garmin running activities, filters them to a geographic bounding box, and renders either a print-quality heatmap poster (PNG) or an animated timelapse MP4.

**Poster pipeline (`render.py`):**
```
auth.py          → writes tokens to .env (run once)
render.py        → orchestrates everything (--config sf|nyc selects city)
  src/sources.py → --fetch dispatch on config.FETCH_SOURCE ("strava" | "garmin")
  src/fetcher.py → fetch & cache activities from Strava API
  src/garmin.py  → Garmin Connect fallback (converts to Strava schema)
  src/processor.py → filter by city bounds + decode polylines
  src/renderer.py  → rasterize routes → post-process (bloom, grain, glow)
  src/tiles.py     → fetch & cache OpenStreetMap background tiles
  src/typography.py → render stats text + color legend
```

**Animation pipeline (`animate.py`):**
```
animate.py       → orchestrates animation (--config, --preview, --fetch, --output)
  src/animator.py  → cursor advance, canvas accumulation, dot rendering, ffmpeg pipe
  src/renderer.py  → pre-pass rasterization + projection (reused)
  src/tiles.py     → map tile (reused)
  src/typography.py → font loader + legend (live stats live in src/animator.py)
```

## File map

| File | Purpose |
|---|---|
| `config.py` | All tunable constants — canvas size, bounds, colors, effects, animation |
| `auth.py` | One-time OAuth flow — writes tokens to `.env` |
| `render.py` | Poster CLI — renders static print-quality PNG |
| `export.py` | Backward-compatible poster CLI alias forwarding to `render.py` |
| `animate.py` | Animation CLI — renders MP4 timelapse |
| `garmin_fetch.py` | Standalone Garmin fetch CLI (`--since`, `--mfa` for non-TTY login) |
| `src/sources.py` | `fetch_from_source()` — routes `--fetch` to Strava or Garmin per `FETCH_SOURCE` |
| `src/fetcher.py` | `StravaClient` + full-history, ID-deduplicated cache reconciliation |
| `src/garmin.py` | Garmin Connect fetch → Strava-shaped records appended to `data/activities.json` |
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

**With rotation** (`CANVAS_ROTATION_DEGREES != 0`): the renderer first pads
`CITY_BOUNDS` in Mercator space to fit the unrotated framing rectangle
(`CANVAS_RENDER_WIDTH`/`HEIGHT`, or the final dimensions when unset). It then
expands that frame and those padded bounds for rotation:

```
render_w = W * abs(cos(θ)) + H * abs(sin(θ))
render_h = W * abs(sin(θ)) + H * abs(cos(θ))
```

The actual `renderer.bounds` Mercator aspect matches
`(renderer.width - 1) / (renderer.height - 1)`. Do not compare the oversized
canvas to the original, unpadded `CITY_BOUNDS`. The NYC regression test instantiates
the renderer with the real preset at preview and full sizes and verifies this.

**3. Activity filter** — `src/processor.py:filter_sf_runs()` uses `CITY_BOUNDS` directly; no code change needed. The function name still says "sf" — rename it if you care.

**4. Map tiles** — `src/tiles.py` derives tile coordinates from the renderer bounds (`renderer.bounds`), which come from `CITY_BOUNDS`. No change needed.

**Animation:** both modes reject `CANVAS_ROTATION_DEGREES != 0`, including the
built-in NYC preset. Other north-up cities require an even-pixel
`ANIMATION_OUTPUT_RESOLUTION` with a matching Mercator aspect.

## Config knobs reference

### Canvas & bounds
- `CITY_BOUNDS` — geographic bounding box. All projection math derives from this.
- `CANVAS_WIDTH_PX` / `CANVAS_HEIGHT_PX` — final output canvas in pixels. When rotation is 0, must match Mercator aspect ratio of `CITY_BOUNDS`. With rotation, these are the post-crop dimensions; the renderer pads the geographic frame before oversizing it to avoid distortion.
- `CANVAS_ROTATION_DEGREES` — degrees counterclockwise to rotate the final output (cv2 convention). `0` = north-up (SF default). `29` = Manhattan-axis-up (NYC). When non-zero, renderer uses an oversized intermediate canvas and `rotate_and_crop()` is called in `render.py` after compositing.
- `CANVAS_RENDER_WIDTH` / `CANVAS_RENDER_HEIGHT` — unrotated framing dimensions. `None` = use `CANVAS_WIDTH_PX` / `CANVAS_HEIGHT_PX`. With rotation, bounds are padded to this frame's aspect, then the intermediate canvas and bounds are expanded together.
- `CANVAS_CROP_X` / `CANVAS_CROP_Y` — top-left pixel of the crop in the rotated intermediate canvas. `None` = centered crop. Set in city configs for non-centered framing (e.g. NYC trims more from the right than the left).
- `PRINT_DPI` — DPI tag written to the PNG (affects print size, not pixel count).

### Color
- `ROUTE_COLOR_RAMP` — list of `(t, [R, G, B])` stops. `t` is a normalized density value [0, 1] after log1p compression and gamma. SF's default (`GAMMA=0.6`, green ramp) keeps single-run routes dim rather than lifting them toward the first color stop; raise the first stop's `t` if you want sparse routes more visible. NYC overrides this back to the original `GAMMA=0.4` / indigo-violet-pink ramp in `nyc_config.py` to keep its look unchanged.
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
- `HOT_BLOOM_THRESHOLD` — density cutoff (post-gamma) to trigger hot bloom. SF's default is 0.92 (paired with `GAMMA=0.6`) so the glow concentrates on the single hottest corridor; NYC overrides back to the older 0.75/`GAMMA=0.4` pairing.
- `HOT_BLOOM_SIGMA_MULT` — width of bloom Gaussian as a multiplier of `bloom_sigma_wide` in renderer.
- `HOT_BLOOM_STRENGTH` — screen-blend intensity of the bloom layer.

### Typography & legend
- `TYPOGRAPHY_SCALE` — overall size multiplier for all text and legend elements. `1.0` = SF default. Set smaller (e.g. `0.7`) for city configs with different canvas proportions.
- `TYPOGRAPHY_WIDTH_SCALE` — additional font-size multiplier applied on top of `TYPOGRAPHY_SCALE`. Narrows the text block without changing vertical spacing.
- `TYPOGRAPHY_X_OFFSET` — horizontal pixel offset for the text block in final canvas coordinates. Positive = toward right edge, negative = toward left. Scaled by the preview factor in `render.py` so it behaves correctly at both preview and full resolution.
- `LEGEND_POSITION` — horizontal placement of the color legend bar: `"center"` (default, centered on canvas) or `"left"` (margin-aligned to left edge).
- `LEGEND_WIDTH_SCALE` — additional width multiplier for the legend bar, applied on top of `TYPOGRAPHY_SCALE`. `1.0` = no change. `0.8` = 20% narrower.

### Map
- `MAP_TILE_ZOOM` / `MAP_PREVIEW_TILE_ZOOM` — poster/preview map zoom (17/11 by default), honored by `render.py` and its `export.py` alias. Animations currently hardcode zoom 15 for both modes and previews.
- Tile composition resamples overlapping row bands with Lanczos context rather than allocating a citywide native-resolution mosaic. Cache identity includes output size because cached basemaps are already resampled. Never disable Pillow's decompression-bomb protections to accommodate zoom-17 maps.
- A shared HTTP session reuses tile connections. Transient failures retry with backoff/Retry-After, and source tiles are cached under `data/map_tiles/` so interrupted downloads resume. Composed caches are replaced atomically.
- CARTO can return an HTTP-200 API-key placeholder; reject the observed error image on download and per-tile cache reads. Fresh downloads may require an authenticated `MAP_TILE_URL`; never treat a successful HTTP status alone as proof of a valid basemap.
- `MAP_ATTRIBUTION` — visible poster credit, also stored in PNG copyright metadata. Animation output does not yet use it. Update it when changing providers. Default: `© OpenStreetMap contributors, © CARTO`.
- `MAP_TILE_OPACITY` — how much the street grid shows through (0 = invisible, 1 = full).

### Animation
- `ANIMATION_FPS` — output frame rate. 60 = default.
- `ANIMATION_DRAWING_SPEED` — pixels/frame for middle runs (the fast constant-speed section). Tune to hit your target duration.
- `ANIMATION_DRAWING_SPEED_SLOW` — pixels/frame for the first and last run. Creates a slow-draw-in / slow-draw-out effect.
- `ANIMATION_SPEED_RAMP_RUNS` — number of runs over which speed linearly ramps from slow → fast after run 1 (and back before the last run).
- `ANIMATION_DOT_RADIUS` — cursor dot radius in pixels at `ANIMATION_OUTPUT_RESOLUTION`.
- `ANIMATION_DOT_BLUR` — Gaussian sigma for the dot halo. 0 = hard edge.
- `ANIMATION_DOT_BRIGHTNESS` — intended sequential dot brightness; `AnimConfig` currently omits it, so the CLI uses the animator's fallback of 1.0.
- `ANIMATION_HOLD_SECONDS` — seconds to hold on the final completed frame after the dot fades out.
- `ANIMATION_OUTPUT_RESOLUTION` — `(width, height)` of the MP4. Default `(1080, 1350)` = Instagram 4:5 portrait. `--preview` halves and rounds down to even dimensions, `(540, 674)`.
- `ANIMATION_PARALLEL_DURATION_S` — drawing duration for the longest route (15s); shorter routes finish sooner at the same pixel speed.
- `ANIMATION_PARALLEL_HOLD_S` — final hold and statistics fade (1s), also forced to 1s in preview.

## Key implementation notes

**Float32 accumulation** (`src/renderer.py`): `cv2.line` on a float32 canvas clips values to [0, 1]. Routes drawn repeatedly would plateau. Fix: each run is drawn onto a zeroed temp buffer, then *added* to the main canvas (`canvas += buf`). This allows values > 1, which encode density. The canvas is only normalized to [0, 1] when converting to image.

**Ordinary bloom is disabled in `render.py`**: `to_image()` receives `bloom=False`
because ordinary bloom caused halos on isolated pixels. `--no-bloom` is an alias
for `--no-hot-bloom` and disables the remaining hot-bloom pass. `--no-glow` controls
the separate broad colored glow.

**Density expand pass order** in `renderer.to_image()`: rasterize → log1p normalize → gamma → density expand (Gaussian thickening) → hot bloom → color map → colored glow → vignette → grain. Density expand runs after gamma on the gamma-corrected normalized canvas.

**Strava reconciliation**: `fetch_activities()` scans every activity page and
upserts by Strava ID, repairing old duplicates and replacing matching Garmin
fallbacks. Never use the last fetch time as Strava's `after`: that filters
activity start time and permanently hides delayed uploads. `cache_meta.json`
is informational, not a fetch cursor. `render.py --fetch` (or its `export.py`
alias) is the full resync path.

**OAuth and tests**: `auth.py` generates and validates a fresh state per flow,
ignores invalid callbacks, and closes the local server on completion or timeout.
Tests must never persist mock tokens to the real `.env`: `tests/conftest.py`
isolates working/home directories, disables dotenv, and blocks unmocked network.
CLI tests launch fresh processes with synthetic remote services and caches.
`tests/test_animation_cli.py` uses real ffmpeg/ffprobe to encode and decode both
modes with synthetic activities and mocked map/font services. It skips if the
system encoder/probe tools are absent.

**Garmin source** (`src/garmin.py`): `FETCH_SOURCE = "garmin"` (or `garmin_fetch.py`) pulls runs since the latest cached activity via the `garminconnect` library, or from 1970-01-01 for a missing/empty cache. `--since` overrides the start date for backfills. It converts activities to the subset of the Strava schema the pipeline reads (`sport_type`, `map.summary_polyline`, `distance`, `start_date`, …), tagged `source: "garmin"`. Dedupe is by Garmin ID (Strava's `external_id` is `garmin_ping_<id>`) or start time within 60 s. A later Strava fetch replaces Garmin entries with matching `external_id`. Login tokens live in `~/.garminconnect`; first login needs `GARMIN_EMAIL`/`GARMIN_PASSWORD` (prompt or `.env`) and MFA — without a TTY, run `garmin_fetch.py` once, then `garmin_fetch.py --mfa <code>` with the same `--since` if supplied.

**Animation normalization** (`src/animator.py`): a pre-pass rasterizes all runs
to compute `final_log_max = log1p(full_canvas).max()`. Frames use this fixed
anchor. The animation separately rasterizes segments and applies its own scaled
density-expand/hot-bloom passes. It does not reuse the poster's full effects
pipeline, and equal final accumulation / pixel-identical poster output must not
be assumed. Parallel mode uses a shared per-frame buffer for all routes.

**Animation cursor**: `advance_cursor()` moves a cursor along pixel-space polylines by a pixel budget per frame, returning drawn sub-segments for rasterization and the new cursor position for dot placement. The last run decelerates over the final `out_w // 4` pixels (linear ramp to 1 px/frame), then the dot fades over 0.5 s before the hold frames begin.

**Animation integration boundaries:** `animate.py --fetch` still calls Strava
directly instead of `fetch_from_source(FETCH_SOURCE)`. Maps are mandatory, fixed
at zoom 15, and currently omit video attribution. Sequential stats use traced
Haversine mileage; parallel final stats use cached activity distance. The CLI
does not create custom output parents; ffmpeg is an external system dependency.
See [animation status](docs/animation-status.md) for validated merge-readiness
gaps. The files in `docs/superpowers/` are historical design/planning records,
not current operating instructions.

**Token refresh** (`src/fetcher.py:_update_env_tokens`): when the access token expires mid-fetch, `StravaClient.refresh_access_token()` POSTs to Strava and writes the new tokens back to `.env` in-place. It only updates existing lines — auth.py must have written them first.

## Environment

- Python 3.14 (Homebrew), `.venv/` virtual environment
- Run tests: `.venv/bin/pytest tests/ -v`
- Worktrees: `.worktrees/` (project-local, in `.gitignore`)
