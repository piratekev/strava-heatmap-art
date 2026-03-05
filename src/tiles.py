import hashlib
import math
import os
import requests
from PIL import Image
import io


CARTO_URL = "https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png"
_SUBDOMAINS = ["a", "b", "c", "d"]


def lat_lng_to_tile(lat, lng, zoom):
    """Convert lat/lng to tile (x, y) at given zoom (Web Mercator)."""
    n = 2 ** zoom
    x = int((lng + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.asinh(math.tan(lat_rad)) / math.pi) / 2 * n)
    return x, y


def _lng_to_world_x(lng, zoom, tile_size):
    return (lng + 180) / 360 * (2 ** zoom) * tile_size


def _lat_to_world_y(lat, zoom, tile_size):
    lat_rad = math.radians(lat)
    return (1 - math.asinh(math.tan(lat_rad)) / math.pi) / 2 * (2 ** zoom) * tile_size


def fetch_map_tile(bounds, zoom, cache_path, target_size,
                   url_template=CARTO_URL, tile_size=256):
    """
    Fetch tiles covering bounds, stitch, crop to exact bounds, resize to target_size.
    Uses CARTO dark_nolabels by default (no token required).
    cache_path is used as a prefix; a 6-char bounds+zoom hash is embedded in the filename
    so that different bounds or zoom levels never share a cached tile.
    """
    bounds_key = hashlib.md5(f"{zoom}:{repr(sorted(bounds.items()))}".encode()).hexdigest()[:6]
    root, ext = os.path.splitext(cache_path)
    actual_cache = f"{root}-{bounds_key}{ext}"

    if os.path.exists(actual_cache):
        img = Image.open(actual_cache).convert("RGB")
        return img.resize(target_size, Image.LANCZOS)

    x_min, y_max = lat_lng_to_tile(bounds["lat_min"], bounds["lng_min"], zoom)
    x_max, y_min = lat_lng_to_tile(bounds["lat_max"], bounds["lng_max"], zoom)

    cols = x_max - x_min + 1
    rows = y_max - y_min + 1
    stitched = Image.new("RGB", (cols * tile_size, rows * tile_size))

    idx = 0
    for tx in range(x_min, x_max + 1):
        for ty in range(y_min, y_max + 1):
            s = _SUBDOMAINS[idx % len(_SUBDOMAINS)]
            idx += 1
            url = url_template.format(s=s, z=zoom, x=tx, y=ty)
            resp = requests.get(url)
            resp.raise_for_status()
            tile_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            stitched.paste(tile_img, ((tx - x_min) * tile_size, (ty - y_min) * tile_size))

    origin_x = x_min * tile_size
    origin_y = y_min * tile_size
    left   = _lng_to_world_x(bounds["lng_min"], zoom, tile_size) - origin_x
    right  = _lng_to_world_x(bounds["lng_max"], zoom, tile_size) - origin_x
    top    = _lat_to_world_y(bounds["lat_max"], zoom, tile_size) - origin_y
    bottom = _lat_to_world_y(bounds["lat_min"], zoom, tile_size) - origin_y
    cropped = stitched.crop((int(left), int(top), int(right), int(bottom)))

    os.makedirs(os.path.dirname(actual_cache) or ".", exist_ok=True)
    cropped.save(actual_cache)
    return cropped.resize(target_size, Image.LANCZOS)
