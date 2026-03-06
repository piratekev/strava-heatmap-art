# Canvas Bounds Fix Design

**Goal:** Fix geographic distortion introduced by changing the canvas from 4960×5400 to 4560×5700. Two bugs: longitude not narrowed proportionally, latitude not extended for correct 4:5 aspect ratio.

---

## Problem

For undistorted Mercator rendering: `lng_range_rad / merc_range = canvas_width / canvas_height`

- Current ratio: `0.002531 / 0.002820 = 0.918` (tuned for 4960×5400)
- Target ratio: `4560 / 5700 = 0.800`
- Result: ~15% vertical stretch

---

## Fix — Update `SF_BOUNDS` in `config.py`

**Longitude** — maintain original pixel density (4960px → 4560px, proportionally narrowed):
- `lng_range_new = 0.145° × (4560/4960) = 0.1333°`, centered at `-122.4479°`
- `lng_min = -122.5146`, `lng_max = -122.3812`

**Latitude** — extend to satisfy `merc_range = lng_range_rad / 0.8 = 0.002909`:
- Extra merc needed: `0.002909 − 0.00282 = 0.000089` → 174 pixels total
- Distribute: 50px south, 124px north
- `lat_min: 37.7080 → 37.7068` (−0.0012°)
- `lat_max: 37.8330 → 37.8359` (+0.0029°)

**Verification:** `lng_range_rad / merc_range = 0.002329 / 0.002909 = 0.800` ✓

---

## Changes

Only `config.py` — four coordinate values and their comments.
