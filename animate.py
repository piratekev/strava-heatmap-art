#!/usr/bin/env python3
"""
Generate a timelapse animation from Strava running data.

Usage:
    python animate.py                      # SF, full render
    python animate.py --config nyc         # NYC render
    python animate.py --preview            # half resolution, no hold
    python animate.py --fetch              # fetch new activities first
    python animate.py --output foo.mp4    # custom output path
"""
import argparse
import importlib
import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# ── Config injection (same pattern as render.py) ──────────────────────────────
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--config", default="sf")
_pre_args, _ = _pre.parse_known_args()

if _pre_args.config != "sf":
    sys.modules["config"] = importlib.import_module(f"{_pre_args.config}_config")
# ─────────────────────────────────────────────────────────────────────────────

import config as _cfg
from src.fetcher import StravaClient, fetch_activities
from src.processor import filter_sf_runs, decode_runs
from src.animator import run_animation
from config import OUTPUT_DIR


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Generate Strava animation")
    parser.add_argument("--config", default="sf")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--preview", action="store_true", help="Half resolution, no hold")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if args.fetch:
        print("Fetching activities from Strava...")
        try:
            client = StravaClient.from_env()
        except KeyError as e:
            print(f"ERROR: Missing token {e} in .env")
            print("Run 'python auth.py' first to authenticate.")
            sys.exit(1)
        fetch_activities(client)

    with open("data/activities.json") as f:
        activities = json.load(f)

    city_runs = filter_sf_runs(activities)
    runs = decode_runs(city_runs)
    print(f"Found {len(runs)} runs.")

    # Build an effective config object for preview overrides
    class AnimConfig:
        ANIMATION_FPS = _cfg.ANIMATION_FPS
        ANIMATION_DRAWING_SPEED = _cfg.ANIMATION_DRAWING_SPEED
        ANIMATION_DRAWING_SPEED_SLOW = _cfg.ANIMATION_DRAWING_SPEED_SLOW
        ANIMATION_SPEED_RAMP_RUNS = _cfg.ANIMATION_SPEED_RAMP_RUNS
        ANIMATION_DOT_RADIUS = _cfg.ANIMATION_DOT_RADIUS
        ANIMATION_DOT_BLUR = _cfg.ANIMATION_DOT_BLUR
        ANIMATION_HOLD_SECONDS = _cfg.ANIMATION_HOLD_SECONDS
        ANIMATION_OUTPUT_RESOLUTION = _cfg.ANIMATION_OUTPUT_RESOLUTION

    if args.preview:
        w, h = _cfg.ANIMATION_OUTPUT_RESOLUTION
        # yuv420p requires dimensions divisible by 2 — floor to nearest even
        AnimConfig.ANIMATION_OUTPUT_RESOLUTION = (w // 2 & ~1, h // 2 & ~1)
        AnimConfig.ANIMATION_HOLD_SECONDS = 0
        print(f"Preview mode: {AnimConfig.ANIMATION_OUTPUT_RESOLUTION[0]}x{AnimConfig.ANIMATION_OUTPUT_RESOLUTION[1]}, no hold.")

    if args.output:
        out_path = args.output
    else:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        config_tag = f"-{_pre_args.config}" if _pre_args.config != "sf" else ""
        preview_tag = "-preview" if args.preview else ""
        out_path = os.path.join(OUTPUT_DIR, f"animation{config_tag}{preview_tag}-{ts}.mp4")

    run_animation(runs, out_path, AnimConfig)


if __name__ == "__main__":
    main()
