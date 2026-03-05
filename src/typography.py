import os
import urllib.request
import numpy as np
from PIL import Image, ImageDraw, ImageFont


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
                      text_color=(255, 255, 255)):
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
    font_size = max(10, h // 40)     # ~135px at 5400, 13px at 540
    margin = max(10, h // 25)        # ~216px at 5400, 22px at 540
    shadow_offset = max(2, h // 1800)
    line_gap = max(8, h // 120)      # ~45px at 5400, 8px at 540

    draw = ImageDraw.Draw(img)
    font = _load_font(font_path, font_size)

    shadow = (0, 0, 0)
    lines = [
        (year_range, font),
        (total_runs,  font),
        (total_dist,  font),
        (total_elev,  font),
    ]

    y = h - margin
    for text, f in reversed(lines):
        bbox = draw.textbbox((0, 0), text, font=f)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = w - margin - text_w
        y -= text_h
        draw.text((x + shadow_offset, y + shadow_offset), text, font=f, fill=shadow)
        draw.text((x, y), text, font=f, fill=text_color)
        y -= line_gap

    return img


def render_legend(img, color_ramp, font_path,
                  text_color=(255, 255, 255)):
    """
    Draw a horizontal color gradient bar in the bottom-center with
    '1 run' on the left and '100+ runs' on the right.
    Mirrors the margin of render_typography but uses a smaller font.
    """
    w, h = img.size
    font_size    = max(6, h // 100)   # much smaller than main stats (h//40)
    margin       = max(10, h // 25)
    bar_height   = max(4, h // 200)
    bar_width    = max(80, w // 6)
    label_gap    = max(4, h // 300)

    font = _load_font(font_path, font_size)
    draw = ImageDraw.Draw(img)

    # Position: bottom-center
    bar_top    = h - margin - font_size - label_gap - bar_height
    bar_bottom = bar_top + bar_height
    bar_left   = (w - bar_width) // 2
    bar_right  = bar_left + bar_width

    # Build gradient by interpolating color_ramp across bar width
    bar_img = Image.new("RGB", (bar_width, bar_height))
    bar_pixels = bar_img.load()
    for px in range(bar_width):
        t = px / max(bar_width - 1, 1)
        # find ramp segment
        r, g, b = color_ramp[0][1]
        for i in range(len(color_ramp) - 1):
            t0, c0 = color_ramp[i]
            t1, c1 = color_ramp[i + 1]
            if t0 <= t <= t1:
                alpha = (t - t0) / (t1 - t0)
                r = int(c0[0] * (1 - alpha) + c1[0] * alpha)
                g = int(c0[1] * (1 - alpha) + c1[1] * alpha)
                b = int(c0[2] * (1 - alpha) + c1[2] * alpha)
                break
        for py in range(bar_height):
            bar_pixels[px, py] = (r, g, b)

    img.paste(bar_img, (bar_left, bar_top))

    # Labels below the bar
    label_y = bar_bottom + label_gap
    shadow = (0, 0, 0)
    shadow_offset = max(1, h // 3600)
    left_label  = "1 run"
    right_label = "100+ runs"
    draw.text((bar_left + shadow_offset, label_y + shadow_offset), left_label, font=font, fill=shadow)
    draw.text((bar_left, label_y), left_label, font=font, fill=text_color)
    right_bbox = draw.textbbox((0, 0), right_label, font=font)
    right_w = right_bbox[2] - right_bbox[0]
    right_x = bar_right - right_w
    draw.text((right_x + shadow_offset, label_y + shadow_offset), right_label, font=font, fill=shadow)
    draw.text((right_x, label_y), right_label, font=font, fill=text_color)

    return img
