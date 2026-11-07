import json
import math
from datetime import datetime, timezone

import polyline as pl
from config import CITY_BOUNDS


def filter_sf_runs(activities):
    """Return only Run activities with a non-empty polyline whose centroid is within SF bounds."""
    result = []
    for act in activities:
        sport = act.get("sport_type") or act.get("type", "")
        if sport != "Run":
            continue
        encoded = act.get("map", {}).get("summary_polyline", "")
        if not encoded:
            continue
        coords = pl.decode(encoded)
        if not coords:
            continue
        lats = [c[0] for c in coords]
        lngs = [c[1] for c in coords]
        centroid_lat = sum(lats) / len(lats)
        centroid_lng = sum(lngs) / len(lngs)
        if (CITY_BOUNDS["lat_min"] <= centroid_lat <= CITY_BOUNDS["lat_max"] and
                CITY_BOUNDS["lng_min"] <= centroid_lng <= CITY_BOUNDS["lng_max"]):
            result.append(act)
    return result


def decode_runs(activities):
    """Decode polylines and attach metadata. Returns list of run dicts."""
    runs = []
    for act in activities:
        encoded = act.get("map", {}).get("summary_polyline", "")
        coords = pl.decode(encoded)
        runs.append({
            "id": act["id"],
            "coords": coords,
            "start_date": act.get("start_date", ""),
            "average_speed": act.get("average_speed", 0.0),
            "total_elevation_gain": act.get("total_elevation_gain", 0.0),
            "distance": act.get("distance", 0.0),
        })
    return runs


def _haversine_meters(coords):
    """Sum great-circle distance (meters) over a sequence of (lat, lng) points."""
    R = 6_371_000
    total = 0.0
    for (lat1, lng1), (lat2, lng2) in zip(coords, coords[1:]):
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dlat, dlng = p2 - p1, math.radians(lng2 - lng1)
        a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
        total += 2 * R * math.asin(math.sqrt(a))
    return total


def load_bike_rides(path):
    """Load Baywheels rides (../baywheels-art format: dict keyed by ride_id, each with
    decoded `coordinates` [[lat, lng], ...] and `start_time_ms`), keep those whose
    centroid is inside CITY_BOUNDS, and return them in decode_runs() shape."""
    with open(path) as f:
        data = json.load(f)
    rides = []
    for ride in data.values():
        coords = [(pt[0], pt[1]) for pt in ride.get("coordinates") or []]
        if not coords:
            continue
        c_lat = sum(c[0] for c in coords) / len(coords)
        c_lng = sum(c[1] for c in coords) / len(coords)
        if not (CITY_BOUNDS["lat_min"] <= c_lat <= CITY_BOUNDS["lat_max"] and
                CITY_BOUNDS["lng_min"] <= c_lng <= CITY_BOUNDS["lng_max"]):
            continue
        start = datetime.fromtimestamp(int(ride["start_time_ms"]) / 1000, timezone.utc)
        rides.append({
            "id": ride.get("ride_id", ""),
            "coords": coords,
            "start_date": start.isoformat().replace("+00:00", "Z"),
            "distance": _haversine_meters(coords),
            "total_elevation_gain": 0.0,
        })
    return rides
