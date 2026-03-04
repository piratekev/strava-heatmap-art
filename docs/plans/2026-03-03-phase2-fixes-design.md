# Phase 2 Fixes Design

**Date:** 2026-03-03
**Goal:** Fix map alignment, map provider, map opacity, typography scaling, and color ramp.

---

## 1. Map Alignment

**Root cause:** Two compounding bugs:
- `fetch_map_tile` stitches a tile grid and naively resizes it to `target_size` — the stitched image covers a slightly larger bounding box than `renderer.bounds` (tiles snap to integer grid), so the map and routes don't align.
- `project()` in the renderer uses linear lat/lng interpolation; Mapbox/CARTO tiles use Web Mercator. These diverge slightly with latitude.

**Fix:**
- Switch `project()` to use Mercator Y (replace linear lat interpolation with `asinh(tan(lat_rad))` formula).
- After stitching tiles, compute exact sub-pixel crop coordinates using the same Mercator math, then `crop → resize` to `target_size`. Routes and map will share the same projection.

**Crop math (within stitched image at tile_size px/tile):**
```
world_x = (lng + 180) / 360 * 2^z * tile_size
world_y = (1 - asinh(tan(lat_rad)) / π) / 2 * 2^z * tile_size
img_x   = world_x - x_min * tile_size
img_y   = world_y - y_min * tile_size

crop = (img_x(lng_min), img_y(lat_max), img_x(lng_max), img_y(lat_min))
```

---

## 2. Map Provider

Switch from Mapbox `dark-v11` to CARTO `dark_nolabels`.

- URL template: `https://a.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png`
- No API token required.
- Tile size: 256px (OSM standard, not 512).
- Use round-robin subdomains `a/b/c/d` to distribute requests.
- Update `config.py`: remove `MAP_TILE_ZOOM` Mapbox-specific reference, add `MAP_TILE_URL` constant.
- `fetch_map_tile` signature drops `token` and `style` params; adds `url_template` param with CARTO default.

---

## 3. Map Opacity

Raise `MAP_TILE_OPACITY` from `0.15` → `0.35` in `config.py`.

---

## 4. Typography Scaling

Derive font sizes and margins from image height so they work at any resolution.

| Parameter | Formula | At 5400px | At 540px |
|-----------|---------|-----------|----------|
| `large_size` | `h // 27` | 200px | 20px |
| `small_size` | `h // 40` | 135px | 13px |
| `margin` | `h // 25` | 216px | 22px |
| `shadow_offset` | `max(2, h // 1800)` | 3px | 2px |

`render_typography` derives these from `img.size` internally — callers pass no font size args.

---

## 5. Color Ramp + Background

Update `config.py`:

```python
BG_COLOR = [0, 0, 0]  # pure black

ROUTE_COLOR_RAMP = [
    (0.0, [ 30,  80, 255]),   # low density  → blue
    (0.5, [150,  50, 200]),   # mid density  → purple
    (1.0, [255,  80, 180]),   # high density → pink
]
```

---

## Affected Files

| File | Change |
|------|--------|
| `config.py` | `BG_COLOR`, `ROUTE_COLOR_RAMP`, `MAP_TILE_OPACITY`, add `MAP_TILE_URL` |
| `src/renderer.py` | `project()` → Mercator Y |
| `src/tiles.py` | CARTO URL format, pixel-accurate crop, drop `token`/`style` params |
| `src/typography.py` | Scale font sizes from `img.size` |
| `export.py` | Update `fetch_map_tile` call (remove `token`, add `url_template`) |
| `tests/test_renderer.py` | Update color ramp tests for blue/pink palette |
| `tests/test_tiles.py` | Update mock URL format for CARTO |

---

## Testing Notes

- `test_color_ramp_low_density_is_gold` → rename + update assertion: low density = blue (`b >= r`)
- `test_color_ramp_high_density_shifts_toward_blue` → update: high density = pink (`r > 150`)
- Tile tests: update mocked URL pattern, remove `token` arg
- Renderer projection tests: Mercator Y changes exact pixel values slightly — update coordinate assertions if needed
