# Polish Pass: Bounds, Font, Typography, Brightness

**Goal:** Tighten SF crop, bundle font, fix typography layout, add elevation, boost route and street visibility.

---

## 1. Bounds tightening

Update `SF_BOUNDS` in `config.py`:

```python
SF_BOUNDS = {
    "lat_min": 37.6999,
    "lat_max": 37.8120,   # was 37.8324 — cuts off Marin, top edge near Golden Gate Bridge
    "lng_min": -122.5270,
    "lng_max": -122.3820,  # was -122.3480 — cuts Treasure Island, Embarcadero near right edge
}
```

No other code changes needed.

---

## 2. Bundle font

- Download `Montserrat-Light.ttf` and commit to `data/fonts/Montserrat-Light.ttf`
- `_download_font()` stays as a no-op when file already exists (no behavior change)
- `MAP_FONT_URL` constant kept for reference / fresh installs
- Em-dash (`\u2013`) renders correctly with bundled TTF; PIL default font fallback uses ` - `

---

## 3. Typography

**Changes to `src/typography.py`:**

- Text color: `(255, 255, 255)` white (was warm yellow `(255, 240, 180)`)
- Line order top-to-bottom: year range (large) → run count → distance (mi) → elevation (ft)
- Line spacing: `h // 120` gap (was `h // 450` — lines were overlapping)
- New elevation line: sum `total_elevation_gain` (meters × 3.28084) across SF runs, format as `"12,345 ft"`, use `font_small`

**Data:** `total_elevation_gain` is already present in `data/activities.json` — no re-fetch needed.

---

## 4. Streets + route brightness

**`config.py`:**
- `MAP_TILE_OPACITY`: `0.55` → `0.70` (streets more visible; screen-blend prevents over-brightening)
- Ramp floor: deep-blue stop `[20, 50, 255]` → `[60, 80, 255]` (quiet streets visible instead of near-black)

**`src/renderer.py`:**
- Gamma curve: `norm = norm ** 0.7` after normalization, before color ramp (lifts all routes uniformly)

---

## Files changed

| File | Change |
|------|--------|
| `config.py` | Bounds, opacity, ramp floor |
| `src/renderer.py` | Gamma curve in `to_image()` |
| `src/typography.py` | Color, layout, elevation line |
| `data/fonts/Montserrat-Light.ttf` | Bundled font (new file) |
| `tests/test_typography.py` | Test for elevation line |
| `tests/test_renderer.py` | Test for gamma brightening |
