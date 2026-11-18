"""Animation pipeline for strava-heatmap-art."""
import math
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from itertools import accumulate

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

from src.renderer import _ramp_colors
from src.typography import _load_font, METERS_PER_MILE


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

    while seg_idx < n - 1:
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

        if pixels_budget <= 0:
            break

        remaining_px = seg_len * (1.0 - t)
        start_x = p0[0] + t * dx
        start_y = p0[1] + t * dy

        if pixels_budget >= remaining_px or math.isclose(
            pixels_budget, remaining_px, rel_tol=1e-12, abs_tol=1e-9
        ):
            # Consume this segment entirely and continue
            pixels_budget = max(0.0, pixels_budget - remaining_px)
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

    Uses a fixed final_log_max anchor across frames. Different rasterization
    means the completed frame need not match the static poster color output.

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

def paint_dot(frame, cx, cy, radius, blur_sigma, brightness=1.0, alpha=1.0):
    """Paint one cursor dot, scaling opacity after brightness clipping."""
    paint_dots_batch(frame, [(cx, cy)], radius, blur_sigma, brightness, alpha)


def paint_dots_batch(frame, positions, radius, blur_sigma, brightness=1.0, alpha=1.0):
    """Paint multiple cursor dots in a single blur pass (screen blend).

    positions: list of (cx, cy) float tuples.
    All dots are drawn onto one layer, blurred once, then screen-blended onto frame.
    Modifies frame in-place.
    """
    if not positions or alpha <= 0:
        return
    h, w = frame.shape[:2]
    dot_layer = np.zeros((h, w), dtype=np.float32)
    for cx, cy in positions:
        cv2.circle(dot_layer, (int(cx), int(cy)), int(radius), color=255.0, thickness=-1)
    if blur_sigma > 0:
        dot_layer = gaussian_filter(dot_layer, sigma=blur_sigma)
    if brightness != 1.0:
        dot_layer = np.clip(dot_layer * brightness, 0.0, 255.0)
    if alpha != 1.0:
        dot_layer *= alpha
    for c in range(3):
        ch = frame[:, :, c].astype(np.float32)
        blended = 255 - (255 - ch) * (255 - dot_layer) / 255
        frame[:, :, c] = np.clip(blended, 0, 255).astype(np.uint8)


# ── Typography ────────────────────────────────────────────────────────────────

def render_animation_typography(img, month_year, run_count, total_miles_floor,
                                 font_path, scale=1.0, font=None):
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
    if font is None:
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
    from config import MAP_ATTRIBUTION
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
        "-metadata", f"copyright={MAP_ATTRIBUTION}",
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


def _format_year(start_date):
    """Extract 4-digit year from ISO date string."""
    return start_date[:4]


def validate_animation_config(config, mode="sequential"):
    """Reject settings that can stall traversal or produce invalid raw video."""
    from numbers import Integral, Real
    import config as style

    def number(name, *, positive=False, integer=False):
        value = getattr(config, name, None)
        kind = Integral if integer else Real
        if (isinstance(value, bool) or not isinstance(value, kind)
                or not math.isfinite(value) or (value <= 0 if positive else value < 0)):
            constraint = "positive" if positive else "nonnegative"
            unit = "integer" if integer else "finite number"
            raise ValueError(f"{name} must be a {constraint} {unit}.")
        return value

    fps = number("ANIMATION_FPS", positive=True)

    def check_frames(name, seconds, *, positive=False):
        frames = seconds * fps
        if not math.isfinite(frames) or (positive and int(frames) < 1):
            raise ValueError(f"{name} * ANIMATION_FPS must yield "
                             f"{'at least one' if positive else 'a finite number of'} frames.")

    size = getattr(config, "ANIMATION_OUTPUT_RESOLUTION", None)
    if (not isinstance(size, (tuple, list)) or len(size) != 2
            or any(isinstance(n, bool) or not isinstance(n, Integral)
                   or n <= 0 or n % 2 for n in size)):
        raise ValueError("ANIMATION_OUTPUT_RESOLUTION must contain two positive even integers.")
    number("ANIMATION_DOT_RADIUS", integer=True)
    number("ANIMATION_DOT_BLUR")
    number("ANIMATION_DOT_BRIGHTNESS")
    if mode == "sequential":
        number("ANIMATION_DRAWING_SPEED", positive=True)
        number("ANIMATION_DRAWING_SPEED_SLOW", positive=True)
        number("ANIMATION_SPEED_RAMP_RUNS", integer=True)
        check_frames("ANIMATION_HOLD_SECONDS", number("ANIMATION_HOLD_SECONDS"))
    else:
        duration = number("ANIMATION_PARALLEL_DURATION_S", positive=True)
        check_frames("ANIMATION_PARALLEL_HOLD_S", number("ANIMATION_PARALLEL_HOLD_S"))
        check_frames("ANIMATION_PARALLEL_DURATION_S", duration, positive=True)
    if style.CANVAS_ROTATION_DEGREES != 0:
        raise ValueError(
            f"Animation does not support CANVAS_ROTATION_DEGREES={style.CANVAS_ROTATION_DEGREES}. "
            "Use a north-up city config with CANVAS_ROTATION_DEGREES = 0."
        )


def _wait_encoder(proc, timeout):
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise RuntimeError("ffmpeg did not finish; encoding was stopped.")


@contextmanager
def _video_pipe(output_path, width, height, fps):
    """Reap the encoder on every exit and replace output only after success."""
    output_path = os.path.abspath(output_path)
    parent = os.path.dirname(output_path)
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".animation-", suffix=".mp4", dir=parent)
    os.close(fd)
    try:
        proc = open_ffmpeg_pipe(temporary, width, height, fps)
        try:
            yield proc.stdin
            close_error = None
            try:
                proc.stdin.close()
            except OSError as exc:
                close_error = exc
            status = _wait_encoder(proc, 30)
            if status != 0 or close_error is not None:
                raise RuntimeError(f"ffmpeg failed (exit status {status}).") from close_error
            if os.path.getsize(temporary) == 0:
                raise RuntimeError("ffmpeg produced no video.")
            os.replace(temporary, output_path)
        except BaseException:
            # This also covers cancellation while closing/flushing or waiting.
            with suppress(OSError):
                proc.terminate()
            try:
                with suppress(OSError):
                    proc.stdin.close()
            finally:
                try:
                    _wait_encoder(proc, 5)
                except RuntimeError:
                    pass
            raise
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary)


@dataclass
class _RoutePixels:
    """Sparse, distance-ordered pixels, each contributed once by this run."""
    indices: np.ndarray
    distances: np.ndarray
    revealed: int = 0

    def reveal(self, canvas, distance, complete=False):
        end = len(self.indices) if complete else int(
            np.searchsorted(self.distances, distance, side="right")
        )
        end = max(self.revealed, end)
        canvas.ravel()[self.indices[self.revealed:end]] += 1.0
        self.revealed = end


def _rasterize_route(points, width, height, thickness):
    """Rasterize full segments once, then order their union by first arrival.

    The canonical mask is the union of OpenCV LINE_8 strokes at animation
    thickness, with no poster bonus pass. Retracing never adds a second visit.
    Temporary masks are bounded to the visible route/segment, not one full
    float canvas per active run.
    """
    if len(points) < 2:
        return _RoutePixels(np.array([], dtype=np.intp), np.array([], dtype=np.float64))
    pad = thickness // 2 + 2
    x0 = max(0, min(p[0] for p in points) - pad)
    y0 = max(0, min(p[1] for p in points) - pad)
    x1 = min(width, max(p[0] for p in points) + pad + 1)
    y1 = min(height, max(p[1] for p in points) + pad + 1)
    if x1 <= x0 or y1 <= y0:
        return _RoutePixels(np.array([], dtype=np.intp), np.array([], dtype=np.float64))
    arrival = np.full((y1 - y0, x1 - x0), np.inf, dtype=np.float64)
    distance = 0.0
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        length = math.hypot(bx - ax, by - ay)
        left, top = max(x0, min(ax, bx) - pad), max(y0, min(ay, by) - pad)
        right, bottom = min(x1, max(ax, bx) + pad + 1), min(y1, max(ay, by) + pad + 1)
        if right > left and bottom > top:
            mask = np.zeros((bottom - top, right - left), dtype=np.uint8)
            cv2.line(mask, (ax - left, ay - top), (bx - left, by - top),
                     1, thickness=thickness, lineType=cv2.LINE_8)
            yy, xx = np.nonzero(mask)
            if length:
                fraction = np.clip(
                    ((xx + left - ax) * (bx - ax) + (yy + top - ay) * (by - ay))
                    / length ** 2, 0.0, 1.0,
                )
                times = distance + fraction * length
            else:
                times = np.full(len(xx), distance)
            ry, rx = yy + top - y0, xx + left - x0
            arrival[ry, rx] = np.minimum(arrival[ry, rx], times)
        distance += length
    yy, xx = np.nonzero(np.isfinite(arrival))
    times = arrival[yy, xx]
    order = np.argsort(times, kind="stable")
    indices = (yy + y0) * width + xx + x0
    return _RoutePixels(indices[order], times[order])


def _sequential_steps(points, speed, is_last, decel_zone):
    """The shared traversal schedule used for both counting and rendering."""
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    prefix = np.concatenate(([0.0], np.cumsum(lengths)))
    total = float(prefix[-1])
    seg, t, progress = 0, 0.0, 0.0
    while True:
        budget = speed
        remaining = max(0.0, total - progress)
        if is_last and 0 < remaining < decel_zone:
            budget = max(1.0, speed * remaining / decel_zone)
        new_seg, new_t, _ = advance_cursor(points, seg, t, budget)
        progress = float(prefix[new_seg] + new_t * lengths[new_seg])
        done = new_seg == len(points) - 2 and new_t == 1.0
        a, b = points[new_seg:new_seg + 2]
        tip = (a[0] + new_t * (b[0] - a[0]), a[1] + new_t * (b[1] - a[1]))
        yield progress, done, tip
        if done:
            return
        seg, t = new_seg, new_t


class _AnimationScene:
    """Shared projection, normalization, basemap, effects, and frame credits."""

    def __init__(self, runs, config, mode):
        from PIL import ImageEnhance
        from src.renderer import StravaRenderer
        from src.tiles import fetch_map_tile
        from src.typography import render_legend, render_attribution, _download_font
        import config as style

        validate_animation_config(config, mode)
        check_ffmpeg()
        self.style = style
        self.width, self.height = config.ANIMATION_OUTPUT_RESOLUTION
        self.runs = sorted(runs, key=lambda run: run["start_date"])
        # Both modes count the same activities, even when a route cannot draw.
        self.mile_totals = [
            meters / METERS_PER_MILE for meters in
            accumulate((run.get("distance", 0.0) for run in self.runs), initial=0.0)
        ]
        self.renderer = StravaRenderer(width=self.width, height=self.height)
        if (self.renderer.width, self.renderer.height) != (self.width, self.height):
            raise ValueError("Animation does not support an intermediate canvas differing from its output size.")
        self.canvas = self.renderer.canvas
        self.scale = self.width / style.CANVAS_WIDTH_PX
        thickness = max(1, round(style.ROUTE_LINE_THICKNESS * self.scale))
        self.routes = []
        print("Pre-pass: rasterizing animation coverage and normalization...")
        for index, run in enumerate(self.runs):
            if len(run["coords"]) < 2:
                continue
            points = build_run_pixel_coords(run, self.renderer)
            pixels = _rasterize_route(points, self.width, self.height, thickness)
            self.canvas.ravel()[pixels.indices] += 1.0
            self.routes.append({
                "index": index, "run": run, "points": points, "pixels": pixels,
                "length": _path_length_px(points),
            })
        self.final_max = float(self.canvas.max())
        self.log_max = float(np.log1p(self.final_max))
        if not self.final_max:
            raise ValueError("No qualifying runs have drawable coordinates. Check CITY_BOUNDS or run with --fetch.")
        self.canvas.fill(0)

        print("Fetching map tile...")
        _download_font(style.MAP_FONT_PATH, style.MAP_FONT_URL)
        self.stats_font = _load_font(
            style.MAP_FONT_PATH, int(max(10, self.height // 40) * style.TYPOGRAPHY_SCALE),
        )
        tile = fetch_map_tile(
            bounds=self.renderer.bounds, zoom=15, cache_path=style.MAP_TILE_CACHE,
            target_size=(self.width, self.height), url_template=style.MAP_TILE_URL,
        ).convert("RGB")
        if style.MAP_TILE_BRIGHTNESS != 1.0:
            tile = ImageEnhance.Brightness(tile).enhance(style.MAP_TILE_BRIGHTNESS)
        self.map = np.asarray(tile.resize((self.width, self.height)), dtype=np.float32)
        self.map *= style.MAP_TILE_OPACITY
        self.legend = np.asarray(render_legend(
            Image.new("RGB", (self.width, self.height)), color_ramp=style.ROUTE_COLOR_RAMP,
            font_path=style.MAP_FONT_PATH, gamma=style.GAMMA, canvas_max_val=self.final_max,
            scale=style.TYPOGRAPHY_SCALE, position=style.LEGEND_POSITION,
            width_scale=style.LEGEND_WIDTH_SCALE, text_width_scale=style.TYPOGRAPHY_WIDTH_SCALE,
            show_elevation=style.SHOW_ELEVATION, y_offset=style.LEGEND_Y_OFFSET,
        ), dtype=np.float32)
        credits = render_attribution(
            Image.new("RGBA", (self.width, self.height)), style.MAP_ATTRIBUTION,
            style.MAP_FONT_PATH,
        )
        self.credit_bounds = credits.getbbox()
        if self.credit_bounds:
            credit = np.asarray(credits.crop(self.credit_bounds))
            self.credit_rgb = credit[:, :, :3].astype(np.float32)
            self.credit_alpha = credit[:, :, 3:4].astype(np.float32) / 255.0

    def frame(self):
        s = self.style
        arr = canvas_to_rgb(
            self.canvas, self.log_max, s.GAMMA, s.ROUTE_COLOR_RAMP, s.BG_COLOR,
            density_expand_sigma=max(0.5, s.DENSITY_EXPAND_SIGMA * self.scale),
            density_expand_power=s.DENSITY_EXPAND_POWER,
            density_expand_strength=s.DENSITY_EXPAND_STRENGTH,
            hot_bloom_sigma=16.0 * s.HOT_BLOOM_SIGMA_MULT * self.scale,
            hot_bloom_threshold=s.HOT_BLOOM_THRESHOLD, hot_bloom_strength=s.HOT_BLOOM_STRENGTH,
        ).astype(np.float32)
        arr = 255 - (255 - self.map) * (255 - arr) / 255
        arr = 255 - (255 - arr) * (255 - self.legend) / 255
        return np.clip(arr, 0, 255).astype(np.uint8)

    def stats(self, frame, date, count, miles):
        return np.array(render_animation_typography(
            Image.fromarray(frame), date, count, int(math.floor(miles)),
            self.style.MAP_FONT_PATH, scale=self.style.TYPOGRAPHY_SCALE, font=self.stats_font,
        ))

    def write(self, pipe, frame):
        # Credits go on last, including opening, dot, fade, and hold frames.
        if self.credit_bounds:
            x0, y0, x1, y1 = self.credit_bounds
            roi = frame[y0:y1, x0:x1]
            roi[:] = np.rint(self.credit_rgb * self.credit_alpha + roi * (1 - self.credit_alpha))
        pipe.write(frame.tobytes())


def run_animation(runs, output_path, config):
    """Draw runs chronologically, contributing each run's covered pixels once."""
    scene = _AnimationScene(runs, config, "sequential")
    fps = config.ANIMATION_FPS
    fast = config.ANIMATION_DRAWING_SPEED
    slow = config.ANIMATION_DRAWING_SPEED_SLOW
    ramp = config.ANIMATION_SPEED_RAMP_RUNS
    hold_frames = int(config.ANIMATION_HOLD_SECONDS * fps)
    fade_frames = int(fps / 2)
    dot_brightness = config.ANIMATION_DOT_BRIGHTNESS
    decel_zone = max(1, scene.width // 4)

    def steps(route):
        index = route["index"]
        speed = _get_run_speed(index, len(scene.runs), fast, slow, ramp)
        return _sequential_steps(route["points"], speed, index == len(scene.runs) - 1, decel_zone)

    drawing_frames = sum(sum(1 for _ in steps(route)) for route in scene.routes)
    # Ensure trailing activities without drawable routes reach the final stats.
    final_stats_frame = not (fade_frames or hold_frames) and (
        scene.routes[-1]["index"] != len(scene.runs) - 1
    )
    total_frames = 1 + drawing_frames + fade_frames + hold_frames + final_stats_frame
    print(f"Expected duration: {total_frames / fps:.2f}s ({total_frames} frames at {fps}fps).")
    print(f"Rendering {len(scene.runs)} runs → {output_path}")
    miles, count, frame_count = 0.0, 0, 0
    month = _format_month_year(scene.runs[0]["start_date"])
    last_tip = None
    by_index = {route["index"]: route for route in scene.routes}
    with _video_pipe(output_path, scene.width, scene.height, fps) as pipe:
        scene.write(pipe, scene.stats(scene.frame(), month, 0, 0))
        frame_count += 1
        for index, run in enumerate(scene.runs):
            count += 1
            month = _format_month_year(run["start_date"])
            route = by_index.get(index)
            if route is None:
                continue
            for progress, done, tip in steps(route):
                route["pixels"].reveal(scene.canvas, progress, complete=done)
                if done:
                    miles = scene.mile_totals[index + 1]
                else:
                    fraction = min(1.0, max(0.0, progress / route["length"]))
                    miles = scene.mile_totals[index] + fraction * (
                        scene.mile_totals[index + 1] - scene.mile_totals[index]
                    )
                frame = scene.stats(scene.frame(), month, count, miles)
                paint_dot(frame, *tip, config.ANIMATION_DOT_RADIUS,
                          config.ANIMATION_DOT_BLUR, dot_brightness)
                scene.write(pipe, frame)
                frame_count += 1
                last_tip = tip
        completed_frame = None
        if fade_frames or hold_frames or final_stats_frame:
            completed_frame = scene.stats(scene.frame(), month, count, scene.mile_totals[-1])
        for i in range(fade_frames):
            frame = completed_frame.copy()
            paint_dot(frame, *last_tip, config.ANIMATION_DOT_RADIUS,
                      config.ANIMATION_DOT_BLUR, dot_brightness, alpha=1 - (i + 1) / fade_frames)
            scene.write(pipe, frame)
            frame_count += 1
        if hold_frames or final_stats_frame:
            scene.write(pipe, completed_frame)
            frame_count += 1
            # Credits are already composited; reuse bytes without painting twice.
            hold_bytes = completed_frame.tobytes()
            for _ in range(hold_frames - 1):
                pipe.write(hold_bytes)
                frame_count += 1
    print(f"Done. {frame_count} frames → {output_path}")


def run_parallel_animation(runs, output_path, config):
    """Draw all routes at a common pixel speed with additive per-run coverage."""
    scene = _AnimationScene(runs, config, "parallel")
    fps = config.ANIMATION_FPS
    drawing_frames = int(config.ANIMATION_PARALLEL_DURATION_S * fps)
    hold_frames = int(config.ANIMATION_PARALLEL_HOLD_S * fps)
    speed = max(route["length"] for route in scene.routes) / drawing_frames
    miles = scene.mile_totals[-1]
    date = (f'{_format_year(scene.runs[0]["start_date"])} – '
            f'{_format_year(scene.runs[-1]["start_date"])}')
    total_frames = 1 + drawing_frames + hold_frames
    print(f"Expected duration: {total_frames / fps:.2f}s ({total_frames} frames at {fps}fps).")
    print(f"Rendering {len(scene.runs)} runs in parallel → {output_path}")
    tracer_radius = max(1, config.ANIMATION_DOT_RADIUS // 2)
    with _video_pipe(output_path, scene.width, scene.height, fps) as pipe:
        scene.write(pipe, scene.frame())
        for index in range(drawing_frames):
            tips = []
            for route in scene.routes:
                if route.get("done"):
                    continue
                points = route["points"]
                seg, t, drawn = advance_cursor(
                    points, route.get("seg", 0), route.get("t", 0.0), speed or 1.0,
                )
                # The fixed schedule must always include the exact final endpoint.
                if index == drawing_frames - 1:
                    seg, t = len(points) - 2, 1.0
                done = seg == len(points) - 2 and t == 1.0
                route["pixels"].reveal(scene.canvas, (index + 1) * speed, complete=done)
                if drawn:
                    tips.append(points[-1] if done else drawn[-1][1])
                route.update(seg=seg, t=t, done=done)
            frame = scene.frame()
            paint_dots_batch(frame, tips, tracer_radius, 0)
            if not hold_frames and index == drawing_frames - 1:
                frame = scene.stats(frame, date, len(scene.runs), miles)
            scene.write(pipe, frame)
        if hold_frames:
            no_text = scene.frame()
            with_text = scene.stats(no_text.copy(), date, len(scene.runs), miles)
            for index in range(hold_frames):
                alpha = 1.0 if hold_frames == 1 else index / (hold_frames - 1)
                frame = (no_text * (1 - alpha) + with_text * alpha).astype(np.uint8)
                scene.write(pipe, frame)
    print(f"Done. {total_frames} frames → {output_path}")
