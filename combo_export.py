#!/usr/bin/env python3
"""
Generate a combined run + Baywheels bike heatmap poster on the SF map.

Runs come from data/activities.json (this repo); rides from BIKE_RIDES_PATH
(../baywheels-art). Each dataset is rendered with its own palette, the two
layers are screen-blended, then composited onto the map. Run stats go in the
bottom-left corner, bike stats in the bottom-right.

Usage:
    python combo_export.py               # full render
    python combo_export.py --preview     # 1/10 scale for quick iteration
    python combo_export.py --no-map
"""
import argparse
import json
import os
import sys
from datetime import datetime

import combo_config
sys.modules["config"] = combo_config  # src/* modules read `config` at import time

import numpy as np
from PIL import Image, ImageEnhance

from src.processor import filter_sf_runs, decode_runs, load_bike_rides
from src.renderer import StravaRenderer
from src.tiles import fetch_map_tile
from src.typography import render_typography, render_corner_legend, _download_font
from combo_config import (
    CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, OUTPUT_DIR, PRINT_DPI, BG_COLOR,
    MAP_TILE_OPACITY, MAP_TILE_CACHE, MAP_TILE_BRIGHTNESS, MAP_TILE_URL,
    MAP_FONT_PATH, MAP_FONT_URL,
    TYPOGRAPHY_SCALE, TYPOGRAPHY_WIDTH_SCALE, SHOW_ELEVATION,
    BIKE_RIDES_PATH, COMBO_LEGEND_WIDTH_SCALE,
    RUN_COLOR_RAMP, RUN_GAMMA, RUN_HOT_BLOOM_THRESHOLD, RUN_HOT_BLOOM_SIGMA_MULT,
    BIKE_COLOR_RAMP, BIKE_GAMMA, BIKE_HOT_BLOOM_THRESHOLD, BIKE_HOT_BLOOM_SIGMA_MULT,
)


def composite_map_background(tile_img, canvas_size, opacity, bg_color):
    """Blend map tile onto solid background at given opacity (same as export.py)."""
    bg = Image.new("RGB", canvas_size, tuple(int(c) for c in bg_color))
    return Image.blend(bg, tile_img.resize(canvas_size, Image.LANCZOS), alpha=opacity)


def screen(a, b):
    """Screen-blend two uint8 RGB arrays."""
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    return np.clip(255 - (255 - a) * (255 - b) / 255, 0, 255).astype(np.uint8)


def render_layer(routes, w, h, args, ramp, gamma, hb_threshold, hb_sigma_mult, grain):
    renderer = StravaRenderer(width=w, height=h)
    renderer.rasterize_all(routes)
    max_val = float(renderer.canvas.max())
    img = renderer.to_image(
        bloom=False, vignette=args.vignette, grain=grain, glow=args.glow,
        hot_bloom=args.hot_bloom, density_expand=args.density_expand,
        gamma=gamma, color_ramp=ramp,
        hot_bloom_threshold=hb_threshold, hot_bloom_sigma_mult=hb_sigma_mult,
    )
    return renderer, img, max_val


def main():
    parser = argparse.ArgumentParser(description="Generate run + bike combo heatmap poster")
    parser.add_argument("--preview", action="store_true", help="1/10 scale for speed")
    parser.add_argument("--no-vignette", dest="vignette", action="store_false", default=True)
    parser.add_argument("--no-grain", dest="grain", action="store_false", default=True)
    parser.add_argument("--no-glow", dest="glow", action="store_false", default=True)
    parser.add_argument("--no-hot-bloom", dest="hot_bloom", action="store_false", default=True)
    parser.add_argument("--no-density-expand", dest="density_expand", action="store_false", default=True)
    parser.add_argument("--no-map", dest="use_map", action="store_false", default=True)
    parser.add_argument("--bikes", default=BIKE_RIDES_PATH, help="Baywheels rides JSON")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    with open("data/activities.json") as f:
        city_runs = filter_sf_runs(json.load(f))
    runs = decode_runs(city_runs)
    rides = load_bike_rides(args.bikes)
    print(f"Rendering {len(runs)} runs + {len(rides)} rides...")

    scale = 0.1 if args.preview else 1.0
    w = int(CANVAS_WIDTH_PX * scale)
    h = int(CANVAS_HEIGHT_PX * scale)

    renderer, run_img, run_max = render_layer(
        runs, w, h, args, RUN_COLOR_RAMP, RUN_GAMMA,
        RUN_HOT_BLOOM_THRESHOLD, RUN_HOT_BLOOM_SIGMA_MULT, grain=False)
    _, bike_img, bike_max = render_layer(
        rides, w, h, args, BIKE_COLOR_RAMP, BIKE_GAMMA,
        BIKE_HOT_BLOOM_THRESHOLD, BIKE_HOT_BLOOM_SIGMA_MULT, grain=False)
    img_array = screen(run_img, bike_img)

    # Grain once on the combined layer (not per layer, which would double it)
    if args.grain:
        noise = np.random.normal(0, 0.025 * 255, img_array.shape).astype(np.float32)
        img_array = np.clip(img_array.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    if args.use_map:
        cache = MAP_TILE_CACHE if not args.preview else MAP_TILE_CACHE.replace(".png", "-preview.png")
        zoom = 15 if not args.preview else 11
        try:
            tile = fetch_map_tile(
                bounds=renderer.bounds, zoom=zoom, cache_path=cache,
                target_size=(renderer.width, renderer.height), url_template=MAP_TILE_URL,
            )
            if MAP_TILE_BRIGHTNESS != 1.0:
                tile = ImageEnhance.Brightness(tile).enhance(MAP_TILE_BRIGHTNESS)
            bg = composite_map_background(tile, (renderer.width, renderer.height),
                                          MAP_TILE_OPACITY, BG_COLOR)
            img_array = screen(np.array(bg), img_array)
        except Exception as e:
            print(f"Map tile skipped: {e}")

    img_array = renderer.rotate_and_crop(img_array)
    img = Image.fromarray(img_array, mode="RGB")

    _download_font(MAP_FONT_PATH, MAP_FONT_URL)
    num_lines = 4 if SHOW_ELEVATION else 3
    corners = [
        ("left",  city_runs, "runs",  RUN_COLOR_RAMP,  RUN_GAMMA,  run_max),
        ("right", rides,     "rides", BIKE_COLOR_RAMP, BIKE_GAMMA, bike_max),
    ]
    for side, items, unit, ramp, gamma, max_val in corners:
        img = render_typography(img, items, font_path=MAP_FONT_PATH,
                                scale=TYPOGRAPHY_SCALE, width_scale=TYPOGRAPHY_WIDTH_SCALE,
                                show_elevation=SHOW_ELEVATION and unit == "runs",
                                align=side, unit=unit)
        img = render_corner_legend(img, color_ramp=ramp, font_path=MAP_FONT_PATH,
                                   side=side, unit=unit, gamma=gamma, canvas_max_val=max_val,
                                   scale=TYPOGRAPHY_SCALE, width_scale=COMBO_LEGEND_WIDTH_SCALE,
                                   text_width_scale=TYPOGRAPHY_WIDTH_SCALE, num_lines=num_lines)

    if args.output:
        out_path = args.output
    else:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = "-preview" if args.preview else ""
        out_path = os.path.join(OUTPUT_DIR, f"poster-combo{suffix}-{ts}.png")

    dpi = 3 if args.preview else PRINT_DPI
    img.save(out_path, dpi=(dpi, dpi))
    print(f"Done. {out_path}")


if __name__ == "__main__":
    main()
