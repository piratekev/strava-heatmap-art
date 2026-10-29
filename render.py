#!/usr/bin/env python3
"""
Generate a running heatmap poster from Strava data.

Usage:
    python render.py                      # SF, full render
    python render.py --config nyc         # NYC render
    python render.py --preview            # 1/10 scale for quick iteration
    python render.py --fetch              # fetch new activities first
    python render.py --no-map
    python render.py --no-bloom --no-grain --no-glow
"""
import argparse
import importlib
import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# ── Config injection ──────────────────────────────────────────────────────────
# Pre-parse --config before any pipeline imports so sys.modules["config"] is set
# before src/* modules load and execute their own `from config import ...`.
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--config", default="sf")
_pre_args, _ = _pre.parse_known_args()

if _pre_args.config != "sf":
    sys.modules["config"] = importlib.import_module(f"{_pre_args.config}_config")
# ─────────────────────────────────────────────────────────────────────────────

import numpy as np
from PIL import Image

from src.fetcher import StravaClient, fetch_activities
from src.processor import filter_sf_runs, decode_runs
from src.renderer import StravaRenderer
from src.tiles import fetch_map_tile
from src.typography import render_typography, render_legend, _download_font
from config import (
    CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, OUTPUT_DIR,
    MAP_TILE_OPACITY, MAP_TILE_CACHE, MAP_TILE_BRIGHTNESS,
    MAP_TILE_URL,
    MAP_FONT_PATH, MAP_FONT_URL,
    ROUTE_COLOR_RAMP, GAMMA, PRINT_DPI,
    TYPOGRAPHY_SCALE, TYPOGRAPHY_WIDTH_SCALE, TYPOGRAPHY_X_OFFSET,
    LEGEND_POSITION, LEGEND_WIDTH_SCALE,
    SHOW_ELEVATION, LEGEND_Y_OFFSET,
)


def composite_map_background(tile_img, canvas_size, opacity, bg_color):
    """Blend Mapbox tile onto solid background at given opacity."""
    bg = Image.new("RGB", canvas_size, tuple(int(c) for c in bg_color))
    tile = tile_img.resize(canvas_size, Image.LANCZOS)
    return Image.blend(bg, tile, alpha=opacity)


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Generate running heatmap poster")
    parser.add_argument("--config", default="sf", help="Config to use: sf (default) or nyc")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--preview", action="store_true", help="1/10 scale for speed")
    parser.add_argument("--no-bloom", dest="bloom", action="store_false", default=True)
    parser.add_argument("--no-vignette", dest="vignette", action="store_false", default=True)
    parser.add_argument("--no-grain", dest="grain", action="store_false", default=True)
    parser.add_argument("--no-glow", dest="glow", action="store_false", default=True)
    parser.add_argument("--no-hot-bloom", dest="hot_bloom", action="store_false", default=True)
    parser.add_argument("--no-density-expand", dest="density_expand", action="store_false", default=True)
    parser.add_argument("--no-map", dest="use_map", action="store_false", default=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if args.fetch:
        print("Fetching activities from Strava...")
        try:
            client = StravaClient.from_env()
        except KeyError as e:
            print(f"ERROR: Missing token {e} in .env")
            print("Run 'python auth.py' first to authenticate with Strava.")
            sys.exit(1)
        fetch_activities(client)

    with open("data/activities.json") as f:
        activities = json.load(f)

    city_runs = filter_sf_runs(activities)
    runs = decode_runs(city_runs)
    print(f"Rendering {len(runs)} runs...")

    scale = 0.1 if args.preview else 1.0
    w = int(CANVAS_WIDTH_PX * scale)   # final output dimensions
    h = int(CANVAS_HEIGHT_PX * scale)

    renderer = StravaRenderer(width=w, height=h)
    renderer.rasterize_all(runs)
    canvas_max_val = float(renderer.canvas.max())

    # to_image() returns oversized array (renderer.width × renderer.height) when rotation != 0
    img_array = renderer.to_image(
        bloom=False, vignette=args.vignette, grain=args.grain,
        glow=args.glow, hot_bloom=args.hot_bloom, density_expand=args.density_expand
    )
    img = Image.fromarray(img_array, mode="RGB")

    # Composite map background at intermediate (oversized) dimensions
    if args.use_map:
        from config import BG_COLOR
        cache = MAP_TILE_CACHE if not args.preview else MAP_TILE_CACHE.replace(".png", "-preview.png")
        zoom = 15 if not args.preview else 11
        try:
            tile = fetch_map_tile(
                bounds=renderer.bounds,
                zoom=zoom,
                cache_path=cache,
                target_size=(renderer.width, renderer.height),
                url_template=MAP_TILE_URL,
            )
            if MAP_TILE_BRIGHTNESS != 1.0:
                from PIL import ImageEnhance
                tile = ImageEnhance.Brightness(tile).enhance(MAP_TILE_BRIGHTNESS)
            bg = composite_map_background(tile, (renderer.width, renderer.height), MAP_TILE_OPACITY, BG_COLOR)
            bg_arr = np.array(bg, dtype=np.float32)
            route_arr = img_array.astype(np.float32)
            result = 255 - ((255 - bg_arr) * (255 - route_arr) / 255)
            img_array = np.clip(result, 0, 255).astype(np.uint8)
        except Exception as e:
            print(f"Map tile skipped: {e}")

    # Rotate + crop to final dimensions (no-op when CANVAS_ROTATION_DEGREES == 0)
    img_array = renderer.rotate_and_crop(img_array)
    img = Image.fromarray(img_array, mode="RGB")

    # Typography at final dimensions
    _download_font(MAP_FONT_PATH, MAP_FONT_URL)
    img = render_typography(img, city_runs, font_path=MAP_FONT_PATH,
                            scale=TYPOGRAPHY_SCALE, width_scale=TYPOGRAPHY_WIDTH_SCALE,
                            x_offset=int(TYPOGRAPHY_X_OFFSET * scale),
                            show_elevation=SHOW_ELEVATION)
    img = render_legend(img, color_ramp=ROUTE_COLOR_RAMP, font_path=MAP_FONT_PATH,
                        gamma=GAMMA, canvas_max_val=canvas_max_val,
                        scale=TYPOGRAPHY_SCALE, position=LEGEND_POSITION,
                        width_scale=LEGEND_WIDTH_SCALE,
                        text_width_scale=TYPOGRAPHY_WIDTH_SCALE,
                        show_elevation=SHOW_ELEVATION,
                        y_offset=int(LEGEND_Y_OFFSET * scale))

    # Save
    if args.output:
        out_path = args.output
    else:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = "-preview" if args.preview else ""
        config_tag = f"-{_pre_args.config}" if _pre_args.config != "sf" else ""
        out_path = os.path.join(OUTPUT_DIR, f"poster{config_tag}{suffix}-{ts}.png")

    dpi = 3 if args.preview else PRINT_DPI
    img.save(out_path, dpi=(dpi, dpi))
    print(f"Done. {out_path}")


if __name__ == "__main__":
    main()
