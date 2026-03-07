# NYC Legend Fixes — Design

**Date:** 2026-03-07

## Problems

Three related issues in the NYC render (SF unaffected):

1. **Preview bar too wide** — `max(120, w * 3 // 8)` floor inflates bar on narrow preview canvas (w=174). Bar is 69% of canvas width instead of ~37%.

2. **Legend aligned to years line, not text center** — `render_legend` re-derives the text block font size using `scale` (TYPOGRAPHY_SCALE=0.7) alone, but `render_typography` uses `scale * width_scale` (TYPOGRAPHY_WIDTH_SCALE=0.7). The 1.43x overestimate pushes `block_mid_y` up toward the top of the block.

3. **Elevation gain always shown** — No config knob to hide it. NYC should not show elevation; removing it changes the text block from 4 to 3 lines, which affects legend centering.

## Solution

### `src/typography.py` — `render_legend`

**Remove floor from bar_width:**
```python
# Before
bar_width = int(max(120, w * 3 // 8) * width_scale)
# After
bar_width = int(w * 3 // 8 * width_scale)
```

**Add `text_width_scale` parameter** (default `1.0`, set to `TYPOGRAPHY_WIDTH_SCALE` by caller):
```python
def render_legend(img, ..., text_width_scale=1.0, show_elevation=True):
```
Use it in block height estimation:
```python
main_font_size = int(max(10, h // 40) * scale * text_width_scale)
```

**Add `show_elevation` parameter** (default `True`):
```python
num_lines = 3 if not show_elevation else 4
block_top = h - margin - num_lines * main_font_size - (num_lines - 1) * main_line_gap
```

### `src/typography.py` — `render_typography`

Add `show_elevation` parameter (default `True`). Skip the elevation line when `False`:
```python
def render_typography(img, sf_runs, font_path, ..., show_elevation=True):
    lines = [year_range, total_runs, total_dist]
    if show_elevation:
        lines.append(total_elev)
```

### `config.py`

Add:
```python
SHOW_ELEVATION = True
```

### `nyc_config.py`

Add:
```python
SHOW_ELEVATION = False
```

### `export.py`

Import `SHOW_ELEVATION` and `TYPOGRAPHY_WIDTH_SCALE`. Pass new params to both render calls:
```python
img = render_typography(..., show_elevation=SHOW_ELEVATION)
img = render_legend(..., text_width_scale=TYPOGRAPHY_WIDTH_SCALE, show_elevation=SHOW_ELEVATION)
```

## Impact

| Issue | Before | After |
|---|---|---|
| NYC preview bar width | 69% of canvas | ~37% of canvas |
| NYC legend vertical position | aligned with years line | centered on text block |
| NYC elevation line | always shown | hidden (SHOW_ELEVATION=False) |
| SF | unchanged | unchanged (all params default to current behavior) |
