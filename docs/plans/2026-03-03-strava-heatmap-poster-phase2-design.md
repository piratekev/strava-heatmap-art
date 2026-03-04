# Strava Heatmap Poster — Phase 2 Design

## Goal

Improve the Phase 1 poster output across four areas: spatial framing, density-adaptive visuals, Mapbox background tile, and typography.

---

## Section 1: Square Canvas + Auto-Fit Bounds

**Canvas:** Change from 18×24" to **18×18" @ 300 DPI (5400×5400px)**. Update `CANVAS_WIDTH_PX` and `CANVAS_HEIGHT_PX` in `config.py`.

**Projection:** Replace the fixed `SF_BOUNDS` projection with a **data-driven bounds fit**. Before rasterizing, `StravaRenderer` computes the min/max lat/lng across all run coordinates and adds 5% padding on each side. A new `set_bounds(runs)` method stores the computed bounds and `project()` uses them instead of the static config values.

---

## Section 2: Density-Adaptive Rendering

**Line weight:** `rasterize_run()` draws at **2px thickness** (up from 1px).

**Color ramp:** `to_image()` maps normalized density to a 3-stop color ramp. Stops are defined in `config.py` as `ROUTE_COLOR_RAMP` for easy tuning:

```python
ROUTE_COLOR_RAMP = [
    (0.0,  [255, 200,  80]),   # low density  → warm gold
    (0.5,  [255, 240, 180]),   # mid density  → white-gold
    (1.0,  [200, 230, 255]),   # high density → blue-white
]
```

Interpolation is linear between stops, applied per-channel to the normalized float canvas.

**Dual-sigma bloom:** Two gaussian passes replace the single bloom pass:
- **Tight pass** (`sigma=4`): preserves route definition
- **Wide pass** (`sigma=16`): creates the halo glow on dense corridors (Embarcadero, GGP)

Screen-blended together: `bloom = tight * 0.4 + wide * 0.6`, then composited as before.

---

## Section 3: Mapbox Tile Background

**New module:** `src/tiles.py`

- Fetches Mapbox Static Tiles API using style `mapbox/dark-v11`
- Covers the data-fitted bounds at zoom level 13
- Stitches tiles into a single image, resizes to canvas dimensions
- Caches result to `data/map_tile.png` (gitignored, only fetched once)

**Compositing:** Applied before route rendering:
```
bg = tile * 0.15 + canvas_background * 0.85
```

**Config additions:**
- `MAPBOX_TOKEN` → `.env` and `.env.example`
- `MAP_TILE_ZOOM = 13` → `config.py`
- `MAP_TILE_OPACITY = 0.15` → `config.py`

---

## Section 4: Typography

**New module:** `src/typography.py`

Renders three lines onto the final image using PIL `ImageDraw`, bottom-right corner, right-aligned, ~60px margin:

```
2021 – 2025          ← year range of SF runs only
541 runs
3,567 mi
```

**Font:** Montserrat (free, Google Fonts). Downloaded once to `data/fonts/Montserrat-Light.ttf` on first run, cached there (gitignored).

**Styling:**
- Year range: ~48pt
- Runs + distance: ~36pt
- Color: mid-density route color `[255, 240, 180]`
- Drop shadow: 2px offset, near-black, for legibility over map background

**Data:** Year range = first/last `start_date` among SF runs only. Distance = sum of SF run distances converted to miles.

---

## Files Changed

| File | Change |
|------|--------|
| `config.py` | Square canvas dims, `ROUTE_COLOR_RAMP`, `MAP_TILE_ZOOM`, `MAP_TILE_OPACITY` |
| `src/renderer.py` | `set_bounds()`, 2px lines, color ramp interpolation, dual-sigma bloom |
| `src/tiles.py` | New — Mapbox tile fetch, stitch, cache |
| `src/typography.py` | New — Montserrat text overlay |
| `export.py` | Wire up tiles + typography; add `--no-map` flag |
| `.env.example` | Add `MAPBOX_TOKEN` |
| `requirements.txt` | Add `requests` (already present), `Pillow` (already present) — no new deps |
