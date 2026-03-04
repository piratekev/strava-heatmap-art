# Strava Heatmap Poster — Design Doc
_2026-03-03_

## Overview

A personal art project that generates a print-quality heatmap poster (18×24" @ 300 DPI) of all running routes in San Francisco, sourced from the Strava API. Built in Python with a modular pipeline and Jupyter notebook for visual iteration.

---

## Architecture

```
strava-art/
├── data/
│   ├── activities.json      # cached activity list (with summary polylines)
│   └── cache_meta.json      # last_fetched timestamp, total activity count
├── src/
│   ├── fetcher.py           # Strava API client with incremental caching
│   ├── processor.py         # filter, decode polylines, geo-filter to SF
│   └── renderer.py          # rendering engine
├── notebooks/
│   └── explore.ipynb        # interactive visual iteration
├── output/                  # generated PNGs (gitignored)
├── export.py                # CLI entrypoint
├── config.py                # SF bounding box, print dimensions, palette defs
└── .env                     # STRAVA_CLIENT_ID, SECRET, ACCESS_TOKEN, REFRESH_TOKEN
```

---

## Data Layer

### Strava API

- Endpoint: `GET /athlete/activities` — returns activity list including `summary_polyline`
- No per-activity detail requests needed; summary polyline has ~1m precision, sufficient for poster scale
- Auth: OAuth2 with stored access + refresh tokens; auto-refresh when expired

### Rate Limits

- Read: 100 requests / 15 min, 1,000 / day
- Pagination at 200 activities/page means ~3 requests for 500 runs — well within limits

### Caching Strategy

- `activities.json`: append-only list of all fetched activities
- `cache_meta.json`: stores `last_fetched` (Unix timestamp) and `total_count`
- First run: paginate all activities, save to cache
- Subsequent runs: pass `after=<last_fetched_unix_ts>` to fetch only new activities, append
- Rate limit handling: on 429 response, sleep until reset window and retry

---

## Processing (`processor.py`)

1. Load activities from cache
2. Filter: `sport_type == 'Run'` (or legacy `type == 'Run'`)
3. Filter to SF bounding box: ~37.70–37.82°N, ~122.52–122.35°W (centroid or any point within bounds)
4. Decode summary polylines (Google Encoded Polyline format) → list of (lat, lng) pairs
5. Attach metadata per run: `start_date`, `average_speed`, `total_elevation_gain`, `distance`
6. Output: clean list of runs with coordinate arrays + metadata, ready for renderer

---

## Rendering (`renderer.py`)

### Canvas

- Size: 5400×7200 px (18×24" @ 300 DPI)
- dtype: float32 numpy array for accumulation
- Projection: linear mapping from SF lat/lng bounds to pixel space — no external tiles needed

### Route Rasterization

- Anti-aliased line segments via `cv2.line` or `skimage.draw`
- Each segment accumulates into a float density array
- Normalize density before applying colormap

### Default Output: Luminosity Heatmap

- Dark background (~#0A0F1E)
- Routes render white/gold, brightness proportional to density
- Frequent routes glow brightest

### Post-Processing Effects

| Effect | Implementation |
|---|---|
| **Bloom** | Gaussian convolve route layer, screen-composite back; halos on dense routes |
| **Vignette** | Radial gradient darker at edges, draws eye to city center |
| **Film grain** | Low-opacity noise overlay; adds physical/printed feel |
| **Color grading** | S-curve contrast boost + subtle color tint |

### Visual Encoding Modes (switchable via config)

| Mode | Encodes | Palette |
|---|---|---|
| `luminosity` | density → brightness | Dark bg, white/gold routes (default) |
| `time_of_day` | start hour → hue | Dawn=rose, morning=gold, afternoon=white, dusk=orange, night=blue |
| `season` | month → hue | Spring=green, summer=gold, fall=amber, winter=blue |
| `pace` | avg speed → temperature | Fast=red/orange, slow=blue/purple |

### Export

- Final output: 300 DPI PNG via Pillow
- `export.py` CLI: `python export.py --palette luminosity --bloom --grain`

---

## Stack

| Library | Purpose |
|---|---|
| `requests` | Strava API calls |
| `polyline` | Decode Google Encoded Polyline |
| `numpy` | Canvas accumulation |
| `opencv-python` | Anti-aliased line rasterization |
| `scipy` | KDE (Phase 2) |
| `Pillow` | Final PNG export at 300 DPI |
| `jupyter` | Interactive exploration notebook |
| `python-dotenv` | Load `.env` credentials |

---

## Phase 2 (after base works)

- **OpenStreetMap street grid overlay:** fog-of-war or subtle underlay showing SF geography
- **KDE mode:** kernel density estimation for organic glowing density pools instead of raw line accumulation
- **Variable line weight:** thickness scales with local density — main corridors become "rivers"
- **Animated preview GIF:** routes accumulating chronologically, built from same pipeline
- **Typography layer:** neighborhood labels, stats footer (total runs, miles, date range), name/year
- **Data-encoded palettes:** per-segment pace gradient (requires detailed polylines from `/activities/{id}`)
