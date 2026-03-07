# Onboarding & Auth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the repo usable by a friend for a new city — `.env`-based auth, clear README, and a CLAUDE.md architecture reference.

**Architecture:** Five isolated tasks: (1) `.env.example`, (2) rewrite `auth.py` to use `.env`, (3) add startup validation to `export.py`, (4) write `README.md`, (5) write `CLAUDE.md`. Tasks 1–3 touch code and have tests; 4–5 are docs only.

**Tech Stack:** Python, python-dotenv, pytest

---

### Task 1: Add `.env.example`

**Files:**
- Create: `.env.example`

No tests needed — this is a static template file.

**Step 1: Create `.env.example`**

```
# Strava API credentials
# Get these from https://www.strava.com/settings/api
# Set "Authorization Callback Domain" to: localhost
STRAVA_CLIENT_ID=your_client_id_here
STRAVA_CLIENT_SECRET=your_client_secret_here

# These are written automatically by auth.py — do not edit manually
STRAVA_ACCESS_TOKEN=
STRAVA_REFRESH_TOKEN=
```

**Step 2: Verify `.env` is in `.gitignore`**

Run: `grep '\.env' .gitignore`
Expected: `.env` appears (already present — no change needed).

**Step 3: Commit**

```bash
git add .env.example
git commit -m "chore: add .env.example with required Strava credentials"
```

---

### Task 2: Rewrite `auth.py` — `.env`-based, writes tokens back

**Files:**
- Modify: `auth.py`
- Create: `tests/test_auth.py`

The OAuth browser flow can't be unit-tested, but the two pure helpers can: `_check_env_credentials` (validates required vars) and `_upsert_env_tokens` (writes/updates tokens in `.env`).

**Step 1: Write failing tests**

Create `tests/test_auth.py`:

```python
import os
import tempfile
import pytest
from unittest.mock import patch


def test_check_env_credentials_raises_if_missing(monkeypatch):
    monkeypatch.delenv("STRAVA_CLIENT_ID", raising=False)
    monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
    from auth import _check_env_credentials
    with pytest.raises(SystemExit):
        _check_env_credentials()


def test_check_env_credentials_passes_when_set(monkeypatch):
    monkeypatch.setenv("STRAVA_CLIENT_ID", "123")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "abc")
    from auth import _check_env_credentials
    _check_env_credentials()  # should not raise


def test_upsert_env_tokens_updates_existing_keys():
    """Updates ACCESS_TOKEN and REFRESH_TOKEN lines that already exist."""
    from auth import _upsert_env_tokens
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("STRAVA_CLIENT_ID=123\n")
        f.write("STRAVA_ACCESS_TOKEN=old_access\n")
        f.write("STRAVA_REFRESH_TOKEN=old_refresh\n")
        path = f.name
    try:
        _upsert_env_tokens(path, "new_access", "new_refresh")
        content = open(path).read()
        assert "STRAVA_ACCESS_TOKEN=new_access" in content
        assert "STRAVA_REFRESH_TOKEN=new_refresh" in content
        assert "STRAVA_CLIENT_ID=123" in content
        assert "old_access" not in content
    finally:
        os.unlink(path)


def test_upsert_env_tokens_appends_missing_keys():
    """Appends ACCESS_TOKEN and REFRESH_TOKEN if not already in .env."""
    from auth import _upsert_env_tokens
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("STRAVA_CLIENT_ID=123\n")
        path = f.name
    try:
        _upsert_env_tokens(path, "new_access", "new_refresh")
        content = open(path).read()
        assert "STRAVA_ACCESS_TOKEN=new_access" in content
        assert "STRAVA_REFRESH_TOKEN=new_refresh" in content
    finally:
        os.unlink(path)


def test_upsert_env_tokens_creates_env_if_missing():
    """Creates .env from scratch if it doesn't exist."""
    from auth import _upsert_env_tokens
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, ".env")
        _upsert_env_tokens(path, "acc", "ref")
        content = open(path).read()
        assert "STRAVA_ACCESS_TOKEN=acc" in content
        assert "STRAVA_REFRESH_TOKEN=ref" in content
```

**Step 2: Run tests to confirm they fail**

```bash
.venv/bin/pytest tests/test_auth.py -v
```

Expected: All 5 FAIL (ImportError — functions don't exist yet).

**Step 3: Rewrite `auth.py`**

Replace the entire file:

```python
#!/usr/bin/env python3
"""
Strava OAuth — run once to get your tokens.

Reads STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET from .env.
After you authorize in the browser, tokens are saved back to .env automatically.
"""
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv

AUTH_CODE = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global AUTH_CODE
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            AUTH_CODE = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Auth successful! You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>No code found. Try again.</h2>")

    def log_message(self, format, *args):
        pass  # suppress server logs


def _check_env_credentials():
    """Exit with a clear message if CLIENT_ID or CLIENT_SECRET are missing."""
    missing = [k for k in ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET") if not os.environ.get(k)]
    if missing:
        print("ERROR: Missing required environment variables:", ", ".join(missing))
        print("Copy .env.example to .env and fill in your Strava API credentials.")
        print("Get them from: https://www.strava.com/settings/api")
        sys.exit(1)


def _upsert_env_tokens(env_file, access_token, refresh_token):
    """Write ACCESS_TOKEN and REFRESH_TOKEN into env_file.

    Updates lines if the keys already exist, appends them if not.
    Creates the file if it doesn't exist.
    """
    lines = []
    if os.path.exists(env_file):
        with open(env_file) as f:
            lines = f.readlines()

    updated_access = False
    updated_refresh = False
    result = []
    for line in lines:
        if line.startswith("STRAVA_ACCESS_TOKEN="):
            result.append(f"STRAVA_ACCESS_TOKEN={access_token}\n")
            updated_access = True
        elif line.startswith("STRAVA_REFRESH_TOKEN="):
            result.append(f"STRAVA_REFRESH_TOKEN={refresh_token}\n")
            updated_refresh = True
        else:
            result.append(line)

    if not updated_access:
        result.append(f"STRAVA_ACCESS_TOKEN={access_token}\n")
    if not updated_refresh:
        result.append(f"STRAVA_REFRESH_TOKEN={refresh_token}\n")

    with open(env_file, "w") as f:
        f.writelines(result)


def main():
    load_dotenv()
    _check_env_credentials()

    client_id = os.environ["STRAVA_CLIENT_ID"]
    client_secret = os.environ["STRAVA_CLIENT_SECRET"]

    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri=http://localhost:8765"
        f"&response_type=code"
        f"&scope=activity:read_all"
    )

    server = HTTPServer(("localhost", 8765), CallbackHandler)
    t = threading.Thread(target=server.handle_request)
    t.start()

    print("Opening Strava in your browser...")
    print("Click 'Authorize' on the Strava page. The browser will redirect to localhost")
    print("and show 'Auth successful' — then come back here.")
    webbrowser.open(auth_url)
    t.join()

    if not AUTH_CODE:
        print("ERROR: Did not receive auth code.")
        sys.exit(1)

    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": AUTH_CODE,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    tokens = resp.json()

    _upsert_env_tokens(".env", tokens["access_token"], tokens["refresh_token"])

    print(f"✓ Auth complete. Tokens saved to .env")
    print(f"  Athlete: {tokens['athlete']['firstname']} {tokens['athlete']['lastname']}")
    print(f"  Run: python export.py --fetch")


if __name__ == "__main__":
    main()
```

**Step 4: Run the tests to confirm they pass**

```bash
.venv/bin/pytest tests/test_auth.py -v
```

Expected: All 5 PASS.

**Step 5: Run full suite to catch regressions**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All tests PASS.

**Step 6: Commit**

```bash
git add auth.py tests/test_auth.py
git commit -m "feat: rewrite auth.py to use .env — drop CLI args, validate credentials, upsert tokens"
```

---

### Task 3: Add startup validation to `export.py`

**Files:**
- Modify: `export.py:56-59`

When `--fetch` is passed and tokens are missing, print a helpful message instead of a traceback.

No new test file needed — add one test to `tests/test_fetcher.py` (it already tests `StravaClient.from_env`).

**Step 1: Write a failing test**

Add to `tests/test_fetcher.py`:

```python
def test_from_env_raises_key_error_when_tokens_missing(monkeypatch):
    """StravaClient.from_env() raises KeyError if tokens not in env."""
    for key in ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET",
                "STRAVA_ACCESS_TOKEN", "STRAVA_REFRESH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(KeyError):
        StravaClient.from_env()
```

Add `import pytest` to the top of `tests/test_fetcher.py` if not already there.

**Step 2: Run the test to confirm it passes already** (this tests existing behavior)

```bash
.venv/bin/pytest tests/test_fetcher.py::test_from_env_raises_key_error_when_tokens_missing -v
```

Expected: PASS (documents current behavior so we don't break it).

**Step 3: Update the `--fetch` block in `export.py`**

Find the block at line 56–59:

```python
    if args.fetch:
        print("Fetching activities from Strava...")
        client = StravaClient.from_env()
        fetch_activities(client)
```

Replace with:

```python
    if args.fetch:
        print("Fetching activities from Strava...")
        try:
            client = StravaClient.from_env()
        except KeyError as e:
            print(f"ERROR: Missing token {e} in .env")
            print("Run 'python auth.py' first to authenticate with Strava.")
            sys.exit(1)
        fetch_activities(client)
```

Also add `import sys` at the top of `export.py` if not already present (check line 1–16).

**Step 4: Run full suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All PASS.

**Step 5: Commit**

```bash
git add export.py tests/test_fetcher.py
git commit -m "feat: add friendly error in export.py when Strava tokens missing from .env"
```

---

### Task 4: Write `README.md`

**Files:**
- Create: `README.md`

No tests. Preview the rendered Markdown locally if you have a viewer.

**Step 1: Create `README.md`**

```markdown
# Strava Art

Generate a print-quality running heatmap poster from your Strava data.

![San Francisco running heatmap](sf.png)

---

## Prerequisites

- Python 3.11+
- A [Strava](https://www.strava.com) account with running activities

## Setup

```bash
git clone <this-repo>
cd strava-art
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

## Strava API setup

1. Go to [strava.com/settings/api](https://www.strava.com/settings/api)
2. Create an application (name and website can be anything)
3. Set **Authorization Callback Domain** to `localhost`
4. Copy your **Client ID** and **Client Secret** into `.env`:
   ```
   STRAVA_CLIENT_ID=12345
   STRAVA_CLIENT_SECRET=abc123...
   ```

## Authenticate

```bash
python auth.py
```

Your browser opens the Strava authorization page. Click **Authorize**. The page redirects to localhost and shows "Auth successful" — your tokens are saved to `.env` automatically. Come back to the terminal; you'll see:

```
✓ Auth complete. Tokens saved to .env
  Athlete: Jane Smith
  Run: python export.py --fetch
```

## Fetch & render

**First run** — fetch activities and render:
```bash
python export.py --fetch
```

**Subsequent runs** — render from cache (fast):
```bash
python export.py
```

**Quick preview** at 1/10 scale for iteration:
```bash
python export.py --preview
```

Output is saved to `output/poster-<timestamp>.png`.

## Adapting for a new city

Open `config.py` and update three things:

**1. Geographic bounds**

```python
SF_BOUNDS = {
    "lat_min": 40.4774,   # south edge
    "lat_max": 40.9176,   # north edge
    "lng_min": -74.2591,  # west edge
    "lng_max": -73.7004,  # east edge
}
```

Use [bboxfinder.com](http://bboxfinder.com) to draw your city's bounding box and copy the coordinates.

**2. Canvas size**

The canvas must match the Mercator aspect ratio of your bounding box or the map will be distorted. After picking your bounds, calculate:

```
lng_range_rad  = (lng_max - lng_min) × π/180
merc_max       = arcsinh(tan(lat_max × π/180))
merc_min       = arcsinh(tan(lat_min × π/180))
merc_range     = merc_max - merc_min
aspect_ratio   = lng_range_rad / merc_range   ← width/height
```

Then set canvas dimensions that match this ratio at your target print size (e.g. 16×20" at 285 DPI = 4560×5700px for a 0.8 ratio):

```python
CANVAS_WIDTH_PX  = 4560
CANVAS_HEIGHT_PX = 5700   # CANVAS_WIDTH_PX / aspect_ratio
```

**3. Activity filter**

`src/processor.py:filter_sf_runs()` filters activities whose centroid falls inside `SF_BOUNDS` — it automatically uses your updated bounds, no code change needed.

## Tweaking visuals

All visual knobs are in `config.py`:

| Variable | What it controls | Safe range |
|---|---|---|
| `GAMMA` | Brightness of rarely-run routes (< 1 lifts dim lines) | 0.3 – 1.0 |
| `ROUTE_LINE_THICKNESS` | Base stroke width in pixels | 1 – 5 |
| `ROUTE_COLOR_RAMP` | Color palette from single-run to peak density | — |
| `HOT_BLOOM_STRENGTH` | Glow intensity on heavily-run corridors | 1.0 – 6.0 |
| `HOT_BLOOM_THRESHOLD` | Density cutoff to trigger hot bloom | 0.5 – 0.9 |
| `MAP_TILE_OPACITY` | How bright the street map shows through | 0.5 – 1.0 |
| `DENSITY_EXPAND_STRENGTH` | How much denser routes appear thicker | 0.5 – 2.0 |
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup, auth, new-city guide, and config reference"
```

---

### Task 5: Write `CLAUDE.md`

**Files:**
- Create: `CLAUDE.md`

No tests.

**Step 1: Create `CLAUDE.md`**

```markdown
# Strava Art — Developer Reference

This file is for Claude and developers who need to understand the codebase quickly.

## What it does

Fetches a user's Strava running activities, filters them to a geographic bounding box, and renders a print-quality heatmap poster. The output is a high-DPI PNG with glowing neon routes on a dark map background.

**Pipeline:**
```
auth.py          → writes tokens to .env (run once)
export.py        → orchestrates everything
  src/fetcher.py → fetch & cache activities from Strava API
  src/processor.py → filter by city bounds + decode polylines
  src/renderer.py  → rasterize routes → post-process (bloom, grain, glow)
  src/tiles.py     → fetch & cache OpenStreetMap background tiles
  src/typography.py → render stats text + color legend
```

## File map

| File | Purpose |
|---|---|
| `config.py` | All tunable constants — canvas size, bounds, colors, effects |
| `auth.py` | One-time OAuth flow — writes tokens to `.env` |
| `export.py` | CLI entry point — wires pipeline together |
| `src/fetcher.py` | `StravaClient` + `fetch_activities()` with incremental cache |
| `src/processor.py` | `filter_sf_runs()` centroid filter + `decode_runs()` polyline decoder |
| `src/renderer.py` | `StravaRenderer`: rasterize → density expand → hot bloom → color map |
| `src/tiles.py` | Fetch and stitch CARTO map tiles |
| `src/typography.py` | Render year range / run count / distance / elevation + color legend |

## Adding a new city

Four changes, all in `config.py` unless noted:

**1. `SF_BOUNDS`** — update the four lat/lng values to your city's bounding box. Use [bboxfinder.com](http://bboxfinder.com).

**2. Canvas dimensions** — the canvas pixel ratio must match the Mercator aspect ratio of the bounds or the map distorts. Formula:

```python
import math
lng_range = (lng_max - lng_min) * math.pi / 180
merc_range = math.asinh(math.tan(math.radians(lat_max))) - math.asinh(math.tan(math.radians(lat_min)))
aspect = lng_range / merc_range  # width / height
```

Set `CANVAS_WIDTH_PX` and `CANVAS_HEIGHT_PX` so `WIDTH / HEIGHT ≈ aspect`. The test `test_sf_bounds_aspect_ratio_matches_canvas` in `tests/test_renderer.py` validates this — update the expected ratio if you change cities.

**3. Activity filter** — `src/processor.py:filter_sf_runs()` uses `SF_BOUNDS` directly; no code change needed. The function name still says "sf" — rename it if you care.

**4. Map tiles** — `src/tiles.py` derives tile coordinates from the renderer bounds (`renderer.bounds`), which come from `SF_BOUNDS`. No change needed.

## Config knobs reference

### Canvas & bounds
- `SF_BOUNDS` — geographic bounding box. All projection math derives from this.
- `CANVAS_WIDTH_PX` / `CANVAS_HEIGHT_PX` — output canvas in pixels. Must match Mercator aspect ratio of `SF_BOUNDS`.
- `PRINT_DPI` — DPI tag written to the PNG (affects print size, not pixel count).

### Color
- `ROUTE_COLOR_RAMP` — list of `(t, [R, G, B])` stops. `t` is a normalized density value [0, 1] *after* gamma. With `GAMMA=0.4`, a single-run route lands around `t ≈ 0.45`, so set the first stop there to control the lowest visible color.
- `BG_COLOR` — background RGB.

### Line drawing
- `GAMMA` — applied as `norm = norm ** GAMMA` before color mapping. Values < 1 lift dim routes; values > 1 suppress them. Affects effective range of `HOT_BLOOM_THRESHOLD`.
- `ROUTE_LINE_THICKNESS` — base stroke width. Thicker lines need a wider `HOT_BLOOM_SIGMA_MULT` to maintain glow proportion.
- `ROUTE_LINE_THICKNESS_50_BONUS` / `ROUTE_LINE_THICKNESS_10_BONUS` — extra stroke for top 50%/10% density routes. Only the highest applicable bonus fires (non-stacking).

### Density expand (thickens heavy corridors)
- `DENSITY_EXPAND_SIGMA` — Gaussian spread (px). Larger = blurrier thickening.
- `DENSITY_EXPAND_STRENGTH` — screen-blend intensity of the expanded layer.
- `DENSITY_EXPAND_POWER` — exponent applied to norm before expanding; concentrates effect on peaks.

### Hot bloom (glow on peak-density routes)
- `HOT_BLOOM_THRESHOLD` — density cutoff (post-gamma) to trigger hot bloom. With `GAMMA=0.4`, keep this at 0.75+ to avoid bloom firing on medium routes.
- `HOT_BLOOM_SIGMA_MULT` — width of bloom Gaussian as a multiplier of `bloom_sigma_wide` in renderer.
- `HOT_BLOOM_STRENGTH` — screen-blend intensity of the bloom layer.

### Map
- `MAP_TILE_ZOOM` — tile zoom level. 16 = default (~600 tiles). 17 = sharper (~2400 tiles, slow first download).
- `MAP_TILE_OPACITY` — how much the street grid shows through (0 = invisible, 1 = full).

## Key implementation notes

**Float32 accumulation** (`src/renderer.py`): `cv2.line` on a float32 canvas clips values to [0, 1]. Routes drawn repeatedly would plateau. Fix: each run is drawn onto a zeroed temp buffer, then *added* to the main canvas (`canvas += buf`). This allows values > 1, which encode density. The canvas is only normalized to [0, 1] when converting to image.

**Bloom is disabled in `export.py`**: The `--no-bloom` flag in `export.py` always passes `bloom=False` to `to_image()`. Regular bloom was removed as it caused halos on single isolated pixels. `hot_bloom` is kept — it fires only above `HOT_BLOOM_THRESHOLD`.

**Density expand pass order** in `renderer.to_image()`: rasterize → density expand (Gaussian thickening) → gamma → color map → hot bloom → grain → vignette. Density expand runs on the raw float canvas before gamma so it operates in linear density space.

**Token refresh** (`src/fetcher.py:_update_env_tokens`): when the access token expires mid-fetch, `StravaClient.refresh_access_token()` POSTs to Strava and writes the new tokens back to `.env` in-place. It only updates existing lines — auth.py must have written them first.

## Environment

- Python 3.14 (Homebrew), `.venv/` virtual environment
- Run tests: `.venv/bin/pytest tests/ -v`
- Worktrees: `.worktrees/` (project-local, in `.gitignore`)
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md with architecture, new-city guide, and config reference"
```

---

### Task 6: Final check

**Step 1: Run full test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All tests PASS.

**Step 2: Verify `.env` is gitignored and `.env.example` is tracked**

```bash
git status .env .env.example
```

Expected: `.env` is untracked/ignored, `.env.example` is clean/tracked.

**Step 3: Commit any remaining untracked plan docs**

```bash
git add docs/plans/2026-03-05-bounds-fix.md docs/plans/2026-03-05-polish8.md
git commit -m "docs: commit previously untracked plan files"
```
