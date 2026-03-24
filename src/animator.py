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
            if seg_idx >= n - 1:
                seg_idx = n - 2
                t = 1.0
                break
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

def canvas_to_rgb(canvas, final_log_max, gamma, color_ramp, bg_color,
                  density_expand_sigma=0.0, density_expand_power=2.0, density_expand_strength=0.0,
                  hot_bloom_sigma=0.0, hot_bloom_threshold=0.75, hot_bloom_strength=4.0):
    """Convert float32 accumulation canvas to uint8 RGB.

    Uses fixed final_log_max so early frames are dim and the final frame
    matches the static poster color output.

    Optional post-processing effects (ported from renderer.to_image):
      density_expand_sigma > 0  — thicken heavy corridors via Gaussian expand
      hot_bloom_sigma > 0       — add bright glow on peak-density pixels
    """
    if final_log_max <= 0:
        norm = np.zeros_like(canvas)
    else:
        norm = np.log1p(canvas) / final_log_max

    norm = norm ** gamma
    norm = np.clip(norm, 0.0, 1.0)

    if density_expand_sigma > 0 and density_expand_strength > 0:
        expanded = gaussian_filter(norm ** density_expand_power, sigma=density_expand_sigma)
        norm = 1 - (1 - norm) * (1 - expanded * density_expand_strength)

    if hot_bloom_sigma > 0:
        hot_mask = np.clip(
            (norm - hot_bloom_threshold) / (1.0 - hot_bloom_threshold), 0, 1
        )
        hot_layer = gaussian_filter(hot_mask, sigma=hot_bloom_sigma)
        norm = 1 - (1 - norm) * (1 - hot_layer * hot_bloom_strength)

    norm = np.clip(norm, 0.0, 1.0)

    bg = np.array(bg_color, dtype=np.float32)
    route_colors = _ramp_colors(norm, color_ramp)
    rgb = np.zeros((*canvas.shape, 3), dtype=np.float32)
    for c in range(3):
        rgb[:, :, c] = bg[c] * (1 - norm) + route_colors[:, :, c] * norm

    return np.clip(rgb, 0, 255).astype(np.uint8)


# ── Dot rendering ─────────────────────────────────────────────────────────────

def paint_dot(frame, cx, cy, radius, blur_sigma, brightness=1.0):
    """Paint a white circle onto frame (uint8 HxWx3) at (cx, cy).

    If blur_sigma > 0, apply Gaussian blur to the dot layer before compositing
    (screen blend) so the dot has a soft halo rather than a hard edge.
    brightness multiplies the dot layer after blur (>1 saturates the core).
    Modifies frame in-place.
    """
    h, w = frame.shape[:2]
    dot_layer = np.zeros((h, w), dtype=np.float32)
    cv2.circle(dot_layer, (int(cx), int(cy)), int(radius), color=255.0, thickness=-1)

    if blur_sigma > 0:
        dot_layer = gaussian_filter(dot_layer, sigma=blur_sigma)

    if brightness != 1.0:
        dot_layer = np.clip(dot_layer * brightness, 0.0, 255.0)

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


# ── ffmpeg pipe ───────────────────────────────────────────────────────────────

def check_ffmpeg():
    """Exit with a clear error if ffmpeg is not on PATH."""
    if shutil.which("ffmpeg") is None:
        sys.exit(
            "ERROR: ffmpeg not found on PATH. Install it (e.g. `brew install ffmpeg`) "
            "and re-run animate.py."
        )


def open_ffmpeg_pipe(output_path, width, height, fps):
    """Open an ffmpeg subprocess that reads raw RGB frames from stdin.

    Returns the Popen object. Write frames as raw bytes to proc.stdin.
    Call proc.stdin.close() and proc.wait() when done.
    """
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "pipe:0",
        "-vcodec", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        output_path,
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


# ── Animation loop helpers ────────────────────────────────────────────────────

def build_run_pixel_coords(run, renderer):
    """Project a run's geo coords to pixel coords using renderer.project()."""
    return [renderer.project(lat, lng) for lat, lng in run["coords"]]


def _path_length_px(pixel_coords):
    """Total Euclidean length of a pixel-space polyline."""
    total = 0.0
    for i in range(len(pixel_coords) - 1):
        total += math.hypot(
            pixel_coords[i + 1][0] - pixel_coords[i][0],
            pixel_coords[i + 1][1] - pixel_coords[i][1],
        )
    return total


def compute_total_frames(runs, renderer, drawing_speed):
    """Estimate total animation frames (excluding hold) for all runs."""
    total_px = 0.0
    for run in runs:
        if len(run["coords"]) < 2:
            continue
        px_coords = build_run_pixel_coords(run, renderer)
        total_px += _path_length_px(px_coords)
    return int(total_px / drawing_speed) if drawing_speed > 0 else 0


def _get_run_speed(run_idx, n_runs, fast_speed, slow_speed, ramp_runs):
    """Return drawing speed (px/frame) for run at 0-based index run_idx.

    First run: slow_speed. Ramps linearly to fast_speed over ramp_runs runs.
    Last run: slow_speed. Ramps linearly back over ramp_runs runs.
    """
    dist_start = run_idx
    dist_end = n_runs - 1 - run_idx
    near = min(dist_start, dist_end)
    if near == 0:
        return slow_speed
    if near < ramp_runs:
        t = near / ramp_runs
        return slow_speed + t * (fast_speed - slow_speed)
    return fast_speed


def _format_month_year(start_date):
    """Convert ISO date string to 'Mon YYYY' e.g. 'Mar 2019'."""
    from datetime import datetime
    try:
        dt = datetime.strptime(start_date[:10], "%Y-%m-%d")
        return dt.strftime("%b %Y")
    except ValueError:
        return start_date[:7]


def run_animation(runs, output_path, config):
    """Run the full animation pipeline.

    Args:
        runs:        list of run dicts from decode_runs()
        output_path: path to write the MP4
        config:      module/object with animation config knobs
    """
    from src.renderer import StravaRenderer
    from src.tiles import fetch_map_tile
    from src.typography import render_legend, _download_font
    from PIL import ImageEnhance
    from config import (
        ROUTE_COLOR_RAMP, BG_COLOR, GAMMA,
        ROUTE_LINE_THICKNESS,
        DENSITY_EXPAND_SIGMA, DENSITY_EXPAND_POWER, DENSITY_EXPAND_STRENGTH,
        HOT_BLOOM_THRESHOLD, HOT_BLOOM_SIGMA_MULT, HOT_BLOOM_STRENGTH,
        MAP_TILE_URL, MAP_TILE_CACHE, MAP_TILE_OPACITY, MAP_TILE_BRIGHTNESS,
        MAP_FONT_PATH, MAP_FONT_URL,
        CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, TYPOGRAPHY_SCALE, LEGEND_POSITION, LEGEND_WIDTH_SCALE,
        TYPOGRAPHY_WIDTH_SCALE, SHOW_ELEVATION, LEGEND_Y_OFFSET,
        CANVAS_ROTATION_DEGREES,
    )

    fps = config.ANIMATION_FPS
    drawing_speed = config.ANIMATION_DRAWING_SPEED
    slow_speed = getattr(config, "ANIMATION_DRAWING_SPEED_SLOW", drawing_speed)
    ramp_runs = getattr(config, "ANIMATION_SPEED_RAMP_RUNS", 0)
    dot_radius = config.ANIMATION_DOT_RADIUS
    dot_blur = config.ANIMATION_DOT_BLUR
    dot_brightness = getattr(config, "ANIMATION_DOT_BRIGHTNESS", 1.0)
    hold_seconds = config.ANIMATION_HOLD_SECONDS
    out_w, out_h = config.ANIMATION_OUTPUT_RESOLUTION

    # Guard: rotation not supported
    if CANVAS_ROTATION_DEGREES != 0:
        sys.exit(
            f"ERROR: animate.py does not support CANVAS_ROTATION_DEGREES={CANVAS_ROTATION_DEGREES}. "
            "Add CANVAS_ROTATION_DEGREES = 0 to your city config override."
        )

    # Guard: ffmpeg
    check_ffmpeg()

    # Sort runs chronologically
    runs = sorted(runs, key=lambda r: r["start_date"])

    # ── Pre-pass ──────────────────────────────────────────────────────────────
    print("Pre-pass: rasterizing all runs to compute normalization anchor...")
    pre_renderer = StravaRenderer(width=out_w, height=out_h)
    pre_renderer.rasterize_all(runs)
    final_canvas_max = float(pre_renderer.canvas.max())
    final_log_max = float(np.log1p(pre_renderer.canvas).max())
    if final_log_max == 0:
        sys.exit("ERROR: No qualifying runs found after filtering. Nothing to animate.")
    del pre_renderer

    # ── Duration estimate ─────────────────────────────────────────────────────
    anim_renderer = StravaRenderer(width=out_w, height=out_h)
    total_frames = compute_total_frames(runs, anim_renderer, drawing_speed)
    hold_frames = int(hold_seconds * fps)
    total_duration_s = (total_frames + hold_frames) / fps
    print(f"Expected duration: {total_duration_s:.0f}s ({total_frames} frames at {fps}fps). "
          f"Adjust ANIMATION_DRAWING_SPEED to change.")

    # ── Map tile ──────────────────────────────────────────────────────────────
    print("Fetching map tile...")
    _download_font(MAP_FONT_PATH, MAP_FONT_URL)
    cache_path = MAP_TILE_CACHE.replace(".png", "-anim.png")
    tile = fetch_map_tile(
        bounds=anim_renderer.bounds,
        zoom=15,
        cache_path=cache_path,
        target_size=(out_w, out_h),
        url_template=MAP_TILE_URL,
    )
    if MAP_TILE_BRIGHTNESS != 1.0:
        tile = ImageEnhance.Brightness(tile).enhance(MAP_TILE_BRIGHTNESS)
    map_arr = np.array(tile.resize((out_w, out_h)), dtype=np.float32)

    # ── Pre-render legend ─────────────────────────────────────────────────────
    # Scale effects to animation canvas size (relative to print canvas)
    px_scale = out_w / CANVAS_WIDTH_PX
    line_thickness = max(1, round(ROUTE_LINE_THICKNESS * px_scale))
    de_sigma = max(0.5, DENSITY_EXPAND_SIGMA * px_scale)
    hb_sigma = 16.0 * HOT_BLOOM_SIGMA_MULT * px_scale  # 16.0 = bloom_sigma_wide default

    legend_base = Image.new("RGB", (out_w, out_h), (0, 0, 0))
    legend_img = render_legend(
        legend_base, color_ramp=ROUTE_COLOR_RAMP, font_path=MAP_FONT_PATH,
        gamma=GAMMA, canvas_max_val=final_canvas_max,
        scale=TYPOGRAPHY_SCALE, position=LEGEND_POSITION,
        width_scale=LEGEND_WIDTH_SCALE,
        text_width_scale=TYPOGRAPHY_WIDTH_SCALE,
        show_elevation=SHOW_ELEVATION,
        y_offset=LEGEND_Y_OFFSET,
    )
    legend_arr = np.array(legend_img, dtype=np.float32)

    # ── Animation pass ────────────────────────────────────────────────────────
    print(f"Rendering {len(runs)} runs → {output_path}")
    proc = open_ffmpeg_pipe(output_path, out_w, out_h, fps)
    accumulation = anim_renderer.canvas  # float32, starts at zero

    total_miles = 0.0
    run_count = 0
    frame_count = 0
    final_frame_bytes = None

    def _build_frame(month_year_str):
        """Composite the current accumulation state into a uint8 RGB frame."""
        f = canvas_to_rgb(
            accumulation, final_log_max, GAMMA, ROUTE_COLOR_RAMP, BG_COLOR,
            density_expand_sigma=de_sigma,
            density_expand_power=DENSITY_EXPAND_POWER,
            density_expand_strength=DENSITY_EXPAND_STRENGTH,
            hot_bloom_sigma=hb_sigma,
            hot_bloom_threshold=HOT_BLOOM_THRESHOLD,
            hot_bloom_strength=HOT_BLOOM_STRENGTH,
        )
        f_f = f.astype(np.float32)
        bg_f = np.zeros_like(f_f)
        for c in range(3):
            bg_f[:, :, c] = map_arr[:, :, c] * MAP_TILE_OPACITY
        result = 255 - (255 - bg_f) * (255 - f_f) / 255
        f = np.clip(result, 0, 255).astype(np.uint8)
        f_f2 = f.astype(np.float32)
        result2 = 255 - (255 - f_f2) * (255 - legend_arr) / 255
        f = np.clip(result2, 0, 255).astype(np.uint8)
        pil_f = Image.fromarray(f, mode="RGB")
        pil_f = render_animation_typography(
            pil_f, month_year_str, run_count, int(math.floor(total_miles)),
            MAP_FONT_PATH, scale=TYPOGRAPHY_SCALE,
        )
        return np.array(pil_f)

    try:
        # ── Blank opening frame (0 runs, 0 miles, nothing drawn) ──────────────
        first_month_year = _format_month_year(runs[0]["start_date"]) if runs else ""
        opening = _build_frame(first_month_year)
        proc.stdin.write(opening.tobytes())
        frame_count += 1
        final_frame_bytes = opening.tobytes()

        for run_idx, run in enumerate(runs):
            geo_coords = run["coords"]
            if len(geo_coords) < 2:
                run_count += 1
                continue

            px_coords = build_run_pixel_coords(run, anim_renderer)
            run_count += 1
            month_year = _format_month_year(run["start_date"])
            run_speed = _get_run_speed(run_idx, len(runs), drawing_speed, slow_speed, ramp_runs)

            seg_idx, t = 0, 0.0

            while True:
                new_seg, new_t, drawn = advance_cursor(px_coords, seg_idx, t, run_speed)

                # Draw segments onto accumulation canvas
                buf = np.zeros((out_h, out_w), dtype=np.float32)
                for (x0, y0), (x1, y1) in drawn:
                    cv2.line(buf, (int(x0), int(y0)), (int(x1), int(y1)),
                             color=1.0, thickness=line_thickness, lineType=cv2.LINE_AA)
                accumulation += buf

                # Mileage for this frame
                if drawn:
                    frame_miles = compute_frame_miles(geo_coords, seg_idx, t, new_seg, new_t)
                    total_miles += frame_miles

                # Build output frame
                frame_rgb = _build_frame(month_year)

                # Paint cursor dot at tip
                if drawn:
                    tip_x, tip_y = drawn[-1][1]
                    paint_dot(frame_rgb, tip_x, tip_y, dot_radius, dot_blur, dot_brightness)

                # Write frame
                final_frame_bytes = frame_rgb.tobytes()
                proc.stdin.write(final_frame_bytes)
                frame_count += 1

                seg_idx, t = new_seg, new_t
                if seg_idx >= len(px_coords) - 2 and t >= 1.0:
                    break

        # Hold frames
        if final_frame_bytes and hold_frames > 0:
            print(f"Writing {hold_frames} hold frames...")
            for _ in range(hold_frames):
                proc.stdin.write(final_frame_bytes)

    finally:
        proc.stdin.close()
        proc.wait()

    print(f"Done. {frame_count + hold_frames} frames → {output_path}")
