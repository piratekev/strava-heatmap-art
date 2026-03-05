import os
import urllib.request
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
