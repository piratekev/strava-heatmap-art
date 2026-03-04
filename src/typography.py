import os
import urllib.request
from PIL import Image, ImageDraw, ImageFont


METERS_PER_MILE = 1609.344


def _download_font(font_path, url):
    """Download font TTF to font_path if not already cached. Silently skips on failure."""
    os.makedirs(os.path.dirname(font_path), exist_ok=True)
    if not os.path.exists(font_path):
        print(f"Downloading font to {font_path}...")
        try:
            urllib.request.urlretrieve(url, font_path)
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
    Font sizes and margins scale automatically with image dimensions.
    Text is right-aligned in the bottom-right corner, top-to-bottom order:
    year range (large) → run count → distance (mi) → elevation (ft).
    Returns the modified image.
    """
    years = sorted({r["start_date"][:4] for r in sf_runs})
    year_range = f"{years[0]} \u2013 {years[-1]}" if len(years) > 1 else years[0]
    total_runs = f"{len(sf_runs):,} runs"
    total_miles = sum(r["distance"] for r in sf_runs) / METERS_PER_MILE
    total_dist = f"{total_miles:,.0f} mi"
    total_elev_ft = sum(r.get("total_elevation_gain", 0) for r in sf_runs) * 3.28084
    total_elev = f"{total_elev_ft:,.0f} ft"

    w, h = img.size
    large_size = max(12, h // 27)    # ~200px at 5400, 20px at 540
    small_size = max(10, h // 40)    # ~135px at 5400, 13px at 540
    margin = max(10, h // 25)        # ~216px at 5400, 22px at 540
    shadow_offset = max(2, h // 1800)
    line_gap = max(8, h // 120)      # ~45px at 5400, 8px at 540 (was h//450)

    draw = ImageDraw.Draw(img)
    font_large = _load_font(font_path, large_size)
    font_small = _load_font(font_path, small_size)

    shadow = (0, 0, 0)
    # Top-to-bottom order: year range, run count, distance, elevation
    lines = [
        (year_range, font_large),
        (total_runs,  font_small),
        (total_dist,  font_small),
        (total_elev,  font_small),
    ]

    y = h - margin
    for text, font in reversed(lines):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = w - margin - text_w
        y -= text_h
        draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow)
        draw.text((x, y), text, font=font, fill=text_color)
        y -= line_gap

    return img
