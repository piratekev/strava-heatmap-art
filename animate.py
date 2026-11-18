#!/usr/bin/env python3
"""
Generate a timelapse animation from Strava running data.

Usage:
    python animate.py                          # sequential mode, full render
    python animate.py --mode parallel          # all runs draw simultaneously (15s)
    python animate.py --config my_city         # north-up city; NYC rotation unsupported
    python animate.py --preview                # half resolution; no sequential hold
    python animate.py --fetch                  # fetch new activities first
    python animate.py --output foo.mp4         # custom output path
"""
import argparse
import importlib
import json
import os
import sys
from datetime import datetime
from types import SimpleNamespace
from dotenv import load_dotenv

# ── Config injection (same pattern as render.py) ──────────────────────────────
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--config", default="sf")
_pre_args, _ = _pre.parse_known_args()

if _pre_args.config != "sf":
    sys.modules["config"] = importlib.import_module(f"{_pre_args.config}_config")
# ─────────────────────────────────────────────────────────────────────────────

import config as _cfg
from src.sources import fetch_from_source
from src.processor import filter_sf_runs, decode_runs
from src.animator import run_animation, run_parallel_animation, validate_animation_config
from config import OUTPUT_DIR


def main():
    load_dotenv(".env")
    parser = argparse.ArgumentParser(description="Generate Strava animation")
    parser.add_argument("--config", default="sf")
    parser.add_argument("--mode", choices=["sequential", "parallel"], default="sequential")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--preview", action="store_true",
                        help="Half resolution; no sequential hold, 1s parallel hold")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    # Preserve all active settings; preview overrides only its documented knobs.
    anim_config = SimpleNamespace(**{k: v for k, v in vars(_cfg).items() if k.isupper()})
    try:
        validate_animation_config(anim_config, args.mode)
    except ValueError as exc:
        parser.error(str(exc))

    if args.preview:
        w, h = _cfg.ANIMATION_OUTPUT_RESOLUTION
        # yuv420p requires dimensions divisible by 2 — floor to nearest even
        anim_config.ANIMATION_OUTPUT_RESOLUTION = (w // 2 & ~1, h // 2 & ~1)
        anim_config.ANIMATION_HOLD_SECONDS = 0
        anim_config.ANIMATION_PARALLEL_HOLD_S = 1
        print(f"Preview mode: {anim_config.ANIMATION_OUTPUT_RESOLUTION[0]}x{anim_config.ANIMATION_OUTPUT_RESOLUTION[1]}")

    try:
        validate_animation_config(anim_config, args.mode)
    except ValueError as exc:
        parser.error(str(exc))

    if args.fetch:
        fetch_from_source(_cfg.FETCH_SOURCE)

    try:
        with open("data/activities.json") as f:
            activities = json.load(f)
    except FileNotFoundError:
        parser.error("No cached activities. Run 'python animate.py --fetch' first.")
    except (OSError, ValueError):
        parser.error("Cannot read data/activities.json. Restore it or run with --fetch.")
    if not isinstance(activities, list):
        parser.error("data/activities.json must contain an activity list. Run with --fetch.")

    city_runs = filter_sf_runs(activities)
    if not city_runs:
        parser.error("No running activities with GPS match this city's bounds. "
                     "Check --config and CITY_BOUNDS, or run with --fetch.")
    runs = decode_runs(city_runs)
    print(f"Found {len(runs)} runs.")

    if args.output:
        out_path = args.output
    else:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        config_tag = f"-{_pre_args.config}" if _pre_args.config != "sf" else ""
        mode_tag = f"-{args.mode}" if args.mode != "sequential" else ""
        preview_tag = "-preview" if args.preview else ""
        out_path = os.path.join(OUTPUT_DIR, f"animation{config_tag}{mode_tag}{preview_tag}-{ts}.mp4")

    try:
        if args.mode == "parallel":
            run_parallel_animation(runs, out_path, anim_config)
        else:
            run_animation(runs, out_path, anim_config)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Animation cancelled.\n")


if __name__ == "__main__":
    main()
