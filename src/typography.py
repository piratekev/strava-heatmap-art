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
        return ImageFont.load_default()


def render_typography(img, sf_runs, font_path,
                      margin=60, text_color=(255, 240, 180),
                      large_size=48, small_size=36):
    """
    Render year range, run count, and distance onto img (PIL Image).
    Text is right-aligned in the bottom-right corner.
    Returns the modified image.
    """
    years = sorted({r["start_date"][:4] for r in sf_runs})
    year_range = f"{years[0]} – {years[-1]}" if len(years) > 1 else years[0]
    total_runs = f"{len(sf_runs):,} runs"
    total_miles = sum(r["distance"] for r in sf_runs) / METERS_PER_MILE
    total_dist = f"{total_miles:,.0f} mi"

    draw = ImageDraw.Draw(img)
    font_large = _load_font(font_path, large_size)
    font_small = _load_font(font_path, small_size)

    w, h = img.size
    shadow = (0, 0, 0)
    shadow_offset = 2

    lines = [
        (year_range, font_large),
        (total_runs, font_small),
        (total_dist, font_small),
    ]

    # Lay out bottom to top
    y = h - margin
    for text, font in reversed(lines):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = w - margin - text_w
        y -= text_h
        # Shadow
        draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow)
        # Text
        draw.text((x, y), text, font=font, fill=text_color)
        y -= 12  # line gap

    return img
