import json

import numpy as np
from unittest.mock import patch
from PIL import Image, ImageFont

from src.processor import load_bike_rides
from src.renderer import StravaRenderer
from src.typography import render_typography, render_corner_legend


def _ride(rid, lat, lng, ms=1_700_000_000_000):
    return {"ride_id": rid, "start_time_ms": ms,
            "coordinates": [[lat, lng], [lat + 0.001, lng + 0.001]]}


def test_load_bike_rides_filters_to_bounds_and_normalizes(tmp_path):
    path = tmp_path / "rides.json"
    path.write_text(json.dumps({
        "a": _ride("a", 37.77, -122.45),          # SF
        "b": _ride("b", 40.70, -74.00),           # NYC → dropped
        "c": {"ride_id": "c", "start_time_ms": 1, "coordinates": []},  # no track → dropped
    }))
    rides = load_bike_rides(str(path))
    assert [r["id"] for r in rides] == ["a"]
    r = rides[0]
    assert r["start_date"].startswith("2023-11-14") and r["start_date"].endswith("Z")
    assert 100 < r["distance"] < 200   # ~140 m diagonal
    assert r["coords"][0] == (37.77, -122.45)


def test_to_image_color_ramp_override():
    r = StravaRenderer(width=60, height=75)
    r.canvas[30:40, 20:40] = 5.0
    ramp = [(0.0, [255, 0, 0]), (1.0, [255, 0, 0])]
    img = r.to_image(bloom=False, glow=False, vignette=False, grain=False,
                     hot_bloom=False, density_expand=False, color_ramp=ramp)
    px = img[35, 30]
    assert px[0] == 255 and px[1] == 0 and px[2] == 0


def _runs():
    return [{"start_date": "2024-01-01T00:00:00Z", "distance": 5000.0}] * 3


def test_render_typography_left_align_draws_on_left():
    img = Image.new("RGB", (600, 750))
    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        out = np.array(render_typography(img, _runs(), font_path="x", align="left",
                                         unit="rides", show_elevation=False))
    assert out[:, :300].any() and not out[:, 300:].any()


def test_render_corner_legend_right_side():
    img = Image.new("RGB", (600, 750))
    ramp = [(0.0, [0, 255, 0]), (1.0, [255, 255, 255])]
    with patch("src.typography._load_font", return_value=ImageFont.load_default()):
        out = np.array(render_corner_legend(img, ramp, font_path="x", side="right",
                                            unit="rides", canvas_max_val=50, width_scale=0.5))
    assert out[:, 300:].any() and not out[:, :300].any()
