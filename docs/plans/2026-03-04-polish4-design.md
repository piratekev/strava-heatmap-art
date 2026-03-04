# Polish Pass 4 Design

**Date:** 2026-03-04

**Goal:** Four targeted fixes — brighter low-density routes, thicker base lines, east map shift, font download fix.

---

## Changes

### 1. Low-density color — brighter indigo

First color ramp stop: `[100, 80, 255]` → `[150, 100, 255]`.
Same hue, pumped luminosity. Upper stops unchanged.

**File:** `config.py` — `ROUTE_COLOR_RAMP[0]`

---

### 2. Line thickness

`ROUTE_LINE_THICKNESS` 3 → 4. One pixel wider for all routes.
Density expand continues to add proportional extra girth on heavy corridors.

**File:** `config.py` — `ROUTE_LINE_THICKNESS`

---

### 3. Map shift east (+225px)

East side of city was clipped; too much Pacific Ocean visible on the west.
Shift both longitude bounds east by 225px worth of degrees.

**Math:**
- lng range: 0.1450° across 4960px → 0.000029234°/px
- 225px × 0.000029234 = +0.0066°

**New values:**
- `lng_min`: -122.5270 → -122.5204
- `lng_max`: -122.3820 → -122.3754

N/S bounds and canvas size unchanged.

**File:** `config.py` — `SF_BOUNDS`

---

### 4. Font download fix

`urllib.request.urlretrieve` sends no User-Agent header; jsDelivr CDN returns 403.
Fix: use `urllib.request.Request` with `User-Agent: Mozilla/5.0`.

**File:** `src/typography.py` — `_download_font`

---

## Architecture

All changes confined to `config.py` and `src/typography.py`. No new modules.
Existing color ramp tests pass — high-density stops untouched.
Font fix is covered by existing mock-based typography tests.
