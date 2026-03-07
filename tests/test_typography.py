import numpy as np
import pytest
from unittest.mock import patch
from PIL import Image, ImageFont
from src.typography import render_typography, render_legend, _download_font

_RAMP = [
    (0.0,  [150, 100, 255]),
    (0.45, [200,   0, 255]),
    (0.8,  [255,   0, 180]),
    (1.0,  [255, 220, 255]),
]


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
    # urllib.request.Request normalises header keys to title-case first char only,
    # so "User-Agent" is stored internally as "User-agent"
    assert "User-agent" in call_arg.headers


def test_render_legend_modifies_bottom_center(tmp_path):
    """render_legend should draw into the bottom-center, not bottom-left or bottom-right."""
    img = Image.new("RGB", (540, 540), color=(10, 15, 30))
    before = np.array(img).copy()
    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        render_legend(img, color_ramp=_RAMP, font_path=str(tmp_path / "f.ttf"))
    after = np.array(img)
    diff = np.abs(after.astype(int) - before.astype(int)).sum(axis=2)
    h, w = diff.shape
    # Divide bottom half into three columns; center column should have the most changes
    third = w // 3
    bottom = diff[h // 2 :, :]
    left_third   = bottom[:, :third].sum()
    center_third = bottom[:, third : 2 * third].sum()
    right_third  = bottom[:, 2 * third :].sum()
    assert center_third > left_third
    assert center_third > right_third


def test_render_legend_bar_has_multiple_colors(tmp_path):
    """The gradient bar should contain more than one distinct color."""
    img = Image.new("RGB", (540, 540), color=(0, 0, 0))
    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        render_legend(img, color_ramp=_RAMP, font_path=str(tmp_path / "f.ttf"))
    arr = np.array(img)
    h, w = arr.shape[:2]
    # Sample a horizontal slice in the bottom-center area
    third = w // 3
    bar_region = arr[h * 3 // 4 :, third : 2 * third]
    unique_colors = len(np.unique(bar_region.reshape(-1, 3), axis=0))
    assert unique_colors > 5


def test_render_legend_labels_include_fixed_max(tmp_path):
    """Labels should include '1 run' on the left and '100+ runs' on the right."""
    img = Image.new("RGB", (540, 540), color=(0, 0, 0))
    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        with patch("PIL.ImageDraw.ImageDraw.text") as mock_text:
            render_legend(img, color_ramp=_RAMP, font_path=str(tmp_path / "f.ttf"))
    all_text = " ".join(str(c) for c in mock_text.call_args_list)
    assert "1 run" in all_text
    assert "100+" in all_text


def test_render_legend_left_color_shifts_with_gamma_correction(tmp_path):
    """Left edge of the legend bar should change when gamma correction is applied.

    Without correction (canvas_max_val=None, gamma=1.0) the bar starts at t=0
    (raw ramp[0] color).  With gamma=0.4 and canvas_max_val=50, t_min≈0.45
    so the left edge should be a noticeably different (violet) color.
    """
    font_path = str(tmp_path / "f.ttf")

    def left_bar_color(gamma_val, max_val):
        img = Image.new("RGB", (540, 540), color=(0, 0, 0))
        with patch("src.typography._load_font", return_value=ImageFont.load_default()):
            render_legend(img, color_ramp=_RAMP, font_path=font_path,
                          gamma=gamma_val, canvas_max_val=max_val)
        arr = np.array(img)
        h, w = arr.shape[:2]
        bar_width = max(120, w * 3 // 8)
        bar_left = (w - bar_width) // 2 + 2   # +2 to avoid edge antialiasing
        col = arr[:, bar_left, :]
        bright = col[col.sum(axis=1) > 30]
        return bright.mean(axis=0) if len(bright) else np.zeros(3)

    raw_color        = left_bar_color(gamma_val=1.0, max_val=None)
    corrected_color  = left_bar_color(gamma_val=0.4, max_val=50.0)

    color_diff = np.abs(corrected_color - raw_color).mean()
    assert color_diff > 15, (
        f"Left bar edge should shift with gamma correction "
        f"(raw={raw_color}, corrected={corrected_color}, diff={color_diff:.1f})"
    )


def test_download_font_redownloads_corrupt_file(tmp_path):
    """If font file exists but is tiny (corrupt/empty), delete and re-download."""
    import os
    import urllib.request
    from unittest.mock import patch, MagicMock

    font_path = str(tmp_path / "fonts" / "test.ttf")
    os.makedirs(os.path.dirname(font_path), exist_ok=True)
    # Write a tiny corrupt file (simulates a failed previous download)
    with open(font_path, "wb") as f:
        f.write(b"not a font")

    mock_response = MagicMock()
    mock_response.read.return_value = b"x" * 100_000   # simulates a real font
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        _download_font(font_path, "https://example.com/font.ttf")

    # Download should have been attempted despite file existing
    mock_urlopen.assert_called_once()
    # File should now contain the downloaded content
    with open(font_path, "rb") as f:
        assert len(f.read()) == 100_000


def test_render_legend_bar_width_not_shrunk_by_typography_scale(tmp_path):
    """bar_width must not be further shrunk when scale (TYPOGRAPHY_SCALE) < 1.

    A city config with TYPOGRAPHY_SCALE=0.7 should produce the same bar-width
    *proportion* (bar_width / canvas_width) as scale=1.0, since bar_width is
    already derived from canvas width w.
    """
    font_path = str(tmp_path / "f.ttf")

    def bar_proportion(scale_val):
        W = 400
        img = Image.new("RGB", (W, 500), color=(0, 0, 0))
        before = np.array(img).copy()
        with patch("src.typography._load_font", return_value=ImageFont.load_default()):
            render_legend(img, color_ramp=_RAMP, font_path=font_path, scale=scale_val)
        after = np.array(img)
        diff = np.abs(after.astype(int) - before.astype(int)).sum(axis=2)
        # Count columns in the bottom quarter that changed — bar lives near the bottom
        h, w = diff.shape
        center_cols = diff[3 * h // 4:, :]
        changed_cols = np.where(center_cols.sum(axis=0) > 0)[0]
        if len(changed_cols) == 0:
            return 0.0
        return (changed_cols[-1] - changed_cols[0]) / W

    prop_full  = bar_proportion(scale_val=1.0)
    prop_nyc   = bar_proportion(scale_val=0.7)

    # Proportions should be within 5% of each other (not 30% smaller as before)
    assert abs(prop_full - prop_nyc) < 0.05, (
        f"scale=1.0 → {prop_full:.2f}, scale=0.7 → {prop_nyc:.2f}; "
        f"bar_width must not shrink with TYPOGRAPHY_SCALE"
    )
