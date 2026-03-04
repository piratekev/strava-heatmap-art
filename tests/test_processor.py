import pytest
from src.processor import filter_sf_runs, decode_runs


def _activity(sport_type="Run", polyline="abcd", lat=37.76, lng=-122.45,
               start_date="2024-06-15T08:00:00Z", speed=3.2, elevation=50.0, distance=8000.0):
    """Build a minimal mock activity dict."""
    import polyline as pl
    # Encode a simple 2-point route near the given lat/lng
    encoded = pl.encode([(lat, lng), (lat + 0.01, lng + 0.01)])
    return {
        "id": 1,
        "sport_type": sport_type,
        "type": sport_type,
        "start_date": start_date,
        "distance": distance,
        "average_speed": speed,
        "total_elevation_gain": elevation,
        "map": {"summary_polyline": encoded},
    }


def test_filter_keeps_sf_runs():
    activities = [_activity()]  # lat=37.76, lng=-122.45 — inside SF
    result = filter_sf_runs(activities)
    assert len(result) == 1


def test_filter_excludes_non_sf_runs():
    activities = [_activity(lat=34.05, lng=-118.24)]  # Los Angeles
    result = filter_sf_runs(activities)
    assert len(result) == 0


def test_filter_excludes_non_run_activities():
    activities = [_activity(sport_type="Ride")]
    result = filter_sf_runs(activities)
    assert len(result) == 0


def test_filter_excludes_empty_polyline():
    activity = _activity()
    activity["map"]["summary_polyline"] = ""
    result = filter_sf_runs([activity])
    assert len(result) == 0


def test_decode_runs_returns_coord_arrays():
    import polyline as pl
    coords = [(37.76, -122.45), (37.77, -122.44)]
    encoded = pl.encode(coords)
    activity = _activity()
    activity["map"]["summary_polyline"] = encoded

    runs = decode_runs([activity])
    assert len(runs) == 1
    assert len(runs[0]["coords"]) == 2
    assert abs(runs[0]["coords"][0][0] - 37.76) < 0.0001


def test_decode_runs_attaches_metadata():
    runs = decode_runs([_activity(start_date="2024-06-15T08:30:00Z", speed=3.5)])
    run = runs[0]
    assert run["start_date"] == "2024-06-15T08:30:00Z"
    assert run["average_speed"] == 3.5
    assert "total_elevation_gain" in run
    assert "distance" in run
