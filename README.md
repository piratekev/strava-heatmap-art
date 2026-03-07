# Strava Heatmap Art

Generate a print-quality running heatmap poster from your Strava data.

![San Francisco running heatmap](sf.png)

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

**First run** — fetch activities and render:
```bash
python export.py --fetch
```

**Subsequent runs** — render from cache (fast):
```bash
python export.py
```

**Quick preview** at 1/10 scale for iteration:
```bash
python export.py --preview
```

Output is saved to `output/poster-<timestamp>.png`.

## Adapting for a new city

Open `config.py` and update three things:

**1. Geographic bounds**

```python
SF_BOUNDS = {
    "lat_min": 40.4774,   # south edge
    "lat_max": 40.9176,   # north edge
    "lng_min": -74.2591,  # west edge
    "lng_max": -73.7004,  # east edge
}
```

Use [bboxfinder.com](http://bboxfinder.com) to draw your city's bounding box and copy the coordinates.

**2. Canvas size**

The canvas must match the Mercator aspect ratio of your bounding box or the map will be distorted. After picking your bounds, calculate:

```
lng_range_rad  = (lng_max - lng_min) × π/180
merc_max       = arcsinh(tan(lat_max × π/180))
merc_min       = arcsinh(tan(lat_min × π/180))
merc_range     = merc_max - merc_min
aspect_ratio   = lng_range_rad / merc_range   ← width/height
```

Then set canvas dimensions that match this ratio at your target print size (e.g. 16×20" at ~285 DPI = 4680×5850px for a 0.8 ratio):

```python
CANVAS_WIDTH_PX  = 4680
CANVAS_HEIGHT_PX = 5850   # CANVAS_WIDTH_PX / aspect_ratio
```

**3. Activity filter**

`src/processor.py:filter_sf_runs()` filters activities whose centroid falls inside `SF_BOUNDS` — it automatically uses your updated bounds, no code change needed.

> **Note:** The variable `SF_BOUNDS` is just a name — you don't need to rename it. If you do rename it in `config.py`, also update the import in `src/processor.py` (`from config import SF_BOUNDS`).

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
