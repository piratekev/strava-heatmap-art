# Animation branch status

Reviewed 2026-11-15 against local `main` at `d3afbd2`.

## Recommendation

**Do not merge `feature/animation` into `main` yet.** The latest main changes
are integrated, poster compatibility is preserved, and both video modes encode
successfully with valid inputs. Animation density, encoder failures, attribution,
and configuration integration still need fixes.

This integration deliberately documents the existing animation defects rather
than silently changing the feature's rendering behavior.

## Differences from main

- `animate.py` adds sequential and parallel H.264 MP4 export via ffmpeg.
- `src/animator.py` adds projected-route traversal, fixed pre-pass normalization,
  per-frame density/color effects, cursor/tracer dots, live stats, and encoding.
- `config.py` adds animation timing, resolution, and dot controls. Main's green
  SF palette and NYC-specific styling remain intact.
- `render.py` is the canonical poster CLI. `export.py` forwards to it, preserving
  main's existing command line rather than deleting it.
- Main's full-history Strava reconciliation, OAuth fixes, Garmin support,
  safe/resumable map caching, poster attribution, error handling, and isolated
  tests are retained. The animation fetch path does not yet use all of these
  shared entry-point behaviors.
- The original animation design and implementation plan are marked historical.
  Current usage is documented in [README](../README.md#animation-animatepy)
  and [CLAUDE.md](../CLAUDE.md).

## Before merging

### [P1] Preserve overlapping parallel route contributions

In [the parallel drawing loop](../src/animator.py#L745), all routes draw `1`
into one shared frame buffer. Overlaps overwrite one another instead of adding
each run's contribution. A synthetic check with two identical routes produced
exactly the same final accumulation as one route: peak `1`, sum `18` in both
cases. Use separate per-run masks/contributions before combining them.

### [P1] Propagate encoder failures instead of reporting success

Both renderers discard [ffmpeg's exit status](../src/animator.py#L585).
A real CLI/ffmpeg check at 16×20, 1 fps, targeting a nonexistent parent directory
returned **exit code 0**, printed `Done.`, and created **no video**.
Check encoder status and output success before reporting completion.

Also ensure cleanup always waits for ffmpeg: a `BrokenPipeError` during
`stdin.close()` currently skips the following `wait()` in both modes.

### [P2] Make density independent of frame boundaries and drawing speed

[Sequential accumulation](../src/animator.py#L535) repeatedly adds inclusive
segment endpoints as new per-frame masks. Parallel drawing has the same boundary
problem. With the same two routes, changing sequential drawing speed from
160 to 5 px/frame changed the final sum from `36` to `47` and peak from `2` to `4`.
Track each run's already-contributed pixels so splitting it across frames does
not create extra visits.

### [P2] Align the normalization pre-pass with animation rasterization

The [pre-pass](../src/animator.py#L403) uses the poster's unscaled strokes and
density-bonus pass, while animation uses scaled base strokes without that pass.
In the same 32×40 synthetic case, pre-pass peak/sum were `4` / `922`, versus
sequential fast-animation `2` / `36`. Even after fixing frame-boundary and
parallel overlap errors, the anchor must describe the canvas actually produced
by the animation, not a differently rasterized poster.

### [P2] Carry provider attribution into the video

Both animation modes require a map, but neither frame builder burns in
`MAP_ATTRIBUTION`, and [the encoder](../src/animator.py#L270) sets no copyright
metadata. Reuse the shared attribution renderer so credit survives standalone
MP4 sharing, not just publication captions.

### [P2] Honor Garmin source selection in animation fetches

[`animate.py --fetch`](../animate.py#L48) always constructs a Strava client.
An isolated Garmin-configured invocation failed asking for `STRAVA_CLIENT_ID`.
Delegate through `fetch_from_source(FETCH_SOURCE)`, as `render.py` does.
Garmin-populated caches already animate without `--fetch`.

### [P2] Forward dot brightness from the active configuration

[`AnimConfig`](../animate.py#L66) omits `ANIMATION_DOT_BRIGHTNESS`.
Capturing the actual config delivered by the CLI confirmed the attribute is
missing, so the renderer uses `1.0` rather than the configured default `2.0`.
Derive effective configuration from the active module or forward every setting.

### [P2] Apply configured map opacity in parallel mode

The [parallel compositor](../src/animator.py#L717) ignores `MAP_TILE_OPACITY`.
With opacity zero and a synthetic `(40, 40, 40)` map, an untouched opening-frame
pixel remained `(40, 40, 40)` instead of black. Share the poster/sequential
compositing semantics.

### [P2] Validate animation settings before starting the encoder

A zero slow speed stalls the first run indefinitely. An instrumented CLI check
observed three consecutive unchanged cursor states with zero budget before the
probe intentionally stopped rendering. Reject nonpositive fast/slow speeds,
FPS, drawing-frame counts, and invalid/odd output dimensions before expensive
preprocessing. Final holds may legitimately be zero.

### [P2] Create custom output parents

[`--output new-directory/movie.mp4`](../animate.py#L86) never creates its
parent. Create the selected parent directory, matching the poster CLI.
The missing-directory encoder failure above is one concrete consequence.

## Smaller verified gaps

- **[P3] Finish parallel endpoints explicitly.** Ten one-pixel advances along
  `(0, 0) → (10, 0)` leave fractional progress `0.9999999999999999`, so integer
  rasterization ends at pixel `9` before the fixed drawing loop stops.
- **[P3] Display stats for a one-frame hold.** The only frame uses
  `alpha = 0 / max(0, 1) = 0`, making final stats invisible. See the
  [fade loop](../src/animator.py#L774).
- **[P3] Explain missing caches cleanly.** A fresh-cache animation invocation
  raises `FileNotFoundError` instead of an actionable CLI error.
- **[P3, source-reviewed] Preserve mileage for collapsed GPS segments.**
  Sequential mileage updates are conditioned on `drawn`; geographic motion
  that projects to identical integer pixels can advance the cursor without
  contributing its distance.
- **[P3] Correct progress reporting.** The sequential duration estimate omits
  speed ramps, final deceleration, opening/fade frames, and per-run rounding.
  Parallel `Done.` frame counts omit the opening frame. These logs must not
  be used as exact timing/frame validators.
- Two existing animator tests emit Pillow `getdata()` deprecation warnings.

There is also duplicated scene preparation, density/color mapping, dot/text
layout, distance constants, and mode-specific basemap cache naming. Consolidate
these where it fixes the drift above; cosmetic restructuring alone is not a
merge blocker.

## Validation and limits

- Full suite after integration: **187 passed**. This includes both poster CLI
  names, SF/NYC previews, and the existing animation unit tests.
- New `tests/test_animation_cli.py` uses real ffmpeg/ffprobe with synthetic
  activities and offline map responses. Both modes produced fully decodable
  80×100 H.264/yuv420p videos. The parallel fixture contains five frames:
  opening + two drawing + two hold frames.
- The isolated reproductions above use synthetic activity records and maps;
  no live Strava/Garmin requests or private activity exports were needed.
- Real `.env`, activity/cache metadata, and the preexisting untracked Amsterdam
  map image were checked for byte-for-byte preservation during testing.
- Full-duration 1080×1350 animation over the private real cache was **not**
  benchmarked or visually approved in this review. Small smoke videos do not
  prove full-history performance or final-poster parity.
- Fresh CARTO downloads can require an API key. Placeholder images are rejected
  by the merged tile loader. Animation still has no mapless fallback, hardcodes
  zoom 15, and rejects rotated configurations (including the bundled NYC preset).
  These are documented limitations, not claims of new support.

## Follow-up acceptance checks

1. Compare per-run accumulation and completed frames across drawing speeds and
   FPS values, including coincident routes, retracing, zero-length segments,
   and repeated endpoints.
2. Compare the completed animation against an independently specified
   same-resolution static reference with matching effects and normalization.
3. Exercise both modes through the real CLI for Garmin dispatch, nested output,
   ignored settings, missing assets, encoder failure, and cancellation.
4. Assert visible video attribution and correct final stats for normal, zero,
   and one-frame holds.
5. Benchmark a complete real-history render with warm/cold asset caches before
   publishing any duration or resource claims.
