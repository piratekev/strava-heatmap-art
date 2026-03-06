# Polish 8 Design

**Goal:** Make the indigo color ([100,100,255]) actually appear for 1-2 pass routes and on the left end of the legend; scale the legend 50% larger in all dimensions.

---

## Problem

With `GAMMA=0.4` and log normalization, a 1-run route maps to `t_min ≈ (log1p(1)/log1p(max_val))^0.4 ≈ 0.44–0.57`. The color ramp's indigo stop was at `t=0.0` and violet at `t=0.45`, so indigo was always below the rendered floor — never visible in the image or the legend.

---

## Change 1 — Restructure `ROUTE_COLOR_RAMP` (`config.py`)

Compress all stops into the actual visible norm range [0.45, 1.0]:

```python
ROUTE_COLOR_RAMP = [
    (0.45, [100, 100, 255]),   # 1-run routes → brighter indigo
    (0.65, [200,   0, 255]),   # moderate     → electric violet
    (0.85, [255,   0, 180]),   # heavy        → neon hot pink
    (1.0,  [255, 220, 255]),   # peak         → blown-out pink-white
]
```

Pixels with `norm < 0.45` (only Gaussian-blurred halos composited against pure black bg) render black — invisible against the background.

---

## Change 2 — Scale legend 1.5× (`src/typography.py`)

| Variable | Before | After |
|---|---|---|
| `font_size` | `max(6, h // 100)` | `max(9, h * 3 // 200)` |
| `bar_height` | `max(4, h // 200)` | `max(6, h * 3 // 400)` |
| `bar_width` | `max(80, w // 4)` | `max(120, w * 3 // 8)` |
| `label_gap` | `max(4, h // 300)` | `max(6, h // 200)` |

---

## Testing

- Update `test_render_legend_left_color_matches_gamma_correction` to expect indigo at the left edge (t_min lands on the indigo stop at 0.45).
- Update any size-related legend tests to reflect new dimensions.
