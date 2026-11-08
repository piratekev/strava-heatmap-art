#!/usr/bin/env python3
"""
Animate the run + bike combo map building up (Instagram story: 0.5s blank intro + 30s build + 2s hold).

Usage:
    python combo_animate.py               # 1080x1350 @ 30fps
    python combo_animate.py --preview     # half resolution, quicker check
    python combo_animate.py --output foo.mp4
    python combo_animate.py --still 0     # PNG of the blank intro frame
    python combo_animate.py --still 32    # PNG of the finished hold frame (fast)
    python combo_animate.py --still 15    # PNG of the frame at 15s
"""
import argparse
import json
import os
import sys
from datetime import datetime

import combo_config as C
sys.modules["config"] = C  # src/* modules read `config` at import time

from src.processor import filter_sf_runs, decode_runs, load_bike_rides
from src.combo_animator import run_combo_animation


def main():
    parser = argparse.ArgumentParser(description="Animate the run + bike combo map")
    parser.add_argument("--preview", action="store_true", help="Half resolution")
    parser.add_argument("--bikes", default=C.BIKE_RIDES_PATH, help="Baywheels rides JSON")
    parser.add_argument("--output", default=None)
    parser.add_argument("--still", type=float, default=None, metavar="SECONDS",
                        help="Save only the frame at this time as a PNG (< 0.5 = intro, >= 30.5 = finished map)")
    args = parser.parse_args()

    with open("data/activities.json") as f:
        runs = decode_runs(filter_sf_runs(json.load(f)))
    rides = load_bike_rides(args.bikes)

    w, h = C.COMBO_ANIM_RESOLUTION
    if args.preview:
        w, h = w // 2 & ~1, h // 2 & ~1   # yuv420p needs even dimensions

    if args.output:
        out_path = args.output
    else:
        os.makedirs(C.OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        tag = "-preview" if args.preview else ""
        if args.still is not None:
            out_path = os.path.join(C.OUTPUT_DIR, f"animation-combo-still-{args.still:g}s{tag}-{ts}.png")
        else:
            out_path = os.path.join(C.OUTPUT_DIR, f"animation-combo{tag}-{ts}.mp4")

    run_combo_animation(
        runs, rides, out_path, resolution=(w, h), fps=C.COMBO_ANIM_FPS,
        duration_s=C.COMBO_ANIM_DURATION_S, hold_s=C.COMBO_ANIM_HOLD_S,
        route_draw_s=C.COMBO_ANIM_ROUTE_DRAW_S,
        tracer_radius=max(1, C.COMBO_ANIM_TRACER_RADIUS // (2 if args.preview else 1)),
        dot_colors=C.COMBO_ANIM_DOT_COLORS, still_at=args.still, intro_s=C.COMBO_ANIM_INTRO_S,
        dot_glow=(C.COMBO_ANIM_DOT_GLOW_SIGMA / (2 if args.preview else 1),
                  C.COMBO_ANIM_DOT_GLOW_STRENGTH),
    )


if __name__ == "__main__":
    main()
