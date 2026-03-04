# Neon Glow Design

**Date:** 2026-03-04
**Goal:** Fix map grid visibility, font download, typography scaling fallback, and add neon sign glow effect to route rendering.

---

## 1. Bug: Map Grid Invisible

**Root cause:** `MAP_TILE_OPACITY = 0.35` — blending a dark CARTO tile onto pure black at 35% produces a nearly-black result; street lines don't survive the screen blend with routes.

**Fix:** Raise `MAP_TILE_OPACITY` from `0.35` → `0.55` in `config.py`.

---

## 2. Bug: Font Download 404

**Root cause:** `MAP_FONT_URL` points to a GitHub raw URL that no longer resolves via `urllib.request.urlretrieve`.

**Fix:** Replace with jsDelivr CDN mirror:
```
https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/montserrat/static/Montserrat-Light.ttf
```

---

## 3. Bug: Typography Tiny (Font Fallback Ignores Size)

**Root cause:** `_load_font` fallback calls `ImageFont.load_default()` with no size argument — always returns the bitmap pixel font regardless of computed scale. Since the font download always fails, this fallback is always hit.

**Fix:** Use `ImageFont.load_default(size=size)` in the except block. Pillow 12 supports sized default fonts.

---

## 4. Feature: Neon Sign Glow

**Aesthetic target:** Neon tube — near-white blown-out core on peak-density streets, wide pink/magenta halo radiating into the black background.

### Color Ramp

4 stops (up from 3), designed as a neon tube cross-section:

| stop | norm | RGB | role |
|------|------|-----|------|
| 0 | 0.0 | `[20, 50, 255]` | rarely-run streets → deep blue |
| 1 | 0.5 | `[220, 0, 220]` | moderate density → saturated magenta |
| 2 | 0.85 | `[255, 60, 255]` | heavy corridors → electric pink |
| 3 | 1.0 | `[255, 220, 255]` | peak density → blown-out white-pink |

### Glow Pass (additive bloom)

Added to `StravaRenderer.to_image()` after the existing bloom step, before vignette:

1. Apply wide gaussian blur to the route color layer: `sigma = canvas_height / 40` (~135px at 5400, ~13px at 540 preview)
2. Screen-blend the blurred layer back onto the sharp core:
   `result = 1 - (1 - core) * (1 - glow * glow_strength)`
3. Controlled by new params: `glow=True`, `glow_strength=1.0`

The existing tight bloom (sigma 4) is kept — it sharpens stroke edges. The new wide glow pass adds the ambient neon halo. Together: crisp bright core + wide pink light spill.

### CLI

Add `--no-glow` flag to `export.py` (mirrors `--no-bloom`, `--no-grain` pattern).

---

## Affected Files

| File | Change |
|------|--------|
| `config.py` | `MAP_TILE_OPACITY` 0.35→0.55; update `MAP_FONT_URL`; update `ROUTE_COLOR_RAMP` (4 stops) |
| `src/typography.py` | `_load_font` fallback: `ImageFont.load_default(size=size)` |
| `src/renderer.py` | Add glow pass to `to_image()` |
| `export.py` | Add `--no-glow` CLI flag |
| `tests/test_renderer.py` | Add glow test; update color ramp tests for new stops |
