#!/usr/bin/env python3
"""
Generate and save the SF running heatmap poster.

Usage:
    python export.py                          # full 300 DPI render
    python export.py --preview                # 1/10 scale for quick iteration
    python export.py --no-bloom --no-grain    # effects off
    python export.py --fetch                  # fetch new activities first
"""
import argparse
import json
import os
from datetime import datetime

from src.fetcher import StravaClient, fetch_activities
from src.processor import filter_sf_runs, decode_runs
from src.renderer import StravaRenderer
from config import CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, OUTPUT_DIR


def main():
    parser = argparse.ArgumentParser(description="Generate SF running heatmap poster")
    parser.add_argument("--fetch", action="store_true", help="Fetch new activities from Strava")
    parser.add_argument("--preview", action="store_true", help="Render at 1/10 scale for speed")
    parser.add_argument("--no-bloom", dest="bloom", action="store_false", default=True)
    parser.add_argument("--no-vignette", dest="vignette", action="store_false", default=True)
    parser.add_argument("--no-grain", dest="grain", action="store_false", default=True)
    parser.add_argument("--output", default=None, help="Output file path (default: output/poster-TIMESTAMP.png)")
    args = parser.parse_args()

    # Optionally fetch new data
    if args.fetch:
        print("Fetching activities from Strava...")
        client = StravaClient.from_env()
        fetch_activities(client)

    # Load and process cached data
    with open("data/activities.json") as f:
        activities = json.load(f)

    sf_runs = filter_sf_runs(activities)
    runs = decode_runs(sf_runs)
    print(f"Rendering {len(runs)} SF runs...")

    # Set up renderer
    scale = 0.1 if args.preview else 1.0
    renderer = StravaRenderer(
        width=int(CANVAS_WIDTH_PX * scale),
        height=int(CANVAS_HEIGHT_PX * scale),
    )

    renderer.rasterize_all(runs)

    # Output path
    if args.output:
        out_path = args.output
    else:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = "-preview" if args.preview else ""
        out_path = os.path.join(OUTPUT_DIR, f"poster{suffix}-{ts}.png")

    dpi = 30 if args.preview else 300
    renderer.save(out_path, dpi=dpi, bloom=args.bloom, vignette=args.vignette, grain=args.grain)
    print(f"Done. {out_path}")


if __name__ == "__main__":
    main()
