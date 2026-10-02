"""Animation pipeline for strava-heatmap-art."""
import math
import shutil
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

from src.renderer import _ramp_colors
from src.typography import _load_font


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


# ── Dot rendering ─────────────────────────────────────────────────────────────

def paint_dot(frame, cx, cy, radius, blur_sigma):
    """Paint a white circle onto frame (uint8 HxWx3) at (cx, cy).

    If blur_sigma > 0, apply Gaussian blur to the dot layer before compositing
    (screen blend) so the dot has a soft halo rather than a hard edge.
    Modifies frame in-place.
    """
    h, w = frame.shape[:2]
    dot_layer = np.zeros((h, w), dtype=np.float32)
    cv2.circle(dot_layer, (int(cx), int(cy)), int(radius), color=255.0, thickness=-1)

    if blur_sigma > 0:
        dot_layer = gaussian_filter(dot_layer, sigma=blur_sigma)

    for c in range(3):
        ch = frame[:, :, c].astype(np.float32)
        # Screen blend: result = 255 - (255 - frame) * (255 - dot) / 255
        blended = 255 - (255 - ch) * (255 - dot_layer) / 255
        frame[:, :, c] = np.clip(blended, 0, 255).astype(np.uint8)


# ── Typography ────────────────────────────────────────────────────────────────

def render_animation_typography(img, month_year, run_count, total_miles_floor,
                                 font_path, scale=1.0):
    """Render live animation stats onto img (PIL Image) in the same bottom-right
    position as render_typography.

    Lines (top to bottom):
        month_year    e.g. "Mar 2019"
        run_count     e.g. "42 runs"
        total_miles   e.g. "312 mi"

    Returns the modified image.
    """
    w, h = img.size
    font_size = int(max(10, h // 40) * scale)
    margin = int(max(10, h // 25) * scale)
    shadow_offset = int(max(2, h // 1800) * scale)
    line_gap = int(max(8, h // 120) * scale)

    draw = ImageDraw.Draw(img)
    font = _load_font(font_path, font_size)
    shadow = (0, 0, 0)
    text_color = (255, 255, 255)

    lines = [
        month_year,
        f"{run_count:,} runs",
        f"{total_miles_floor} mi",
    ]

    y = h - margin
    for text in reversed(lines):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = w - margin - text_w
        y -= text_h
        draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow)
        draw.text((x, y), text, font=font, fill=text_color)
        y -= line_gap

    return img
