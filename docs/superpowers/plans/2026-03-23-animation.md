# Animation Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `animate.py` that generates a 60fps MP4 timelapse of all Strava runs being drawn stroke-by-stroke with a glowing cursor, accumulating density over time, ending with a frame that matches the static poster.

**Architecture:** A new `src/animator.py` module holds all animation logic (cursor tracking, mileage, color mapping, dot rendering, ffmpeg pipe). A thin `animate.py` CLI entry point wires the existing pipeline together with `src/animator.py`, mirroring the structure of `export.py`. No existing source files are modified.

**Tech Stack:** Python, NumPy, OpenCV (cv2), PIL (Pillow), scipy.ndimage, ffmpeg subprocess (must be on PATH), existing src/* pipeline.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `config.py` | Modify | Add 6 animation config knobs |
| `src/animator.py` | Create | All animation logic: cursor, mileage, color map, dot, ffmpeg pipe, main loop |
| `animate.py` | Create | CLI entry point — config injection + pipeline wiring |
| `tests/test_animator.py` | Create | Unit + integration tests for src/animator.py |

---

## Important Codebase Notes

- The projection method is `renderer.project(lat, lng) → (x, y)` — **not** `geo_to_pixel()`. The spec has the wrong name. Use `project()`.
- `StravaRenderer.rasterize_all(runs)` does a two-pass density-scoring rasterize. Use this for the pre-pass.
- `to_image()` applies density expand, bloom, glow, grain, vignette — **do not call this per-frame**. Instead implement color mapping inline in `src/animator.py`.
- `render_legend()` needs `canvas_max_val=renderer.canvas.max()` (raw, not log) from the pre-pass to compute `t_min`. Capture this before discarding the pre-pass renderer.
- `render_typography(img, sf_runs, font_path, ...)` expects a list of run dicts. For animation we write a separate `render_animation_typography()` that takes explicit scalar args.
- **Import discipline:** `numpy`, `cv2`, `scipy.ndimage`, and `config` values must all be imported at the **top of `src/animator.py`**, not inside function bodies or loops. In particular, `ROUTE_LINE_THICKNESS` and `cv2` must not appear inside the per-frame while-loop — hoist them to module level.
- Tests use `pytest`. Run with `.venv/bin/pytest tests/ -v`.
- Active branch: `feature/animation`. All commits go here.

---

## Task 1: Add Animation Config Knobs

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Add knobs to config.py**

Append to the bottom of `config.py`:

```python
# ── Animation ─────────────────────────────────────────────────────────────────
ANIMATION_FPS = 60
ANIMATION_DRAWING_SPEED = 80   # pixels/frame at ANIMATION_OUTPUT_RESOLUTION; tune to hit ~60s
ANIMATION_DOT_RADIUS = 12      # cursor dot radius in pixels at ANIMATION_OUTPUT_RESOLUTION
ANIMATION_DOT_BLUR = 4         # Gaussian sigma for dot halo; 0 = hard edge
ANIMATION_HOLD_SECONDS = 3     # seconds to hold on final frame
ANIMATION_OUTPUT_RESOLUTION = (1080, 1350)  # (width, height) — 4:5 for Instagram
```

- [ ] **Step 2: Verify import**

```bash
.venv/bin/python -c "from config import ANIMATION_FPS, ANIMATION_DRAWING_SPEED, ANIMATION_DOT_RADIUS, ANIMATION_DOT_BLUR, ANIMATION_HOLD_SECONDS, ANIMATION_OUTPUT_RESOLUTION; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "feat: add animation config knobs"
```

---

## Task 2: Haversine Distance + Per-Frame Mileage

**Files:**
- Create: `src/animator.py` (initial skeleton + haversine)
- Create: `tests/test_animator.py` (initial)

The cursor tracks `(seg_idx, t)` where `t ∈ [0.0, 1.0]` is the fractional progress along segment `seg_idx` in pixel space. Mileage uses the same `(seg_idx, t)` to interpolate geo coordinates, so no pixel→geo inverse is needed.

- [ ] **Step 1: Write failing tests**

Create `tests/test_animator.py`:

```python
import math
import pytest
from src.animator import haversine_miles, compute_frame_miles


def test_haversine_same_point_is_zero():
    assert haversine_miles(37.76, -122.45, 37.76, -122.45) == pytest.approx(0.0)


def test_haversine_known_distance():
    # SF City Hall to ~1 mile north: rough check within 5%
    miles = haversine_miles(37.7749, -122.4194, 37.7904, -122.4194)
    assert 0.95 < miles < 1.15


def test_compute_frame_miles_full_segment():
    # geo_coords: two points ~1 mile apart
    geo = [(37.7749, -122.4194), (37.7904, -122.4194)]
    miles = compute_frame_miles(geo, 0, 0.0, 0, 1.0)
    assert 0.95 < miles < 1.15


def test_compute_frame_miles_half_segment():
    geo = [(37.7749, -122.4194), (37.7904, -122.4194)]
    full = compute_frame_miles(geo, 0, 0.0, 0, 1.0)
    half = compute_frame_miles(geo, 0, 0.0, 0, 0.5)
    assert half == pytest.approx(full / 2, rel=0.01)


def test_compute_frame_miles_spans_two_segments():
    # Three points: A→B ~0.5mi, B→C ~0.5mi
    geo = [(37.7749, -122.4194), (37.7826, -122.4194), (37.7904, -122.4194)]
    # Full path from start of seg0 to end of seg1
    miles = compute_frame_miles(geo, 0, 0.0, 1, 1.0)
    assert 0.95 < miles < 1.15


def test_compute_frame_miles_zero_distance():
    geo = [(37.7749, -122.4194), (37.7904, -122.4194)]
    assert compute_frame_miles(geo, 0, 0.5, 0, 0.5) == pytest.approx(0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_animator.py -v
```

Expected: `ImportError` — `src/animator.py` does not exist yet.

- [ ] **Step 3: Create `src/animator.py` with haversine and compute_frame_miles**

```python
"""Animation pipeline for strava-heatmap-art."""
import math
import subprocess
import sys


# ── Mileage ───────────────────────────────────────────────────────────────────

_EARTH_RADIUS_M = 6_371_000
_METERS_PER_MILE = 1609.344


def haversine_miles(lat1, lng1, lat2, lng2):
    """Haversine distance between two (lat, lng) points in miles."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a)) / _METERS_PER_MILE


def compute_frame_miles(geo_coords, start_seg, start_t, end_seg, end_t):
    """Haversine distance (miles) traversed from (start_seg, start_t) to (end_seg, end_t).

    geo_coords: list of (lat, lng) tuples.
    seg N spans geo_coords[N] → geo_coords[N+1].
    t ∈ [0, 1] is fractional progress along segment N.
    """
    total = 0.0
    seg = start_seg
    t0 = start_t
    while seg <= end_seg:
        t1 = end_t if seg == end_seg else 1.0
        lat0 = geo_coords[seg][0] + t0 * (geo_coords[seg + 1][0] - geo_coords[seg][0])
        lng0 = geo_coords[seg][1] + t0 * (geo_coords[seg + 1][1] - geo_coords[seg][1])
        lat1 = geo_coords[seg][0] + t1 * (geo_coords[seg + 1][0] - geo_coords[seg][0])
        lng1 = geo_coords[seg][1] + t1 * (geo_coords[seg + 1][1] - geo_coords[seg][1])
        total += haversine_miles(lat0, lng0, lat1, lng1)
        seg += 1
        t0 = 0.0
    return total
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_animator.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/animator.py tests/test_animator.py
git commit -m "feat: add haversine_miles and compute_frame_miles"
```

---

## Task 3: Cursor Advancement

**Files:**
- Modify: `src/animator.py`
- Modify: `tests/test_animator.py`

The cursor walks along a list of pixel-space `(x, y)` points. Each frame, advance `pixels_budget` pixels. Returns the new `(seg_idx, t)` position, plus a list of drawn sub-segments as `((x0,y0), (x1,y1))` tuples (for rasterization and dot placement).

- [ ] **Step 1: Write failing tests**

Append to `tests/test_animator.py`:

```python
from src.animator import advance_cursor


def test_advance_cursor_within_single_segment():
    pts = [(0, 0), (100, 0)]  # 100px horizontal segment
    new_seg, new_t, drawn = advance_cursor(pts, 0, 0.0, 50.0)
    assert new_seg == 0
    assert new_t == pytest.approx(0.5)
    assert len(drawn) == 1
    assert drawn[0][0] == pytest.approx((0.0, 0.0))
    assert drawn[0][1] == pytest.approx((50.0, 0.0))


def test_advance_cursor_crosses_segment_boundary():
    pts = [(0, 0), (50, 0), (150, 0)]  # seg0=50px, seg1=100px
    new_seg, new_t, drawn = advance_cursor(pts, 0, 0.0, 75.0)
    assert new_seg == 1
    assert new_t == pytest.approx(0.25)
    assert len(drawn) == 2  # one sub-seg per spanned segment


def test_advance_cursor_stops_at_path_end():
    pts = [(0, 0), (100, 0)]
    new_seg, new_t, drawn = advance_cursor(pts, 0, 0.0, 999.0)
    assert new_seg == 0   # last valid segment index
    assert new_t == pytest.approx(1.0)


def test_advance_cursor_from_mid_segment():
    pts = [(0, 0), (100, 0)]
    new_seg, new_t, drawn = advance_cursor(pts, 0, 0.5, 25.0)
    assert new_seg == 0
    assert new_t == pytest.approx(0.75)
    assert drawn[0][0] == pytest.approx((50.0, 0.0))
    assert drawn[0][1] == pytest.approx((75.0, 0.0))


def test_advance_cursor_zero_length_segment_skipped():
    pts = [(10, 10), (10, 10), (110, 10)]  # seg0 has zero length
    new_seg, new_t, drawn = advance_cursor(pts, 0, 0.0, 50.0)
    # should advance into seg1 (or skip seg0) without dividing by zero
    assert new_t >= 0.0
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/test_animator.py::test_advance_cursor_within_single_segment -v
```

Expected: FAIL (`ImportError` or `AttributeError`).

- [ ] **Step 3: Implement `advance_cursor` in `src/animator.py`**

```python
# ── Cursor ────────────────────────────────────────────────────────────────────

def advance_cursor(pixel_coords, seg_idx, t, pixels_budget):
    """Advance cursor along pixel_coords by pixels_budget pixels.

    Returns:
        (new_seg_idx, new_t, drawn_segments)

    drawn_segments: list of ((x0,y0), (x1,y1)) float tuples — one entry per
        segment boundary crossed. Used for rasterization and dot placement.
        The final entry's [1] is the new cursor tip position.
    """
    drawn = []
    n = len(pixel_coords)

    while pixels_budget > 0 and seg_idx < n - 1:
        p0 = pixel_coords[seg_idx]
        p1 = pixel_coords[seg_idx + 1]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        seg_len = math.hypot(dx, dy)

        if seg_len == 0:
            # Zero-length segment: skip to next without consuming budget
            seg_idx += 1
            t = 0.0
            continue

        remaining_px = seg_len * (1.0 - t)
        start_x = p0[0] + t * dx
        start_y = p0[1] + t * dy

        if pixels_budget >= remaining_px:
            # Consume this segment entirely and continue
            pixels_budget -= remaining_px
            end_x, end_y = float(p1[0]), float(p1[1])
            drawn.append(((start_x, start_y), (end_x, end_y)))
            seg_idx += 1
            t = 0.0
            # If we've just finished the last segment, stop
            if seg_idx >= n - 1:
                seg_idx = n - 2
                t = 1.0
                break
        else:
            # Consume partial segment
            frac = pixels_budget / seg_len
            t += frac
            t = min(t, 1.0)
            end_x = p0[0] + t * dx
            end_y = p0[1] + t * dy
            drawn.append(((start_x, start_y), (end_x, end_y)))
            pixels_budget = 0

    return seg_idx, t, drawn
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_animator.py -v -k "cursor"
```

Expected: all cursor tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/animator.py tests/test_animator.py
git commit -m "feat: add advance_cursor for frame-by-frame path traversal"
```

---

## Task 4: Canvas → RGB Color Mapping

**Files:**
- Modify: `src/animator.py`
- Modify: `tests/test_animator.py`

This is the per-frame color pipeline: `log1p(canvas) / final_log_max → gamma → color ramp → RGB`. No density expand, no bloom.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_animator.py`:

```python
import numpy as np
from src.animator import canvas_to_rgb


def test_canvas_to_rgb_all_zero_is_bg_color():
    canvas = np.zeros((10, 10), dtype=np.float32)
    final_log_max = 1.0
    color_ramp = [(0.0, [0, 0, 255]), (1.0, [255, 0, 0])]
    bg = [0, 0, 0]
    rgb = canvas_to_rgb(canvas, final_log_max, gamma=1.0, color_ramp=color_ramp, bg_color=bg)
    assert rgb.shape == (10, 10, 3)
    assert rgb.dtype == np.uint8
    assert rgb.max() == 0  # all background = black


def test_canvas_to_rgb_at_final_log_max_is_bright():
    # A canvas where one pixel equals e^final_log_max - 1 (i.e. log1p = final_log_max)
    final_log_max = math.log1p(5.0)
    canvas = np.zeros((5, 5), dtype=np.float32)
    canvas[2, 2] = 5.0  # log1p(5) / final_log_max = 1.0
    color_ramp = [(0.0, [0, 0, 255]), (1.0, [255, 0, 0])]
    bg = [0, 0, 0]
    rgb = canvas_to_rgb(canvas, final_log_max, gamma=1.0, color_ramp=color_ramp, bg_color=bg)
    # Peak pixel should be near [255, 0, 0]
    assert rgb[2, 2, 0] > 200
    assert rgb[2, 2, 2] < 50


def test_canvas_to_rgb_shape_preserved():
    canvas = np.ones((20, 15), dtype=np.float32)
    rgb = canvas_to_rgb(canvas, final_log_max=1.0, gamma=1.0,
                        color_ramp=[(0.0, [0,0,0]), (1.0, [255,255,255])],
                        bg_color=[0,0,0])
    assert rgb.shape == (20, 15, 3)
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/test_animator.py -v -k "rgb"
```

Expected: FAIL.

- [ ] **Step 3: Implement `canvas_to_rgb` in `src/animator.py`**

Add after the cursor section. Also import `_ramp_colors` from `src/renderer.py` (it's a module-level function):

```python
# ── Color mapping ─────────────────────────────────────────────────────────────

import numpy as np
from src.renderer import _ramp_colors


def canvas_to_rgb(canvas, final_log_max, gamma, color_ramp, bg_color):
    """Convert float32 accumulation canvas to uint8 RGB.

    Uses fixed final_log_max so early frames are dim and the final frame
    matches the static poster color output (without density expand / bloom).
    """
    if final_log_max <= 0:
        norm = np.zeros_like(canvas)
    else:
        norm = np.log1p(canvas) / final_log_max

    norm = norm ** gamma
    norm = np.clip(norm, 0.0, 1.0)

    bg = np.array(bg_color, dtype=np.float32)
    route_colors = _ramp_colors(norm, color_ramp)
    rgb = np.zeros((*canvas.shape, 3), dtype=np.float32)
    for c in range(3):
        rgb[:, :, c] = bg[c] * (1 - norm) + route_colors[:, :, c] * norm

    return np.clip(rgb, 0, 255).astype(np.uint8)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_animator.py -v -k "rgb"
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/animator.py tests/test_animator.py
git commit -m "feat: add canvas_to_rgb color mapping for animation frames"
```

---

## Task 5: Cursor Dot Rendering

**Files:**
- Modify: `src/animator.py`
- Modify: `tests/test_animator.py`

Paint a white circle with optional Gaussian blur onto a uint8 RGB frame. The dot is painted directly onto the output frame (not the accumulation canvas).

- [ ] **Step 1: Write failing tests**

Append to `tests/test_animator.py`:

```python
from src.animator import paint_dot


def test_paint_dot_center_is_white():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    paint_dot(frame, cx=50, cy=50, radius=5, blur_sigma=0)
    assert frame[50, 50, 0] == 255
    assert frame[50, 50, 1] == 255
    assert frame[50, 50, 2] == 255


def test_paint_dot_does_not_modify_far_pixels():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    paint_dot(frame, cx=50, cy=50, radius=5, blur_sigma=0)
    assert frame[0, 0, 0] == 0  # top-left corner untouched


def test_paint_dot_with_blur_does_not_crash():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    paint_dot(frame, cx=50, cy=50, radius=5, blur_sigma=4)
    # Blur spreads energy — center should still be bright-ish
    assert frame[50, 50, 0] > 100


def test_paint_dot_clipped_at_edge():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # Should not raise even when dot is partially out of bounds
    paint_dot(frame, cx=0, cy=0, radius=10, blur_sigma=0)
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/test_animator.py -v -k "dot"
```

Expected: FAIL.

- [ ] **Step 3: Implement `paint_dot` in `src/animator.py`**

```python
# ── Dot rendering ─────────────────────────────────────────────────────────────

import cv2
from scipy.ndimage import gaussian_filter


def paint_dot(frame, cx, cy, radius, blur_sigma):
    """Paint a white circle onto frame (uint8 HxWx3) at (cx, cy).

    If blur_sigma > 0, apply Gaussian blur to the dot layer before compositing
    (screen blend) so the dot has a soft halo rather than a hard edge.
    Modifies frame in-place.
    """
    h, w = frame.shape[:2]
    dot_layer = np.zeros((h, w), dtype=np.float32)
    cv2.circle(dot_layer, (int(cx), int(cy)), int(radius), color=255.0, thickness=-1)

    if blur_sigma > 0:
        dot_layer = gaussian_filter(dot_layer, sigma=blur_sigma)

    for c in range(3):
        ch = frame[:, :, c].astype(np.float32)
        # Screen blend: result = 255 - (255 - frame) * (255 - dot) / 255
        blended = 255 - (255 - ch) * (255 - dot_layer) / 255
        frame[:, :, c] = np.clip(blended, 0, 255).astype(np.uint8)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_animator.py -v -k "dot"
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/animator.py tests/test_animator.py
git commit -m "feat: add paint_dot for animation cursor rendering"
```

---

## Task 6: Animation Typography

**Files:**
- Modify: `src/animator.py`
- Modify: `tests/test_animator.py`

`render_animation_typography` replaces `render_typography` for animation. It takes explicit scalar values instead of a run list, so it can be called with live-updating stats.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_animator.py`:

```python
from PIL import Image
from src.animator import render_animation_typography


def test_render_animation_typography_returns_image():
    img = Image.new("RGB", (1080, 1350), (0, 0, 0))
    result = render_animation_typography(
        img,
        month_year="Mar 2019",
        run_count=42,
        total_miles_floor=312,
        font_path="data/fonts/Montserrat-SemiBold.ttf",
        scale=1.0,
    )
    assert isinstance(result, Image.Image)
    assert result.size == (1080, 1350)


def test_render_animation_typography_modifies_pixels():
    img = Image.new("RGB", (1080, 1350), (0, 0, 0))
    before = list(img.getdata())
    result = render_animation_typography(
        img, "Jan 2020", 1, 0,
        font_path="data/fonts/Montserrat-SemiBold.ttf",
        scale=1.0,
    )
    after = list(result.getdata())
    assert before != after  # some pixels changed (text was drawn)
```

- [ ] **Step 2: Ensure font exists**

```bash
.venv/bin/python -c "from src.typography import _download_font; from config import MAP_FONT_PATH, MAP_FONT_URL; _download_font(MAP_FONT_PATH, MAP_FONT_URL); print('font ok')"
```

Expected: `font ok` (downloads if needed).

- [ ] **Step 3: Run to verify failure**

```bash
.venv/bin/pytest tests/test_animator.py -v -k "typography"
```

Expected: FAIL.

- [ ] **Step 4: Implement `render_animation_typography` in `src/animator.py`**

```python
# ── Typography ────────────────────────────────────────────────────────────────

from PIL import Image, ImageDraw
from src.typography import _load_font


def render_animation_typography(img, month_year, run_count, total_miles_floor,
                                 font_path, scale=1.0):
    """Render live animation stats onto img (PIL Image) in the same bottom-right
    position as render_typography.

    Lines (top to bottom):
        month_year    e.g. "Mar 2019"
        run_count     e.g. "42 runs"
        total_miles   e.g. "312 mi"

    Returns the modified image.
    """
    w, h = img.size
    font_size = int(max(10, h // 40) * scale)
    margin = int(max(10, h // 25) * scale)
    shadow_offset = int(max(2, h // 1800) * scale)
    line_gap = int(max(8, h // 120) * scale)

    draw = ImageDraw.Draw(img)
    font = _load_font(font_path, font_size)
    shadow = (0, 0, 0)
    text_color = (255, 255, 255)

    lines = [
        month_year,
        f"{run_count:,} runs",
        f"{total_miles_floor} mi",
    ]

    y = h - margin
    for text in reversed(lines):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = w - margin - text_w
        y -= text_h
        draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow)
        draw.text((x, y), text, font=font, fill=text_color)
        y -= line_gap

    return img
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/test_animator.py -v -k "typography"
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/animator.py tests/test_animator.py
git commit -m "feat: add render_animation_typography for live stats overlay"
```

---

## Task 7: ffmpeg Pipe

**Files:**
- Modify: `src/animator.py`
- Modify: `tests/test_animator.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_animator.py`:

```python
from unittest.mock import patch, MagicMock
from src.animator import check_ffmpeg, open_ffmpeg_pipe


def test_check_ffmpeg_passes_when_available():
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        check_ffmpeg()  # should not raise


def test_check_ffmpeg_exits_when_missing():
    with patch("shutil.which", return_value=None):
        with pytest.raises(SystemExit):
            check_ffmpeg()


def test_open_ffmpeg_pipe_uses_correct_args():
    mock_proc = MagicMock()
    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        proc = open_ffmpeg_pipe("out.mp4", width=1080, height=1350, fps=60)
        call_args = mock_popen.call_args[0][0]
        assert "ffmpeg" in call_args[0]
        assert "1080x1350" in call_args
        assert "60" in call_args
        assert "out.mp4" in call_args
        assert proc is mock_proc
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/test_animator.py -v -k "ffmpeg"
```

Expected: FAIL.

- [ ] **Step 3: Implement `check_ffmpeg` and `open_ffmpeg_pipe` in `src/animator.py`**

```python
# ── ffmpeg pipe ───────────────────────────────────────────────────────────────

import shutil
import subprocess


def check_ffmpeg():
    """Exit with a clear error if ffmpeg is not on PATH."""
    if shutil.which("ffmpeg") is None:
        sys.exit(
            "ERROR: ffmpeg not found on PATH. Install it (e.g. `brew install ffmpeg`) "
            "and re-run animate.py."
        )


def open_ffmpeg_pipe(output_path, width, height, fps):
    """Open an ffmpeg subprocess that reads raw RGB frames from stdin.

    Returns the Popen object. Write frames as raw bytes to proc.stdin.
    Call proc.stdin.close() and proc.wait() when done.
    """
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "pipe:0",
        "-vcodec", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        output_path,
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_animator.py -v -k "ffmpeg"
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/animator.py tests/test_animator.py
git commit -m "feat: add check_ffmpeg and open_ffmpeg_pipe"
```

---

## Task 8: Animation Loop

**Files:**
- Modify: `src/animator.py`
- Modify: `tests/test_animator.py`

The main loop: pre-pass → get `final_log_max` and `final_canvas_max` → animation pass. This task also adds the unit tests for monotonic mileage, run count tracking, and <2-point run handling.

- [ ] **Step 1: Write failing unit tests**

Append to `tests/test_animator.py`:

```python
from src.animator import compute_total_frames, build_run_pixel_coords


def _make_renderer(width=200, height=250):
    from src.renderer import StravaRenderer
    return StravaRenderer(width=width, height=height)


def _make_run(coords):
    return {
        "id": 1,
        "coords": coords,
        "start_date": "2020-03-15T08:00:00Z",
        "distance": 5000.0,
        "average_speed": 3.0,
        "total_elevation_gain": 50.0,
    }


def test_compute_total_frames_proportional_to_distance():
    renderer = _make_renderer()
    run_a = _make_run([(37.77, -122.45), (37.78, -122.45)])
    run_b = _make_run([(37.77, -122.45), (37.77, -122.44)])  # similar length
    frames_a = compute_total_frames([run_a], renderer, drawing_speed=10)
    frames_b = compute_total_frames([run_b], renderer, drawing_speed=10)
    # Both should produce some frames; difference < 50% of mean
    assert frames_a > 0
    assert frames_b > 0


def test_compute_total_frames_zero_for_single_point_run():
    renderer = _make_renderer()
    run = _make_run([(37.77, -122.45)])  # only one point, no segments
    frames = compute_total_frames([run], renderer, drawing_speed=10)
    assert frames == 0


def test_build_run_pixel_coords_single_point_run_returns_one_point():
    renderer = _make_renderer()
    run = _make_run([(37.77, -122.45)])
    px = build_run_pixel_coords(run, renderer)
    assert len(px) == 1  # no segments — caller must guard len < 2


def test_build_run_pixel_coords_returns_list_of_tuples():
    renderer = _make_renderer()
    run = _make_run([(37.77, -122.45), (37.78, -122.44)])
    px = build_run_pixel_coords(run, renderer)
    assert len(px) == 2
    assert all(isinstance(p, tuple) and len(p) == 2 for p in px)
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/test_animator.py -v -k "total_frames or pixel_coords"
```

Expected: FAIL.

- [ ] **Step 3: Implement helpers in `src/animator.py`**

```python
# ── Animation loop helpers ────────────────────────────────────────────────────

def build_run_pixel_coords(run, renderer):
    """Project a run's geo coords to pixel coords using renderer.project()."""
    return [renderer.project(lat, lng) for lat, lng in run["coords"]]


def _path_length_px(pixel_coords):
    """Total Euclidean length of a pixel-space polyline."""
    total = 0.0
    for i in range(len(pixel_coords) - 1):
        total += math.hypot(
            pixel_coords[i + 1][0] - pixel_coords[i][0],
            pixel_coords[i + 1][1] - pixel_coords[i][1],
        )
    return total


def compute_total_frames(runs, renderer, drawing_speed):
    """Estimate total animation frames (excluding hold) for all runs."""
    total_px = 0.0
    for run in runs:
        if len(run["coords"]) < 2:
            continue
        px_coords = build_run_pixel_coords(run, renderer)
        total_px += _path_length_px(px_coords)
    return int(total_px / drawing_speed) if drawing_speed > 0 else 0
```

- [ ] **Step 4: Run unit tests**

```bash
.venv/bin/pytest tests/test_animator.py -v -k "total_frames or pixel_coords"
```

Expected: all PASS.

- [ ] **Step 5: Implement the main `run_animation` function in `src/animator.py`**

```python
def run_animation(runs, output_path, config):
    """Run the full animation pipeline.

    Args:
        runs:        list of run dicts from decode_runs()
        output_path: path to write the MP4
        config:      module with animation config knobs (typically the active config module)
    """
    import os
    from datetime import datetime
    from src.renderer import StravaRenderer
    from src.tiles import fetch_map_tile
    from src.typography import render_legend, _download_font
    from config import (
        ROUTE_COLOR_RAMP, BG_COLOR, GAMMA,
        ROUTE_LINE_THICKNESS,
        MAP_TILE_URL, MAP_TILE_CACHE, MAP_TILE_OPACITY, MAP_TILE_BRIGHTNESS,
        MAP_FONT_PATH, MAP_FONT_URL,
        CANVAS_HEIGHT_PX, TYPOGRAPHY_SCALE, LEGEND_POSITION, LEGEND_WIDTH_SCALE,
        TYPOGRAPHY_WIDTH_SCALE, SHOW_ELEVATION, LEGEND_Y_OFFSET,
        CANVAS_ROTATION_DEGREES,
    )

    fps = config.ANIMATION_FPS
    drawing_speed = config.ANIMATION_DRAWING_SPEED
    dot_radius = config.ANIMATION_DOT_RADIUS
    dot_blur = config.ANIMATION_DOT_BLUR
    hold_seconds = config.ANIMATION_HOLD_SECONDS
    out_w, out_h = config.ANIMATION_OUTPUT_RESOLUTION

    # Guard: rotation not supported
    if CANVAS_ROTATION_DEGREES != 0:
        sys.exit(
            f"ERROR: animate.py does not support CANVAS_ROTATION_DEGREES={CANVAS_ROTATION_DEGREES}. "
            "Add CANVAS_ROTATION_DEGREES = 0 to your city config override."
        )

    # Guard: ffmpeg
    check_ffmpeg()

    # Sort runs chronologically
    runs = sorted(runs, key=lambda r: r["start_date"])

    # ── Pre-pass ──────────────────────────────────────────────────────────────
    print("Pre-pass: rasterizing all runs to compute normalization anchor...")
    pre_renderer = StravaRenderer(width=out_w, height=out_h)
    pre_renderer.rasterize_all(runs)
    final_canvas_max = float(pre_renderer.canvas.max())
    if final_canvas_max == 0:
        sys.exit("ERROR: No qualifying runs found after filtering. Nothing to animate.")
    final_log_max = float(np.log1p(pre_renderer.canvas).max())
    del pre_renderer

    # ── Duration estimate ─────────────────────────────────────────────────────
    anim_renderer = StravaRenderer(width=out_w, height=out_h)
    total_frames = compute_total_frames(runs, anim_renderer, drawing_speed)
    hold_frames = int(hold_seconds * fps)
    total_duration_s = (total_frames + hold_frames) / fps
    print(f"Expected duration: {total_duration_s:.0f}s ({total_frames + hold_frames} frames at {fps}fps). "
          f"Adjust ANIMATION_DRAWING_SPEED to change.")

    # ── Map tile ──────────────────────────────────────────────────────────────
    print("Fetching map tile...")
    _download_font(MAP_FONT_PATH, MAP_FONT_URL)
    cache_path = MAP_TILE_CACHE.replace(".png", "-anim.png")
    tile = fetch_map_tile(
        bounds=anim_renderer.bounds,
        zoom=15,
        cache_path=cache_path,
        target_size=(out_w, out_h),
        url_template=MAP_TILE_URL,
    )
    if MAP_TILE_BRIGHTNESS != 1.0:
        from PIL import ImageEnhance
        tile = ImageEnhance.Brightness(tile).enhance(MAP_TILE_BRIGHTNESS)
    map_arr = np.array(tile.resize((out_w, out_h)), dtype=np.float32)

    # ── Pre-render legend ────────────────────────────────────────────────────
    anim_scale = (out_h / CANVAS_HEIGHT_PX) * TYPOGRAPHY_SCALE
    legend_base = Image.new("RGB", (out_w, out_h), (0, 0, 0))
    legend_img = render_legend(
        legend_base, color_ramp=ROUTE_COLOR_RAMP, font_path=MAP_FONT_PATH,
        gamma=GAMMA, canvas_max_val=final_canvas_max,
        scale=anim_scale, position=LEGEND_POSITION,
        width_scale=LEGEND_WIDTH_SCALE,
        text_width_scale=TYPOGRAPHY_WIDTH_SCALE,
        show_elevation=SHOW_ELEVATION,
        y_offset=LEGEND_Y_OFFSET,
    )
    legend_arr = np.array(legend_img, dtype=np.float32)

    # ── Animation pass ────────────────────────────────────────────────────────
    print(f"Rendering {len(runs)} runs → {output_path}")
    proc = open_ffmpeg_pipe(output_path, out_w, out_h, fps)
    accumulation = anim_renderer.canvas  # float32, starts at zero

    total_miles = 0.0
    run_count = 0
    frame_count = 0
    final_frame_bytes = None

    try:
        for run in runs:
            geo_coords = run["coords"]
            if len(geo_coords) < 2:
                run_count += 1
                continue

            px_coords = build_run_pixel_coords(run, anim_renderer)
            run_count += 1
            month_year = _format_month_year(run["start_date"])

            seg_idx, t = 0, 0.0

            while True:
                new_seg, new_t, drawn = advance_cursor(px_coords, seg_idx, t, drawing_speed)

                # Draw segments onto accumulation canvas
                buf = np.zeros((out_h, out_w), dtype=np.float32)
                for (x0, y0), (x1, y1) in drawn:
                    cv2.line(buf, (int(x0), int(y0)), (int(x1), int(y1)),
                             color=1.0, thickness=ROUTE_LINE_THICKNESS, lineType=cv2.LINE_AA)
                accumulation += buf

                # Mileage for this frame
                if drawn:
                    frame_miles = compute_frame_miles(geo_coords, seg_idx, t, new_seg, new_t)
                    total_miles += frame_miles

                # Build output frame
                frame_rgb = canvas_to_rgb(accumulation, final_log_max, GAMMA, ROUTE_COLOR_RAMP, BG_COLOR)
                frame_f = frame_rgb.astype(np.float32)

                # Composite map tile (screen blend)
                bg_f = np.zeros_like(frame_f)
                for c in range(3):
                    bg_c = map_arr[:, :, c] * MAP_TILE_OPACITY
                    bg_f[:, :, c] = bg_c
                result = 255 - (255 - bg_f) * (255 - frame_f) / 255
                frame_rgb = np.clip(result, 0, 255).astype(np.uint8)

                # Composite static legend (screen blend)
                frame_f2 = frame_rgb.astype(np.float32)
                result2 = 255 - (255 - frame_f2) * (255 - legend_arr) / 255
                frame_rgb = np.clip(result2, 0, 255).astype(np.uint8)

                # Paint cursor dot at tip
                if drawn:
                    tip_x, tip_y = drawn[-1][1]
                    paint_dot(frame_rgb, tip_x, tip_y, dot_radius, dot_blur)

                # Stamp live typography
                pil_frame = Image.fromarray(frame_rgb, mode="RGB")
                pil_frame = render_animation_typography(
                    pil_frame, month_year, run_count, int(math.floor(total_miles)),
                    MAP_FONT_PATH, scale=anim_scale,
                )
                frame_rgb = np.array(pil_frame)

                # Write frame
                final_frame_bytes = frame_rgb.tobytes()
                proc.stdin.write(final_frame_bytes)
                frame_count += 1

                seg_idx, t = new_seg, new_t
                if seg_idx >= len(px_coords) - 1 and t >= 1.0:
                    break

        # Hold frames
        if final_frame_bytes and hold_frames > 0:
            print(f"Writing {hold_frames} hold frames...")
            for _ in range(hold_frames):
                proc.stdin.write(final_frame_bytes)

    finally:
        proc.stdin.close()
        proc.wait()

    print(f"Done. {frame_count + hold_frames} frames → {output_path}")


def _format_month_year(start_date):
    """Convert ISO date string to 'Mon YYYY' e.g. 'Mar 2019'."""
    from datetime import datetime
    try:
        dt = datetime.strptime(start_date[:10], "%Y-%m-%d")
        return dt.strftime("%b %Y")
    except ValueError:
        return start_date[:7]
```

- [ ] **Step 6: Run all tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all existing tests PASS, new tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/animator.py tests/test_animator.py
git commit -m "feat: add animation loop — pre-pass, frame rendering, ffmpeg output"
```

---

## Task 9: CLI Entry Point (`animate.py`)

**Files:**
- Create: `animate.py`

Mirrors the structure of `export.py` — config injection first, then pipeline wiring.

- [ ] **Step 1: Create `animate.py`**

```python
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

# ── Config injection (same pattern as export.py) ──────────────────────────────
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
from config import OUTPUT_DIR, ANIMATION_OUTPUT_RESOLUTION, ANIMATION_FPS, ANIMATION_HOLD_SECONDS


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
        ANIMATION_DOT_RADIUS = _cfg.ANIMATION_DOT_RADIUS
        ANIMATION_DOT_BLUR = _cfg.ANIMATION_DOT_BLUR
        ANIMATION_HOLD_SECONDS = _cfg.ANIMATION_HOLD_SECONDS
        ANIMATION_OUTPUT_RESOLUTION = _cfg.ANIMATION_OUTPUT_RESOLUTION

    if args.preview:
        w, h = _cfg.ANIMATION_OUTPUT_RESOLUTION
        AnimConfig.ANIMATION_OUTPUT_RESOLUTION = (w // 2, h // 2)
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
```

- [ ] **Step 2: Verify syntax**

```bash
.venv/bin/python -m py_compile animate.py && echo "syntax ok"
```

Expected: `syntax ok`

- [ ] **Step 3: Commit**

```bash
git add animate.py
git commit -m "feat: add animate.py CLI entry point"
```

---

## Task 10: Smoke Test

- [ ] **Step 1: Run all unit tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 2: Run preview animation**

```bash
.venv/bin/python animate.py --preview --output /tmp/test-animation.mp4
```

Expected: completes without error, prints `Done. X frames → /tmp/test-animation.mp4`.

- [ ] **Step 3: Verify output with ffprobe**

```bash
ffprobe -v quiet -print_format json -show_format /tmp/test-animation.mp4 | python3 -c "import json,sys; d=json.load(sys.stdin); dur=float(d['format']['duration']); print(f'Duration: {dur:.1f}s'); assert dur > 0, 'zero duration!'; print('ok')"
```

Expected: prints `Duration: Xs` and `ok`.

- [ ] **Step 4: Final commit**

```bash
git add -A
git status  # verify nothing unexpected
git commit -m "feat: animation feature complete — timelapse MP4 from Strava runs"
```
