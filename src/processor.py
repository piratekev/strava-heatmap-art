import polyline as pl
from config import SF_BOUNDS


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
        if (SF_BOUNDS["lat_min"] <= centroid_lat <= SF_BOUNDS["lat_max"] and
                SF_BOUNDS["lng_min"] <= centroid_lng <= SF_BOUNDS["lng_max"]):
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
