# Animation branch status

The P1/P2 defects and smaller gaps identified in the 2026-11-15 review are
fixed on `feature/animation`. Latest local `main` was already integrated;
poster entry points and main's authentication, fetching, and tile hardening
remain intact.

## Completed fixes

| Finding | Repair |
|---|---|
| P1: parallel overlap erased visits | Each run contributes its own coverage; overlapping runs add independently. |
| P1: ffmpeg failures reported success | Check exit status and nonempty output, propagate failure, and reap the process on every exit. |
| P2: density depended on frame boundaries | Rasterize each complete segment once; reveal the union of each run's pixels by first path distance. Retracing and split-frame endpoints do not add visits. |
| P2: incompatible normalization | Compute the fixed anchor from exactly those animation-scaled per-run masks, without the poster's bonus-stroke pass. |
| P2: missing video attribution | Burn `MAP_ATTRIBUTION` into every frame after other overlays, and set MP4 copyright metadata. Small-frame credits wrap instead of clipping whole words. |
| P2: Garmin ignored by `--fetch` | Dispatch through `fetch_from_source(FETCH_SOURCE)`, shared with the poster CLI. |
| P2: dot brightness dropped | Derive effective config from all active settings and override only documented preview values. |
| P2: parallel map opacity ignored | Both modes use one scene compositor honoring `MAP_TILE_OPACITY`. |
| P2: invalid settings could stall or break encoding | Validate positive finite FPS/speeds, even positive integer dimensions, nonnegative dot/hold values, integer ramp/radius, and a positive parallel drawing-frame count before assets/fetching. |
| P2: custom output parents missing | Create selected parents automatically. |
| P3: endpoint rounding | Tolerant cursor completion and explicit fixed-schedule parallel endpoint completion. |
| P3: one-frame hold hid stats | A single hold frame uses full stats opacity. Zero-hold parallel output shows stats on its final drawing frame. |
| P3: missing/empty cache errors | Actionable CLI errors for missing, unreadable, invalid-list, empty, and unmatched caches. |
| P3: inconsistent/lost mileage | Both modes use the same cached-distance prefix totals over all filtered activities. Sequential mileage advances with route progress; short/collapsed routes retain their full cached distance. |
| P3: inaccurate progress counts | Count the sequential rendering schedule itself, including ramps, deceleration, opening, fade, and holds. Parallel counts include opening. |
| Test deprecations | Replace Pillow `getdata()` snapshots with NumPy arrays. |

Both modes now share projection/coverage preparation, normalization, map/legend
compositing, credits, and encoder lifecycle. Animation reuses the shared mileage
constant and composed-map cache naming. Coverage storage is sparse per run,
with temporary masks bounded to the visible route/segment rather than retaining
a full floating-point canvas for every active run.

Merge preparation removes the obsolete Haversine mileage helpers, unused
alternate frame estimator, and copied-loop tests. Single and batched dots share
one blending implementation, preserving brightness-before-alpha semantics.
The scene loads its statistics font once and reuses its completed sequential
background for fade/hold frames, without applying attribution repeatedly.
Tests assert the real entry points' final mileage/count/date population,
intermediate mileage, font loads, and unchanged hold pixels.

Encoding writes a temporary sibling MP4. Only successful completion replaces
the requested destination. Failed writes, failed close/flush, nonzero exit,
empty output, timeout, and cancellation preserve an existing destination and
remove the temporary file. Cancellation during encoder finalization is covered,
not just cancellation while drawing.

## Validation

- **289 tests passed** with `.venv/bin/pytest tests/ -q`, without warnings.
- Density tests compare both modes at 1, 5, and 160 px/frame and 2/10 fps
  against independent full-frame OpenCV masks. They cover coincident routes,
  diagonal segments, retracing, repeated endpoints, and monotonic intermediate
  accumulation. Both final density and normalization anchors agree.
- Sparse rasterization also matches independent full-canvas strokes in 150
  deterministic clipped-route cases across thicknesses 1, 2, 3, 4, and 7.
- Completed frames match an independent same-resolution static renderer with
  the same coverage and optional effects disabled, plus shared attribution.
  This is not a claim of full-poster visual parity.
- Regression tests cover exact endpoint completion, matching cached mileage,
  short/collapsed routes and trailing activities without drawing/fade/hold,
  map opacity, attribution on all frame phases, zero/one/many-frame holds,
  invalid configuration, and reported versus actual frame counts.
- Real CLI tests encode and fully decode sequential/parallel videos and both
  previews using synthetic activities and offline map/font services. They
  verify H.264/yuv420p, dimensions, copyright metadata, nested output creation,
  and exact reported/probed frame counts.
- CLI tests exercise configured Garmin dispatch and preview/brightness
  forwarding without credentials or live requests.
- Real ffmpeg failure and cancellation checks cover both entry points,
  preserving an existing destination and leaving no temporary video or running
  encoder. Unit checks additionally cover close failures, empty output,
  timeouts, and cancellation during close/wait.
- The real `.env`, activity JSON, cache metadata, and preexisting untracked
  Amsterdam map image remained byte-for-byte unchanged.

### Full SF render review

On 2026-11-16, both modes rendered all **680 SF runs** offline from the genuine
cached zoom-15 map, at **1080×1350, 60 fps**, with the then-current rendering
code. Both fully decoded, matched their reported frame counts, and carried
copyright metadata. The user approved their appearance, while requesting
matching mileage. Those original review videos are preserved unchanged.

| Mode | Frames | Video duration | File size | Render wall time |
|---|---:|---:|---:|---:|
| Sequential | 5,318 | 88.633 s | 10.09 MB | 931.09 s |
| Parallel | 961 | 16.017 s | 3.58 MB | 148.37 s |

These are warm-cache observations on this machine, before the mileage/cleanup
change, not portable performance guarantees or measurements of the final
cleanup. No claim of cold-download readiness is made.

After the mileage/cleanup change, fresh processes rendered both modes through
the real CLI's `--preview` path using all 680 cached SF runs. Both final frames
show **680 runs, 4,935 mi**, matching the independently summed cached distances.
Sequential displayed mileage was monotonic from zero. Both outputs fully
decoded as H.264/yuv420p at 540×674/60 fps, with matching reported/probed counts
and copyright metadata:

| Corrected preview | Frames | Video duration | Render wall time |
|---|---:|---:|---:|
| Sequential | 2,788 | 46.467 s | 92.86 s |
| Parallel | 961 | 16.017 s | 28.24 s |

These measure the final cleanup at preview resolution, not an inferred
full-resolution speedup. Original review videos, credentials, activity/cache
metadata, and the preexisting Amsterdam image remained unchanged.

### Cleanup and compatibility review

The committed branch diff against `origin/main` plus the task's unstaged
repairs and regression tests received reuse, quality/provenance, and efficiency
reviews. No additional high-confidence merge blocker was found. The removed
animation helpers existed only on this unmerged branch, not the comparison
base, so no compatibility wrappers remain for them.

Retained helpers have current consumers: sparse coverage/reveal, the shared
scene, exact traversal scheduling, validation, encoder lifecycle, and date/
projection helpers. Poster/live typography and source-specific retry/reconcile
logic remain separate because their contracts differ. The `export.py` alias,
city-config injection/crop hooks, and font fallback preserve interfaces present
on the comparison base. Public CARTO runtime/fixture images remain deliberately
separate for independent validation.

## Remaining limits

These are documented feature/validation limits, not unresolved findings above:

- Rotated city presets (including bundled NYC) and intermediate canvases that
  differ from the requested output dimensions remain unsupported.
- Maps remain mandatory, fixed at zoom 15. There is no mapless animation
  fallback. Fresh CARTO downloads may require an API key; the tile loader
  rejects the known HTTP-200 placeholder.
- Animation uses scaled base strokes and density-expand/hot-bloom effects, not
  the poster's bonus strokes, broad glow, vignette, or grain. Pixel-identical
  full-poster output is not promised.
- The original full-resolution videos precede the mileage/cleanup correction;
  their mileage text is not evidence for the corrected total.
- Very tiny custom resolutions cannot provide readable map credits or stats;
  use the default or normal preview resolution for publishable output.

The [README](../README.md#animation-animatepy) and [developer reference](../CLAUDE.md)
describe current behavior. Records under `docs/superpowers/` remain historical.
