# Polish 7 Design

**Goal:** Three visual improvements — accurate legend colors, density-proportional line thickness, and legend repositioning/sizing.

---

## Item 1: Gamma-corrected legend colors

**Problem:** `render_legend` interpolates the raw `color_ramp` linearly from t=0→1. The renderer applies `log1p` normalization + `gamma` before color lookup, so a 1-run route lands at t≈0.45 (electric violet) — not t=0. The legend left end shows a color (indigo) that never appears on screen.

**Design:**

`render_legend` gains two new parameters: `gamma` (float, default = `GAMMA` from config) and `max_runs` (int, required — the maximum number of times any single route appears in the dataset).

The bar sweep is remapped:

```
t_min = (log1p(1) / log1p(max_runs)) ** gamma   # norm for a 1-run route
t_max = 1.0
for px in 0..bar_width:
    t_raw = px / (bar_width - 1)                 # 0→1 linear position
    t_ramp = t_min + t_raw * (t_max - t_min)     # clamp to visible range
    t_ramp = t_ramp ** (1/1)                     # already gamma-in-ramp-space
    → look up color_ramp at t_ramp
```

Wait — the gamma is already baked into `t_min` derivation. The bar should sweep **linearly in ramp space** from `t_min` to `t_max`, since positions in ramp space are post-gamma by definition.

So simply: `t_ramp = t_min + (px / (bar_width - 1)) * (1.0 - t_min)`

`export.py` computes `max_runs` as the count of activities in `sf_runs` (each entry is one run, so `max_runs = len(sf_runs)` is a conservative upper bound; alternatively count max frequency of any route, but `len(sf_runs)` gives the correct normalization ceiling since the renderer normalizes by the max canvas pixel, which is at most equal to run count).

Actually more precisely: the renderer normalizes by `canvas.max()`, which is the pixel with the most accumulated weight. For routes run N times through the same corridor, that pixel ≈ N. So `max_runs` should be the maximum overlap count. A safe approximation: pass `len(sf_runs)` as the ceiling (conservative — makes left end slightly too blue — or use the actual canvas max). Best: pass the canvas `max_val` from the renderer, since it's already computed.

**Revised approach:** Export passes `canvas_max_val = renderer.canvas.max()` (after `rasterize_all`) to `render_legend`. Then:

```python
t_min = (np.log1p(1) / np.log1p(canvas_max_val)) ** gamma
```

This is exact — same formula the renderer uses.

**Files:** `src/typography.py` (`render_legend` signature + bar loop), `export.py` (pass `canvas_max_val` and `GAMMA`).

---

## Item 2: Density-proportional line thickness

**Problem:** All routes are drawn at the same base thickness regardless of how heavily-run their corridor is. Hot corridors should visually dominate with thicker lines.

**Design — two-pass rasterize:**

**Pass 1 (existing):** `rasterize_all` draws all runs at `ROUTE_LINE_THICKNESS`. Canvas accumulates density.

**Scoring:** After pass 1, for each run compute a density score = mean of `canvas[y, x]` sampled at each of its projected points. This reflects how heavily-trafficked that route's corridor is.

**Ranking:** Sort density scores. Compute:
- `p50` = 50th-percentile score threshold
- `p90` = 90th-percentile score threshold

**Pass 2:** Re-rasterize runs above thresholds with extra thickness on top of base:
- Score in [p50, p90): add `ROUTE_LINE_THICKNESS_50_BONUS` px to thickness
- Score ≥ p90: add `ROUTE_LINE_THICKNESS_10_BONUS` px to thickness

The extra lines are added to the canvas (correct — popular routes deserve more density).

**New config constants:**
```python
# Extra pixels added to base ROUTE_LINE_THICKNESS for top-50% routes.
ROUTE_LINE_THICKNESS_50_BONUS = 4

# Extra pixels added for top-10% routes (cumulative with 50-bonus is not applied;
# this replaces it — only one bonus fires per run).
ROUTE_LINE_THICKNESS_10_BONUS = 10
```

**New renderer method:** `_density_score(coords) -> float` — samples canvas along projected path.

**Modified method:** `rasterize_run(coords, weight, thickness)` — thickness defaults to `ROUTE_LINE_THICKNESS`.

**Modified method:** `rasterize_all(runs, weight)` — does both passes.

**Files:** `src/renderer.py`, `config.py`.

---

## Item 3: Legend repositioning and sizing

**Changes:**
1. **Width:** `bar_width = max(80, w // 4)` (was `w // 6` — 50% wider)
2. **Vertical position:** Center the legend's visual height on the vertical midpoint of the typography text block.

**Text block midpoint computation** (replicates `render_typography` layout math):
```python
main_font_size = max(10, h // 40)
main_line_gap  = max(8,  h // 120)
# 4 lines + 3 gaps, block bottom at h - margin
block_top    = h - margin - 4 * main_font_size - 3 * main_line_gap
block_bottom = h - margin
block_mid_y  = (block_top + block_bottom) // 2
```

**Legend positioned around that midpoint:**
```python
legend_h = bar_height + label_gap + font_size   # total legend visual height
bar_top  = block_mid_y - legend_h // 2
bar_bottom = bar_top + bar_height
```

**File:** `src/typography.py`.

---

## Testing

- **Item 1:** New test `test_render_legend_left_color_matches_gamma_correction` — creates a renderer with known canvas max, calls `render_legend` with matching `gamma`/`canvas_max_val`, samples the left edge of the bar, and asserts color matches `_ramp_colors(t_min, ROUTE_COLOR_RAMP)`.
- **Item 2:** New test `test_rasterize_all_thickens_hot_routes` — two identical routes (both sampled at canvas peak), verify top-10% run is drawn with higher total canvas contribution than a zero-density route would produce.
- **Item 3:** Update `test_render_legend_modifies_bottom_center` to remain valid (bar is still in the center column, just at a different y).
