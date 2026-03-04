import numpy as np
import pytest
from src.renderer import StravaRenderer
from config import SF_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX


@pytest.fixture
def renderer():
    return StravaRenderer(width=540, height=540)  # 1/10 scale for tests


def test_project_sf_center_to_canvas_center(renderer):
    """SF centroid should project near the canvas center."""
    center_lat = (SF_BOUNDS["lat_min"] + SF_BOUNDS["lat_max"]) / 2
    center_lng = (SF_BOUNDS["lng_min"] + SF_BOUNDS["lng_max"]) / 2
    x, y = renderer.project(center_lat, center_lng)
    assert abs(x - 270) < 30  # within 30px of center (540/2)
    assert abs(y - 270) < 30  # within 30px of center (540/2)


def test_project_top_left_corner(renderer):
    """SW corner of SF bounds → near bottom-left of canvas (lat inverted)."""
    x, y = renderer.project(SF_BOUNDS["lat_min"], SF_BOUNDS["lng_min"])
    assert x < 100
    assert y > 490  # near bottom of 540px canvas


def test_project_top_right_corner(renderer):
    """NE corner → near top-right."""
    x, y = renderer.project(SF_BOUNDS["lat_max"], SF_BOUNDS["lng_max"])
    assert x > 440
    assert y < 100


def test_canvas_initialized_to_zero(renderer):
    assert renderer.canvas.shape == (540, 540)
    assert renderer.canvas.dtype == np.float32
    assert renderer.canvas.max() == 0.0


def test_full_resolution_canvas():
    r = StravaRenderer()
    assert r.canvas.shape == (CANVAS_HEIGHT_PX, CANVAS_WIDTH_PX)  # (5400, 5400)


def test_rasterize_run_draws_nonzero_pixels(renderer):
    """Drawing a run across the canvas produces non-zero pixels."""
    coords = [
        (37.76, -122.47),
        (37.77, -122.44),
        (37.78, -122.42),
    ]
    renderer.rasterize_run(coords)
    assert renderer.canvas.max() > 0


def test_rasterize_two_runs_doubles_density_on_overlap(renderer):
    """Same route drawn twice doubles the density values."""
    coords = [(37.76, -122.47), (37.78, -122.42)]
    renderer.rasterize_run(coords)
    first_max = renderer.canvas.max()
    renderer.rasterize_run(coords)
    assert renderer.canvas.max() == pytest.approx(first_max * 2)


def test_rasterize_all_runs(renderer):
    runs = [
        {"coords": [(37.76, -122.47), (37.77, -122.44)]},
        {"coords": [(37.75, -122.46), (37.78, -122.42)]},
    ]
    renderer.rasterize_all(runs)
    assert renderer.canvas.max() > 0


def test_to_image_returns_rgb_array(renderer):
    renderer.rasterize_run([(37.76, -122.47), (37.77, -122.44)])
    img = renderer.to_image()
    assert img.shape == (540, 540, 3)
    assert img.dtype == np.uint8


def test_to_image_background_is_dark(renderer):
    """Empty canvas should produce a near-black image."""
    img = renderer.to_image()
    assert img.mean() < 20


def test_to_image_routes_are_bright(renderer):
    """Canvas with a run should produce brighter pixels than empty canvas."""
    empty = renderer.to_image().mean()
    renderer.rasterize_run([(37.72, -122.50), (37.82, -122.35)])
    with_run = renderer.to_image().mean()
    assert with_run > empty


def test_bloom_increases_brightness(renderer):
    """Bloom effect should produce a brighter image than without it."""
    renderer.rasterize_run([(37.76, -122.47), (37.77, -122.44)])
    without_bloom = renderer.to_image(bloom=False).mean()
    with_bloom = renderer.to_image(bloom=True).mean()
    assert with_bloom > without_bloom



def test_vignette_darkens_corners_vs_center(renderer):
    """Corners should be darker than center after vignette."""
    renderer.canvas[:] = 5.0
    img = renderer.to_image(bloom=False, vignette=True, grain=False)
    center = int(img[270, 270].mean())
    corner = int(img[10, 10].mean())
    assert corner < center


def test_grain_adds_pixel_variance(renderer):
    """Film grain should increase variance of a flat region."""
    # Use empty canvas so base image is near-uniform; use large grain_amount for clear signal
    without = renderer.to_image(bloom=False, vignette=False, grain=False).std()
    with_grain = renderer.to_image(bloom=False, vignette=False, grain=True, grain_amount=0.5).std()
    assert with_grain > without


def test_set_bounds_updates_projection():
    """After set_bounds(), project() maps run extent to canvas edges."""
    r = StravaRenderer(width=540, height=540)
    runs = [{"coords": [(37.70, -122.50), (37.80, -122.40)]}]
    r.set_bounds(runs, padding=0.0)
    # SW corner should project near bottom-left
    x, y = r.project(37.70, -122.50)
    assert x < 10
    assert y > 530
    # NE corner should project near top-right
    x, y = r.project(37.80, -122.40)
    assert x > 530
    assert y < 10


def test_set_bounds_adds_padding():
    """Padding pushes route extents inward from canvas edges."""
    r = StravaRenderer(width=540, height=540)
    runs = [{"coords": [(37.70, -122.50), (37.80, -122.40)]}]
    r.set_bounds(runs, padding=0.1)
    x, y = r.project(37.70, -122.50)
    assert x > 20   # inset from left edge due to padding
    assert y < 520  # inset from bottom edge due to padding


def test_set_bounds_defaults_to_sf_bounds():
    """Renderer without set_bounds() uses SF_BOUNDS (existing behaviour)."""
    r = StravaRenderer(width=540, height=540)
    center_lat = (SF_BOUNDS["lat_min"] + SF_BOUNDS["lat_max"]) / 2
    center_lng = (SF_BOUNDS["lng_min"] + SF_BOUNDS["lng_max"]) / 2
    x, y = r.project(center_lat, center_lng)
    assert abs(x - 270) < 30
    assert abs(y - 270) < 30


def test_color_ramp_low_density_is_blue(renderer):
    """Low-density pixels should appear blue (B >= R)."""
    renderer.canvas[100, 100] = 1.0    # low density
    renderer.canvas[200, 200] = 50.0   # high density anchor
    img = renderer.to_image(bloom=False, vignette=False, grain=False)
    r, g, b = img[100, 100]
    assert int(b) >= int(r)


def test_color_ramp_high_density_is_pink(renderer):
    """High-density pixels should appear pink (R > 150)."""
    renderer.canvas[100, 100] = 1.0
    renderer.canvas[200, 200] = 50.0
    img = renderer.to_image(bloom=False, vignette=False, grain=False)
    r, g, b = img[200, 200]
    assert int(r) > 150


def test_project_uses_mercator_y():
    """Mercator midpoint (not geographic midpoint) should map to canvas center."""
    import math
    r = StravaRenderer(width=540, height=540)
    # Compute the Mercator midpoint of SF bounds
    merc_min = math.asinh(math.tan(math.radians(SF_BOUNDS["lat_min"])))
    merc_max = math.asinh(math.tan(math.radians(SF_BOUNDS["lat_max"])))
    merc_mid = (merc_min + merc_max) / 2
    # Back-convert Mercator midpoint to lat
    lat_mercator_center = math.degrees(math.atan(math.sinh(merc_mid)))
    lng_center = (SF_BOUNDS["lng_min"] + SF_BOUNDS["lng_max"]) / 2
    x, y = r.project(lat_mercator_center, lng_center)
    assert abs(y - 270) < 2  # should be very close to canvas center
