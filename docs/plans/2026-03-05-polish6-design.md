# Polish 6 Design — Map Quality, Line Tuning, Legend Centering

Date: 2026-03-05

## Goals

1. Make map tile zoom configurable so a high-quality print run is one config change away.
2. Tighten line rendering: medium/low-use routes 25% thinner, glow only on white-hot pixels, single-run routes more visible.
3. Move legend from bottom-left to bottom-center.
4. Make all line-drawing config knobs human-readable with plain-English comments.

## Changes

### `config.py`

- Add `MAP_TILE_ZOOM = 15` with comments explaining zoom levels 11–17 and their tile counts / download cost.
- Change `ROUTE_LINE_THICKNESS`: 16 → 12 (25% thinner base; dense routes still appear thick via hot bloom + density expand).
- Add `GAMMA = 0.55` (was hardcoded default `0.7` in renderer). Lower gamma lifts low-density routes so single/double-run lines are clearly visible.
- Add plain-English inline comments to `DENSITY_EXPAND_*` and `HOT_BLOOM_*` blocks explaining the visual effect of each knob.

### `renderer.py`

- Import `GAMMA` from config.
- Use `GAMMA` as the default value for the `gamma` parameter in `to_image()`. No logic changes.

### `export.py`

- Pass `bloom=False` to `to_image()`. Removes the general soft-glow bloom pass that applied to all routes.
- `hot_bloom=True` remains (default), so glow is preserved only for white-hot high-density pixels.

### `src/typography.py`

- In `render_legend()`, change bar position from bottom-left (`bar_left = margin`) to bottom-center:
  ```python
  bar_left  = (w - bar_width) // 2
  bar_right = bar_left + bar_width
  ```
- Labels ("1 run" / "100+ runs") stay anchored to bar ends, shifted with it.

## Files Changed

| File | Change |
|------|--------|
| `config.py` | Add `MAP_TILE_ZOOM`, `GAMMA`; change `ROUTE_LINE_THICKNESS`; add comments |
| `src/renderer.py` | Import + use `GAMMA` from config |
| `export.py` | Pass `bloom=False` |
| `src/typography.py` | Center legend bar |

## Non-Goals

- No changes to hot bloom threshold or strength.
- No per-run density tier classification (uniform base thickness; density accumulation + effects handle visual differentiation).
- No changes to color ramp.
