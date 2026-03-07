# NYC Legend Width Fix — Design

**Date:** 2026-03-07

## Problem

For the NYC config, the legend bar is too small in the full render but looks correct in preview. The preview is accidentally correct: the `max(120, w * 3 // 8)` floor kicks in at preview scale (w=174, formula gives 65 < 120), inflating the bar to 38.5% of canvas width. At full scale (w=1740, formula gives 652 > 120), there is no floor rescue, and `TYPOGRAPHY_SCALE * LEGEND_WIDTH_SCALE = 0.7 * 0.8 = 0.56` shrinks the bar to 21% of canvas width.

SF is unaffected because `TYPOGRAPHY_SCALE = 1.0`.

## Root Cause

`bar_width` in `render_legend` applies `scale` (TYPOGRAPHY_SCALE) as a multiplier:

```python
bar_width = int(max(120, w * 3 // 8) * scale * width_scale)
```

`TYPOGRAPHY_SCALE` was designed to shrink font sizes, which derive from canvas height. But `bar_width` already derives from canvas width `w`, so it scales naturally with the canvas. Applying `scale` on top double-shrinks it for city configs where `TYPOGRAPHY_SCALE < 1`.

## Solution

**`src/typography.py`** — remove `scale` from `bar_width`:
```python
bar_width = int(max(120, w * 3 // 8) * width_scale)
```

**`nyc_config.py`** — update `LEGEND_WIDTH_SCALE`:
```python
LEGEND_WIDTH_SCALE = 1.0  # was 0.8
```

With `scale` removed, `LEGEND_WIDTH_SCALE = 1.0` targets ~37.5% of canvas width consistently in both preview and full render.

## Impact

| | Preview | Full render |
|---|---|---|
| Before | 38.5% (67px) | 21% (365px) |
| After | 37.4% (65px) | 37.5% (652px) |

SF render: no change (`TYPOGRAPHY_SCALE = 1.0`, so removing it is a no-op).
