"""Unit tests for animation traversal, color, dots, typography, and encoding."""
import math
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image
import pytest

from src.animator import (
    advance_cursor, build_run_pixel_coords, canvas_to_rgb, check_ffmpeg,
    open_ffmpeg_pipe, paint_dot, render_animation_typography,
)

# ── Cursor ────────────────────────────────────────────────────────────────────



def test_advance_cursor_within_single_segment():
    pts = [(0, 0), (100, 0)]  # 100px horizontal segment
    new_seg, new_t, drawn = advance_cursor(pts, 0, 0.0, 50.0)
    assert new_seg == 0
    assert new_t == pytest.approx(0.5)
    assert len(drawn) == 1
    assert drawn[0][0] == pytest.approx((0.0, 0.0))
    assert drawn[0][1] == pytest.approx((50.0, 0.0))


def test_advance_cursor_crosses_segment_boundary():
    pts = [(0, 0), (50, 0), (150, 0)]  # seg0=50px, seg1=100px
    new_seg, new_t, drawn = advance_cursor(pts, 0, 0.0, 75.0)
    assert new_seg == 1
    assert new_t == pytest.approx(0.25)
    assert len(drawn) == 2  # one sub-seg per spanned segment


def test_advance_cursor_stops_at_path_end():
    pts = [(0, 0), (100, 0)]
    new_seg, new_t, drawn = advance_cursor(pts, 0, 0.0, 999.0)
    assert new_seg == 0   # last valid segment index
    assert new_t == pytest.approx(1.0)


def test_advance_cursor_from_mid_segment():
    pts = [(0, 0), (100, 0)]
    new_seg, new_t, drawn = advance_cursor(pts, 0, 0.5, 25.0)
    assert new_seg == 0
    assert new_t == pytest.approx(0.75)
    assert drawn[0][0] == pytest.approx((50.0, 0.0))
    assert drawn[0][1] == pytest.approx((75.0, 0.0))


def test_advance_cursor_zero_length_segment_skipped():
    pts = [(10, 10), (10, 10), (110, 10)]  # seg0 has zero length
    new_seg, new_t, drawn = advance_cursor(pts, 0, 0.0, 50.0)
    # should advance into seg1 (or skip seg0) without dividing by zero
    assert new_t >= 0.0


def test_advance_cursor_zero_length_last_segment_clamps():
    """Zero-length last segment must not advance seg_idx past n-2."""
    pts = [(0, 0), (100, 0), (100, 0)]  # seg1 (index 1) has zero length (last)
    new_seg, new_t, drawn = advance_cursor(pts, 1, 0.0, 50.0)
    # n=3, last valid segment is n-2=1 → must clamp to (1, 1.0)
    assert new_seg == 1
    assert new_t == pytest.approx(1.0)


# ── Color mapping ─────────────────────────────────────────────────────────────



def test_canvas_to_rgb_all_zero_is_bg_color():
    canvas = np.zeros((10, 10), dtype=np.float32)
    final_log_max = 1.0
    color_ramp = [(0.0, [0, 0, 255]), (1.0, [255, 0, 0])]
    bg = [0, 0, 0]
    rgb = canvas_to_rgb(canvas, final_log_max, gamma=1.0, color_ramp=color_ramp, bg_color=bg)
    assert rgb.shape == (10, 10, 3)
    assert rgb.dtype == np.uint8
    assert rgb.max() == 0  # all background = black


def test_canvas_to_rgb_at_final_log_max_is_bright():
    # A canvas where one pixel equals e^final_log_max - 1 (i.e. log1p = final_log_max)
    final_log_max = math.log1p(5.0)
    canvas = np.zeros((5, 5), dtype=np.float32)
    canvas[2, 2] = 5.0  # log1p(5) / final_log_max = 1.0
    color_ramp = [(0.0, [0, 0, 255]), (1.0, [255, 0, 0])]
    bg = [0, 0, 0]
    rgb = canvas_to_rgb(canvas, final_log_max, gamma=1.0, color_ramp=color_ramp, bg_color=bg)
    # Peak pixel should be near [255, 0, 0]
    assert rgb[2, 2, 0] > 200
    assert rgb[2, 2, 2] < 50


def test_canvas_to_rgb_shape_preserved():
    canvas = np.ones((20, 15), dtype=np.float32)
    rgb = canvas_to_rgb(canvas, final_log_max=1.0, gamma=1.0,
                        color_ramp=[(0.0, [0,0,0]), (1.0, [255,255,255])],
                        bg_color=[0,0,0])
    assert rgb.shape == (20, 15, 3)


# ── Dot rendering ─────────────────────────────────────────────────────────────



def test_paint_dot_center_is_white():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    paint_dot(frame, cx=50, cy=50, radius=5, blur_sigma=0)
    assert frame[50, 50, 0] == 255
    assert frame[50, 50, 1] == 255
    assert frame[50, 50, 2] == 255


def test_paint_dot_does_not_modify_far_pixels():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    paint_dot(frame, cx=50, cy=50, radius=5, blur_sigma=0)
    assert frame[0, 0, 0] == 0  # top-left corner untouched


def test_paint_dot_with_blur_does_not_crash():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    paint_dot(frame, cx=50, cy=50, radius=5, blur_sigma=4)
    # Blur spreads energy — center should still be bright-ish
    assert frame[50, 50, 0] > 100


def test_paint_dot_clipped_at_edge():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # Should not raise even when dot is partially out of bounds
    paint_dot(frame, cx=0, cy=0, radius=10, blur_sigma=0)


# ── Typography ────────────────────────────────────────────────────────────────



def test_render_animation_typography_returns_image():
    img = Image.new("RGB", (1080, 1350), (0, 0, 0))
    result = render_animation_typography(
        img,
        month_year="Mar 2019",
        run_count=42,
        total_miles_floor=312,
        font_path="data/fonts/Montserrat-SemiBold.ttf",
        scale=1.0,
    )
    assert isinstance(result, Image.Image)
    assert result.size == (1080, 1350)


def test_render_animation_typography_modifies_pixels():
    img = Image.new("RGB", (1080, 1350), (0, 0, 0))
    before = np.array(img)
    result = render_animation_typography(
        img, "Jan 2020", 1, 0,
        font_path="data/fonts/Montserrat-SemiBold.ttf",
        scale=1.0,
    )
    after = np.array(result)
    assert not np.array_equal(before, after)  # text changed some pixels


# ── ffmpeg pipe ───────────────────────────────────────────────────────────────



def test_check_ffmpeg_passes_when_available():
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        check_ffmpeg()  # should not raise


def test_check_ffmpeg_exits_when_missing():
    with patch("shutil.which", return_value=None):
        with pytest.raises(SystemExit):
            check_ffmpeg()


def test_open_ffmpeg_pipe_uses_correct_args():
    mock_proc = MagicMock()
    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        proc = open_ffmpeg_pipe("out.mp4", width=1080, height=1350, fps=60)
        call_args = mock_popen.call_args[0][0]
        assert "ffmpeg" in call_args[0]
        assert "1080x1350" in call_args
        assert "60" in call_args
        assert "out.mp4" in call_args
        assert proc is mock_proc


# ── Animation loop helpers ────────────────────────────────────────────────────



def _make_renderer(width=200, height=250):
    from src.renderer import StravaRenderer
    return StravaRenderer(width=width, height=height)


def _make_run(coords):
    return {
        "id": 1,
        "coords": coords,
        "start_date": "2020-03-15T08:00:00Z",
        "distance": 5000.0,
        "average_speed": 3.0,
        "total_elevation_gain": 50.0,
    }


def test_build_run_pixel_coords_single_point_run_returns_one_point():
    renderer = _make_renderer()
    run = _make_run([(37.77, -122.45)])
    px = build_run_pixel_coords(run, renderer)
    assert len(px) == 1  # no segments — caller must guard len < 2


def test_build_run_pixel_coords_returns_list_of_tuples():
    renderer = _make_renderer()
    run = _make_run([(37.77, -122.45), (37.78, -122.44)])
    px = build_run_pixel_coords(run, renderer)
    assert len(px) == 2
    assert all(isinstance(p, tuple) and len(p) == 2 for p in px)
