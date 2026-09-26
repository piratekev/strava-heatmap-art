"""Animation pipeline for strava-heatmap-art."""
import math
import subprocess
import sys


# ── Mileage ───────────────────────────────────────────────────────────────────

_EARTH_RADIUS_M = 6_371_000
_METERS_PER_MILE = 1609.344


def haversine_miles(lat1, lng1, lat2, lng2):
    """Haversine distance between two (lat, lng) points in miles."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a)) / _METERS_PER_MILE


def compute_frame_miles(geo_coords, start_seg, start_t, end_seg, end_t):
    """Haversine distance (miles) traversed from (start_seg, start_t) to (end_seg, end_t).

    geo_coords: list of (lat, lng) tuples.
    seg N spans geo_coords[N] → geo_coords[N+1].
    t ∈ [0, 1] is fractional progress along segment N.
    """
    total = 0.0
    seg = start_seg
    t0 = start_t
    while seg <= end_seg:
        t1 = end_t if seg == end_seg else 1.0
        lat0 = geo_coords[seg][0] + t0 * (geo_coords[seg + 1][0] - geo_coords[seg][0])
        lng0 = geo_coords[seg][1] + t0 * (geo_coords[seg + 1][1] - geo_coords[seg][1])
        lat1 = geo_coords[seg][0] + t1 * (geo_coords[seg + 1][0] - geo_coords[seg][0])
        lng1 = geo_coords[seg][1] + t1 * (geo_coords[seg + 1][1] - geo_coords[seg][1])
        total += haversine_miles(lat0, lng0, lat1, lng1)
        seg += 1
        t0 = 0.0
    return total
