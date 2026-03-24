import math
import pytest
from src.animator import haversine_miles, compute_frame_miles


def test_haversine_same_point_is_zero():
    assert haversine_miles(37.76, -122.45, 37.76, -122.45) == pytest.approx(0.0)


def test_haversine_known_distance():
    # SF City Hall to ~1 mile north: rough check within 5%
    miles = haversine_miles(37.7749, -122.4194, 37.7904, -122.4194)
    assert 0.95 < miles < 1.15


def test_compute_frame_miles_full_segment():
    # geo_coords: two points ~1 mile apart
    geo = [(37.7749, -122.4194), (37.7904, -122.4194)]
    miles = compute_frame_miles(geo, 0, 0.0, 0, 1.0)
    assert 0.95 < miles < 1.15


def test_compute_frame_miles_half_segment():
    geo = [(37.7749, -122.4194), (37.7904, -122.4194)]
    full = compute_frame_miles(geo, 0, 0.0, 0, 1.0)
    half = compute_frame_miles(geo, 0, 0.0, 0, 0.5)
    assert half == pytest.approx(full / 2, rel=0.01)


def test_compute_frame_miles_spans_two_segments():
    # Three points: A→B ~0.5mi, B→C ~0.5mi
    geo = [(37.7749, -122.4194), (37.7826, -122.4194), (37.7904, -122.4194)]
    # Full path from start of seg0 to end of seg1
    miles = compute_frame_miles(geo, 0, 0.0, 1, 1.0)
    assert 0.95 < miles < 1.15


def test_compute_frame_miles_zero_distance():
    geo = [(37.7749, -122.4194), (37.7904, -122.4194)]
    assert compute_frame_miles(geo, 0, 0.5, 0, 0.5) == pytest.approx(0.0)


# ── Cursor ────────────────────────────────────────────────────────────────────

from src.animator import advance_cursor


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


# ── Color mapping ─────────────────────────────────────────────────────────────

import numpy as np
from src.animator import canvas_to_rgb


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

from src.animator import paint_dot


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

from PIL import Image
from src.animator import render_animation_typography


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
    before = list(img.getdata())
    result = render_animation_typography(
        img, "Jan 2020", 1, 0,
        font_path="data/fonts/Montserrat-SemiBold.ttf",
        scale=1.0,
    )
    after = list(result.getdata())
    assert before != after  # some pixels changed (text was drawn)
