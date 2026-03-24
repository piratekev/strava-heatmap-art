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
