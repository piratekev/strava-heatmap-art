import polyline as pl

from src.garmin import garmin_to_strava, merge_new
from src.processor import decode_runs, filter_sf_runs


def _summary(**kw):
    s = {
        "activityId": 123,
        "activityName": "Morning Run",
        "activityType": {"typeKey": "running"},
        "startTimeGMT": "2026-10-01 14:00:00",
        "startTimeLocal": "2026-10-01 07:00:00",
        "distance": 8000.0,
        "averageSpeed": 3.2,
        "elevationGain": 50.0,
    }
    s.update(kw)
    return s


DETAILS = {"geoPolylineDTO": {"polyline": [
    {"lat": 37.77, "lon": -122.45}, {"lat": 37.78, "lon": -122.44},
]}}


def test_converts_run_to_strava_shape_that_processor_accepts():
    act = garmin_to_strava(_summary(), DETAILS)
    assert act["sport_type"] == "Run"
    assert act["start_date"] == "2026-10-01T14:00:00Z"
    assert act["external_id"] == "garmin_ping_123"
    assert pl.decode(act["map"]["summary_polyline"]) == [(37.77, -122.45), (37.78, -122.44)]
    assert filter_sf_runs([act]) == [act]
    assert decode_runs([act])[0]["distance"] == 8000.0


def test_skips_non_runs_and_runs_without_gps():
    assert garmin_to_strava(_summary(activityType={"typeKey": "cycling"}), DETAILS) is None
    assert garmin_to_strava(_summary(), {"geoPolylineDTO": None}) is None


def test_merge_dedupes_by_garmin_id_and_start_time():
    act = garmin_to_strava(_summary(), DETAILS)
    strava_same_id = {"external_id": "garmin_ping_123", "start_date": "2020-01-01T00:00:00Z"}
    strava_same_time = {"external_id": None, "start_date": "2026-10-01T14:00:30Z"}
    assert merge_new([strava_same_id], [act]) == []
    assert merge_new([strava_same_time], [act]) == []
    assert merge_new([], [act, act]) == [act]
