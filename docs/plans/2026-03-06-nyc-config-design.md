# NYC Config Design

**Date:** 2026-03-06

## Goal

Add a `nyc_config.py` for rendering a New York City running heatmap poster. The map should be oriented along Manhattan's grid axis (rotated ~29° from true north) and cover the full NYC marathon course, Hoboken to the west, and Washington Heights to the north. The existing SF config and pipeline must be unaffected.

---

## Section 1: Config loading architecture

`nyc_config.py` starts with `from config import *` and overrides only the values that differ (bounds, canvas size, `CANVAS_ROTATION_DEGREES`). All other constants (colors, bloom, grain, etc.) inherit from `config.py`.

In `export.py`, a `--config` flag (default `sf`) uses `importlib.import_module()` to load the chosen config, then injects it into `sys.modules['config']` before the pipeline runs. The `src/` files (`fetcher`, `processor`, `renderer`, `tiles`, `typography`) are untouched — they import from `config` as usual and automatically receive the correct values.

---

## Section 2: Geographic bounds

`SF_BOUNDS` is renamed to `CITY_BOUNDS` everywhere: `config.py`, `nyc_config.py`, `src/processor.py`, `CLAUDE.md`, `README.md`, and tests.

NYC bounds:

```python
CITY_BOUNDS = {
    "lat_min": 40.575,  # Verrazzano Bridge / Staten Island marathon start
    "lat_max": 40.875,  # Washington Heights
    "lng_min": -74.105, # Hoboken
    "lng_max": -73.730, # eastern Brooklyn/Queens
}
```

Canvas dimensions will be computed from the Mercator aspect ratio of these bounds (per the formula in CLAUDE.md), sized for a sharp-looking output image without a specific print target.

---

## Section 3: Canvas dimensions and rotation

`nyc_config.py` sets `CANVAS_ROTATION_DEGREES = 29`. `config.py` gets `CANVAS_ROTATION_DEGREES = 0` as a default.

`StravaRenderer.__init__` computes an oversized intermediate canvas by expanding `CANVAS_WIDTH_PX` and `CANVAS_HEIGHT_PX` by `1 / cos(CANVAS_ROTATION_DEGREES)` (~1.14 for 29°). Geographic bounds are expanded proportionally so the extra pixels contain real map content. `tiles.py` picks this up automatically via `renderer.bounds`.

---

## Section 4: Renderer rotation

One new step at the end of `renderer.to_image()`, after grain and vignette:

```python
if CANVAS_ROTATION_DEGREES != 0:
    h, w = image.shape[:2]
    M = cv2.getRotationMatrix2D((w/2, h/2), -CANVAS_ROTATION_DEGREES, 1.0)
    image = cv2.warpAffine(image, M, (w, h))
    # crop to CANVAS_WIDTH_PX x CANVAS_HEIGHT_PX from center
```

SF passes `CANVAS_ROTATION_DEGREES = 0` and skips this step entirely. No other `src/` files change.

---

## Files changed

| File | Change |
|---|---|
| `config.py` | Rename `SF_BOUNDS` → `CITY_BOUNDS`; add `CANVAS_ROTATION_DEGREES = 0` |
| `nyc_config.py` | New file: `from config import *`, override `CITY_BOUNDS`, canvas dims, `CANVAS_ROTATION_DEGREES = 29` |
| `export.py` | Add `--config` flag; inject chosen config into `sys.modules['config']` |
| `src/processor.py` | Update import: `CITY_BOUNDS` |
| `src/renderer.py` | Oversized canvas in `__init__`; rotation step in `to_image()` |
| `CLAUDE.md` | Update `SF_BOUNDS` references to `CITY_BOUNDS` |
| `README.md` | Update `SF_BOUNDS` references to `CITY_BOUNDS` |
| `tests/` | Update bound references; add NYC aspect ratio test |
