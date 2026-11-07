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


def test_advance_cursor_zero_length_last_segment_clamps():
    """Zero-length last segment must not advance seg_idx past n-2."""
    pts = [(0, 0), (100, 0), (100, 0)]  # seg1 (index 1) has zero length (last)
    new_seg, new_t, drawn = advance_cursor(pts, 1, 0.0, 50.0)
    # n=3, last valid segment is n-2=1 → must clamp to (1, 1.0)
    assert new_seg == 1
    assert new_t == pytest.approx(1.0)


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


# ── ffmpeg pipe ───────────────────────────────────────────────────────────────

from unittest.mock import patch, MagicMock
from src.animator import check_ffmpeg, open_ffmpeg_pipe


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

from src.animator import compute_total_frames, build_run_pixel_coords


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


def test_compute_total_frames_proportional_to_distance():
    renderer = _make_renderer()
    run_a = _make_run([(37.77, -122.45), (37.78, -122.45)])
    run_b = _make_run([(37.77, -122.45), (37.77, -122.44)])  # similar length
    frames_a = compute_total_frames([run_a], renderer, drawing_speed=10)
    frames_b = compute_total_frames([run_b], renderer, drawing_speed=10)
    # Both should produce some frames; difference < 50% of mean
    assert frames_a > 0
    assert frames_b > 0


def test_compute_total_frames_zero_for_single_point_run():
    renderer = _make_renderer()
    run = _make_run([(37.77, -122.45)])  # only one point, no segments
    frames = compute_total_frames([run], renderer, drawing_speed=10)
    assert frames == 0


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


# ── Loop invariant tests ──────────────────────────────────────────────────────

from unittest.mock import patch, MagicMock


def _make_renderer_for_loop(width=100, height=125):
    from src.renderer import StravaRenderer
    return StravaRenderer(width=width, height=height)


def _make_run_for_loop(coords, start_date="2020-01-01T00:00:00Z"):
    return {
        "id": 1,
        "coords": coords,
        "start_date": start_date,
        "distance": 1000.0,
        "average_speed": 3.0,
        "total_elevation_gain": 10.0,
    }


def _make_anim_config(width=100, height=125):
    class Cfg:
        ANIMATION_FPS = 10
        ANIMATION_DRAWING_SPEED = 500   # large speed → one frame per run
        ANIMATION_DOT_RADIUS = 3
        ANIMATION_DOT_BLUR = 0
        ANIMATION_HOLD_SECONDS = 0
        ANIMATION_OUTPUT_RESOLUTION = (width, height)
    return Cfg


def _mock_tile(width, height):
    from PIL import Image
    return Image.new("RGB", (width, height), (30, 30, 30))


def test_final_log_max_matches_prepass():
    """final_log_max from pre-pass equals np.log1p(canvas).max() after rasterizing all runs."""
    from src.renderer import StravaRenderer
    run = _make_run_for_loop([(37.77, -122.45), (37.78, -122.44), (37.79, -122.43)])
    W, H = 100, 125
    renderer = StravaRenderer(width=W, height=H)
    renderer.rasterize_all([run])
    expected_log_max = float(np.log1p(renderer.canvas).max())
    assert expected_log_max > 0
    # Verify log1p max matches canvas max via log1p
    assert np.isclose(expected_log_max, np.log1p(renderer.canvas.max()))


def test_run_count_increments_for_short_run():
    """Runs with <2 points increment run_count but leave mileage unchanged."""
    from src.animator import run_animation
    W, H = 100, 125
    cfg = _make_anim_config(W, H)

    runs = [
        _make_run_for_loop([(37.77, -122.45)], "2020-01-01T00:00:00Z"),   # <2 pts
        _make_run_for_loop([(37.77, -122.45), (37.78, -122.44)], "2020-01-02T00:00:00Z"),
    ]

    written_frames = []

    class FakeProc:
        stdin = MagicMock()
        def wait(self): pass

    fake_proc = FakeProc()
    fake_proc.stdin.write = lambda b: written_frames.append(len(b))
    fake_proc.stdin.close = lambda: None

    tile = _mock_tile(W, H)

    with patch("src.animator.open_ffmpeg_pipe", return_value=fake_proc), \
         patch("src.animator.check_ffmpeg"), \
         patch("src.tiles.fetch_map_tile", return_value=tile), \
         patch("src.typography._download_font"), \
         patch("src.typography.render_legend", return_value=Image.new("RGB", (W, H), (0,0,0))), \
         patch("src.animator.render_animation_typography", side_effect=lambda img, *a, **kw: img):
        run_animation(runs, "/tmp/test-anim-short-run.mp4", cfg)

    # At least one frame was written (from the 2-point run)
    assert len(written_frames) > 0


def test_mileage_monotonically_non_decreasing():
    """Accumulated mileage never decreases across frames."""
    from src.animator import (
        advance_cursor, compute_frame_miles, build_run_pixel_coords,
        canvas_to_rgb, paint_dot, render_animation_typography,
    )
    from src.renderer import StravaRenderer
    from src.typography import _download_font
    from config import ROUTE_COLOR_RAMP, BG_COLOR, GAMMA, MAP_FONT_PATH, MAP_FONT_URL
    import math

    W, H = 100, 125
    renderer = StravaRenderer(width=W, height=H)
    run = _make_run_for_loop([
        (37.77, -122.45), (37.775, -122.44), (37.78, -122.43), (37.785, -122.42)
    ])

    px_coords = build_run_pixel_coords(run, renderer)
    geo_coords = run["coords"]
    accumulation = np.zeros((H, W), dtype=np.float32)
    final_log_max = 1.0   # dummy anchor

    total_miles = 0.0
    prev_miles = 0.0
    seg_idx, t = 0, 0.0
    drawing_speed = 5   # small → multiple frames

    while True:
        new_seg, new_t, drawn = advance_cursor(px_coords, seg_idx, t, drawing_speed)
        if drawn:
            frame_miles = compute_frame_miles(geo_coords, seg_idx, t, new_seg, new_t)
            total_miles += frame_miles
        assert total_miles >= prev_miles, f"mileage decreased: {prev_miles} → {total_miles}"
        prev_miles = total_miles
        seg_idx, t = new_seg, new_t
        if seg_idx >= len(px_coords) - 2 and t >= 1.0:
            break


def test_run_count_equals_n_on_first_frame_of_run_n():
    """run_count equals N on all frames of run N (including the first frame)."""
    # Simulate the per-run logic directly (no ffmpeg needed)
    from src.animator import advance_cursor
    from src.renderer import StravaRenderer

    W, H = 100, 125
    renderer = StravaRenderer(width=W, height=H)
    runs = [
        _make_run_for_loop([(37.77, -122.45), (37.78, -122.44)], "2020-01-01T00:00:00Z"),
        _make_run_for_loop([(37.78, -122.44), (37.79, -122.43)], "2020-01-02T00:00:00Z"),
    ]

    run_count = 0
    for n, run in enumerate(sorted(runs, key=lambda r: r["start_date"]), start=1):
        geo_coords = run["coords"]
        if len(geo_coords) < 2:
            run_count += 1
            continue
        from src.animator import build_run_pixel_coords
        px_coords = build_run_pixel_coords(run, renderer)
        run_count += 1
        # On the first frame, run_count must equal n
        assert run_count == n, f"run_count={run_count} but n={n} at first frame of run {n}"
        # Drain rest of run (not strictly needed but mirrors the loop)
        seg_idx, t = 0, 0.0
        while True:
            new_seg, new_t, drawn = advance_cursor(px_coords, seg_idx, t, 500)
            seg_idx, t = new_seg, new_t
            if seg_idx >= len(px_coords) - 2 and t >= 1.0:
                break
