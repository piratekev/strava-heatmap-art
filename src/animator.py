"""Animation pipeline for strava-heatmap-art."""
import math
import subprocess
import sys

import numpy as np
from src.renderer import _ramp_colors


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


# ── Cursor ────────────────────────────────────────────────────────────────────

def advance_cursor(pixel_coords, seg_idx, t, pixels_budget):
    """Advance cursor along pixel_coords by pixels_budget pixels.

    Returns:
        (new_seg_idx, new_t, drawn_segments)

    drawn_segments: list of ((x0,y0), (x1,y1)) float tuples — one entry per
        segment boundary crossed. Used for rasterization and dot placement.
        The final entry's [1] is the new cursor tip position.
    """
    drawn = []
    n = len(pixel_coords)

    while pixels_budget > 0 and seg_idx < n - 1:
        p0 = pixel_coords[seg_idx]
        p1 = pixel_coords[seg_idx + 1]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        seg_len = math.hypot(dx, dy)

        if seg_len == 0:
            # Zero-length segment: skip to next without consuming budget
            seg_idx += 1
            t = 0.0
            continue

        remaining_px = seg_len * (1.0 - t)
        start_x = p0[0] + t * dx
        start_y = p0[1] + t * dy

        if pixels_budget >= remaining_px:
            # Consume this segment entirely and continue
            pixels_budget -= remaining_px
            end_x, end_y = float(p1[0]), float(p1[1])
            drawn.append(((start_x, start_y), (end_x, end_y)))
            seg_idx += 1
            t = 0.0
            # If we've just finished the last segment, stop
            if seg_idx >= n - 1:
                seg_idx = n - 2
                t = 1.0
                break
        else:
            # Consume partial segment
            frac = pixels_budget / seg_len
            t += frac
            t = min(t, 1.0)
            end_x = p0[0] + t * dx
            end_y = p0[1] + t * dy
            drawn.append(((start_x, start_y), (end_x, end_y)))
            pixels_budget = 0

    return seg_idx, t, drawn


# ── Color mapping ─────────────────────────────────────────────────────────────

def canvas_to_rgb(canvas, final_log_max, gamma, color_ramp, bg_color):
    """Convert float32 accumulation canvas to uint8 RGB.

    Uses fixed final_log_max so early frames are dim and the final frame
    matches the static poster color output (without density expand / bloom).
    """
    if final_log_max <= 0:
        norm = np.zeros_like(canvas)
    else:
        norm = np.log1p(canvas) / final_log_max

    norm = norm ** gamma
    norm = np.clip(norm, 0.0, 1.0)

    bg = np.array(bg_color, dtype=np.float32)
    route_colors = _ramp_colors(norm, color_ramp)
    rgb = np.zeros((*canvas.shape, 3), dtype=np.float32)
    for c in range(3):
        rgb[:, :, c] = bg[c] * (1 - norm) + route_colors[:, :, c] * norm

    return np.clip(rgb, 0, 255).astype(np.uint8)
