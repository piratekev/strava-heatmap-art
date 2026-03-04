#!/usr/bin/env python3
"""
Generate and save the SF running heatmap poster.

Usage:
    python export.py                 # full 300 DPI render
    python export.py --preview       # 1/10 scale for quick iteration
    python export.py --fetch         # fetch new activities first
    python export.py --no-map        # skip Mapbox background tile
    python export.py --no-bloom --no-grain
"""
import argparse
import json
import os
from datetime import datetime
from dotenv import load_dotenv

from src.fetcher import StravaClient, fetch_activities
from src.processor import filter_sf_runs, decode_runs
from src.renderer import StravaRenderer
from src.tiles import fetch_map_tile
from src.typography import render_typography, _download_font
from config import (
    CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, OUTPUT_DIR,
    MAP_TILE_OPACITY, MAP_TILE_CACHE,
    MAP_TILE_URL,
    MAP_FONT_PATH, MAP_FONT_URL,
)
from PIL import Image
import numpy as np


def composite_map_background(tile_img, canvas_size, opacity, bg_color):
    """Blend Mapbox tile onto solid background at given opacity."""
    bg = Image.new("RGB", canvas_size, tuple(int(c) for c in bg_color))
    tile = tile_img.resize(canvas_size, Image.LANCZOS)
    return Image.blend(bg, tile, alpha=opacity)


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Generate SF running heatmap poster")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--preview", action="store_true", help="1/10 scale for speed")
    parser.add_argument("--no-bloom", dest="bloom", action="store_false", default=True)
    parser.add_argument("--no-vignette", dest="vignette", action="store_false", default=True)
    parser.add_argument("--no-grain", dest="grain", action="store_false", default=True)
    parser.add_argument("--no-map", dest="use_map", action="store_false", default=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if args.fetch:
        print("Fetching activities from Strava...")
        client = StravaClient.from_env()
        fetch_activities(client)

    with open("data/activities.json") as f:
        activities = json.load(f)

    sf_runs = filter_sf_runs(activities)
    runs = decode_runs(sf_runs)
    print(f"Rendering {len(runs)} SF runs...")

    scale = 0.1 if args.preview else 1.0
    w = int(CANVAS_WIDTH_PX * scale)
    h = int(CANVAS_HEIGHT_PX * scale)

    renderer = StravaRenderer(width=w, height=h)
    renderer.set_bounds(runs, padding=0.05)
    renderer.rasterize_all(runs)

    img_array = renderer.to_image(
        bloom=args.bloom, vignette=args.vignette, grain=args.grain
    )
    img = Image.fromarray(img_array, mode="RGB")

    # Composite map background
    if args.use_map:
        from config import BG_COLOR, MAP_TILE_URL
        cache = MAP_TILE_CACHE if not args.preview else MAP_TILE_CACHE.replace(".png", "-preview.png")
        zoom = 13 if not args.preview else 11
        try:
            tile = fetch_map_tile(
                bounds=renderer.bounds,
                zoom=zoom,
                cache_path=cache,
                target_size=(w, h),
                url_template=MAP_TILE_URL,
            )
            bg = composite_map_background(tile, (w, h), MAP_TILE_OPACITY, BG_COLOR)
            bg_arr = np.array(bg, dtype=np.float32)
            route_arr = img_array.astype(np.float32)
            result = 255 - ((255 - bg_arr) * (255 - route_arr) / 255)
            img = Image.fromarray(np.clip(result, 0, 255).astype(np.uint8), mode="RGB")
        except Exception as e:
            print(f"Map tile skipped: {e}")

    # Typography
    _download_font(MAP_FONT_PATH, MAP_FONT_URL)
    img = render_typography(img, sf_runs, font_path=MAP_FONT_PATH)

    # Save
    if args.output:
        out_path = args.output
    else:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = "-preview" if args.preview else ""
        out_path = os.path.join(OUTPUT_DIR, f"poster{suffix}-{ts}.png")

    dpi = 30 if args.preview else 300
    img.save(out_path, dpi=(dpi, dpi))
    print(f"Done. {out_path}")


if __name__ == "__main__":
    main()
