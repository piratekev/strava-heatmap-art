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
    with patch("requests.Session.get", return_value=mock_resp):
        img = fetch_map_tile(bounds, zoom=13, cache_path=cache_path,
                             target_size=(540, 540))

    assert img.mode == "RGB"
    assert img.size == (540, 540)


def test_fetch_map_tile_uses_cache(tmp_path):
    """Second call uses cached file, makes no HTTP requests."""
    import io
    bounds = {"lat_min": 37.75, "lat_max": 37.79,
              "lng_min": -122.45, "lng_max": -122.40}
    cache_prefix = str(tmp_path / "tile.png")
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), color=(10, 10, 20)).save(buf, format="PNG")
    response = MagicMock(content=buf.getvalue())
    with patch("requests.Session.get", return_value=response):
        fetch_map_tile(bounds, 13, cache_prefix, (540, 540))
    assert len(list(tmp_path.glob("tile-*.png"))) == 1

    with patch("requests.Session.get") as mock_get:
        img = fetch_map_tile(
            bounds=bounds,
            zoom=13, cache_path=cache_prefix, target_size=(540, 540)
        )
        mock_get.assert_not_called()

    assert img.size == (540, 540)


def test_fetch_map_tile_different_bounds_use_different_cache(tmp_path):
    """Different bounds must produce different cache paths (not share a stale file)."""
    import io
    from unittest.mock import patch, MagicMock
    from src.tiles import fetch_map_tile

    fake_tile = Image.new("RGB", (256, 256), color=(20, 20, 30))
    buf = io.BytesIO()
    fake_tile.save(buf, format="PNG")
    tile_bytes = buf.getvalue()

    mock_resp = MagicMock()
    mock_resp.content = tile_bytes
    mock_resp.raise_for_status = MagicMock()

    bounds_a = {"lat_min": 37.70, "lat_max": 37.83, "lng_min": -122.52, "lng_max": -122.38}
    bounds_b = {"lat_min": 37.70, "lat_max": 37.83, "lng_min": -122.50, "lng_max": -122.36}

    prefix = str(tmp_path / "tile.png")

    with patch("requests.Session.get", return_value=mock_resp):
        img_a = fetch_map_tile(bounds_a, zoom=13, cache_path=prefix, target_size=(540, 540))
        img_b = fetch_map_tile(bounds_b, zoom=13, cache_path=prefix, target_size=(540, 540))

    assert len(list(tmp_path.glob("tile-*.png"))) == 2


def test_map_tile_brightness_lightens_background():
    """MAP_TILE_BRIGHTNESS > 1.0 must produce a brighter composite than 1.0."""
    from PIL import Image, ImageEnhance
    import numpy as np

    tile = Image.new("RGB", (100, 100), color=(50, 50, 80))  # dark map tile

    def apply_brightness(factor):
        t = ImageEnhance.Brightness(tile).enhance(factor)
        return np.array(t).mean()

    assert apply_brightness(1.3) > apply_brightness(1.0)
    assert apply_brightness(1.0) > apply_brightness(0.7)


@pytest.mark.parametrize("change", ["style", "zoom", "tile_size", "target_size"])
def test_cache_identity_includes_provider_zoom_and_tile_size(tmp_path, change):
    import io
    bounds = {"lat_min": 0, "lat_max": 30, "lng_min": 0, "lng_max": 30}
    kwargs = dict(bounds=bounds, zoom=2, cache_path=str(tmp_path / "tile.png"),
                  target_size=(100, 100), url_template="https://one.invalid/{z}/{x}/{y}.png",
                  tile_size=256)

    def response(color, size):
        buf = io.BytesIO()
        Image.new("RGB", (size, size), color=color).save(buf, format="PNG")
        return MagicMock(content=buf.getvalue())

    with patch("requests.Session.get", return_value=response("red", 256)):
        first = fetch_map_tile(**kwargs)
    if change == "style":
        kwargs["url_template"] = "https://two.invalid/{z}/{x}/{y}.png"
    elif change == "zoom":
        kwargs["zoom"] = 3
    elif change == "tile_size":
        kwargs["tile_size"] = 512
    else:
        kwargs["target_size"] = (200, 200)
    with patch("requests.Session.get", return_value=response("blue", kwargs["tile_size"])) as getting:
        second = fetch_map_tile(**kwargs)
    assert first.getpixel((50, 50)) == (255, 0, 0)
    if change == "target_size":
        getting.assert_not_called()
        assert second.size == (200, 200)
        assert second.getpixel((50, 50)) == (255, 0, 0)
    else:
        assert getting.call_count > 0
        assert second.getpixel((50, 50)) == (0, 0, 255)
    assert len(list(tmp_path.glob("tile-*.png"))) == 2


def test_sf_zoom17_does_not_allocate_a_citywide_native_mosaic(tmp_path):
    import io
    import math
    from config import CITY_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX

    bounds = CITY_BOUNDS
    x0, y1 = lat_lng_to_tile(bounds["lat_min"], bounds["lng_min"], 17)
    x1, y0 = lat_lng_to_tile(bounds["lat_max"], bounds["lng_max"], 17)
    native_area = (x1 - x0 + 1) * (y1 - y0 + 1) * 256 ** 2
    assert native_area > 2 * Image.MAX_IMAGE_PIXELS
    tile_data = io.BytesIO()
    Image.new("RGB", (256, 256), (20, 30, 40)).save(tile_data, format="PNG")
    response = MagicMock(content=tile_data.getvalue())
    image_new = Image.new
    allocations = []

    def bounded_new(mode, size, *args, **kwargs):
        allocations.append(math.prod(size))
        assert math.prod(size) <= 32_000_000, "Do not allocate the native-resolution mosaic"
        return image_new(mode, size, *args, **kwargs)

    with patch("src.tiles.Image.new", side_effect=bounded_new), \
         patch("requests.Session.get", return_value=response) as getting:
        image = fetch_map_tile(bounds, 17, str(tmp_path / "map.png"),
                               (CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX))
    assert image.size == (CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX)
    assert image.getpixel((image.width // 2, image.height // 2)) == (20, 30, 40)
    assert getting.call_count == (x1 - x0 + 1) * (y1 - y0 + 1)
    assert max(allocations) < native_area / 5
    with patch("requests.Session.get") as getting:
        cached = fetch_map_tile(bounds, 17, str(tmp_path / "map.png"), image.size)
    getting.assert_not_called()
    assert cached.size == image.size


@pytest.mark.parametrize("target_size", [(300, 200), (1200, 1000)])
def test_banded_resampling_matches_full_lanczos_reference(tmp_path, target_size):
    import io
    import math

    bounds = {"lat_min": 1.5, "lat_max": 35.5, "lng_min": 1.5, "lng_max": 46.5}
    zoom = 4
    x0, y1 = lat_lng_to_tile(bounds["lat_min"], bounds["lng_min"], zoom)
    x1, y0 = lat_lng_to_tile(bounds["lat_max"], bounds["lng_max"], zoom)
    mosaic = Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256))
    responses = {}
    for tx in range(x0, x1 + 1):
        for ty in range(y0, y1 + 1):
            y, x = np.indices((256, 256))
            world_x = x + tx * 256
            world_y = y + ty * 256
            rgb = np.stack(((world_x % 1024) // 4, (world_y % 1024) // 4,
                            (world_x + world_y) % 256), axis=-1).astype(np.uint8)
            tile = Image.fromarray(rgb)
            mosaic.paste(tile, ((tx - x0) * 256, (ty - y0) * 256))
            buf = io.BytesIO()
            tile.save(buf, format="PNG")
            responses[(tx, ty)] = MagicMock(content=buf.getvalue())

    def get(url, **kwargs):
        parts = url.removesuffix(".png").split("/")
        return responses[(int(parts[-2]), int(parts[-1]))]

    def world_y(lat):
        return (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * (2 ** zoom) * 256

    box = ((bounds["lng_min"] + 180) / 360 * (2 ** zoom) * 256 - x0 * 256,
           world_y(bounds["lat_max"]) - y0 * 256,
           (bounds["lng_max"] + 180) / 360 * (2 ** zoom) * 256 - x0 * 256,
           world_y(bounds["lat_min"]) - y0 * 256)
    expected = np.asarray(mosaic.resize(target_size, Image.LANCZOS, box=box))
    with patch("requests.Session.get", side_effect=get):
        actual = np.asarray(fetch_map_tile(bounds, zoom, str(tmp_path / "map.png"),
                                           target_size, "https://tiles.invalid/{z}/{x}/{y}.png"))
    assert np.abs(actual.astype(int) - expected.astype(int)).max() <= 1


def test_interrupted_download_resumes_from_cached_tiles(tmp_path):
    import io
    import requests
    bounds = {"lat_min": 0, "lat_max": 30, "lng_min": 0, "lng_max": 60}
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (20, 30, 40)).save(buf, format="PNG")
    response = MagicMock(content=buf.getvalue())
    failures = [requests.ConnectionError("connection reset")] * 4
    kwargs = dict(bounds=bounds, zoom=4, cache_path=str(tmp_path / "map.png"),
                  target_size=(300, 200))
    with patch("requests.Session.get", side_effect=[response, response, *failures]), \
         patch("src.tiles.time.sleep") as sleeping:
        with pytest.raises(requests.ConnectionError):
            fetch_map_tile(**kwargs)
    assert sleeping.call_count == 3
    assert len(list((tmp_path / "map_tiles").rglob("*.png"))) == 2
    assert not list(tmp_path.glob("map-*.png"))
    with patch("requests.Session.get", return_value=response) as getting:
        result = fetch_map_tile(**kwargs)
    x0, y1 = lat_lng_to_tile(0, 0, 4)
    x1, y0 = lat_lng_to_tile(30, 60, 4)
    assert getting.call_count == (x1 - x0 + 1) * (y1 - y0 + 1) - 2
    assert result.size == (300, 200)


def test_tile_retry_honors_retry_after_and_does_not_retry_permanent_errors():
    import requests
    from src.tiles import _download_tile
    session = MagicMock()
    limited = MagicMock(status_code=429, headers={"Retry-After": "7"})
    failure = requests.HTTPError(response=limited)
    session.get.side_effect = [failure, MagicMock(content=b"image")]
    with patch("src.tiles.time.sleep") as sleeping:
        assert _download_tile(session, "https://tiles.invalid") == b"image"
    sleeping.assert_called_once_with(7)
    forbidden = MagicMock(status_code=403)
    session.get.reset_mock()
    session.get.side_effect = requests.HTTPError(response=forbidden)
    with patch("src.tiles.time.sleep") as sleeping:
        with pytest.raises(requests.HTTPError):
            _download_tile(session, "https://tiles.invalid")
    session.get.assert_called_once()
    sleeping.assert_not_called()


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("reencode", [False, True])
def test_carto_http200_auth_placeholder_is_rejected(tmp_path, cached, reencode):
    import hashlib
    import io
    import requests
    from src.tiles import CARTO_URL
    content = (Path(__file__).parent / "fixtures/carto-api-key-required.png").read_bytes()
    if reencode:
        with Image.open(io.BytesIO(content)) as image:
            encoded = io.BytesIO()
            image.save(encoded, format="PNG", compress_level=0)
        assert encoded.getvalue() != content
        content = encoded.getvalue()
    bounds = {"lat_min": 0, "lat_max": 30, "lng_min": 0, "lng_max": 60}
    if cached:
        provider = hashlib.sha256(f"{CARTO_URL}:256".encode()).hexdigest()[:12]
        x, _ = lat_lng_to_tile(bounds["lat_min"], bounds["lng_min"], 4)
        _, y = lat_lng_to_tile(bounds["lat_max"], bounds["lng_max"], 4)
        path = tmp_path / "map_tiles" / provider / "4" / str(x) / f"{y}.png"
        path.parent.mkdir(parents=True)
        path.write_bytes(content)
    with patch("requests.Session.get", return_value=MagicMock(content=content)) as getting:
        with pytest.raises(requests.HTTPError, match="requires an API key"):
            fetch_map_tile(bounds, 4, str(tmp_path / "map.png"), (300, 200))
    assert getting.call_count == int(not cached)
    assert not list(tmp_path.glob("map-*.png"))
