import numpy as np
import pytest
from unittest.mock import patch
from PIL import Image, ImageFont
from src.typography import render_typography, _download_font


def _make_runs(n=10, year_start=2021, year_end=2024):
    """Build minimal sf_runs list for typography tests."""
    runs = []
    for i in range(n):
        year = year_start + (i % (year_end - year_start + 1))
        runs.append({
            "start_date": f"{year}-06-15T08:00:00Z",
            "distance": 10000.0,       # 10 km = ~6.2 mi each
            "total_elevation_gain": 100.0,  # 100 m = ~328 ft each
        })
    return runs


def test_render_typography_changes_pixels(tmp_path):
    """render_typography should modify the image (some pixels change)."""
    font_path = str(tmp_path / "font.ttf")
    img = Image.new("RGB", (540, 540), color=(10, 15, 30))
    before = np.array(img).copy()

    # Use a default PIL font (no file needed) for the test
    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        result = render_typography(img, _make_runs(), font_path=font_path)

    after = np.array(result)
    assert not np.array_equal(before, after)


def test_render_typography_text_in_bottom_right(tmp_path):
    """Text should appear in the bottom-right quadrant."""
    font_path = str(tmp_path / "font.ttf")
    img = Image.new("RGB", (540, 540), color=(10, 15, 30))
    before = np.array(img).copy()

    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        result = render_typography(img, _make_runs(), font_path=font_path)

    after = np.array(result)
    diff = (after.astype(int) - before.astype(int)).sum(axis=2)
    # Bottom-right quadrant should have more changed pixels than top-left
    h, w = diff.shape
    bottom_right = diff[h//2:, w//2:].sum()
    top_left = diff[:h//2, :w//2].sum()
    assert bottom_right > top_left


def test_render_typography_shows_miles(tmp_path):
    """Distance should be in miles, not km."""
    font_path = str(tmp_path / "font.ttf")
    # 10 runs × 10km = ~62.1 miles

    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        with patch("PIL.ImageDraw.ImageDraw.text") as mock_text:
            img = Image.new("RGB", (540, 540), color=(10, 15, 30))
            render_typography(img, _make_runs(n=10), font_path=font_path)
            all_text = " ".join(str(call) for call in mock_text.call_args_list)
            assert "mi" in all_text


def test_render_typography_year_range_from_sf_runs(tmp_path):
    """Year range derived from SF runs, not all activities."""
    font_path = str(tmp_path / "font.ttf")
    runs = _make_runs(year_start=2021, year_end=2024)

    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        with patch("PIL.ImageDraw.ImageDraw.text") as mock_text:
            img = Image.new("RGB", (540, 540), color=(10, 15, 30))
            render_typography(img, runs, font_path=font_path)
            all_text = " ".join(str(call) for call in mock_text.call_args_list)
            assert "2021" in all_text
            assert "2024" in all_text


def test_render_typography_scales_with_image_size(tmp_path):
    """Larger images should produce larger text (more changed pixels)."""
    font_path = str(tmp_path / "font.ttf")
    runs = _make_runs(n=5)

    with patch("src.typography._load_font", side_effect=lambda path, size: ImageFont.load_default(size=size)):
        small_img = Image.new("RGB", (200, 200), color=(0, 0, 0))
        render_typography(small_img, runs, font_path=font_path)
        small_changed = np.count_nonzero(np.array(small_img).sum(axis=2))

        large_img = Image.new("RGB", (800, 800), color=(0, 0, 0))
        render_typography(large_img, runs, font_path=font_path)
        large_changed = np.count_nonzero(np.array(large_img).sum(axis=2))

    assert large_changed > small_changed * 2.5


def test_render_typography_shows_elevation(tmp_path):
    """Elevation total should appear in footer as feet."""
    font_path = str(tmp_path / "font.ttf")
    # 10 runs × 100 m = 1000 m = 3281 ft

    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        with patch("PIL.ImageDraw.ImageDraw.text") as mock_text:
            img = Image.new("RGB", (540, 540), color=(10, 15, 30))
            render_typography(img, _make_runs(n=10), font_path=font_path)
            all_text = " ".join(str(call) for call in mock_text.call_args_list)
            assert "ft" in all_text


def test_render_typography_elevation_has_arrow(tmp_path):
    """Elevation label should include an upward arrow."""
    font_path = str(tmp_path / "font.ttf")
    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        with patch("PIL.ImageDraw.ImageDraw.text") as mock_text:
            img = Image.new("RGB", (540, 540), color=(10, 15, 30))
            render_typography(img, _make_runs(n=10), font_path=font_path)
            all_text = " ".join(str(call) for call in mock_text.call_args_list)
            assert "↑" in all_text


def test_render_typography_uniform_font_size(tmp_path):
    """All four lines should be rendered with the same font size."""
    font_path = str(tmp_path / "font.ttf")
    with patch("src.typography._load_font",
               side_effect=lambda path, size: ImageFont.load_default(size=size)) as mock_load:
        img = Image.new("RGB", (540, 540), color=(0, 0, 0))
        render_typography(img, _make_runs(), font_path=font_path)
        sizes = [call.args[1] for call in mock_load.call_args_list]
        assert len(set(sizes)) == 1  # every _load_font call uses the same size


def test_load_font_fallback_uses_size(tmp_path):
    """Font fallback should scale with requested size, not return tiny bitmap."""
    from src.typography import _load_font
    from PIL import Image, ImageDraw
    draw = ImageDraw.Draw(Image.new("RGB", (300, 300)))
    nonexistent = str(tmp_path / "nope.ttf")

    font_large = _load_font(nonexistent, size=40)
    font_small = _load_font(nonexistent, size=10)

    h_large = draw.textbbox((0, 0), "X", font=font_large)[3]
    h_small = draw.textbbox((0, 0), "X", font=font_small)[3]
    assert h_large > h_small


def test_download_font_sends_user_agent(tmp_path):
    """_download_font must use a Request with User-Agent to avoid CDN 403."""
    import urllib.request
    from unittest.mock import patch, MagicMock

    font_path = str(tmp_path / "fonts" / "test.ttf")
    mock_response = MagicMock()
    mock_response.read.return_value = b"fake font data"
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        _download_font(font_path, "https://example.com/font.ttf")

    call_arg = mock_urlopen.call_args[0][0]
    assert isinstance(call_arg, urllib.request.Request)
    assert "User-agent" in call_arg.headers
