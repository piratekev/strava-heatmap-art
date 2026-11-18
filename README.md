# Strava Heatmap Art

Generate a print-quality running heatmap poster or an animated timelapse MP4
from cached Strava or Garmin running data.

https://github.com/user-attachments/assets/8e8825a0-4cb1-4dc9-b96f-c4a8dcb9a426

![San Francisco running heatmap](sf.png)

NYC is also pre-configured — optimized to show the full NYC Marathon course (Staten Island → Brooklyn → Queens → Bronx → Manhattan), which one day they will let me run.

![New York City running heatmap](nyc.png)

Basemaps: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
© [CARTO](https://carto.com/attribution/).

---

## Prerequisites

- Python 3.11+
- A [Strava](https://www.strava.com) account with running activities, or
  Garmin Connect (see the Garmin onboarding section)

## Setup

```bash
git clone <this-repo>
cd strava-heatmap-art
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
source .venv/bin/activate
```

## Strava API setup

1. Go to [strava.com/settings/api](https://www.strava.com/settings/api)
2. Create an application (name and website can be anything)
3. Set **Authorization Callback Domain** to `localhost`
4. Copy your **Client ID** and **Client Secret** into `.env`:
   ```
   STRAVA_CLIENT_ID=12345
   STRAVA_CLIENT_SECRET=abc123...
   ```

## Authenticate

```bash
python auth.py
```

Your browser opens the Strava authorization page. Click **Authorize**. The page redirects to localhost and shows "Auth successful! You can close this tab." — your tokens are saved to `.env` automatically. Come back to the terminal; you'll see:

```
✓ Auth complete. Tokens saved to .env
  Athlete: Example Runner
  Run: python render.py --fetch
```

---

## Poster (`render.py`)

Generates a high-DPI PNG suitable for large-format printing.

**First run, or refresh/backfill** — fetch activities and render:
```bash
python render.py --fetch
```

Strava refreshes scan the complete activity history and merge by activity ID.
This catches delayed uploads, updates existing records, and removes duplicate
IDs without inflating your totals. `data/cache_meta.json` records the last
successful fetch for information only; its timestamp does not limit fetching.
Unmatched cached records, including Garmin fallback runs, are retained.

**Subsequent runs** — render from cache (fast):
```bash
python render.py
```

**Quick preview** at 1/10 scale for iteration:
```bash
python render.py --preview
```

**NYC render:**
```bash
python render.py --config nyc
```

Output is saved to `output/poster-<timestamp>.png`.

Choose a poster output path with `--output prints/sf.png`; missing parent
directories are created automatically. Run commands from the repository root.
`export.py` remains a backward-compatible alias for `render.py`, including
`--fetch`, `--config`, and preview/effect flags.

## Animation (`animate.py`)

Requires [ffmpeg](https://ffmpeg.org) on `PATH` (`brew install ffmpeg` on macOS).
Both modes encode H.264 (`libx264`), `yuv420p`, CRF 18, at 60 fps by default.
Populate the activity cache before running. A map is mandatory: unlike posters,
animations currently have no `--no-map` option or map-download fallback.

**Sequential** (default) draws runs chronologically, with slower first/last runs,
a decelerating cursor, a half-second cursor fade, and a three-second final hold.
Live stats show month/year, run count, and cached activity mileage. Mileage
advances proportionally along each route and reaches its full cached distance.
The printed frame count follows the actual speed envelope and includes
deceleration, opening, cursor fade, and hold frames.

```bash
python animate.py                         # 1080×1350
python animate.py --preview               # 540×674, no final hold; cursor fade remains
```

**Parallel** starts all routes together at equal pixel speed. Shorter routes
finish earlier; the longest finishes after 15 seconds by default. Small tracer
dots mark active routes. Year range, run count, and cached activity mileage
fade in during the one-second final hold. A one-frame hold shows full stats;
with no hold, stats appear on the last drawing frame.

Both modes use the same filtered activities and cached distances, including
single-point and collapsed routes in their statistics. Final mileage is
identical in both modes and displayed rounded down to whole miles.

```bash
python animate.py --mode parallel
python animate.py --mode parallel --preview  # same timing, half resolution, 1s hold
```

**Refresh the configured source first**, or choose a custom filename:

```bash
python animate.py --fetch
python animate.py --mode parallel --output output/videos/sf-parallel.mp4
```

`animate.py --fetch` honors `FETCH_SOURCE` (`"strava"` or `"garmin"`), just like
the poster CLI. Missing output directories are created automatically.

Both modes reject rotated configurations, including the built-in NYC preset.
Custom north-up cities can use `--config <city>` with
`CANVAS_ROTATION_DEGREES = 0` and a positive, even-pixel
`ANIMATION_OUTPUT_RESOLUTION` matching the geographic Mercator aspect.
Animation map zoom is currently fixed at **15**, independent of poster and
preview map-zoom settings. Fresh CARTO downloads may require an API key.

Default names are `output/animation[-<city>][-parallel][-preview]-<timestamp>.mp4`;
the `sf` and sequential tags are omitted. Existing `--output` files are replaced
only after ffmpeg succeeds; failures or cancellation preserve them and remove
the temporary video.

Each run contributes one visit to every pixel in its scaled route stroke,
including retraced segments. Different runs add separate visits at overlaps.
Both modes use that same coverage for fixed pre-pass normalization, so final
density does not depend on speed or frame rate. Animation omits the poster's
density-bonus strokes and some effects, so **pixel-identical poster output is
not guaranteed**. See [animation status](docs/animation-status.md) for validation
and remaining limits.

## Garmin Connect instead of Strava

Garmin can populate a new cache without a Strava account. Install the normal
requirements, then choose one of these entry points:

```bash
python garmin_fetch.py                    # saved login, or interactive first login
python garmin_fetch.py --since 2026-01-01  # backfill from a particular date
python render.py                         # render the shared activity cache
```

For `render.py --fetch` or `animate.py --fetch` to use Garmin, set `FETCH_SOURCE = "garmin"` in
`config.py` or your city configuration. The standalone `garmin_fetch.py` always
uses Garmin regardless of that setting.

The first login prompts for email/password and an MFA code if required.
Alternatively, set `GARMIN_EMAIL` and `GARMIN_PASSWORD` in `.env` as shown in
`.env.example`. Reusable login tokens are stored in `~/.garminconnect`.

Without an interactive terminal, set those credentials in `.env` and complete
MFA in two steps:

```bash
python garmin_fetch.py --since 2026-01-01
# If Garmin sends a code, rerun with that code and the same --since date:
python garmin_fetch.py --since 2026-01-01 --mfa <code>
```

With no cache and no `--since`, Garmin starts from 1970-01-01 to retrieve all
available GPS runs. Later fetches start on the latest cached activity date.
Use `--since` explicitly to recover older uploads. Garmin and Strava records
share `data/activities.json`; matching Strava records replace Garmin fallbacks
on a later Strava refresh.

## Troubleshooting and cache recovery

- **Strava token refresh fails with HTTP 400/401:** rerun `python auth.py`, then
  `python render.py --fetch`. If you previously exported access/refresh tokens
  in your shell, run `unset STRAVA_ACCESS_TOKEN STRAVA_REFRESH_TOKEN` first so
  stale environment values do not override `.env`.
- **Authorization times out or is declined:** rerun `python auth.py` and approve
  the new browser flow within five minutes. Keep localhost port 8765 available.
- **No cached activities:** run with `--fetch` once, or populate the cache with
  `garmin_fetch.py`. Authentication alone does not fetch activities.
- **No runs match the city:** check `--config`, `CITY_BOUNDS`, and GPS availability.
  Only `Run` activities whose route centroid is inside the bounds are included.
  The poster CLI exits with a clear error rather than writing an empty poster.
- **Older Strava activities are missing:** use `python render.py --fetch` for a
  full, idempotent resync. No metadata deletion is needed. For Garmin, use
  `python garmin_fetch.py --since YYYY-MM-DD`.
- **Corrupt cache or a deliberate clean rebuild:** stop other fetch/export jobs,
  move `data/activities.json` to a uniquely named backup such as
  `data/activities-backup-YYYYMMDD.json`, then fetch again. Keep the backup until
  you verify the new result, especially if it contains Garmin-only runs.
  Missing or stale `cache_meta.json` does not prevent a Strava resync.
- **Rate limited:** Strava retries at the next applicable 15-minute or daily
  UTC quota reset. A daily-limit wait can be long; cancel and retry after reset
  if preferred.
- **Map/font unavailable:** posters warn and fall back to routes without a map
  or Pillow's default font. `render.py --no-map` explicitly skips the basemap.
  Animations require a map and fail if it cannot be loaded. Rendering is fully
  offline only when all needed assets are already cached.

Activity JSON, `.env`, and Garmin's token directory contain private data. Keep
them and their backups out of version control and do not share them in logs.

## Tests

```bash
.venv/bin/pytest tests/ -v
.venv/bin/pytest tests/test_export.py -v  # real CLI with synthetic data/services
.venv/bin/pytest tests/test_animator.py -v
.venv/bin/pytest tests/test_animation_regressions.py -v
.venv/bin/pytest tests/test_animation_cli.py -v  # real ffmpeg/ffprobe, synthetic data
```

Tests run in temporary working/home directories, disable dotenv loading, and
block unmocked network requests. Token-persistence tests use temporary `.env`
files, not your real credentials or activity cache.
The MP4 smoke tests require `ffmpeg` and `ffprobe` on `PATH` and skip when
either is unavailable. They encode and fully decode both animation modes and
previews, check metadata/frame counts, and exercise encoder failure and cancellation.

## Adapting for a new city

Create `my_city_config.py` that inherits from `config.py` and overrides the
values that differ. This complete north-up example uses NYC bounds without
the narrow crop and rotation of the built-in NYC preset:

```python
from config import *  # inherit SF defaults

CITY_BOUNDS = {
    "lat_min": 40.575,
    "lat_max": 40.875,
    "lng_min": -74.105,
    "lng_max": -73.730,
}

CANVAS_WIDTH_PX  = 4737   # width/height ≈ 0.9473, matching these Mercator bounds
CANVAS_HEIGHT_PX = 5000
MAP_TILE_CACHE = "data/map_tile-my-city.png"
```

Then render with:

```bash
python render.py --config my_city
```

NYC comes pre-configured — `nyc_config.py` is included and uses a 29° rotation so Manhattan's street grid runs vertically, with a non-centered crop to frame the borough.

**To configure your own city:**

**1. Geographic bounds** — use [bboxfinder.com](http://bboxfinder.com) to draw your bounding box and set `CITY_BOUNDS`.

**2. Canvas size** — the canvas must match the Mercator aspect ratio of your bounds or the map will be distorted:

```
lng_range_rad  = (lng_max - lng_min) × π/180
merc_max       = arcsinh(tan(lat_max × π/180))
merc_min       = arcsinh(tan(lat_min × π/180))
aspect_ratio   = lng_range_rad / (merc_max - merc_min)   ← width/height
```

Set `CANVAS_WIDTH_PX` and `CANVAS_HEIGHT_PX` so `WIDTH / HEIGHT ≈ aspect_ratio`.

**With rotation** (`CANVAS_ROTATION_DEGREES != 0`): `CANVAS_RENDER_WIDTH` /
`CANVAS_RENDER_HEIGHT` describe the unrotated framing rectangle; the renderer
pads its geographic bounds as needed to preserve Mercator proportions, then
expands both the frame and bounds for rotation. Set `CANVAS_WIDTH_PX` /
`CANVAS_HEIGHT_PX` to the desired final crop size. Use `CANVAS_CROP_X` /
`CANVAS_CROP_Y` for a non-centered crop in the oversized, rotated canvas.
Copy the complete built-in `nyc_config.py` if you want its rotated, narrow framing.

**3. Activity filter** — `src/processor.py:filter_sf_runs()` filters by `CITY_BOUNDS` automatically — no code change needed.

## Tweaking visuals

All visual knobs are in `config.py`:

| Variable | What it controls | Safe range |
|---|---|---|
| `GAMMA` | Brightness of rarely-run routes (< 1 lifts dim lines) | 0.3 – 1.0 |
| `ROUTE_LINE_THICKNESS` | Base stroke width in pixels | 1 – 5 |
| `ROUTE_COLOR_RAMP` | Color palette from single-run to peak density | — |
| `HOT_BLOOM_STRENGTH` | Glow intensity on heavily-run corridors | 1.0 – 6.0 |
| `HOT_BLOOM_THRESHOLD` | Density cutoff to trigger hot bloom | 0.5 – 0.9 |
| `MAP_TILE_OPACITY` | How bright the street map shows through | 0.5 – 1.0 |
| `DENSITY_EXPAND_STRENGTH` | How much denser routes appear thicker | 0.5 – 2.0 |

Animation-specific knobs:

| Variable | What it controls |
|---|---|
| `ANIMATION_FPS` | Output frame rate (60); use a positive value |
| `ANIMATION_OUTPUT_RESOLUTION` | Positive even-pixel dimensions (1080×1350) |
| `ANIMATION_DRAWING_SPEED` | Pixels/frame for the fast middle section — tune for target duration |
| `ANIMATION_DRAWING_SPEED_SLOW` | Pixels/frame for first and last run |
| `ANIMATION_SPEED_RAMP_RUNS` | Runs over which speed ramps slow → fast (and back) |
| `ANIMATION_DOT_RADIUS` | Cursor dot size |
| `ANIMATION_DOT_BLUR` | Sequential cursor halo sigma; parallel tracers are unblurred |
| `ANIMATION_DOT_BRIGHTNESS` | Sequential cursor brightness (2.0 by default) |
| `ANIMATION_HOLD_SECONDS` | Sequential final hold (3s; disabled in preview) |
| `ANIMATION_PARALLEL_DURATION_S` | Longest route's drawing duration (15s) |
| `ANIMATION_PARALLEL_HOLD_S` | Parallel final hold / stats fade (1s, including preview) |

`MAP_TILE_ZOOM` controls poster-resolution map downloads (currently 17);
`MAP_PREVIEW_TILE_ZOOM` controls previews (11). Each extra zoom level downloads
roughly four times as many tiles. These settings do not control animation zoom.
Large print maps can take several minutes on
their first download. The tile cache separates providers/styles, tile/output sizes,
bounds, and zoom levels, so changing any of those downloads a new basemap.
High-resolution tiles are composed in overlapping row bands instead of an
oversized native-resolution mosaic, keeping Pillow's image safety limits enabled.
Individual source tiles are cached in `data/map_tiles/`, so interrupted downloads
resume without losing completed tiles. Connections are reused, and transient
connection failures, server errors, and rate limits are retried.

CARTO may require an API key for new downloads. Its HTTP-200 “API KEY REQUIRED”
placeholder is rejected rather than cached as a map. Use an authenticated
`MAP_TILE_URL`, another properly attributed provider, or a genuine existing cache.

Ordinary bloom is disabled. `--no-bloom` is an alias for `--no-hot-bloom`;
`--no-glow` separately disables the broad colored glow.

### Map attribution

Poster exports with a basemap and every animation frame include the visible credit
**© OpenStreetMap contributors, © CARTO**, also stored in PNG/MP4 copyright metadata.
For existing images made before this credit was added, include it in their
caption or regenerate them. See [OpenStreetMap copyright](https://www.openstreetmap.org/copyright)
and [CARTO attribution](https://carto.com/attribution/).
If you change `MAP_TILE_URL` to another provider, update `MAP_ATTRIBUTION` to
match that provider's requirements.

Regenerate older videos that lack embedded attribution, or include the provider
credit in their publication caption.
