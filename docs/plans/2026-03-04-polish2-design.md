# Polish Pass 2 — Design

**Goal:** Fix map/route misalignment, match canvas to geographic aspect ratio, density-driven bloom overexposure on heavy-use lines, uniform typography block, clearer elevation label.

---

## 1. Map Tile Cache Fix

The committed `data/map_tile.png` and `data/map_tile-preview.png` are stale — `fetch_map_tile` returns the cached file without checking whether bounds changed. Fix: remove both files from git and add them to `.gitignore`. The tile regenerates automatically on next run from `renderer.bounds`.

---

## 2. Bounds + Canvas Dimensions

**Bounds** — unchanged from polish pass 1 (they look good):
```python
SF_BOUNDS = {
    "lat_min": 37.7080,
    "lat_max": 37.8330,
    "lng_min": -122.5270,
    "lng_max": -122.3820,
}
```

**Canvas** — match the Mercator aspect ratio of the bounds:
```
lng_range  = 0.145° → 0.002531 rad
merc_range = arcsinh(tan(37.833°)) − arcsinh(tan(37.708°)) ≈ 0.0028
aspect     = 0.002531 / 0.0028 ≈ 0.904
```

```python
CANVAS_HEIGHT_PX = 5400   # 18" at 300 DPI — unchanged
CANVAS_WIDTH_PX  = 4860   # 16.2" at 300 DPI — was 5400
```

Preview: 486×540. Both map tile and routes use `renderer.bounds`, so they're always in sync.

---

## 3. Density-Driven Bloom Overexposure

Add a second bloom pass targeting only high-density pixels (norm > 0.7). These spread aggressively into the dark background; low-density routes are unaffected.

```python
hot_mask  = np.clip((norm - HOT_BLOOM_THRESHOLD) / (1.0 - HOT_BLOOM_THRESHOLD), 0, 1)
hot_bloom = gaussian_filter(hot_mask, sigma=bloom_sigma_wide * HOT_BLOOM_SIGMA_MULT)
norm      = 1 - (1 - norm) * (1 - hot_bloom * HOT_BLOOM_STRENGTH)
```

Runs *after* the regular bloom pass so overexposure compounds. Parameters in `config.py`:
```python
HOT_BLOOM_THRESHOLD  = 0.7
HOT_BLOOM_SIGMA_MULT = 2.5
HOT_BLOOM_STRENGTH   = 1.5
```

`to_image()` gains `hot_bloom=True` flag (default True) alongside the existing `bloom` flag. CLI gains `--no-hot-bloom`.

---

## 4. Typography — Uniform Size

Drop `font_large` / `large_size`. All four lines use `font_small`. Year range right-aligns flush with the stats below it — a clean uniform block.

```python
lines = [
    (year_range, font_small),
    (total_runs, font_small),
    (total_dist, font_small),
    (total_elev, font_small),
]
```

---

## 5. Elevation Label

```python
total_elev = f"{total_elev_ft:,.0f} ft ↑"
```

---

## Files Changed

| File | Change |
|------|--------|
| `.gitignore` | Add `data/map_tile.png`, `data/map_tile-preview.png` |
| `config.py` | `CANVAS_WIDTH_PX` → 4860; add `HOT_BLOOM_*` constants |
| `src/renderer.py` | Add hot bloom pass in `to_image()`; `hot_bloom=True` param |
| `export.py` | Add `--no-hot-bloom` CLI flag |
| `src/typography.py` | All lines use `font_small`; elevation label uses `↑` |
| `tests/test_renderer.py` | Test for hot bloom, test canvas is not square |
| `tests/test_typography.py` | Test elevation label contains `↑`; test all lines same height |
