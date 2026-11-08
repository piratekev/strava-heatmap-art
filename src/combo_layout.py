"""Run + bike combo overlay, shared by combo_export.py (poster) and
src/combo_animator.py (animation) so both draw identical text.

Layout:
  top-center      one combined year range (+ optional month line in the animation)
  bottom-center   two stat blocks (count / miles): runs left of center, rides right
  very bottom     each block's color legend, underneath its stats

Reads combo_config values via `config` — callers must set
sys.modules["config"] = combo_config before importing this module.
"""
from PIL import ImageDraw

from config import (
    MAP_FONT_PATH, TYPOGRAPHY_SCALE, TYPOGRAPHY_WIDTH_SCALE,
    COMBO_CENTER_GAP, COMBO_LEGEND_WIDTH_SCALE,
    COMBO_DATE_SCALE, COMBO_MONTH_SCALE, COMBO_DATE_TOP,
    RUN_COLOR_RAMP, RUN_GAMMA, BIKE_COLOR_RAMP, BIKE_GAMMA,
)
from src.typography import render_typography, render_corner_legend, _load_font

SHADOW = (0, 0, 0)


def _blocks(width):
    """(side, anchor_x, unit) for the runs block (left of center) and rides block (right)."""
    half_gap = int(width * COMBO_CENTER_GAP / 2)
    return [
        ("right", width // 2 - half_gap, "runs"),
        ("left",  width // 2 + half_gap, "rides"),
    ]


def _metrics(h):
    """Pixel sizes, using the same formulas as typography.render_* so things line up."""
    s = TYPOGRAPHY_SCALE
    return {
        "margin":      int(max(10, h // 25) * s),
        "main_font":   int(max(10, h // 40) * s * TYPOGRAPHY_WIDTH_SCALE),
        "line_gap":    int(max(8,  h // 120) * s),
        "legend_font": int(max(9,  h * 3 // 200) * s),
        "bar_height":  int(max(6,  h * 3 // 400) * s),
        "label_gap":   int(max(6,  h // 200) * s),
    }


def _legend_height(m):
    # bar + gap + label text (+ a little for descenders)
    return m["bar_height"] + m["label_gap"] + int(m["legend_font"] * 1.2)


def _bar_width(width):
    # same formula as typography.render_corner_legend
    return int(width * 3 // 8 * COMBO_LEGEND_WIDTH_SCALE)


def draw_combo_text(img, run_lines, bike_lines):
    """Draw both stat blocks (lists of strings, top-to-bottom), each centered over
    its legend bar and lifted to leave room for the legends underneath."""
    m = _metrics(img.height)
    lift = _legend_height(m) + m["line_gap"] * 3
    half_bar = _bar_width(img.width) // 2
    for (side, anchor_x, unit), lines in zip(_blocks(img.width), [run_lines, bike_lines]):
        center_x = anchor_x - half_bar if side == "right" else anchor_x + half_bar
        img = render_typography(img, None, font_path=MAP_FONT_PATH,
                                scale=TYPOGRAPHY_SCALE, width_scale=TYPOGRAPHY_WIDTH_SCALE,
                                align="center", unit=unit, anchor_x=center_x,
                                fixed_line_height=True, lines=lines, bottom_offset=lift)
    return img


def draw_combo_legends(img, run_max, bike_max):
    """Draw the cyan (runs) and pink (rides) legend bars at the very bottom.
    run_max / bike_max are each layer's density canvas max (sets the '1 run' color)."""
    m = _metrics(img.height)
    bar_top = img.height - m["margin"] - _legend_height(m)
    ramps = [(RUN_COLOR_RAMP, RUN_GAMMA, run_max), (BIKE_COLOR_RAMP, BIKE_GAMMA, bike_max)]
    for (side, anchor_x, unit), (ramp, gamma, max_val) in zip(_blocks(img.width), ramps):
        img = render_corner_legend(img, color_ramp=ramp, font_path=MAP_FONT_PATH,
                                   side=side, unit=unit, gamma=gamma, canvas_max_val=max_val,
                                   scale=TYPOGRAPHY_SCALE, width_scale=COMBO_LEGEND_WIDTH_SCALE,
                                   text_width_scale=TYPOGRAPHY_WIDTH_SCALE,
                                   anchor_x=anchor_x, bar_top=bar_top)
    return img


def draw_combo_date(img, year_range, month=None):
    """Combined year range centered at the top (over the bay), with an optional
    smaller month line underneath (e.g. 'Mar 2024' while the animation runs)."""
    m = _metrics(img.height)
    draw = ImageDraw.Draw(img)
    shadow_offset = max(2, img.height // 1800)
    y = int(img.height * COMBO_DATE_TOP)
    rows = [(year_range, int(m["main_font"] * COMBO_DATE_SCALE), (255, 255, 255))]
    if month:
        rows.append((month, int(m["main_font"] * COMBO_MONTH_SCALE), (200, 200, 200)))
    for text, size, color in rows:
        font = _load_font(MAP_FONT_PATH, size)
        bbox = draw.textbbox((0, 0), text, font=font)
        x = (img.width - (bbox[2] - bbox[0])) // 2 - bbox[0]
        draw.text((x + shadow_offset, y - bbox[1] + shadow_offset), text, font=font, fill=SHADOW)
        draw.text((x, y - bbox[1]), text, font=font, fill=color)
        y += (bbox[3] - bbox[1]) + m["line_gap"] * 2
    return img
