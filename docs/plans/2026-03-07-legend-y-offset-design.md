# Legend Y Offset — Design

**Date:** 2026-03-07

## Problem

The legend vertical position for NYC needs manual fine-tuning. No config knob exists to shift it up or down independently of the text block centering logic.

## Solution

Add `LEGEND_Y_OFFSET` config value (default `0`, SF unchanged). Positive = lower, negative = higher.

**`src/typography.py` — `render_legend`**: add `y_offset=0` param, apply after centering:
```python
bar_top = block_mid_y - legend_h // 2 + y_offset
bar_bottom = bar_top + bar_height
```

**`config.py`**: add `LEGEND_Y_OFFSET = 0`

**`nyc_config.py`**: add `LEGEND_Y_OFFSET = 40`

**`export.py`**: import `LEGEND_Y_OFFSET`, pass `y_offset=LEGEND_Y_OFFSET` to `render_legend`.
