# Polish Pass 3 — Design

**Goal:** Correct SF bounds, neon-sign burn on heavy routes, indigo-to-pink color ramp, thicker lines, SemiBold font, sharper map tiles.

---

## 1. Bounds + Canvas Aspect Ratio

Update `SF_BOUNDS` to the correct city extents:

```python
SF_BOUNDS = {
    "lat_min": 37.7080,   # tightened — actual SF city line (Geneva Ave / Daly City border)
    "lat_max": 37.8330,   # extended — just north of GG Bridge road
    "lng_min": -122.5270, # unchanged
    "lng_max": -122.3820, # unchanged
}
```

Both `fetch_map_tile` and `project()` use `renderer.bounds`, so map tile and routes shift together — no alignment work needed.

Canvas width is recomputed from the new Mercator aspect ratio:

```
lng_range_rad  = 0.145 × π/180          ≈ 0.002531 rad
merc_range     ≈ lat_range_rad / cos(lat_mid)
               = (0.125 × π/180) / cos(37.7705°)
               ≈ 0.002182 / 0.7919      ≈ 0.002756
aspect         = lng_range_rad / merc_range ≈ 0.919
CANVAS_WIDTH_PX = round(5400 × 0.919)  = 4960   # 16.53" at 300 DPI
```

Preview: 496×540.

---

## 2. Color Ramp — Indigo → Neon

```python
ROUTE_COLOR_RAMP = [
    (0.0,  [100,  80, 255]),   # rarely-run → royal indigo-blue
    (0.45, [200,   0, 255]),   # moderate   → electric violet
    (0.8,  [255,   0, 180]),   # heavy      → neon hot pink
    (1.0,  [255, 200, 255]),   # peak       → blown-out pink-white
]
```

---

## 3. Neon Burn — Line Thickness + Density Expansion

**Base thickness:** `ROUTE_LINE_THICKNESS = 3` (was 2). Used in `rasterize_run`.

**Density expansion pass** in `to_image()`, applied immediately after gamma and before hot bloom:

```python
if density_expand:
    expanded = gaussian_filter(norm ** DENSITY_EXPAND_POWER, sigma=DENSITY_EXPAND_SIGMA)
    norm = 1 - (1 - norm) * (1 - expanded * DENSITY_EXPAND_STRENGTH)
```

Config constants:

```python
DENSITY_EXPAND_SIGMA    = 3.0   # tight spread — thickens lines, not halos
DENSITY_EXPAND_STRENGTH = 1.4   # screen-blend intensity
DENSITY_EXPAND_POWER    = 2.0   # squares norm so effect focuses on dense routes only
```

With `power=2.0`, a route at norm=0.3 contributes `0.09` to the expansion; a route at norm=0.9 contributes `0.81` — the heavy corridors get the burn, light routes are barely touched.

The heaviest routes stack three brightness passes: gamma lift → density expand → hot bloom, producing the overdriven neon-sign effect.

CLI flag: `--no-density-expand`.

---

## 4. Font — Montserrat SemiBold

```python
MAP_FONT_PATH = "data/fonts/Montserrat-SemiBold.ttf"
MAP_FONT_URL  = "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/montserrat/static/Montserrat-SemiBold.ttf"
```

No other typography changes.

---

## 5. Map Zoom — 15 for Full Render

```python
zoom = 15 if not args.preview else 11   # was 13
```

At zoom 15, CARTO tiles cover ~1/4 the ground area of zoom 13 tiles — streets are ~4× sharper at the same canvas size. SF bounds at zoom 15 requires ~20–25 tiles. Preview stays at zoom 11.

Delete `data/map_tile.png` before running to force regeneration.

---

## Files Changed

| File | Change |
|------|--------|
| `config.py` | Update `SF_BOUNDS`, `CANVAS_WIDTH_PX`, `ROUTE_COLOR_RAMP`, add `DENSITY_EXPAND_*` + `ROUTE_LINE_THICKNESS` |
| `src/renderer.py` | Use `ROUTE_LINE_THICKNESS` in `rasterize_run`; add density expand pass in `to_image()` |
| `export.py` | `zoom=15`; add `--no-density-expand` flag |
| `src/typography.py` | No change |
| `tests/test_renderer.py` | Test canvas width updated; test density expand brightens dense pixels |
| `tests/test_config.py` | _(none — config changes covered by renderer tests)_ |
