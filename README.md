# Strava Heatmap Art

Generate a print-quality running heatmap poster from your Strava data.

![San Francisco running heatmap](sf.png)

NYC is also pre-configured — optimized to show the full NYC Marathon course (Staten Island → Brooklyn → Queens → Bronx → Manhattan), which one day they will let me run.

![New York City running heatmap](nyc.png)

Basemaps: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
© [CARTO](https://carto.com/attribution/).

---

## Prerequisites

- Python 3.11+
- A [Strava](https://www.strava.com) account with running activities

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
  Athlete: Kev Ay
  Run: python export.py --fetch
```

## Fetch & render

**First run, or refresh/backfill** — fetch activities and render:
```bash
python export.py --fetch
```

Strava refreshes scan the complete activity history and merge by activity ID.
This catches delayed uploads, updates existing records, and removes duplicate
IDs without inflating your totals. `data/cache_meta.json` records the last
successful fetch for information only; its timestamp does not limit fetching.
Unmatched cached records, including Garmin fallback runs, are retained.

**Subsequent runs** — render from cache (fast):
```bash
python export.py
```

**Quick preview** at 1/10 scale for iteration:
```bash
python export.py --preview
```

**NYC render:**
```bash
python export.py --config nyc
```

Output is saved to `output/poster-<timestamp>.png`.

Choose an output path with `--output prints/sf.png`; missing parent directories
are created automatically. Run commands from the repository root.

## Garmin Connect instead of Strava

Garmin can populate a new cache without a Strava account. Install the normal
requirements, then choose one of these entry points:

```bash
python garmin_fetch.py                    # saved login, or interactive first login
python garmin_fetch.py --since 2026-01-01  # backfill from a particular date
python export.py                         # render the shared activity cache
```

For `export.py --fetch` to use Garmin, set `FETCH_SOURCE = "garmin"` in
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
  `python export.py --fetch`. If you previously exported access/refresh tokens
  in your shell, run `unset STRAVA_ACCESS_TOKEN STRAVA_REFRESH_TOKEN` first so
  stale environment values do not override `.env`.
- **Authorization times out or is declined:** rerun `python auth.py` and approve
  the new browser flow within five minutes. Keep localhost port 8765 available.
- **No cached activities:** run with `--fetch` once, or populate the cache with
  `garmin_fetch.py`. Authentication alone does not fetch activities.
- **No runs match the city:** check `--config`, `CITY_BOUNDS`, and GPS availability.
  Only `Run` activities whose route centroid is inside the bounds are included.
  Export exits with a clear error rather than writing an empty poster.
- **Older Strava activities are missing:** use `python export.py --fetch` for a
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
- **Map/font unavailable:** export warns and falls back to routes without a map
  or Pillow's default font. `--no-map` explicitly skips the basemap. Rendering
  is fully offline only when all needed assets are already cached.

Activity JSON, `.env`, and Garmin's token directory contain private data. Keep
them and their backups out of version control and do not share them in logs.

## Tests

```bash
.venv/bin/pytest tests/ -v
.venv/bin/pytest tests/test_export.py -v  # real CLI with synthetic data/services
```

Tests run in temporary working/home directories, disable dotenv loading, and
block unmocked network requests. Token-persistence tests use temporary `.env`
files, not your real credentials or activity cache.

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
python export.py --config my_city
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

`MAP_TILE_ZOOM` controls full-resolution map downloads (currently 17);
`MAP_PREVIEW_TILE_ZOOM` controls previews (11). Each extra zoom level downloads
roughly four times as many tiles. Large print maps can take several minutes on
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

Exports with a basemap include the visible credit
**© OpenStreetMap contributors, © CARTO**, also stored in PNG copyright metadata.
For existing images made before this credit was added, include it in their
caption or regenerate them. See [OpenStreetMap copyright](https://www.openstreetmap.org/copyright)
and [CARTO attribution](https://carto.com/attribution/).
If you change `MAP_TILE_URL` to another provider, update `MAP_ATTRIBUTION` to
match that provider's requirements.
