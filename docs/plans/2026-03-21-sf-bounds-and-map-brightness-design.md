# SF Bounds Extension + Map Brightness — Design

**Date:** 2026-03-21

## Changes

### 1. SF canvas + bounds extension

Extend the SF canvas 40px west and 50px south to reclaim the frame-clipped area, while maintaining the 16×20" (4:5) print ratio.

**Canvas:**
- `CANVAS_WIDTH_PX`: 4680 → 4720
- `CANVAS_HEIGHT_PX`: 5850 → 5900
- Ratio: 4720/5900 = 0.8 ✓ (unchanged)

**Bounds:**
- `lng_min`: –122.5152 → ~–122.5163 (40px × 0.134°/4680px = +0.001145°)
- `lat_min`: 37.7068 → ~37.7057 (50px south, Mercator equivalent)
- `lat_max`, `lng_max`: unchanged

**Tests:** `test_sf_bounds_aspect_ratio_matches_canvas` compares canvas ratio to geo aspect — update expected value after tuning the new bounds.

SF only. NYC config is unaffected.

---

### 2. Map tile brightness (both cities)

Add `MAP_TILE_BRIGHTNESS = 1.0` to `config.py`. Apply `PIL.ImageEnhance.Brightness` to the tile in `export.py` before compositing with the route layer.

Brightening lifts all map tile pixels uniformly: streets become lighter grey, water/bay shifts from near-black to visible dark blue. Routes, typography, and legend are unaffected (rendered on top after compositing).

`MAP_TILE_OPACITY` (blend ratio with black background) stays at 0.85. `MAP_TILE_BRIGHTNESS` is a separate amplifier that can exceed 1.0.

Starting value: `1.3` for both cities — expected to require iteration.

**`config.py`:** add `MAP_TILE_BRIGHTNESS = 1.3`

**`export.py`:** import `MAP_TILE_BRIGHTNESS`; apply before compositing:
```python
from PIL import ImageEnhance
tile = ImageEnhance.Brightness(tile).enhance(MAP_TILE_BRIGHTNESS)
```

NYC can override `MAP_TILE_BRIGHTNESS` in `nyc_config.py` if needed.
