# Canvas Bounds Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix geographic distortion in the 4560×5700 canvas by correcting SF_BOUNDS so lng and lat ranges match the 4:5 pixel aspect ratio exactly.

**Architecture:** Single config change — update four coordinate values in `SF_BOUNDS`. The renderer and tile fetcher both derive from these values, so alignment is automatic. No code changes needed.

**Tech Stack:** Python, pytest

---

### Task 1: Fix SF_BOUNDS

**Files:**
- Modify: `config.py:2-7`
- Test: `tests/test_renderer.py`

**Step 1: Run existing projection tests as baseline**

```bash
.venv/bin/pytest tests/test_renderer.py::test_project_sf_center_to_canvas_center tests/test_renderer.py::test_project_top_left_corner tests/test_renderer.py::test_project_top_right_corner tests/test_renderer.py::test_sf_bounds_excludes_treasure_island -v
```

Expected: All 4 PASS.

**Step 2: Write a failing test that verifies the Mercator aspect ratio**

Add this test to `tests/test_renderer.py`:

```python
def test_sf_bounds_aspect_ratio_matches_canvas():
    """SF_BOUNDS Mercator aspect ratio must match canvas pixel ratio (4:5 = 0.8)."""
    import math
    from config import SF_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX

    lng_range_rad = (SF_BOUNDS["lng_max"] - SF_BOUNDS["lng_min"]) * math.pi / 180
    merc_max = math.asinh(math.tan(math.radians(SF_BOUNDS["lat_max"])))
    merc_min = math.asinh(math.tan(math.radians(SF_BOUNDS["lat_min"])))
    merc_range = merc_max - merc_min

    actual_ratio = lng_range_rad / merc_range
    target_ratio = CANVAS_WIDTH_PX / CANVAS_HEIGHT_PX

    assert abs(actual_ratio - target_ratio) < 0.005, (
        f"Mercator aspect ratio {actual_ratio:.4f} does not match "
        f"canvas ratio {target_ratio:.4f} (tolerance 0.005)"
    )
```

**Step 3: Run the new test to confirm it fails**

```bash
.venv/bin/pytest tests/test_renderer.py::test_sf_bounds_aspect_ratio_matches_canvas -v
```

Expected: FAIL — current ratio is ~0.918, target is 0.800.

**Step 4: Update SF_BOUNDS in `config.py`**

Replace:

```python
SF_BOUNDS = {
    "lat_min": 37.7080,   # SF south city line (Geneva Ave / Daly City border)
    "lat_max": 37.8330,   # just north of GG Bridge road
    "lng_min": -122.5204, # shifted +0.0066° east (225px at 4960px canvas width)
    "lng_max": -122.3754, # shifted +0.0066° east
}
```

With:

```python
SF_BOUNDS = {
    "lat_min": 37.7068,   # 50px south of previous (extended for 4:5 aspect ratio)
    "lat_max": 37.8359,   # 124px north of previous (extended for 4:5 aspect ratio)
    "lng_min": -122.5146, # proportionally trimmed: 0.1333° range for 4560px canvas
    "lng_max": -122.3812, # proportionally trimmed: same pixel density as original 4960px
}
```

**Step 5: Run the aspect ratio test to confirm it passes**

```bash
.venv/bin/pytest tests/test_renderer.py::test_sf_bounds_aspect_ratio_matches_canvas -v
```

Expected: PASS — ratio should be ~0.800.

**Step 6: Run the full test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All tests pass.

Note: `test_sf_bounds_excludes_treasure_island` checks that Treasure Island (37.825, -122.370) projects beyond the right canvas edge. With `lng_max = -122.3812`, Treasure Island at lng `-122.370` is east of the new boundary and still projects to x > 540. ✓

**Step 7: Commit**

```bash
git add config.py tests/test_renderer.py
git commit -m "fix: correct SF_BOUNDS for undistorted 4560x5700 canvas

Lng range trimmed proportionally (4960→4560px, same pixel density).
Lat range extended +50px south / +124px north so Mercator aspect
ratio matches canvas 4:5 ratio exactly (verified: 0.800).

Previously the map was stretched ~15% vertically."
```
