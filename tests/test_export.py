import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image
import polyline
import pytest


ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "export.py"

# Run the real entry point in a fresh process. Only remote services are faked;
# configuration loading, source dispatch, tiles, rendering, and saving stay real.
BOOTSTRAP = """
import io, json, runpy, sys, urllib.request
from pathlib import Path
import requests
from PIL import Image
entry = sys.argv[1]
sys.argv = [entry, *sys.argv[2:]]
sys.path.insert(0, str(Path(entry).parent))
def offline(*args, **kwargs):
    raise OSError("External network is disabled in CLI tests")
requests.sessions.Session.request = offline
urllib.request.urlopen = offline
class Response:
    status_code = 200
    headers = {}
    def raise_for_status(self):
        pass
    def json(self):
        return self.activities
def get(url, **kwargs):
    response = Response()
    if url.endswith("/athlete/activities"):
        print("TEST_STRAVA_PAGE", kwargs["params"]["page"])
        response.activities = (json.loads(Path("api.json").read_text())
                               if kwargs["params"]["page"] == 1 else [])
    elif "basemaps.cartocdn.com" in url:
        print("TEST_TILE_URL", url)
        buf = io.BytesIO()
        Image.new("RGB", (256, 256), (25, 25, 25)).save(buf, format="PNG")
        response.content = buf.getvalue()
    else:
        raise AssertionError("Unexpected HTTP endpoint")
    return response
requests.get = get
requests.Session.get = lambda self, *args, **kwargs: get(*args, **kwargs)
runpy.run_path(entry, run_name="__main__")
"""


def activity(city="sf", activity_id=1):
    coords = ([(37.77, -122.45), (37.78, -122.44)] if city == "sf"
              else [(40.76, -73.98), (40.78, -73.97)])
    return {"id": activity_id, "sport_type": "Run", "start_date": "2021-01-01T08:00:00Z",
            "distance": 1000, "total_elevation_gain": 20,
            "map": {"summary_polyline": polyline.encode(coords)}}


def write_cache(workspace, activities):
    (workspace / "data").mkdir(exist_ok=True)
    (workspace / "data" / "activities.json").write_text(json.dumps(activities))


def run_export(workspace, *args, entry=EXPORT):
    env = dict(os.environ, PYTHON_DOTENV_DISABLED="1", HOME=str(workspace))
    return subprocess.run([sys.executable, "-c", BOOTSTRAP, str(entry), *args],
                          cwd=workspace, env=env, text=True, capture_output=True, timeout=30)


def write_small_config(workspace, city="sf"):
    name = f"small_{city}"
    if city == "sf":
        source = "from config import *\nCANVAS_WIDTH_PX = 472\nCANVAS_HEIGHT_PX = 590\n"
    else:
        source = ("from nyc_config import *\nCANVAS_WIDTH_PX = 174\nCANVAS_HEIGHT_PX = 500\n"
                  "CANVAS_RENDER_WIDTH = 480\nCANVAS_RENDER_HEIGHT = 580\n"
                  "CANVAS_CROP_X = 176\nCANVAS_CROP_Y = 179\n"
                  "TYPOGRAPHY_X_OFFSET = -40\nLEGEND_Y_OFFSET = 4\n")
    (workspace / f"{name}_config.py").write_text(
        source + "MAP_TILE_ZOOM = 13\nMAP_PREVIEW_TILE_ZOOM = 12\n")
    return name


@pytest.mark.parametrize("city,size", [("sf", (472, 590)), ("nyc", (174, 500))])
@pytest.mark.parametrize("entry", [EXPORT, ROOT / "render.py"])
def test_preset_preview_cli_loads_real_city_configuration(tmp_path, city, size, entry):
    write_cache(tmp_path, [activity(city)])
    output = tmp_path / "new-directory" / "poster.png"
    args = ["--preview", "--output", str(output)]
    if city != "sf":
        args += ["--config", city]
    result = run_export(tmp_path, *args, entry=entry)
    assert result.returncode == 0, result.stdout + result.stderr
    with Image.open(output) as img:
        assert img.size == size
        assert img.mode == "RGB"
        assert img.info["dpi"] == pytest.approx((3, 3), abs=0.02)
        assert img.info["Copyright"] == "© OpenStreetMap contributors, © CARTO"
        assert np.asarray(img).max() > 150
    assert "dark_nolabels/11/" in result.stdout


@pytest.mark.parametrize("city,size", [("sf", (472, 590)), ("nyc", (174, 500))])
@pytest.mark.parametrize("preview", [False, True])
def test_cli_honors_configured_map_zoom_and_print_metadata(tmp_path, city, size, preview):
    write_cache(tmp_path, [activity(city)])
    name = write_small_config(tmp_path, city)
    output = tmp_path / "nested" / "poster.png"
    args = ["--config", name, "--output", str(output)]
    if preview:
        args.append("--preview")
    result = run_export(tmp_path, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    with Image.open(output) as img:
        assert img.size == (tuple(int(n * 0.1) for n in size) if preview else size)
        assert img.info["dpi"] == pytest.approx((3, 3) if preview else (285, 285), abs=0.02)
        assert "© CARTO" in img.info["Copyright"]
    assert f"dark_nolabels/{12 if preview else 13}/" in result.stdout


@pytest.mark.parametrize("cache_state", ["missing", "empty", "other-city", "non-run"])
def test_cli_reports_missing_or_unmatched_activities_without_traceback(tmp_path, cache_state):
    if cache_state != "missing":
        records = [] if cache_state == "empty" else [activity("nyc" if cache_state == "other-city" else "sf")]
        if cache_state == "non-run":
            records[0]["sport_type"] = "Ride"
        write_cache(tmp_path, records)
    result = run_export(tmp_path, "--preview")
    assert result.returncode == 2
    message = "No cached activities" if cache_state == "missing" else "No running activities"
    assert message in result.stderr
    assert "Traceback" not in result.stderr
    assert "TEST_TILE_URL" not in result.stdout
    assert not (tmp_path / "output").exists()


def test_cli_no_bloom_alias_disables_hot_bloom(tmp_path):
    write_cache(tmp_path, [activity()])
    args = ["--preview", "--no-map", "--no-grain", "--no-glow"]
    images = []
    for name, flags in (("default", []), ("alias", ["--no-bloom"]), ("explicit", ["--no-hot-bloom"])):
        output = tmp_path / f"{name}.png"
        result = run_export(tmp_path, *args, *flags, "--output", str(output))
        assert result.returncode == 0, result.stdout + result.stderr
        with Image.open(output) as img:
            assert "Copyright" not in img.info
            images.append(np.array(img))
    assert np.array_equal(images[1], images[2])
    assert not np.array_equal(images[0], images[1])


def test_cli_fetch_reconciles_delayed_uploads_without_duplicates_or_env_writes(tmp_path, monkeypatch):
    cached = activity(activity_id=1)
    delayed = activity(activity_id=2)
    write_cache(tmp_path, [cached, cached])
    (tmp_path / "data" / "cache_meta.json").write_text('{"last_fetched": 9999999999}')
    (tmp_path / "api.json").write_text(json.dumps([dict(cached, distance=2000), delayed]))
    env_file = tmp_path / ".env"
    env_file.write_text("STRAVA_ACCESS_TOKEN=sentinel\nSTRAVA_REFRESH_TOKEN=sentinel\n")
    original_env = env_file.read_bytes()
    for key in ("CLIENT_ID", "CLIENT_SECRET", "ACCESS_TOKEN", "REFRESH_TOKEN"):
        monkeypatch.setenv(f"STRAVA_{key}", "fake-value")
    for _ in range(2):
        result = run_export(tmp_path, "--fetch", "--preview", "--no-map")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "TEST_STRAVA_PAGE 1" in result.stdout
        assert "TEST_STRAVA_PAGE 2" in result.stdout
    records = json.loads((tmp_path / "data" / "activities.json").read_text())
    assert {a["id"]: a["distance"] for a in records} == {1: 2000, 2: 1000}
    assert len(records) == 2
    assert env_file.read_bytes() == original_env
    assert list((tmp_path / "output").glob("poster-preview-*.png"))


def test_readme_city_example_is_usable_and_preserves_mercator_aspect(tmp_path):
    readme = (ROOT / "README.md").read_text()
    example = readme.split("```python\n", 1)[1].split("```", 1)[0]
    namespace = {}
    exec(example, namespace)
    bounds = namespace["CITY_BOUNDS"]
    merc_span = (math.asinh(math.tan(math.radians(bounds["lat_max"]))) -
                 math.asinh(math.tan(math.radians(bounds["lat_min"]))))
    geo_aspect = math.radians(bounds["lng_max"] - bounds["lng_min"]) / merc_span
    assert namespace["CANVAS_WIDTH_PX"] / namespace["CANVAS_HEIGHT_PX"] == pytest.approx(geo_aspect, abs=0.001)
    assert namespace["CANVAS_ROTATION_DEGREES"] == 0
    (tmp_path / "my_city_config.py").write_text(example)
    write_cache(tmp_path, [activity("nyc")])
    output = tmp_path / "documented-example.png"
    result = run_export(tmp_path, "--config", "my_city", "--preview", "--output", str(output))
    assert result.returncode == 0, result.stdout + result.stderr
    with Image.open(output) as img:
        assert img.size == (int(namespace["CANVAS_WIDTH_PX"] * 0.1),
                            int(namespace["CANVAS_HEIGHT_PX"] * 0.1))
