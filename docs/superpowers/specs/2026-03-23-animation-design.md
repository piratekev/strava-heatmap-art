# Animation Feature Design
**Date:** 2026-03-23
**Status:** Approved

## Overview

Generate an MP4 timelapse animation from years of Strava running data. Routes are drawn stroke-by-stroke with a visible leading cursor, accumulating density and glow over time. The final frame matches the static poster output exactly.

## Goal

Produce a 60–65 second, 60fps MP4 video suitable for sharing on Instagram and saving to an iPhone camera roll. The video shows all runs in chronological order being drawn on the map, with each run traced by a bright dot cursor at constant drawing speed. Existing routes get brighter as more runs overlap them.

## Non-Goals

- GIF output
- Per-frame activity type filtering
- Route color changes based on activity type
- Smooth interpolation between GPS points (raw polyline segments only)

---

## Architecture

A new `animate.py` entry point sits alongside `export.py`. It reuses the full existing pipeline without modifying any existing source files:

| Component | Role in animation |
|---|---|
| `src/fetcher.py` + `src/processor.py` | Same activity fetch / filter / decode |
| `src/tiles.py` | Map tile fetched once, cached, reused every frame |
| `src/renderer.py` | Projection math + color mapping; accumulation canvas managed externally |
| `src/typography.py` | `render_typography` called per frame with live stats |
| `cv2.VideoWriter` | Encodes frames directly to MP4, no temp files |

---

## Normalization Strategy

The central design constraint: the final frame must match the static poster, and early frames must be dim (not full-brightness).

**Solution: fixed normalization against the pre-computed final canvas max.**

1. **Pre-pass:** Rasterize all runs in full (same logic as static render) → record `final_canvas_max` → discard canvas.
2. **Animation pass:** Rebuild the accumulation canvas from scratch. Every frame normalizes using `norm = current_canvas / final_canvas_max`. Early frames have a small numerator → dim. Routes accumulate naturally. The last frame is identical to the static render.

This also handles out-and-back routes correctly: the cursor passes over the same pixels twice during a single run, incrementing the canvas value both times, making those segments visibly brighter on the second pass.

---

## Frame Loop

Runs are sorted by `start_date` ascending.

For each run:
1. Decode polyline to pixel coordinates via `renderer.geo_to_pixel()`.
2. Walk the path in steps of `ANIMATION_DRAWING_SPEED` pixels per frame.
3. For each frame:
   a. Draw the new segment onto the float32 accumulation canvas (`canvas += buf`, same as static renderer).
   b. Compute `norm = canvas / final_canvas_max`.
   c. Apply gamma → color ramp → produce RGB array.
   d. Composite: map tile background (screen blend) + color-mapped routes.
   e. Paint bright dot overlay at current tip position (not written to accumulation canvas).
   f. Stamp live typography block.
   g. Write frame to `cv2.VideoWriter`.

After all runs: hold the final frame for `ANIMATION_HOLD_SECONDS` seconds (written as repeated identical frames).

---

## Drawing Speed & Duration

Drawing speed is constant in pixels/frame (`ANIMATION_DRAWING_SPEED`). Longer runs take proportionally more frames than shorter runs.

Total frame count ≈ `(sum of all run path lengths in pixels) / ANIMATION_DRAWING_SPEED`

`ANIMATION_DRAWING_SPEED` is tuned so that total duration ≈ 60 seconds at 60fps (3600 frames). With ~550 runs this is calibrated at startup: the script computes expected duration and prints it before rendering, allowing the user to abort and adjust the speed knob.

---

## Bright Dot (Cursor)

The cursor is a white filled circle rendered on top of the composited frame each frame. It is **not** written to the accumulation canvas — it disappears when the cursor moves on.

- Color: white `[255, 255, 255]`
- Size: `ANIMATION_DOT_RADIUS` pixels (scaled to output resolution)
- Optional soft edge: small Gaussian blur on the dot layer before compositing, producing a subtle halo

Config knobs: `ANIMATION_DOT_RADIUS`, `ANIMATION_DOT_BRIGHTNESS` (multiplier applied before compositing).

---

## Live Typography

The typography block is rendered every frame (PIL text at 1080×1350 is fast — ~19× cheaper than full poster resolution).

| Field | Update frequency |
|---|---|
| Month Year (e.g. "Mar 2019") | Once per run (from run's `start_date`) |
| N runs | Once per run (increments at run start) |
| N mi (floor integer) | Every frame (accumulates as cursor advances) |

Mileage per frame: each drawn segment's pixel length is converted back to geographic distance (meters → miles) using the renderer's scale factor, and added to the running total. Display uses `math.floor()`.

The color legend is static — rendered once and composited the same way every frame.

---

## Output

- **Format:** MP4, H.264, yuv420p (maximum iPhone/Instagram compatibility)
- **Resolution:** `ANIMATION_OUTPUT_RESOLUTION = (1080, 1350)` (4:5, Instagram portrait)
- **Frame rate:** `ANIMATION_FPS = 60`
- **Duration:** ~60s video + 3s hold = ~63s total
- **Filename:** `output/animation-<config>-<timestamp>.mp4`
- **Encoding:** `cv2.VideoWriter` with `mp4v` or `avc1` codec; fallback to `ffmpeg` subprocess if OpenCV H.264 support is unavailable

---

## New Config Knobs

Added to `config.py` (overridable in city configs):

```python
# Animation
ANIMATION_FPS = 60
ANIMATION_DRAWING_SPEED = 80        # pixels/frame at output resolution; tune to hit ~60s
ANIMATION_DOT_RADIUS = 12           # pixels at output resolution
ANIMATION_DOT_BRIGHTNESS = 1.0      # multiplier on white dot before compositing
ANIMATION_HOLD_SECONDS = 3          # hold on final frame
ANIMATION_OUTPUT_RESOLUTION = (1080, 1350)  # width, height
```

---

## CLI

```
python animate.py                    # SF, full animation
python animate.py --config nyc       # NYC animation
python animate.py --preview          # fast preview: lower resolution, skip hold
python animate.py --fetch            # fetch new activities first
python animate.py --output foo.mp4  # custom output path
```

`--preview` reduces output resolution (e.g. 540×675) and skips the hold frames for fast iteration.

---

## Implementation Notes

- The pre-pass rasterizes at full render scale (same as static), not at animation output resolution. The animation renders at `ANIMATION_OUTPUT_RESOLUTION` directly — no downscaling needed since 1080×1350 < 4720×5900.
- `cv2.VideoWriter` requires frames in BGR order; convert with `img[:, :, ::-1]` before writing.
- Map tile is fetched/cached at `ANIMATION_OUTPUT_RESOLUTION` to avoid per-frame resize.
- Typography is stamped last (on top of everything) to avoid being obscured by routes.
- Branch: `feature/animation` (all work isolated here, no changes to `main` pipeline).

---

## Testing

- Unit test: verify `final_canvas_max` from pre-pass equals `canvas.max()` after full static rasterization.
- Unit test: verify per-frame mileage accumulation is monotonically increasing.
- Smoke test: `--preview` mode completes without error and produces a valid MP4.
- Visual test: final frame of animation visually matches static poster output.
