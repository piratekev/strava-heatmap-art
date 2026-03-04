# Strava Heatmap Poster Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python pipeline that fetches all SF running routes from Strava, caches them locally, and renders a print-quality (18×24" @ 300 DPI) heatmap poster with bloom, vignette, and film grain effects.

**Architecture:** Modular pipeline — `fetcher.py` handles Strava API + incremental caching, `processor.py` filters/decodes routes, `renderer.py` rasterizes onto a numpy canvas and applies post-processing effects. A Jupyter notebook enables visual iteration; `export.py` is the final CLI.

**Tech Stack:** Python 3.11+, `requests`, `polyline`, `numpy`, `opencv-python`, `Pillow`, `scipy`, `python-dotenv`, `pytest`, `jupyter`

---

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `config.py`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `data/.gitkeep`
- Create: `output/.gitkeep`

**Step 1: Create `requirements.txt`**

```
requests==2.31.0
polyline==2.0.2
numpy==1.26.4
opencv-python==4.9.0.80
Pillow==10.3.0
scipy==1.13.0
python-dotenv==1.0.1
pytest==8.1.1
jupyter==1.0.0
ipykernel==6.29.4
```

**Step 2: Create `.env.example`**

```
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
STRAVA_ACCESS_TOKEN=your_access_token
STRAVA_REFRESH_TOKEN=your_refresh_token
```

Copy to `.env` and fill in your real credentials.

**Step 3: Create `.gitignore`**

```
.env
data/*.json
output/
__pycache__/
*.pyc
.pytest_cache/
.ipynb_checkpoints/
*.egg-info/
dist/
.DS_Store
```

**Step 4: Create `config.py`**

```python
# San Francisco bounding box
SF_BOUNDS = {
    "lat_min": 37.6999,
    "lat_max": 37.8324,
    "lng_min": -122.5270,
    "lng_max": -122.3480,
}

# Print canvas: 18x24" @ 300 DPI
CANVAS_WIDTH_PX = 5400
CANVAS_HEIGHT_PX = 7200
PRINT_DPI = 300

# Strava API
STRAVA_BASE_URL = "https://www.strava.com/api/v3"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_ACTIVITIES_PER_PAGE = 200

# Cache paths
CACHE_DIR = "data"
ACTIVITIES_CACHE_FILE = "data/activities.json"
CACHE_META_FILE = "data/cache_meta.json"

# Output
OUTPUT_DIR = "output"
```

**Step 5: Create empty `src/__init__.py` and `tests/__init__.py`**

```bash
touch src/__init__.py tests/__init__.py data/.gitkeep output/.gitkeep
```

**Step 6: Install dependencies**

```bash
pip install -r requirements.txt
```

**Step 7: Commit**

```bash
git add .
git commit -m "feat: project scaffolding, config, and dependencies"
```

---

### Task 2: Strava Auth & Token Refresh

**Files:**
- Create: `src/fetcher.py`
- Create: `tests/test_fetcher.py`

**Step 1: Write the failing test**

Create `tests/test_fetcher.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock
from src.fetcher import StravaClient


def test_token_refresh_updates_access_token():
    """When access token is expired, client refreshes it and stores new token."""
    client = StravaClient(
        client_id="123",
        client_secret="secret",
        access_token="old_token",
        refresh_token="refresh_token",
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "new_token",
        "refresh_token": "new_refresh",
        "expires_at": 9999999999,
    }
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response) as mock_post:
        client.refresh_access_token()

    assert client.access_token == "new_token"
    assert client.refresh_token == "new_refresh"
    mock_post.assert_called_once()


def test_get_headers_include_bearer_token():
    client = StravaClient(
        client_id="123",
        client_secret="secret",
        access_token="mytoken",
        refresh_token="refresh",
    )
    headers = client._headers()
    assert headers["Authorization"] == "Bearer mytoken"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_fetcher.py -v
```
Expected: `ImportError` or `ModuleNotFoundError` — `fetcher.py` doesn't exist yet.

**Step 3: Implement `src/fetcher.py`**

```python
import json
import os
import time
import requests
from config import STRAVA_TOKEN_URL


class StravaClient:
    def __init__(self, client_id, client_secret, access_token, refresh_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def refresh_access_token(self):
        response = requests.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
        )
        response.raise_for_status()
        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv
        load_dotenv()
        return cls(
            client_id=os.environ["STRAVA_CLIENT_ID"],
            client_secret=os.environ["STRAVA_CLIENT_SECRET"],
            access_token=os.environ["STRAVA_ACCESS_TOKEN"],
            refresh_token=os.environ["STRAVA_REFRESH_TOKEN"],
        )
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_fetcher.py -v
```
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add src/fetcher.py tests/test_fetcher.py
git commit -m "feat: Strava client with OAuth token refresh"
```

---

### Task 3: Activity Fetching with Caching

**Files:**
- Modify: `src/fetcher.py`
- Modify: `tests/test_fetcher.py`

**Step 1: Write the failing tests**

Add to `tests/test_fetcher.py`:

```python
import os
import tempfile
from src.fetcher import StravaClient, fetch_activities


def make_client():
    return StravaClient(
        client_id="123", client_secret="secret",
        access_token="token", refresh_token="refresh"
    )


def _mock_activity(activity_id, start_date="2024-01-15T08:00:00Z"):
    return {
        "id": activity_id,
        "type": "Run",
        "sport_type": "Run",
        "start_date": start_date,
        "start_date_local": start_date,
        "distance": 8000.0,
        "average_speed": 3.2,
        "total_elevation_gain": 50.0,
        "map": {"summary_polyline": "abcd"},
    }


def test_fetch_activities_paginates_until_empty(tmp_path):
    """Fetcher paginates /athlete/activities until an empty page is returned."""
    client = make_client()

    page1 = [_mock_activity(i) for i in range(3)]
    page2 = []

    responses = [
        MagicMock(**{"json.return_value": page1, "raise_for_status": MagicMock()}),
        MagicMock(**{"json.return_value": page2, "raise_for_status": MagicMock()}),
    ]

    with patch("requests.get", side_effect=responses):
        activities = fetch_activities(client, cache_dir=str(tmp_path))

    assert len(activities) == 3
    cache_file = tmp_path / "activities.json"
    assert cache_file.exists()
    saved = json.loads(cache_file.read_text())
    assert len(saved) == 3


def test_fetch_activities_incremental_appends_new(tmp_path):
    """Second fetch only fetches activities after last_fetched and appends them."""
    existing = [_mock_activity(1, "2024-01-01T08:00:00Z")]
    cache_file = tmp_path / "activities.json"
    cache_file.write_text(json.dumps(existing))

    meta_file = tmp_path / "cache_meta.json"
    meta_file.write_text(json.dumps({"last_fetched": 1704067200, "total_count": 1}))

    new_activity = _mock_activity(2, "2024-02-01T08:00:00Z")
    responses = [
        MagicMock(**{"json.return_value": [new_activity], "raise_for_status": MagicMock()}),
        MagicMock(**{"json.return_value": [], "raise_for_status": MagicMock()}),
    ]

    client = make_client()
    with patch("requests.get", side_effect=responses) as mock_get:
        activities = fetch_activities(client, cache_dir=str(tmp_path))

    assert len(activities) == 2
    # Verify `after` param was used
    call_kwargs = mock_get.call_args_list[0][1]
    assert "after" in call_kwargs.get("params", {})


def test_fetch_activities_handles_rate_limit(tmp_path):
    """On 429, fetcher sleeps and retries."""
    client = make_client()

    rate_limited = MagicMock()
    rate_limited.status_code = 429
    rate_limited.headers = {"X-RateLimit-Reset": str(int(time.time()) + 1)}
    rate_limited.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=rate_limited
    )

    success = MagicMock(**{
        "json.return_value": [_mock_activity(1)],
        "raise_for_status": MagicMock(),
        "status_code": 200,
    })
    empty = MagicMock(**{"json.return_value": [], "raise_for_status": MagicMock()})

    with patch("requests.get", side_effect=[rate_limited, success, empty]):
        with patch("time.sleep") as mock_sleep:
            activities = fetch_activities(client, cache_dir=str(tmp_path))

    assert len(activities) == 1
    mock_sleep.assert_called_once()
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_fetcher.py::test_fetch_activities_paginates_until_empty -v
```
Expected: `ImportError` — `fetch_activities` not defined yet.

**Step 3: Implement `fetch_activities` in `src/fetcher.py`**

Add after the `StravaClient` class:

```python
import time

def _get_with_retry(client, url, params=None, max_retries=3):
    """GET request with automatic rate-limit retry."""
    for attempt in range(max_retries):
        response = requests.get(url, headers=client._headers(), params=params or {})
        if response.status_code == 429:
            reset_ts = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
            sleep_secs = max(reset_ts - time.time(), 1)
            print(f"Rate limited. Sleeping {sleep_secs:.0f}s...")
            time.sleep(sleep_secs)
            continue
        response.raise_for_status()
        return response
    raise RuntimeError("Max retries exceeded after rate limiting")


def fetch_activities(client, cache_dir="data"):
    """Fetch all activities with incremental caching. Returns full list."""
    import os
    from config import STRAVA_BASE_URL, STRAVA_ACTIVITIES_PER_PAGE

    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "activities.json")
    meta_file = os.path.join(cache_dir, "cache_meta.json")

    # Load existing cache
    existing = []
    last_fetched = None
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            existing = json.load(f)
    if os.path.exists(meta_file):
        with open(meta_file) as f:
            meta = json.load(f)
            last_fetched = meta.get("last_fetched")

    # Fetch new activities
    new_activities = []
    page = 1
    fetch_time = int(time.time())

    while True:
        params = {"per_page": STRAVA_ACTIVITIES_PER_PAGE, "page": page}
        if last_fetched:
            params["after"] = last_fetched

        response = _get_with_retry(
            client, f"{STRAVA_BASE_URL}/athlete/activities", params=params
        )
        batch = response.json()
        if not batch:
            break
        new_activities.extend(batch)
        page += 1

    all_activities = existing + new_activities

    # Save cache
    with open(cache_file, "w") as f:
        json.dump(all_activities, f)
    with open(meta_file, "w") as f:
        json.dump({"last_fetched": fetch_time, "total_count": len(all_activities)}, f)

    if new_activities:
        print(f"Fetched {len(new_activities)} new activities. Total: {len(all_activities)}")
    else:
        print(f"No new activities. Total cached: {len(all_activities)}")

    return all_activities
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_fetcher.py -v
```
Expected: all PASSED

**Step 5: Commit**

```bash
git add src/fetcher.py tests/test_fetcher.py
git commit -m "feat: incremental activity fetching with caching and rate-limit retry"
```

---

### Task 4: Processor — Filter & Decode

**Files:**
- Create: `src/processor.py`
- Create: `tests/test_processor.py`

**Step 1: Write the failing tests**

Create `tests/test_processor.py`:

```python
import pytest
from src.processor import filter_sf_runs, decode_runs


def _activity(sport_type="Run", polyline="abcd", lat=37.76, lng=-122.45,
               start_date="2024-06-15T08:00:00Z", speed=3.2, elevation=50.0, distance=8000.0):
    """Build a minimal mock activity dict."""
    import polyline as pl
    # Encode a simple 2-point route near the given lat/lng
    encoded = pl.encode([(lat, lng), (lat + 0.01, lng + 0.01)])
    return {
        "id": 1,
        "sport_type": sport_type,
        "type": sport_type,
        "start_date": start_date,
        "distance": distance,
        "average_speed": speed,
        "total_elevation_gain": elevation,
        "map": {"summary_polyline": encoded},
    }


def test_filter_keeps_sf_runs():
    activities = [_activity()]  # lat=37.76, lng=-122.45 — inside SF
    result = filter_sf_runs(activities)
    assert len(result) == 1


def test_filter_excludes_non_sf_runs():
    activities = [_activity(lat=34.05, lng=-118.24)]  # Los Angeles
    result = filter_sf_runs(activities)
    assert len(result) == 0


def test_filter_excludes_non_run_activities():
    activities = [_activity(sport_type="Ride")]
    result = filter_sf_runs(activities)
    assert len(result) == 0


def test_filter_excludes_empty_polyline():
    activity = _activity()
    activity["map"]["summary_polyline"] = ""
    result = filter_sf_runs([activity])
    assert len(result) == 0


def test_decode_runs_returns_coord_arrays():
    import polyline as pl
    coords = [(37.76, -122.45), (37.77, -122.44)]
    encoded = pl.encode(coords)
    activity = _activity()
    activity["map"]["summary_polyline"] = encoded

    runs = decode_runs([activity])
    assert len(runs) == 1
    assert len(runs[0]["coords"]) == 2
    assert abs(runs[0]["coords"][0][0] - 37.76) < 0.0001


def test_decode_runs_attaches_metadata():
    runs = decode_runs([_activity(start_date="2024-06-15T08:30:00Z", speed=3.5)])
    run = runs[0]
    assert run["start_date"] == "2024-06-15T08:30:00Z"
    assert run["average_speed"] == 3.5
    assert "total_elevation_gain" in run
    assert "distance" in run
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_processor.py -v
```
Expected: `ImportError` — `processor.py` doesn't exist yet.

**Step 3: Implement `src/processor.py`**

```python
import polyline as pl
from config import SF_BOUNDS


def filter_sf_runs(activities):
    """Return only Run activities with a non-empty polyline whose centroid is within SF bounds."""
    result = []
    for act in activities:
        sport = act.get("sport_type") or act.get("type", "")
        if sport != "Run":
            continue
        encoded = act.get("map", {}).get("summary_polyline", "")
        if not encoded:
            continue
        coords = pl.decode(encoded)
        if not coords:
            continue
        lats = [c[0] for c in coords]
        lngs = [c[1] for c in coords]
        centroid_lat = sum(lats) / len(lats)
        centroid_lng = sum(lngs) / len(lngs)
        if (SF_BOUNDS["lat_min"] <= centroid_lat <= SF_BOUNDS["lat_max"] and
                SF_BOUNDS["lng_min"] <= centroid_lng <= SF_BOUNDS["lng_max"]):
            result.append(act)
    return result


def decode_runs(activities):
    """Decode polylines and attach metadata. Returns list of run dicts."""
    runs = []
    for act in activities:
        encoded = act.get("map", {}).get("summary_polyline", "")
        coords = pl.decode(encoded)
        runs.append({
            "id": act["id"],
            "coords": coords,
            "start_date": act.get("start_date", ""),
            "average_speed": act.get("average_speed", 0.0),
            "total_elevation_gain": act.get("total_elevation_gain", 0.0),
            "distance": act.get("distance", 0.0),
        })
    return runs
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_processor.py -v
```
Expected: all PASSED

**Step 5: Commit**

```bash
git add src/processor.py tests/test_processor.py
git commit -m "feat: processor filters SF runs and decodes polylines"
```

---

### Task 5: Renderer — Coordinate Projection

**Files:**
- Create: `src/renderer.py`
- Create: `tests/test_renderer.py`

**Step 1: Write the failing tests**

Create `tests/test_renderer.py`:

```python
import numpy as np
import pytest
from src.renderer import StravaRenderer
from config import SF_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX


@pytest.fixture
def renderer():
    return StravaRenderer(width=540, height=720)  # 1/10 scale for tests


def test_project_sf_center_to_canvas_center(renderer):
    """SF centroid should project near the canvas center."""
    center_lat = (SF_BOUNDS["lat_min"] + SF_BOUNDS["lat_max"]) / 2
    center_lng = (SF_BOUNDS["lng_min"] + SF_BOUNDS["lng_max"]) / 2
    x, y = renderer.project(center_lat, center_lng)
    assert abs(x - 270) < 30  # within 30px of center (540/2)
    assert abs(y - 360) < 30  # within 30px of center (720/2)


def test_project_top_left_corner(renderer):
    """SW corner of SF bounds → near bottom-left of canvas (lat inverted)."""
    x, y = renderer.project(SF_BOUNDS["lat_min"], SF_BOUNDS["lng_min"])
    assert x < 100
    assert y > 620  # near bottom (lat_min = south = high y)


def test_project_top_right_corner(renderer):
    """NE corner → near top-right."""
    x, y = renderer.project(SF_BOUNDS["lat_max"], SF_BOUNDS["lng_max"])
    assert x > 440
    assert y < 100


def test_canvas_initialized_to_zero(renderer):
    assert renderer.canvas.shape == (720, 540)
    assert renderer.canvas.dtype == np.float32
    assert renderer.canvas.max() == 0.0


def test_full_resolution_canvas():
    r = StravaRenderer()
    assert r.canvas.shape == (CANVAS_HEIGHT_PX, CANVAS_WIDTH_PX)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_renderer.py -v
```
Expected: `ImportError` — `renderer.py` doesn't exist yet.

**Step 3: Implement `src/renderer.py`**

```python
import numpy as np
from config import SF_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX


class StravaRenderer:
    def __init__(self, width=CANVAS_WIDTH_PX, height=CANVAS_HEIGHT_PX):
        self.width = width
        self.height = height
        self.canvas = np.zeros((height, width), dtype=np.float32)

    def project(self, lat, lng):
        """Map (lat, lng) to (x, y) pixel coordinates."""
        x = int((lng - SF_BOUNDS["lng_min"]) /
                (SF_BOUNDS["lng_max"] - SF_BOUNDS["lng_min"]) * (self.width - 1))
        # Latitude is inverted: higher lat = lower y
        y = int((SF_BOUNDS["lat_max"] - lat) /
                (SF_BOUNDS["lat_max"] - SF_BOUNDS["lat_min"]) * (self.height - 1))
        return x, y
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_renderer.py -v
```
Expected: all PASSED

**Step 5: Commit**

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "feat: renderer with lat/lng to pixel projection"
```

---

### Task 6: Route Rasterization & Density Accumulation

**Files:**
- Modify: `src/renderer.py`
- Modify: `tests/test_renderer.py`

**Step 1: Write the failing tests**

Add to `tests/test_renderer.py`:

```python
def test_rasterize_run_draws_nonzero_pixels(renderer):
    """Drawing a run across the canvas produces non-zero pixels."""
    coords = [
        (37.76, -122.47),
        (37.77, -122.44),
        (37.78, -122.42),
    ]
    renderer.rasterize_run(coords)
    assert renderer.canvas.max() > 0


def test_rasterize_two_runs_doubles_density_on_overlap(renderer):
    """Same route drawn twice doubles the density values."""
    coords = [(37.76, -122.47), (37.78, -122.42)]
    renderer.rasterize_run(coords)
    first_max = renderer.canvas.max()
    renderer.rasterize_run(coords)
    assert renderer.canvas.max() == pytest.approx(first_max * 2)


def test_rasterize_all_runs(renderer):
    runs = [
        {"coords": [(37.76, -122.47), (37.77, -122.44)]},
        {"coords": [(37.75, -122.46), (37.78, -122.42)]},
    ]
    renderer.rasterize_all(runs)
    assert renderer.canvas.max() > 0
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_renderer.py::test_rasterize_run_draws_nonzero_pixels -v
```
Expected: `AttributeError` — `rasterize_run` not defined.

**Step 3: Add rasterization to `src/renderer.py`**

```python
import cv2

class StravaRenderer:
    # ... existing code ...

    def rasterize_run(self, coords, weight=1.0):
        """Draw anti-aliased route onto the density canvas."""
        if len(coords) < 2:
            return
        points = [self.project(lat, lng) for lat, lng in coords]
        for i in range(len(points) - 1):
            cv2.line(self.canvas, points[i], points[i + 1],
                     color=weight, thickness=1, lineType=cv2.LINE_AA)

    def rasterize_all(self, runs, weight=1.0):
        """Rasterize all runs onto the canvas."""
        for run in runs:
            self.rasterize_run(run["coords"], weight=weight)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_renderer.py -v
```
Expected: all PASSED

**Step 5: Commit**

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "feat: anti-aliased route rasterization and density accumulation"
```

---

### Task 7: Luminosity Heatmap + Export

**Files:**
- Modify: `src/renderer.py`
- Modify: `tests/test_renderer.py`

**Step 1: Write the failing tests**

Add to `tests/test_renderer.py`:

```python
def test_to_image_returns_rgb_array(renderer):
    renderer.rasterize_run([(37.76, -122.47), (37.77, -122.44)])
    img = renderer.to_image()
    assert img.shape == (720, 540, 3)
    assert img.dtype == np.uint8


def test_to_image_background_is_dark(renderer):
    """Empty canvas should produce a near-black image."""
    img = renderer.to_image()
    assert img.mean() < 20


def test_to_image_routes_are_bright(renderer):
    """Canvas with a run should produce brighter pixels than empty canvas."""
    empty = renderer.to_image().mean()
    renderer.rasterize_run([(37.72, -122.50), (37.82, -122.35)])
    with_run = renderer.to_image().mean()
    assert with_run > empty
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_renderer.py::test_to_image_returns_rgb_array -v
```
Expected: `AttributeError` — `to_image` not defined.

**Step 3: Add `to_image` to `src/renderer.py`**

```python
from PIL import Image

class StravaRenderer:
    # ... existing code ...

    # Background color: near-black navy
    BG_COLOR = np.array([10, 15, 30], dtype=np.float32)
    # Route color: warm gold/white
    ROUTE_COLOR = np.array([255, 240, 180], dtype=np.float32)

    def to_image(self):
        """Normalize density canvas and apply luminosity colormap. Returns HxWx3 uint8 array."""
        max_val = self.canvas.max()
        if max_val == 0:
            norm = self.canvas
        else:
            # Log-scale normalization: brings out faint routes without blowing out dense ones
            norm = np.log1p(self.canvas) / np.log1p(max_val)

        # Blend: background → route color based on normalized density
        rgb = np.zeros((self.height, self.width, 3), dtype=np.float32)
        for c in range(3):
            rgb[:, :, c] = self.BG_COLOR[c] * (1 - norm) + self.ROUTE_COLOR[c] * norm

        return np.clip(rgb, 0, 255).astype(np.uint8)

    def save(self, path, dpi=300):
        """Save the rendered image as a PNG at the given DPI."""
        import os
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        img_array = self.to_image()
        img = Image.fromarray(img_array, mode="RGB")
        img.save(path, dpi=(dpi, dpi))
        print(f"Saved: {path}")
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_renderer.py -v
```
Expected: all PASSED

**Step 5: Commit**

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "feat: luminosity colormap with log-scale normalization and PNG export"
```

---

### Task 8: Post-Processing Effects — Bloom

**Files:**
- Modify: `src/renderer.py`
- Modify: `tests/test_renderer.py`

**Step 1: Write the failing test**

Add to `tests/test_renderer.py`:

```python
def test_bloom_increases_brightness(renderer):
    """Bloom effect should produce a brighter image than without it."""
    renderer.rasterize_run([(37.76, -122.47), (37.77, -122.44)])
    without_bloom = renderer.to_image(bloom=False).mean()
    with_bloom = renderer.to_image(bloom=True).mean()
    assert with_bloom > without_bloom


def test_bloom_spreads_light_to_adjacent_pixels(renderer):
    """A single bright pixel should produce non-zero neighbors after bloom."""
    # Draw a tiny single-point route
    renderer.canvas[360, 270] = 10.0
    img = renderer.to_image(bloom=True)
    # Neighbors should be brighter than background
    center = int(img[360, 270].mean())
    neighbor = int(img[358, 270].mean())
    assert neighbor > 10  # background is ~10
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_renderer.py::test_bloom_increases_brightness -v
```
Expected: `TypeError` — `to_image` doesn't accept `bloom` argument.

**Step 3: Add bloom to `src/renderer.py`**

```python
from scipy.ndimage import gaussian_filter

class StravaRenderer:
    # ... existing code ...

    def to_image(self, bloom=True, bloom_sigma=8.0, bloom_strength=0.6):
        max_val = self.canvas.max()
        if max_val == 0:
            norm = self.canvas
        else:
            norm = np.log1p(self.canvas) / np.log1p(max_val)

        if bloom:
            # Gaussian blur creates the glow halo
            blurred = gaussian_filter(norm, sigma=bloom_sigma)
            # Screen blend: combine original + bloom
            norm = 1 - (1 - norm) * (1 - blurred * bloom_strength)

        rgb = np.zeros((self.height, self.width, 3), dtype=np.float32)
        for c in range(3):
            rgb[:, :, c] = self.BG_COLOR[c] * (1 - norm) + self.ROUTE_COLOR[c] * norm

        return np.clip(rgb, 0, 255).astype(np.uint8)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_renderer.py -v
```
Expected: all PASSED

**Step 5: Commit**

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "feat: bloom effect via Gaussian screen composite"
```

---

### Task 9: Post-Processing Effects — Vignette & Film Grain

**Files:**
- Modify: `src/renderer.py`
- Modify: `tests/test_renderer.py`

**Step 1: Write the failing tests**

Add to `tests/test_renderer.py`:

```python
def test_vignette_darkens_corners_vs_center(renderer):
    """Corners should be darker than center after vignette."""
    # Fill canvas uniformly
    renderer.canvas[:] = 5.0
    img = renderer.to_image(bloom=False, vignette=True, grain=False)
    center = int(img[360, 270].mean())
    corner = int(img[10, 10].mean())
    assert corner < center


def test_grain_adds_pixel_variance(renderer):
    """Film grain should increase variance of a flat region."""
    renderer.canvas[:] = 5.0
    without = renderer.to_image(bloom=False, vignette=False, grain=False).std()
    with_grain = renderer.to_image(bloom=False, vignette=False, grain=True).std()
    assert with_grain > without
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_renderer.py::test_vignette_darkens_corners_vs_center -v
```
Expected: `TypeError` — `to_image` doesn't accept `vignette`/`grain` args.

**Step 3: Add vignette and grain to `src/renderer.py`**

```python
class StravaRenderer:
    # ... existing code ...

    def _make_vignette(self, strength=0.5):
        """Radial gradient mask: 1.0 at center, (1-strength) at corners."""
        cx, cy = self.width / 2, self.height / 2
        y_idx, x_idx = np.ogrid[:self.height, :self.width]
        dist = np.sqrt(((x_idx - cx) / cx) ** 2 + ((y_idx - cy) / cy) ** 2)
        mask = 1 - strength * np.clip(dist, 0, 1)
        return mask.astype(np.float32)

    def to_image(self, bloom=True, bloom_sigma=8.0, bloom_strength=0.6,
                 vignette=True, vignette_strength=0.5,
                 grain=True, grain_amount=0.025):
        max_val = self.canvas.max()
        if max_val == 0:
            norm = self.canvas
        else:
            norm = np.log1p(self.canvas) / np.log1p(max_val)

        if bloom:
            blurred = gaussian_filter(norm, sigma=bloom_sigma)
            norm = 1 - (1 - norm) * (1 - blurred * bloom_strength)

        rgb = np.zeros((self.height, self.width, 3), dtype=np.float32)
        for c in range(3):
            rgb[:, :, c] = self.BG_COLOR[c] * (1 - norm) + self.ROUTE_COLOR[c] * norm

        if vignette:
            mask = self._make_vignette(strength=vignette_strength)
            rgb *= mask[:, :, np.newaxis]

        if grain:
            noise = np.random.normal(0, grain_amount * 255, rgb.shape).astype(np.float32)
            rgb += noise

        return np.clip(rgb, 0, 255).astype(np.uint8)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_renderer.py -v
```
Expected: all PASSED

**Step 5: Commit**

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "feat: vignette and film grain post-processing effects"
```

---

### Task 10: Export CLI

**Files:**
- Create: `export.py`

No tests needed — this is a thin CLI wrapper around already-tested modules.

**Step 1: Create `export.py`**

```python
#!/usr/bin/env python3
"""
Generate and save the SF running heatmap poster.

Usage:
    python export.py                          # full 300 DPI render
    python export.py --preview                # 1/10 scale for quick iteration
    python export.py --no-bloom --no-grain    # effects off
    python export.py --fetch                  # fetch new activities first
"""
import argparse
import os
from datetime import datetime

from src.fetcher import StravaClient, fetch_activities
from src.processor import filter_sf_runs, decode_runs
from src.renderer import StravaRenderer
from config import CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, OUTPUT_DIR


def main():
    parser = argparse.ArgumentParser(description="Generate SF running heatmap poster")
    parser.add_argument("--fetch", action="store_true", help="Fetch new activities from Strava")
    parser.add_argument("--preview", action="store_true", help="Render at 1/10 scale for speed")
    parser.add_argument("--no-bloom", dest="bloom", action="store_false", default=True)
    parser.add_argument("--no-vignette", dest="vignette", action="store_false", default=True)
    parser.add_argument("--no-grain", dest="grain", action="store_false", default=True)
    parser.add_argument("--output", default=None, help="Output file path (default: output/poster-TIMESTAMP.png)")
    args = parser.parse_args()

    # Optionally fetch new data
    if args.fetch:
        print("Fetching activities from Strava...")
        client = StravaClient.from_env()
        fetch_activities(client)

    # Load and process cached data
    import json
    with open("data/activities.json") as f:
        activities = json.load(f)

    sf_runs = filter_sf_runs(activities)
    runs = decode_runs(sf_runs)
    print(f"Rendering {len(runs)} SF runs...")

    # Set up renderer
    scale = 0.1 if args.preview else 1.0
    renderer = StravaRenderer(
        width=int(CANVAS_WIDTH_PX * scale),
        height=int(CANVAS_HEIGHT_PX * scale),
    )

    renderer.rasterize_all(runs)

    # Output path
    if args.output:
        out_path = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = "-preview" if args.preview else ""
        out_path = os.path.join(OUTPUT_DIR, f"poster{suffix}-{ts}.png")

    dpi = 30 if args.preview else 300
    renderer.save(out_path, dpi=dpi, bloom=args.bloom, vignette=args.vignette, grain=args.grain)
    print(f"Done. {out_path}")


if __name__ == "__main__":
    main()
```

Note: update `renderer.save()` to pass kwargs through to `to_image()`:

```python
def save(self, path, dpi=300, **kwargs):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img_array = self.to_image(**kwargs)
    img = Image.fromarray(img_array, mode="RGB")
    img.save(path, dpi=(dpi, dpi))
    print(f"Saved: {path}")
```

**Step 2: Run a quick smoke test**

First, fetch your data:
```bash
python export.py --fetch
```

Then render a preview:
```bash
python export.py --preview
```
Expected: `output/poster-preview-TIMESTAMP.png` created. Open it and verify routes appear.

**Step 3: Commit**

```bash
git add export.py
git commit -m "feat: export CLI with --fetch, --preview, and effect flags"
```

---

### Task 11: Jupyter Notebook for Visual Iteration

**Files:**
- Create: `notebooks/explore.ipynb`

**Step 1: Launch Jupyter and create the notebook**

```bash
jupyter notebook notebooks/explore.ipynb
```

Create cells in this order:

**Cell 1 — Imports & setup:**
```python
import sys; sys.path.insert(0, "..")
import json
import numpy as np
import matplotlib.pyplot as plt
from src.processor import filter_sf_runs, decode_runs
from src.renderer import StravaRenderer
%matplotlib inline
```

**Cell 2 — Load cached data:**
```python
with open("../data/activities.json") as f:
    activities = json.load(f)
sf_runs = filter_sf_runs(activities)
runs = decode_runs(sf_runs)
print(f"{len(runs)} SF runs loaded")
```

**Cell 3 — Quick preview render:**
```python
r = StravaRenderer(width=540, height=720)
r.rasterize_all(runs)
img = r.to_image(bloom=True, vignette=True, grain=False)
plt.figure(figsize=(6, 8))
plt.imshow(img)
plt.axis("off")
plt.tight_layout()
plt.show()
```

**Cell 4 — Effect comparison:**
```python
fig, axes = plt.subplots(1, 3, figsize=(15, 8))
for ax, (bloom, vignette, title) in zip(axes, [
    (False, False, "Raw"),
    (True, False, "+ Bloom"),
    (True, True, "+ Bloom + Vignette"),
]):
    r2 = StravaRenderer(width=540, height=720)
    r2.rasterize_all(runs)
    ax.imshow(r2.to_image(bloom=bloom, vignette=vignette, grain=False))
    ax.set_title(title)
    ax.axis("off")
plt.tight_layout()
plt.show()
```

**Step 2: Commit**

```bash
git add notebooks/explore.ipynb
git commit -m "feat: Jupyter notebook for visual iteration and effect comparison"
```

---

### Task 12: Run Full Test Suite

**Step 1: Run all tests**

```bash
pytest tests/ -v
```
Expected: all tests PASS.

**Step 2: Generate final poster**

```bash
python export.py --fetch  # fetch any new runs
python export.py          # full 300 DPI render
```
Expected: `output/poster-TIMESTAMP.png` at 5400×7200px, ~50-100MB.

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete Phase 1 heatmap poster pipeline"
```
