import pytest
import numpy as np
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image
from src.tiles import lat_lng_to_tile, fetch_map_tile


def test_lat_lng_to_tile_sf_center():
    """SF center at zoom 13 should produce tile within expected range."""
    x, y = lat_lng_to_tile(37.77, -122.42, zoom=13)
    # Rough expected tile for SF at zoom 13
    assert 1307 <= x <= 1310
    assert 3165 <= y <= 3168


def test_lat_lng_to_tile_zoom_doubles_range():
    """Each zoom increment doubles tile coordinates."""
    x0, y0 = lat_lng_to_tile(37.77, -122.42, zoom=12)
    x1, y1 = lat_lng_to_tile(37.77, -122.42, zoom=13)
    assert x1 == x0 * 2 or x1 == x0 * 2 + 1
    assert y1 == y0 * 2 or y1 == y0 * 2 + 1


def test_fetch_map_tile_returns_rgb_image(tmp_path):
    """fetch_map_tile returns a PIL Image in RGB mode."""
    bounds = {
        "lat_min": 37.75, "lat_max": 37.79,
        "lng_min": -122.45, "lng_max": -122.40,
    }
    fake_tile = Image.new("RGB", (256, 256), color=(20, 20, 30))
    import io
    tile_bytes = io.BytesIO()
    fake_tile.save(tile_bytes, format="PNG")
    tile_content = tile_bytes.getvalue()

    mock_resp = MagicMock()
    mock_resp.content = tile_content
    mock_resp.raise_for_status = MagicMock()

    cache_path = str(tmp_path / "tile.png")
    with patch("requests.get", return_value=mock_resp):
        img = fetch_map_tile(bounds, zoom=13, cache_path=cache_path,
                             target_size=(540, 540))

    assert img.mode == "RGB"
    assert img.size == (540, 540)


def test_fetch_map_tile_uses_cache(tmp_path):
    """Second call uses cached file, makes no HTTP requests."""
    cache_path = str(tmp_path / "tile.png")
    fake = Image.new("RGB", (540, 540), color=(10, 10, 20))
    fake.save(cache_path)

    with patch("requests.get") as mock_get:
        img = fetch_map_tile(
            bounds={"lat_min": 37.75, "lat_max": 37.79,
                    "lng_min": -122.45, "lng_max": -122.40},
            zoom=13, cache_path=cache_path, target_size=(540, 540)
        )
        mock_get.assert_not_called()

    assert img.size == (540, 540)
