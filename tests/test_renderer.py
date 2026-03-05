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


def test_sf_bounds_excludes_treasure_island():
    """Treasure Island coords should fall outside the right canvas edge."""
    r = StravaRenderer(width=540, height=540)
    x, _ = r.project(37.825, -122.370)  # Treasure Island centroid
    assert x > 540


def test_canvas_initialized_to_zero(renderer):
    assert renderer.canvas.shape == (540, 540)
    assert renderer.canvas.dtype == np.float32
    assert renderer.canvas.max() == 0.0


def test_full_resolution_canvas():
    r = StravaRenderer()
    assert r.canvas.shape == (CANVAS_HEIGHT_PX, CANVAS_WIDTH_PX)  # (5400, 4960)


def test_canvas_is_not_square():
    """Default canvas should be portrait (width < height) to match SF bounds aspect ratio."""
    assert CANVAS_WIDTH_PX < CANVAS_HEIGHT_PX


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


def test_color_ramp_peak_density_is_near_white(renderer):
    """Peak density pixels should blow out toward near-white (all channels > 200)."""
    renderer.canvas[100, 100] = 1.0    # low anchor
    renderer.canvas[200, 200] = 50.0   # peak density
    img = renderer.to_image(bloom=False, vignette=False, grain=False)
    r, g, b = img[200, 200]
    assert int(r) > 200 and int(g) > 200 and int(b) > 200


def test_glow_increases_brightness(renderer):
    """Glow pass should produce a brighter image than without it."""
    renderer.rasterize_run([(37.76, -122.47), (37.77, -122.44)])
    without = renderer.to_image(bloom=False, vignette=False, grain=False, glow=False).mean()
    with_glow = renderer.to_image(bloom=False, vignette=False, grain=False, glow=True).mean()
    assert with_glow > without


def test_gamma_brightens_mid_density(renderer):
    """gamma < 1 should produce brighter mid-density pixels than gamma=1 (linear)."""
    renderer.canvas[200, 200] = 10.0  # mid-density
    renderer.canvas[300, 300] = 50.0  # high-density anchor
    without = renderer.to_image(bloom=False, vignette=False, grain=False, glow=False, gamma=1.0).mean()
    with_gamma = renderer.to_image(bloom=False, vignette=False, grain=False, glow=False, gamma=0.7).mean()
    assert with_gamma > without


def test_hot_bloom_brightens_dense_pixels(renderer):
    """hot_bloom=True should produce a brighter image when high-density pixels exist."""
    renderer.canvas[150:250, 150:250] = 100.0  # 100x100 block — enough for measurable gaussian spread
    without = renderer.to_image(bloom=False, vignette=False, grain=False, glow=False, hot_bloom=False).mean()
    with_hot = renderer.to_image(bloom=False, vignette=False, grain=False, glow=False, hot_bloom=True).mean()
    assert with_hot > without


def test_hot_bloom_does_not_spread_to_medium_density(renderer):
    """Hot bloom must not fire on medium-density pixels that fall below HOT_BLOOM_THRESHOLD.

    With GAMMA=0.4, canvas=5 normalises to ~0.67 post-gamma — below the intended
    HOT_BLOOM_THRESHOLD of 0.75.  The blocks are 330 px apart so gaussian spread from
    the peak block does not contaminate the medium region.
    """
    renderer.canvas[50:100, 50:100] = 100.0    # peak: norm → 1.0
    renderer.canvas[380:430, 380:430] = 5.0    # medium: norm ≈ 0.39 → ~0.67 after gamma 0.4

    without_hot = renderer.to_image(bloom=False, vignette=False, grain=False,
                                    glow=False, hot_bloom=False, density_expand=False, gamma=0.4)
    with_hot    = renderer.to_image(bloom=False, vignette=False, grain=False,
                                    glow=False, hot_bloom=True,  density_expand=False, gamma=0.4)
    medium_delta = float(with_hot[380:430, 380:430].astype(int).mean() -
                         without_hot[380:430, 380:430].astype(int).mean())
    assert medium_delta < 3  # medium region should not glow from hot bloom


def test_rasterize_all_second_pass_thickens_hot_routes():
    """Two-pass rasterize_all should add extra density to hot corridors vs single-pass."""
    hot  = [(37.76, -122.47), (37.77, -122.44)]
    cold = [(37.73, -122.50), (37.72, -122.49)]

    runs = [{"coords": hot}] * 10 + [{"coords": cold}]

    # Two-pass (rasterize_all)
    r_two = StravaRenderer(width=540, height=540)
    r_two.rasterize_all(runs)

    # Single-pass (bare rasterize_run loop, no bonus)
    r_one = StravaRenderer(width=540, height=540)
    for run in runs:
        r_one.rasterize_run(run["coords"])

    # Hot corridor should be denser after two-pass because top routes get extra thickness
    assert r_two.canvas.max() > r_one.canvas.max()


def test_density_expand_brightens_dense_routes(renderer):
    """density_expand=True should produce a brighter image on dense pixel regions."""
    renderer.canvas[150:250, 150:250] = 50.0  # 100x100 dense block
    without = renderer.to_image(bloom=False, vignette=False, grain=False, glow=False,
                                hot_bloom=False, density_expand=False).mean()
    with_expand = renderer.to_image(bloom=False, vignette=False, grain=False, glow=False,
                                    hot_bloom=False, density_expand=True).mean()
    assert with_expand > without


def test_to_image_default_gamma_matches_config():
    """Default gamma in to_image() should equal GAMMA from config."""
    import inspect
    from config import GAMMA
    sig = inspect.signature(StravaRenderer.to_image)
    assert sig.parameters["gamma"].default == GAMMA


def test_near_peak_density_pixels_are_not_black(renderer):
    """Near-peak-density pixels must not render black — norm > 1 overflow bug guard.

    density_expand uses a screen-blend with DENSITY_EXPAND_STRENGTH > 1.0, which can
    push norm above 1.0 for pixels just below peak density.  When norm > 1 the colour
    formula produces negative values that clip to 0 (black).
    """
    # Peak block sets the normalisation ceiling (norm → 1.0 there).
    renderer.canvas[150:200, 100:150] = 200.0
    # Near-peak block: norm ≈ log1p(150)/log1p(200) ≈ 0.946 → after gamma+expand → > 1.0
    renderer.canvas[300:350, 100:150] = 150.0
    img = renderer.to_image(bloom=False, vignette=False, grain=False, glow=False, hot_bloom=False)
    near_peak = img[300:350, 100:150]
    assert near_peak.mean() > 50  # should be near-white hot, not black (0)


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
