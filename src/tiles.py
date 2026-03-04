import math
import os
import requests
from PIL import Image
import io


def lat_lng_to_tile(lat, lng, zoom):
    """Convert lat/lng to Mapbox tile (x, y) at given zoom."""
    n = 2 ** zoom
    x = int((lng + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.asinh(math.tan(lat_rad)) / math.pi) / 2 * n)
    return x, y


def fetch_map_tile(bounds, zoom, token, cache_path, target_size,
                   style="mapbox/dark-v11", tile_size=512):
    """
    Fetch Mapbox tiles covering bounds, stitch, resize to target_size.
    Caches result to cache_path — subsequent calls return cached image.
    """
    if os.path.exists(cache_path):
        img = Image.open(cache_path).convert("RGB")
        return img.resize(target_size, Image.LANCZOS)

    x_min, y_max = lat_lng_to_tile(bounds["lat_min"], bounds["lng_min"], zoom)
    x_max, y_min = lat_lng_to_tile(bounds["lat_max"], bounds["lng_max"], zoom)

    cols = x_max - x_min + 1
    rows = y_max - y_min + 1
    stitched = Image.new("RGB", (cols * tile_size, rows * tile_size))

    base_url = f"https://api.mapbox.com/styles/v1/{style}/tiles/{tile_size}"
    for tx in range(x_min, x_max + 1):
        for ty in range(y_min, y_max + 1):
            url = f"{base_url}/{zoom}/{tx}/{ty}?access_token={token}"
            resp = requests.get(url)
            resp.raise_for_status()
            tile_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            px = (tx - x_min) * tile_size
            py = (ty - y_min) * tile_size
            stitched.paste(tile_img, (px, py))

    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    stitched.save(cache_path)

    return stitched.resize(target_size, Image.LANCZOS)
