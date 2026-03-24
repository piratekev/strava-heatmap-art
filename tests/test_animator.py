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
