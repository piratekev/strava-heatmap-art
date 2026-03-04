import numpy as np
import pytest
from src.renderer import StravaRenderer
from config import SF_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX


@pytest.fixture
def renderer():
    return StravaRenderer(width=540, height=720)  # 1/10 scale for tests


def test_project_sf_center_to_canvas_center(renderer):
    """SF centroid should project near the canvas center."""
    center_lat = (SF_BOUNDS["lat_min"] + SF_BOUNDS["lat_max"]) / 2
    center_lng = (SF_BOUNDS["lng_min"] + SF_BOUNDS["lng_max"]) / 2
    x, y = renderer.project(center_lat, center_lng)
    assert abs(x - 270) < 30  # within 30px of center (540/2)
    assert abs(y - 360) < 30  # within 30px of center (720/2)


def test_project_top_left_corner(renderer):
    """SW corner of SF bounds → near bottom-left of canvas (lat inverted)."""
    x, y = renderer.project(SF_BOUNDS["lat_min"], SF_BOUNDS["lng_min"])
    assert x < 100
    assert y > 620  # near bottom (lat_min = south = high y)


def test_project_top_right_corner(renderer):
    """NE corner → near top-right."""
    x, y = renderer.project(SF_BOUNDS["lat_max"], SF_BOUNDS["lng_max"])
    assert x > 440
    assert y < 100


def test_canvas_initialized_to_zero(renderer):
    assert renderer.canvas.shape == (720, 540)
    assert renderer.canvas.dtype == np.float32
    assert renderer.canvas.max() == 0.0


def test_full_resolution_canvas():
    r = StravaRenderer()
    assert r.canvas.shape == (CANVAS_HEIGHT_PX, CANVAS_WIDTH_PX)


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
    assert img.shape == (720, 540, 3)
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


def test_bloom_spreads_light_to_adjacent_pixels(renderer):
    """A single bright pixel should produce non-zero neighbors after bloom."""
    renderer.canvas[360, 270] = 10.0
    img = renderer.to_image(bloom=True)
    # Neighbors should be brighter than background
    center = int(img[360, 270].mean())
    neighbor = int(img[358, 270].mean())
    assert neighbor > 10  # background is ~10
