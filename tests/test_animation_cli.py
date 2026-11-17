"""Real MP4 smoke tests with synthetic activities and offline map responses."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import polyline
import pytest


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = """
import io, runpy, sys, urllib.request
from pathlib import Path
import requests
from PIL import Image
entry = sys.argv[1]
sys.argv = [entry, *sys.argv[2:]]
sys.path.insert(0, str(Path(entry).parent))
import config
config.ANIMATION_FPS = 4
config.ANIMATION_OUTPUT_RESOLUTION = (80, 100)
config.ANIMATION_DRAWING_SPEED = 160
config.ANIMATION_DRAWING_SPEED_SLOW = 160
config.ANIMATION_SPEED_RAMP_RUNS = 0
config.ANIMATION_DOT_RADIUS = 1
config.ANIMATION_DOT_BLUR = 0
config.ANIMATION_HOLD_SECONDS = 0.25
config.ANIMATION_PARALLEL_DURATION_S = 0.5
config.ANIMATION_PARALLEL_HOLD_S = 0.5
def offline(*args, **kwargs):
    raise AssertionError("Unexpected network request in animation smoke test")
requests.sessions.Session.request = offline
urllib.request.urlopen = offline
class Response:
    def raise_for_status(self):
        pass
def get(url, **kwargs):
    assert "basemaps.cartocdn.com" in url
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (20, 20, 20)).save(buf, format="PNG")
    response = Response()
    response.content = buf.getvalue()
    return response
requests.Session.get = lambda self, *args, **kwargs: get(*args, **kwargs)
import src.typography
src.typography._download_font = lambda *args, **kwargs: None
runpy.run_path(entry, run_name="__main__")
"""


def write_synthetic_cache(workspace):
    records = [
        {"id": 1, "sport_type": "Run", "start_date": "2021-01-01T08:00:00Z",
         "distance": 4000, "total_elevation_gain": 20,
         "map": {"summary_polyline": polyline.encode(
             [(37.74, -122.50), (37.80, -122.44)])}},
        {"id": 2, "sport_type": "Run", "start_date": "2022-01-01T08:00:00Z",
         "distance": 3000, "total_elevation_gain": 10,
         "map": {"summary_polyline": polyline.encode(
             [(37.76, -122.48), (37.82, -122.40)])}},
    ]
    (workspace / "data").mkdir()
    (workspace / "data/activities.json").write_text(json.dumps(records))


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="Animation smoke tests require ffmpeg and ffprobe",
)
@pytest.mark.parametrize("mode", ["sequential", "parallel"])
def test_animation_cli_encodes_decodable_mp4_offline(tmp_path, mode):
    write_synthetic_cache(tmp_path)
    output = tmp_path / f"synthetic-{mode}.mp4"
    env = dict(os.environ, PYTHON_DOTENV_DISABLED="1", HOME=str(tmp_path))
    result = subprocess.run(
        [sys.executable, "-c", BOOTSTRAP, str(ROOT / "animate.py"),
         "--mode", mode, "--output", str(output)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.is_file() and output.stat().st_size > 0
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=codec_name,pix_fmt,width,height,nb_read_frames,duration",
         "-of", "json", str(output)],
        capture_output=True, text=True, check=True, timeout=10,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream["codec_name"] == "h264"
    assert stream["pix_fmt"] == "yuv420p"
    assert (stream["width"], stream["height"]) == (80, 100)
    assert float(stream["duration"]) > 0
    if mode == "parallel":
        assert int(stream["nb_read_frames"]) == 5  # opening + drawing + hold
    else:
        assert int(stream["nb_read_frames"]) >= 5
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(output), "-f", "rawvideo",
         "-pix_fmt", "rgb24", "pipe:1"],
        capture_output=True, check=True, timeout=10,
    )
    frame_bytes = 80 * 100 * 3
    assert len(decoded.stdout) == int(stream["nb_read_frames"]) * frame_bytes
    assert decoded.stdout[:frame_bytes] != decoded.stdout[-frame_bytes:]
