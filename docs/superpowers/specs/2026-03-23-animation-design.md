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
| `src/tiles.py` | Map tile fetched once at `ANIMATION_OUTPUT_RESOLUTION`, cached, reused every frame |
| `src/renderer.py` | Projection math (`geo_to_pixel()`) and color-mapping logic; `StravaRenderer` instantiated at animation resolution |
| `src/typography.py` | `render_typography` and `render_legend` called per frame / once per run |
| `ffmpeg` subprocess | Frames piped via stdin for H.264 encoding |

---

## Canvas Resolution

Both the pre-pass and animation pass use `ANIMATION_OUTPUT_RESOLUTION` (default: `(1080, 1350)`) as the canvas size. `StravaRenderer` is instantiated at this resolution for both passes. A fresh renderer instance is created for the animation pass (not reused from the pre-pass).

The full poster resolution (4720×5900) is not used during animation. All rendering occurs at animation resolution.

---

## Two Distinct Canvas Concepts

To avoid confusion, the spec uses two distinct terms:

- **Accumulation canvas** — the persistent float32 array that routes are drawn into (`canvas += buf`). It carries density across frames and across runs. It is never reset between frames.
- **Output frame** — the uint8 RGB array built from scratch each frame: color-map the current accumulation canvas state → composite with map tile → paint dot → stamp typography. Each output frame is independent of the previous output frame.

---

## Normalization Strategy

The static renderer pipeline: `accumulation_canvas → log1p → normalize by log1p max → gamma → color ramp → RGB`. The density expand and hot bloom passes are **omitted from animation** — density expand is expensive per-frame, and hot bloom's threshold is calibrated for global-max normalization which is visually unstable when the max grows each frame. The animation output will match the static render's color mapping but without these post-process effects.

The animation replicates the core pipeline with a fixed normalization anchor so early frames are dim and the final frame matches the static render:

1. **Pre-pass:** Instantiate `StravaRenderer` at `ANIMATION_OUTPUT_RESOLUTION`. Rasterize all runs. Compute `final_log_max = np.log1p(canvas).max()`. If `final_log_max == 0` (no qualifying runs), exit with a clear error. Discard canvas and renderer.

2. **Animation pass:** Create a fresh `StravaRenderer` at the same resolution. Every frame:
   - `norm = np.log1p(accumulation_canvas) / final_log_max`
   - Apply gamma → color ramp → uint8 RGB

Early frames: accumulation canvas is small → norm is small → dim. Final frame: `np.log1p(canvas).max() == final_log_max` → norm peaks at 1.0 → identical color output to static render.

**Canvas rotation is out of scope for animation.** `animate.py` does not support `CANVAS_ROTATION_DEGREES`. If a city config sets rotation, animate.py exits with an error advising the user to add a `CANVAS_ROTATION_DEGREES = 0` override.

---

## Frame Loop

Runs are sorted by `start_date` ascending. No inter-run frames — next run begins immediately after the last frame of the previous run.

Each run carries two parallel representations: geo coordinates (lat/lng pairs, for mileage) and pixel coordinates (for rasterization). Both are computed from the decoded polyline at run start.

**At the start of each run:**
1. Increment run count (N).
2. Update Month Year from `start_date`.
3. Project polyline to pixel coordinates via `renderer.geo_to_pixel()`.
4. Set `segment_index = 0`, `segment_offset = 0.0` (fractional position along current segment).
5. If the polyline has fewer than 2 points, skip the run (no frames drawn; run count still increments; mileage unchanged).

**For each frame within a run:**
1. Advance cursor by `ANIMATION_DRAWING_SPEED` pixels along the pixel-coordinate path. Track position as `(segment_index, segment_offset)`. Stop when path end is reached.
2. Collect the drawn subsegment's start and end in pixel coordinates. Draw it onto the accumulation canvas (`canvas += buf`).
3. **Mileage:** the cursor tracks `(segment_index, t)` where `t ∈ [0,1]` is the fractional progress along segment `segment_index` in pixel space. The same `(segment_index, t)` indexes into the parallel geo-coordinate path. For each geo segment spanned by the cursor step, interpolate start/end geo points using the same `t` fractions, compute Haversine distance (meters → miles), add to `total_miles`. Display `math.floor(total_miles)`. At run N's first frame the display is cumulative miles from runs 1..N-1 plus the first drawn segment's distance.
4. Build output frame:
   a. `norm = np.log1p(accumulation_canvas) / final_log_max`
   b. Gamma → color ramp → uint8 RGB
   c. Screen-blend with map tile background
   d. Paint cursor dot at current tip pixel
   e. Stamp live typography (Month Year, N runs, `math.floor(total_miles)` mi)
   f. Stamp static pre-rendered color legend
5. Convert RGB → BGR, write bytes to ffmpeg stdin.

**After all runs:** write `int(ANIMATION_HOLD_SECONDS × ANIMATION_FPS)` copies of the final output frame.

---

## Drawing Speed & Duration

`ANIMATION_DRAWING_SPEED` pixels/frame (at `ANIMATION_OUTPUT_RESOLUTION`). At startup, before rendering, `animate.py` computes and prints:

```
Expected duration: Xs (Y frames at Z fps). Adjust ANIMATION_DRAWING_SPEED to change.
```

The user can then abort (Ctrl-C) and tune the knob. Default is calibrated for ~60s with ~550 SF runs.

---

## Bright Dot (Cursor)

White filled circle on the output frame. Not written to the accumulation canvas.

- **Color:** `[255, 255, 255]`
- **Radius:** `ANIMATION_DOT_RADIUS` pixels
- **Soft edge:** Gaussian blur on dot layer with sigma `ANIMATION_DOT_BLUR` (0 = hard edge, 4 = default soft halo)
- If no segment is drawn in a frame (defensive guard for zero-length runs, which are skipped), no dot is painted.

---

## Live Typography

Typography is rendered every output frame. The color legend (color ramp bar only — no run stats) is pre-rendered once before the animation loop and composited onto every frame unchanged.

| Field | Update frequency |
|---|---|
| Month Year (e.g. "Mar 2019") | Once per run (from `start_date`) |
| N runs | Once per run (increments before first segment drawn) |
| N mi (floor integer) | Every frame |

**Typography scale:** `anim_scale = (ANIMATION_OUTPUT_RESOLUTION[1] / CANVAS_HEIGHT_PX) * TYPOGRAPHY_SCALE`

`CANVAS_HEIGHT_PX` and `TYPOGRAPHY_SCALE` come from the active config (SF or NYC or other), which is correct — city configs set these values relative to their poster dimensions.

---

## Output Encoding

Frames are piped to an `ffmpeg` subprocess. `ffmpeg` must be on `PATH`; `animate.py` checks at startup and exits with a clear error message if not found.

```
ffmpeg -y -f rawvideo -vcodec rawvideo -pix_fmt rgb24 \
    -s {W}x{H} -r {FPS} -i pipe:0 \
    -vcodec libx264 -pix_fmt yuv420p -crf 18 \
    output.mp4
```

`ANIMATION_OUTPUT_RESOLUTION = (1080, 1350)` is `(width, height)` — same convention as `CANVAS_WIDTH_PX / CANVAS_HEIGHT_PX`. In the ffmpeg command: `W=1080, H=1350`, giving `-s 1080x1350`.

- **Filename:** `output/animation-<config>-<timestamp>.mp4`
- **Quality:** `-crf 18` (visually lossless H.264)

---

## Preview Mode

`--preview` halves the output resolution: `preview_resolution = (W // 2, H // 2)` where `W, H = ANIMATION_OUTPUT_RESOLUTION`. `ANIMATION_DRAWING_SPEED` stays the same in pixel units — at half canvas size the total path lengths in pixels are roughly half, so the video is shorter (~30s) and the cursor appears to move at half the visual speed. This is acceptable for preview purposes. Hold frames are omitted. The color legend is pre-rendered once at the same reduced size.

---

## New Config Knobs

Added to `config.py` (overridable in city configs):

```python
# Animation
ANIMATION_FPS = 60
ANIMATION_DRAWING_SPEED = 80        # pixels/frame at ANIMATION_OUTPUT_RESOLUTION
ANIMATION_DOT_RADIUS = 12           # pixels at ANIMATION_OUTPUT_RESOLUTION
ANIMATION_DOT_BLUR = 4              # Gaussian sigma for dot halo; 0 = hard edge
ANIMATION_HOLD_SECONDS = 3          # seconds to hold on final frame
ANIMATION_OUTPUT_RESOLUTION = (1080, 1350)  # width, height (4:5 for Instagram)
```

---

## CLI

```
python animate.py                    # SF, full animation
python animate.py --config nyc       # NYC animation
python animate.py --preview          # half resolution, no hold frames
python animate.py --fetch            # fetch new activities first
python animate.py --output foo.mp4  # custom output path
```

---

## Implementation Notes

- Mileage is computed from geo coordinates, not pixel coordinates. No `pixel_to_geo()` is needed or added.
- Map tile is fetched/cached at `ANIMATION_OUTPUT_RESOLUTION`.
- Branch: `feature/animation` — no changes to `main` branch pipeline.

---

## Testing

- **Unit:** `final_log_max` from pre-pass equals `np.log1p(canvas).max()` after rasterizing all runs at animation resolution.
- **Unit:** Accumulated mileage is monotonically non-decreasing across all frames.
- **Unit:** Run count is monotonically non-decreasing; equals N on all frames of run N (including run N's first frame).
- **Unit:** Runs with fewer than 2 points are skipped; run count still increments, mileage unchanged.
- **Smoke:** `--preview` produces a non-empty valid MP4 (file size > 0 and ffprobe reports duration > 0).
- **Visual:** Final frame of animation matches static poster output (manual inspection at same resolution).
