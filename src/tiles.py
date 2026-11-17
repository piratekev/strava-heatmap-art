import hashlib
import math
import os
import tempfile
import time
from functools import lru_cache
from pathlib import Path
import requests
from PIL import Image
import io


CARTO_URL = "https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png"
_SUBDOMAINS = ["a", "b", "c", "d"]


@lru_cache(maxsize=1)
def _carto_auth_tile_pixels():
    """Load the public HTTP-200 error image once, independent of PNG encoding."""
    path = Path(__file__).parent / "assets" / "carto-api-key-required.png"
    with Image.open(path) as reference:
        return reference.convert("RGB").tobytes()


def _validate_tile(tile, tile_size):
    if tile.size != (tile_size, tile_size):
        raise ValueError("Map tile has the wrong dimensions")
    if tile.convert("RGB").tobytes() == _carto_auth_tile_pixels():
        raise requests.HTTPError(
            "CARTO requires an API key and returned a placeholder instead of a map. "
            "Configure an authenticated MAP_TILE_URL or use a genuine cached basemap."
        )


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


def _download_tile(session, url, max_retries=3):
    """Retry transient failures without losing already downloaded map tiles."""
    for attempt in range(max_retries + 1):
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            return response.content
        except requests.RequestException as error:
            response = getattr(error, "response", None)
            status = getattr(response, "status_code", None)
            if (attempt == max_retries or
                    (status is not None and status != 429 and not 500 <= status < 600)):
                raise
            delay = 2 ** attempt
            try:
                delay = max(1, float(response.headers["Retry-After"]))
            except (AttributeError, KeyError, ValueError):
                pass
            print(f"Retrying interrupted map tile in {delay:g}s...")
            time.sleep(delay)


def fetch_map_tile(bounds, zoom, cache_path, target_size,
                   url_template=CARTO_URL, tile_size=256):
    """
    Fetch tiles covering bounds and resample overlapping rows to target_size.
    Uses CARTO dark_nolabels by default; new downloads may require an API key.
    Cache identity includes provider/style URL, tile/output sizes, bounds, and zoom.
    """
    target_size = tuple(target_size)
    cache_key = f"{url_template}:{tile_size}:{target_size}:{zoom}:{repr(sorted(bounds.items()))}"
    bounds_key = hashlib.sha256(cache_key.encode()).hexdigest()[:12]
    root, ext = os.path.splitext(cache_path)
    actual_cache = f"{root}-{bounds_key}{ext}"

    if os.path.exists(actual_cache):
        with Image.open(actual_cache) as cached:
            return cached.convert("RGB")

    x_min, y_max = lat_lng_to_tile(bounds["lat_min"], bounds["lng_min"], zoom)
    x_max, y_min = lat_lng_to_tile(bounds["lat_max"], bounds["lng_max"], zoom)

    cols = x_max - x_min + 1
    left = _lng_to_world_x(bounds["lng_min"], zoom, tile_size) - x_min * tile_size
    right = _lng_to_world_x(bounds["lng_max"], zoom, tile_size) - x_min * tile_size
    top = _lat_to_world_y(bounds["lat_max"], zoom, tile_size)
    bottom = _lat_to_world_y(bounds["lat_min"], zoom, tile_size)
    width, height = target_size
    source_per_pixel = (bottom - top) / height
    # Lanczos needs neighboring source pixels on either side of a row boundary.
    # Keep that context, but never build the enormous zoom-17 citywide mosaic.
    context = max(1, math.ceil(3 * max(1, source_per_pixel) / tile_size))
    row_cache = {}
    provider_key = hashlib.sha256(f"{url_template}:{tile_size}".encode()).hexdigest()[:12]
    tile_dir = os.path.join(os.path.dirname(cache_path), "map_tiles", provider_key, str(zoom))
    session = requests.Session()
    tile_count = 0

    def load_row(ty):
        nonlocal tile_count
        if ty in row_cache:
            return row_cache[ty]
        row = Image.new("RGB", (cols * tile_size, tile_size))
        row_cache[ty] = row
        for tx in range(x_min, x_max + 1):
            tile_path = os.path.join(tile_dir, str(tx), f"{ty}.png")
            try:
                with Image.open(tile_path) as tile:
                    _validate_tile(tile, tile_size)
                    row.paste(tile.convert("RGB"), ((tx - x_min) * tile_size, 0))
                tile_count += 1
                continue
            except requests.HTTPError:
                raise
            except (OSError, ValueError):
                pass
            idx = (ty - y_min) * cols + tx - x_min
            s = _SUBDOMAINS[idx % len(_SUBDOMAINS)]
            url = url_template.format(s=s, z=zoom, x=tx, y=ty)
            content = _download_tile(session, url)
            with Image.open(io.BytesIO(content)) as tile:
                _validate_tile(tile, tile_size)
                row.paste(tile.convert("RGB"), ((tx - x_min) * tile_size, 0))
            os.makedirs(os.path.dirname(tile_path), exist_ok=True)
            with open(tile_path, "wb") as cached_tile:
                cached_tile.write(content)
            tile_count += 1
        return row

    result = Image.new("RGB", target_size)
    try:
        for ty in range(y_min, y_max + 1):
            y0 = max(0, min(height, round((ty * tile_size - top) / source_per_pixel)))
            y1 = max(0, min(height, round(((ty + 1) * tile_size - top) / source_per_pixel)))
            if y1 <= y0:
                continue
            first = max(y_min, ty - context)
            last = min(y_max, ty + context)
            for old in list(row_cache):
                if old < first:
                    row_cache.pop(old).close()
            strip = Image.new("RGB", (cols * tile_size, (last - first + 1) * tile_size))
            try:
                for row_y in range(first, last + 1):
                    strip.paste(load_row(row_y), (0, (row_y - first) * tile_size))
                box = (left, max(0, top + y0 * source_per_pixel - first * tile_size),
                       right, min(strip.height, top + y1 * source_per_pixel - first * tile_size))
                band = strip.resize((width, y1 - y0), Image.LANCZOS, box=box)
                result.paste(band, (0, y0))
                band.close()
                if (ty - y_min + 1) % 10 == 0 or ty == y_max:
                    total = cols * (y_max - y_min + 1)
                    print(f"Map tiles: {tile_count}/{total} ready (downloaded or cached)")
            finally:
                strip.close()
    finally:
        for row in row_cache.values():
            row.close()
        session.close()

    os.makedirs(os.path.dirname(actual_cache) or ".", exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(actual_cache) or ".",
                                     prefix=os.path.basename(actual_cache) + ".", suffix=".png")
    os.close(fd)
    try:
        result.save(temporary)
        os.replace(temporary, actual_cache)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return result
