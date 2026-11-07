"""Run + bike combo overlay: two stat blocks + legends at bottom-center.

Shared by combo_export.py (poster) and src/combo_animator.py (animation) so both
draw identical text. Reads combo_config values via `config` — callers must set
sys.modules["config"] = combo_config before importing this module.
"""
from config import (
    MAP_FONT_PATH, TYPOGRAPHY_SCALE, TYPOGRAPHY_WIDTH_SCALE, SHOW_ELEVATION,
    COMBO_CENTER_GAP, COMBO_LEGEND_WIDTH_SCALE,
    RUN_COLOR_RAMP, RUN_GAMMA, BIKE_COLOR_RAMP, BIKE_GAMMA,
)
from src.typography import render_typography, render_corner_legend


def _blocks(width):
    """(side, anchor_x, unit) for the runs block (left of center) and bikes block (right)."""
    half_gap = int(width * COMBO_CENTER_GAP / 2)
    return [
        ("right", width // 2 - half_gap, "runs"),
        ("left",  width // 2 + half_gap, "rides"),
    ]


def num_lines():
    return 4 if SHOW_ELEVATION else 3


def draw_combo_text(img, run_lines, bike_lines):
    """Draw both stat blocks (lists of strings, top-to-bottom) onto img (PIL)."""
    for (side, anchor_x, unit), lines in zip(_blocks(img.width), [run_lines, bike_lines]):
        img = render_typography(img, None, font_path=MAP_FONT_PATH,
                                scale=TYPOGRAPHY_SCALE, width_scale=TYPOGRAPHY_WIDTH_SCALE,
                                align=side, unit=unit, anchor_x=anchor_x,
                                fixed_line_height=True, lines=lines)
    return img


def draw_combo_legends(img, run_max, bike_max):
    """Draw the cyan (runs) and pink (rides) legend bars above their stat blocks.
    run_max / bike_max are each layer's density canvas max (sets the '1 run' color)."""
    ramps = [(RUN_COLOR_RAMP, RUN_GAMMA, run_max), (BIKE_COLOR_RAMP, BIKE_GAMMA, bike_max)]
    for (side, anchor_x, unit), (ramp, gamma, max_val) in zip(_blocks(img.width), ramps):
        img = render_corner_legend(img, color_ramp=ramp, font_path=MAP_FONT_PATH,
                                   side=side, unit=unit, gamma=gamma, canvas_max_val=max_val,
                                   scale=TYPOGRAPHY_SCALE, width_scale=COMBO_LEGEND_WIDTH_SCALE,
                                   text_width_scale=TYPOGRAPHY_WIDTH_SCALE,
                                   num_lines=num_lines(), anchor_x=anchor_x)
    return img
