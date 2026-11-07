"""Sequential run + bike animation for the combo poster.

Runs and rides are merged in date order and paced by activity count: activity i
starts drawing at an evenly spaced frame, and every route takes the same
ROUTE_DRAW_S to draw, so many routes grow at once and the map builds at a steady
rate. Each layer (runs / rides) has its own accumulation canvas and palette,
normalized against its finished canvas so the last frame matches the poster's
look. The poster's stat blocks tally up live underneath.

Callers must set sys.modules["config"] = combo_config before importing.
"""
import math
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageEnhance

from config import (
    BG_COLOR, CANVAS_WIDTH_PX, CANVAS_ROTATION_DEGREES,
    ROUTE_LINE_THICKNESS, ROUTE_LINE_THICKNESS_50_BONUS, ROUTE_LINE_THICKNESS_10_BONUS,
    DENSITY_EXPAND_SIGMA, DENSITY_EXPAND_POWER, DENSITY_EXPAND_STRENGTH, HOT_BLOOM_STRENGTH,
    MAP_TILE_URL, MAP_TILE_CACHE, MAP_TILE_OPACITY, MAP_TILE_BRIGHTNESS,
    MAP_FONT_PATH, MAP_FONT_URL,
    RUN_COLOR_RAMP, RUN_GAMMA, RUN_HOT_BLOOM_THRESHOLD, RUN_HOT_BLOOM_SIGMA_MULT,
    BIKE_COLOR_RAMP, BIKE_GAMMA, BIKE_HOT_BLOOM_THRESHOLD, BIKE_HOT_BLOOM_SIGMA_MULT,
)
from src.animator import (
    advance_cursor, canvas_to_rgb, paint_dots_batch, check_ffmpeg, open_ffmpeg_pipe,
)
from src.combo_layout import draw_combo_text, draw_combo_legends
from src.renderer import StravaRenderer
from src.tiles import fetch_map_tile
from src.typography import stats_lines, year_range_str, _download_font

METERS_PER_MILE = 1609.344
KINDS = ("run", "bike")
UNITS = {"run": "runs", "bike": "rides"}
LAYER_STYLE = {
    "run":  (RUN_COLOR_RAMP,  RUN_GAMMA,  RUN_HOT_BLOOM_THRESHOLD,  RUN_HOT_BLOOM_SIGMA_MULT),
    "bike": (BIKE_COLOR_RAMP, BIKE_GAMMA, BIKE_HOT_BLOOM_THRESHOLD, BIKE_HOT_BLOOM_SIGMA_MULT),
}


# ── Pure helpers ─────────────────────────────────────────────────────────────

def schedule_start_frames(n, drawing_frames, draw_frames):
    """Evenly spaced start frames for n activities so the last one finishes
    exactly at drawing_frames (paced by activity count, not calendar time)."""
    if n <= 0:
        return []
    span = max(drawing_frames - draw_frames, 0)
    if n == 1:
        return [0]
    return [round(i * span / (n - 1)) for i in range(n)]


def live_lines(kind_state, unit):
    """Poster-style stat lines from live tallies:
    kind_state = {"first_year", "last_year" (None until one starts), "count", "meters"}."""
    last = kind_state["last_year"] or kind_state["first_year"]
    return [
        year_range_str(kind_state["first_year"], last),
        f"{kind_state['count']:,} {unit}",
        f"{kind_state['meters'] / METERS_PER_MILE:,.0f} mi",
    ]


def _screen(a, b):
    return 255 - (255 - a) * (255 - b) / 255


# ── Route prep ───────────────────────────────────────────────────────────────

def _prep_route(item, kind, renderer, pad):
    """Project to pixels, drop repeated points, and compute a padded bbox so each
    route draws into a small local buffer instead of a full-frame one."""
    pts = []
    for lat, lng in item["coords"]:
        p = renderer.project(lat, lng)
        if not pts or p != pts[-1]:
            pts.append(p)
    route = {"kind": kind, "item": item, "px": None, "year": item["start_date"][:4],
             "meters": float(item.get("distance", 0.0))}
    # Undrawable routes (single point, zero length, off-canvas) still count in
    # the tallies so the final numbers match the poster — they just draw nothing.
    length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    if len(pts) < 2 or length <= 0:
        return route
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0 = max(0, min(xs) - pad); x1 = min(renderer.width,  max(xs) + pad + 1)
    y0 = max(0, min(ys) - pad); y1 = min(renderer.height, max(ys) + pad + 1)
    if x1 <= x0 or y1 <= y0:
        return route
    route.update(px=pts, length=length, bbox=(x0, y0, x1, y1))
    return route


def _draw_full(route, thickness):
    x0, y0, x1, y1 = route["bbox"]
    buf = np.zeros((y1 - y0, x1 - x0), dtype=np.float32)
    pts = [(x - x0, y - y0) for x, y in route["px"]]
    for a, b in zip(pts, pts[1:]):
        cv2.line(buf, a, b, color=1.0, thickness=thickness, lineType=cv2.LINE_AA)
    return buf


def _add(canvas, route, buf):
    x0, y0, x1, y1 = route["bbox"]
    canvas[y0:y1, x0:x1] += buf


def _assign_thickness(routes, shape, px_scale):
    """Mirror the poster's two-pass thickness: routes whose path runs through the
    densest corridors (top 50% / 10% per layer) draw thicker."""
    base = max(1, round(ROUTE_LINE_THICKNESS * px_scale))
    t50 = max(base, round((ROUTE_LINE_THICKNESS + ROUTE_LINE_THICKNESS_50_BONUS) * px_scale))
    t10 = max(base, round((ROUTE_LINE_THICKNESS + ROUTE_LINE_THICKNESS_10_BONUS) * px_scale))
    for kind in KINDS:
        rs = [r for r in routes if r["kind"] == kind]
        if not rs:
            continue
        canvas = np.zeros(shape, dtype=np.float32)
        for r in rs:
            _add(canvas, r, _draw_full(r, base))
        scores = [float(np.mean([canvas[y, x] for x, y in r["px"]
                                 if 0 <= x < shape[1] and 0 <= y < shape[0]] or [0.0]))
                  for r in rs]
        ordered = sorted(scores)
        p50 = ordered[int(len(rs) * 0.5)] if len(rs) > 1 else math.inf
        p90 = ordered[int(len(rs) * 0.9)] if len(rs) > 1 else math.inf
        for r, s in zip(rs, scores):
            r["thickness"] = t10 if s >= p90 else t50 if s >= p50 else base


# ── Main loop ────────────────────────────────────────────────────────────────

def run_combo_animation(runs, rides, output_path, resolution, fps, duration_s, hold_s,
                        route_draw_s, tracer_radius):
    if CANVAS_ROTATION_DEGREES != 0:
        sys.exit("ERROR: combo animation does not support canvas rotation.")
    check_ffmpeg()

    out_w, out_h = resolution
    px_scale = out_w / CANVAS_WIDTH_PX
    drawing_frames = int(duration_s * fps)
    hold_frames = int(hold_s * fps)
    draw_frames = max(1, int(route_draw_s * fps))

    renderer = StravaRenderer(width=out_w, height=out_h)
    pad = max(2, round((ROUTE_LINE_THICKNESS + ROUTE_LINE_THICKNESS_10_BONUS) * px_scale) + 2)

    tagged = [(r, "run") for r in runs] + [(r, "bike") for r in rides]
    tagged.sort(key=lambda t: t[0]["start_date"])
    all_routes = [_prep_route(item, kind, renderer, pad) for item, kind in tagged]
    routes = [r for r in all_routes if r["px"]]
    print(f"Animating {sum(r['kind'] == 'run' for r in routes)} runs + "
          f"{sum(r['kind'] == 'bike' for r in routes)} rides: "
          f"{drawing_frames} frames ({duration_s}s @ {fps}fps) + {hold_frames} hold")

    shape = (out_h, out_w)
    _assign_thickness(routes, shape, px_scale)

    # Finished canvases → normalization anchors + legend start colors
    final_log_max, final_max = {}, {}
    for kind in KINDS:
        canvas = np.zeros(shape, dtype=np.float32)
        for r in routes:
            if r["kind"] == kind:
                _add(canvas, r, _draw_full(r, r["thickness"]))
        final_max[kind] = float(canvas.max())
        final_log_max[kind] = float(np.log1p(canvas).max())

    for r, start in zip(all_routes, schedule_start_frames(len(all_routes), drawing_frames, draw_frames)):
        r["start"] = start
        if r["px"]:
            r["speed"] = r["length"] / draw_frames

    # ── Static layers ────────────────────────────────────────────────────────
    _download_font(MAP_FONT_PATH, MAP_FONT_URL)
    tile = fetch_map_tile(bounds=renderer.bounds, zoom=15, cache_path=MAP_TILE_CACHE,
                          target_size=(out_w, out_h), url_template=MAP_TILE_URL)
    if MAP_TILE_BRIGHTNESS != 1.0:
        tile = ImageEnhance.Brightness(tile).enhance(MAP_TILE_BRIGHTNESS)
    bg = Image.new("RGB", (out_w, out_h), tuple(int(c) for c in BG_COLOR))
    map_arr = np.array(Image.blend(bg, tile, alpha=MAP_TILE_OPACITY), dtype=np.float32)

    legend_arr = np.array(draw_combo_legends(Image.new("RGB", (out_w, out_h)),
                                             final_max["run"], final_max["bike"]),
                          dtype=np.float32)
    vignette = renderer._make_vignette(strength=0.5)[:, :, None]
    glow_sigma = out_h / 40.0
    de_sigma = max(0.5, DENSITY_EXPAND_SIGMA * px_scale)

    first_year = {k: next((r["year"] for r in all_routes if r["kind"] == k), "") for k in KINDS}
    state = {k: {"first_year": first_year[k], "last_year": None, "count": 0, "meters": 0.0}
             for k in KINDS}
    base = {k: np.zeros(shape, dtype=np.float32) for k in KINDS}

    def build_frame(accum, lines, tips):
        layers = []
        for kind in KINDS:
            ramp, gamma, hb_thresh, hb_mult = LAYER_STYLE[kind]
            layers.append(canvas_to_rgb(
                accum[kind], final_log_max[kind], gamma, ramp, BG_COLOR,
                density_expand_sigma=de_sigma, density_expand_power=DENSITY_EXPAND_POWER,
                density_expand_strength=DENSITY_EXPAND_STRENGTH,
                hot_bloom_sigma=16.0 * hb_mult * px_scale, hot_bloom_threshold=hb_thresh,
                hot_bloom_strength=HOT_BLOOM_STRENGTH,
            ).astype(np.float32))
        rgb = _screen(layers[0], layers[1])
        glow = cv2.GaussianBlur(rgb, (0, 0), sigmaX=glow_sigma)
        rgb = _screen(rgb, glow) * vignette
        out = _screen(_screen(map_arr, rgb), legend_arr)
        img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGB")
        img = draw_combo_text(img, *lines)
        frame = np.array(img)
        if tips:
            paint_dots_batch(frame, tips, tracer_radius, blur_sigma=0)
        return frame

    proc = open_ffmpeg_pipe(output_path, out_w, out_h, fps)
    active = []
    next_idx = 0
    t_start = time.time()
    try:
        for f in range(drawing_frames):
            while next_idx < len(all_routes) and all_routes[next_idx]["start"] <= f:
                r = all_routes[next_idx]
                next_idx += 1
                s = state[r["kind"]]
                s["count"] += 1
                s["last_year"] = r["year"]
                if not r["px"]:
                    s["meters"] += r["meters"]
                    continue
                x0, y0, x1, y1 = r["bbox"]
                r["buf"] = np.zeros((y1 - y0, x1 - x0), dtype=np.float32)
                r["seg"], r["t"] = 0, 0.0
                active.append(r)

            tips, still_active = [], []
            for r in active:
                new_seg, new_t, drawn = advance_cursor(r["px"], r["seg"], r["t"], r["speed"])
                x0, y0 = r["bbox"][:2]
                drawn_px = 0.0
                for (ax, ay), (bx, by) in drawn:
                    cv2.line(r["buf"], (int(round(ax)) - x0, int(round(ay)) - y0),
                             (int(round(bx)) - x0, int(round(by)) - y0),
                             color=1.0, thickness=r["thickness"], lineType=cv2.LINE_AA)
                    drawn_px += math.hypot(bx - ax, by - ay)
                r["drawn"] = r.get("drawn", 0.0) + drawn_px
                state[r["kind"]]["meters"] += r["meters"] * drawn_px / r["length"]
                r["seg"], r["t"] = new_seg, new_t
                if drawn:
                    tips.append(drawn[-1][1])
                if new_seg >= len(r["px"]) - 2 and new_t >= 1.0:
                    _add(base[r["kind"]], r, r.pop("buf"))
                    state[r["kind"]]["meters"] += r["meters"] * max(0.0, 1 - r["drawn"] / r["length"])
                else:
                    still_active.append(r)
            active = still_active

            accum = {k: base[k].copy() for k in KINDS}
            for r in active:
                _add(accum[r["kind"]], r, r["buf"])
            lines = (live_lines(state["run"], "runs"), live_lines(state["bike"], "rides"))
            proc.stdin.write(build_frame(accum, lines, tips).tobytes())

            if (f + 1) % fps == 0:
                el = time.time() - t_start
                print(f"  {f + 1}/{drawing_frames} frames, {len(active)} drawing, "
                      f"~{el / (f + 1) * (drawing_frames - f - 1):.0f}s left", flush=True)

        # Anything still mid-draw (rounding at the tail) lands in full.
        for r in active:
            _add(base[r["kind"]], r, _draw_full(r, r["thickness"]))

        # Hold: finished map with exact poster stats.
        final_lines = (stats_lines(runs, "runs", False), stats_lines(rides, "rides", False))
        hold = build_frame(base, final_lines, []).tobytes()
        for _ in range(hold_frames):
            proc.stdin.write(hold)
    finally:
        proc.stdin.close()
        proc.wait()
    print(f"Done in {time.time() - t_start:.0f}s → {output_path}")
