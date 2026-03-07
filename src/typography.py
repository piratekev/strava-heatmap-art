import os
import urllib.request
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from config import GAMMA


METERS_PER_MILE = 1609.344

_MIN_FONT_BYTES = 50_000   # real TTF files are 100 KB+; anything smaller is corrupt


def _download_font(font_path, url):
    """Download font TTF to font_path if not already cached. Silently skips on failure.
    If an existing file is under _MIN_FONT_BYTES it is deleted and re-downloaded."""
    os.makedirs(os.path.dirname(font_path), exist_ok=True)
    if os.path.exists(font_path) and os.path.getsize(font_path) < _MIN_FONT_BYTES:
        os.remove(font_path)
    if not os.path.exists(font_path):
        print(f"Downloading font to {font_path}...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as response:
                with open(font_path, "wb") as f:
                    f.write(response.read())
        except Exception as e:
            print(f"Font download failed ({e}) — using PIL default font")


def _load_font(font_path, size):
    """Load Montserrat TTF at given size, fall back to PIL default."""
    try:
        return ImageFont.truetype(font_path, size)
    except (OSError, IOError):
        return ImageFont.load_default(size=size)


def render_typography(img, sf_runs, font_path,
                      text_color=(255, 255, 255), scale=1.0, width_scale=1.0,
                      x_offset=0, show_elevation=True):
    """
    Render year range, run count, distance, and elevation onto img (PIL Image).
    All four lines use the same font size, right-aligned in the bottom-right corner.
    Order top-to-bottom: year range → run count → distance (mi) → elevation (ft ↑).
    Returns the modified image.
    """
    years = sorted({r["start_date"][:4] for r in sf_runs})
    year_range = f"{years[0]} \u2013 {years[-1]}" if len(years) > 1 else years[0]
    total_runs = f"{len(sf_runs):,} runs"
    total_miles = sum(r["distance"] for r in sf_runs) / METERS_PER_MILE
    total_dist = f"{total_miles:,.0f} mi"
    total_elev_ft = sum(r.get("total_elevation_gain", 0) for r in sf_runs) * 3.28084
    total_elev = f"{total_elev_ft:,.0f} ft \u2191"

    w, h = img.size
    font_size = int(max(10, h // 40) * scale * width_scale)
    margin = int(max(10, h // 25) * scale)
    shadow_offset = int(max(2, h // 1800) * scale)
    line_gap = int(max(8, h // 120) * scale)

    draw = ImageDraw.Draw(img)
    font = _load_font(font_path, font_size)

    shadow = (0, 0, 0)
    lines = [
        (year_range, font),
        (total_runs,  font),
        (total_dist,  font),
    ]
    if show_elevation:
        lines.append((total_elev, font))

    y = h - margin
    for text, f in reversed(lines):
        bbox = draw.textbbox((0, 0), text, font=f)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = w - margin - text_w + x_offset
        y -= text_h
        draw.text((x + shadow_offset, y + shadow_offset), text, font=f, fill=shadow)
        draw.text((x, y), text, font=f, fill=text_color)
        y -= line_gap

    return img


def render_legend(img, color_ramp, font_path,
                  text_color=(255, 255, 255), gamma=GAMMA, canvas_max_val=None,
                  scale=1.0, position="center", width_scale=1.0,
                  text_width_scale=1.0, show_elevation=True):
    """
    Draw a horizontal color gradient bar centered on the typography text block.

    The bar sweeps from the color a single-run route actually produces
    (computed from canvas_max_val + gamma) to the peak color, matching what
    the renderer renders.  If canvas_max_val is None the bar starts at t=0
    (raw ramp start).

    Args:
        gamma:           Same gamma used in renderer.to_image().
        canvas_max_val:  renderer.canvas.max() after rasterize_all().
        scale:           Overall size multiplier (e.g. 0.3 for NYC).
        position:        "center" (default) or "left" — horizontal placement of bar.
        width_scale:     Additional bar-width multiplier (e.g. 0.7 = 30% narrower).
    """
    import math
    w, h = img.size
    font_size  = int(max(9,  h * 3 // 200) * scale)
    margin     = int(max(10, h // 25) * scale)
    bar_height = int(max(6,  h * 3 // 400) * scale)
    bar_width  = int(w * 3 // 8 * width_scale)
    label_gap  = int(max(6,  h // 200) * scale)

    font = _load_font(font_path, font_size)
    draw = ImageDraw.Draw(img)

    # Vertical: center legend on the midpoint of the typography block
    main_font_size = int(max(10, h // 40) * scale * text_width_scale)
    main_line_gap  = int(max(8,  h // 120) * scale)
    num_lines    = 3 if not show_elevation else 4
    block_top    = h - margin - num_lines * main_font_size - (num_lines - 1) * main_line_gap
    block_bottom = h - margin
    block_mid_y  = (block_top + block_bottom) // 2
    legend_h     = bar_height + label_gap + font_size
    bar_top      = block_mid_y - legend_h // 2
    bar_bottom   = bar_top + bar_height

    # Horizontal: centered or left-aligned
    if position == "left":
        bar_left = margin
    else:
        bar_left  = (w - bar_width) // 2
    bar_right = bar_left + bar_width

    # t_min: the ramp position a single-run route produces after log+gamma
    if canvas_max_val is not None and canvas_max_val > 1:
        t_min = (math.log1p(1.0) / math.log1p(float(canvas_max_val))) ** gamma
    else:
        t_min = 0.0

    # Build gradient by interpolating color_ramp from t_min → 1.0
    bar_img    = Image.new("RGB", (bar_width, bar_height))
    bar_pixels = bar_img.load()
    for px in range(bar_width):
        t = px / max(bar_width - 1, 1)
        t_ramp = t_min + t * (1.0 - t_min)   # sweep t_min → 1.0
        r, g, b = color_ramp[0][1]
        for i in range(len(color_ramp) - 1):
            t0, c0 = color_ramp[i]
            t1, c1 = color_ramp[i + 1]
            if t0 <= t_ramp <= t1:
                alpha = (t_ramp - t0) / (t1 - t0)
                r = int(c0[0] * (1 - alpha) + c1[0] * alpha)
                g = int(c0[1] * (1 - alpha) + c1[1] * alpha)
                b = int(c0[2] * (1 - alpha) + c1[2] * alpha)
                break
        for py in range(bar_height):
            bar_pixels[px, py] = (r, g, b)

    img.paste(bar_img, (bar_left, bar_top))

    # Labels below the bar
    label_y       = bar_bottom + label_gap
    shadow        = (0, 0, 0)
    shadow_offset = max(1, h // 3600)
    left_label    = "1 run"
    right_label   = "100+ runs"
    draw.text((bar_left + shadow_offset, label_y + shadow_offset), left_label,  font=font, fill=shadow)
    draw.text((bar_left, label_y),                                  left_label,  font=font, fill=text_color)
    right_bbox = draw.textbbox((0, 0), right_label, font=font)
    right_w = right_bbox[2] - right_bbox[0]
    right_x = bar_right - right_w
    draw.text((right_x + shadow_offset, label_y + shadow_offset), right_label, font=font, fill=shadow)
    draw.text((right_x, label_y),                                  right_label, font=font, fill=text_color)

    return img
