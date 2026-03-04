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
            "distance": 10000.0,  # 10km = ~6.2 miles each
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
