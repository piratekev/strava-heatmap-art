"""Real MP4 smoke tests with synthetic activities and offline map responses."""
import json
import os
from pathlib import Path
import re
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
@pytest.mark.parametrize("preview", [False, True])
def test_animation_cli_encodes_decodable_mp4_offline(tmp_path, mode, preview):
    write_synthetic_cache(tmp_path)
    output = tmp_path / "new-directory" / f"synthetic-{mode}.mp4"
    env = dict(os.environ, PYTHON_DOTENV_DISABLED="1", HOME=str(tmp_path))
    result = subprocess.run(
        [sys.executable, "-c", BOOTSTRAP, str(ROOT / "animate.py"),
         "--mode", mode, "--output", str(output), *(["--preview"] if preview else [])],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.is_file() and output.stat().st_size > 0
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=codec_name,pix_fmt,width,height,nb_read_frames,duration:format_tags=copyright",
         "-of", "json", str(output)],
        capture_output=True, text=True, check=True, timeout=10,
    )
    info = json.loads(probe.stdout)
    stream = info["streams"][0]
    assert info["format"]["tags"]["copyright"] == "© OpenStreetMap contributors, © CARTO"
    assert stream["codec_name"] == "h264"
    assert stream["pix_fmt"] == "yuv420p"
    width, height = (40, 50) if preview else (80, 100)
    assert (stream["width"], stream["height"]) == (width, height)
    assert float(stream["duration"]) > 0
    if mode == "parallel":
        assert int(stream["nb_read_frames"]) == (7 if preview else 5)
    else:
        assert int(stream["nb_read_frames"]) >= 5
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(output), "-f", "rawvideo",
         "-pix_fmt", "rgb24", "pipe:1"],
        capture_output=True, check=True, timeout=10,
    )
    frame_bytes = width * height * 3
    assert len(decoded.stdout) == int(stream["nb_read_frames"]) * frame_bytes
    assert decoded.stdout[:frame_bytes] != decoded.stdout[-frame_bytes:]
    assert int(re.search(r"\((\d+) frames at", result.stdout)[1]) == int(stream["nb_read_frames"])
    assert int(re.search(r"Done\. (\d+) frames", result.stdout)[1]) == int(stream["nb_read_frames"])
    assert not list(output.parent.glob(".animation-*"))


def invoke(tmp_path, *args, setup=""):
    bootstrap = BOOTSTRAP.replace('runpy.run_path(entry, run_name="__main__")',
                                  setup + '\nrunpy.run_path(entry, run_name="__main__")')
    return subprocess.run(
        [sys.executable, "-c", bootstrap, str(ROOT / "animate.py"), *args],
        cwd=tmp_path, env=dict(os.environ, PYTHON_DOTENV_DISABLED="1", HOME=str(tmp_path)),
        capture_output=True, text=True, timeout=30,
    )


@pytest.mark.parametrize("mode", ["sequential", "parallel"])
def test_cli_garmin_dispatch_and_all_config_forwarded(tmp_path, mode):
    write_synthetic_cache(tmp_path)
    setup = """
config.FETCH_SOURCE = "garmin"
config.ANIMATION_DOT_BRIGHTNESS = 3.5
import src.garmin, src.fetcher, src.animator
session = object()
def login():
    print("GARMIN LOGIN")
    return session
def fetch(client):
    assert client is session
    print("GARMIN FETCH")
src.garmin.login = login
src.garmin.fetch_garmin_activities = fetch
def unexpected(*args):
    raise AssertionError("Strava must not be used for Garmin")
src.fetcher.StravaClient.from_env = unexpected
def capture(runs, output, cfg):
    assert cfg.ANIMATION_DOT_BRIGHTNESS == 3.5
    assert cfg.ANIMATION_OUTPUT_RESOLUTION == (40, 50)
    assert cfg.ANIMATION_HOLD_SECONDS == 0
    assert cfg.ANIMATION_PARALLEL_HOLD_S == 1
    print("CONFIG FORWARDED")
src.animator.run_animation = capture
src.animator.run_parallel_animation = capture
"""
    result = invoke(tmp_path, "--fetch", "--preview", "--mode", mode, setup=setup)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "GARMIN LOGIN" in result.stdout and "GARMIN FETCH" in result.stdout
    assert "CONFIG FORWARDED" in result.stdout


@pytest.mark.parametrize("cache", [None, "[]", "{}", "invalid json", '[{"sport_type":"Ride"}]'])
def test_cli_missing_empty_or_invalid_cache_has_actionable_error(tmp_path, cache):
    if cache is not None:
        (tmp_path / "data").mkdir()
        (tmp_path / "data/activities.json").write_text(cache)
    result = invoke(tmp_path)
    assert result.returncode != 0
    assert "--fetch" in result.stderr
    assert "Traceback" not in result.stderr
    assert "Done." not in result.stdout


@pytest.mark.parametrize("setting,mode", [
    ("ANIMATION_DRAWING_SPEED_SLOW = 0", "sequential"),
    ("ANIMATION_FPS = float('nan')", "parallel"),
    ("ANIMATION_OUTPUT_RESOLUTION = (80, 99)", "sequential"),
    ("ANIMATION_PARALLEL_DURATION_S = 0", "parallel"),
])
def test_cli_validation_precedes_fetch_and_cache_loading(tmp_path, setting, mode):
    setup = f"""
config.{setting}
import src.sources
def unexpected(*args):
    raise AssertionError("Must validate before fetching")
src.sources.fetch_from_source = unexpected
"""
    result = invoke(tmp_path, "--fetch", "--mode", mode, setup=setup)
    assert result.returncode != 0
    assert setting.split(" =")[0] in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="Requires real ffmpeg")
@pytest.mark.parametrize("mode", ["sequential", "parallel"])
def test_cli_real_encoder_failure_never_reports_success(tmp_path, mode):
    write_synthetic_cache(tmp_path)
    output = tmp_path / "existing.mp4"
    output.write_bytes(b"existing video")
    setup = """
import subprocess
real_popen = subprocess.Popen
def failing_encoder(command, **kwargs):
    command[command.index("libx264")] = "intentionally_missing_encoder"
    return real_popen(command, **kwargs)
subprocess.Popen = failing_encoder
"""
    result = invoke(tmp_path, "--mode", mode, "--output", str(output), setup=setup)
    assert result.returncode != 0
    assert "ERROR:" in result.stderr
    assert "Done." not in result.stdout
    assert "Traceback" not in result.stderr
    assert output.read_bytes() == b"existing video"
    assert not list(tmp_path.glob(".animation-*"))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="Requires real ffmpeg")
@pytest.mark.parametrize("mode", ["sequential", "parallel"])
def test_cli_cancellation_reaps_real_encoder(tmp_path, mode):
    write_synthetic_cache(tmp_path)
    output = tmp_path / "existing.mp4"
    output.write_bytes(b"existing video")
    setup = f"""
import src.animator
real_open = src.animator.open_ffmpeg_pipe
def track(*args):
    proc = real_open(*args)
    Path("encoder.pid").write_text(str(proc.pid))
    return proc
def cancel(*args):
    raise KeyboardInterrupt
src.animator.open_ffmpeg_pipe = track
src.animator.{"paint_dot" if mode == "sequential" else "paint_dots_batch"} = cancel
"""
    result = invoke(tmp_path, "--mode", mode, "--output", str(output), setup=setup)
    assert result.returncode == 130, result.stdout + result.stderr
    assert "cancelled" in result.stderr
    assert "Traceback" not in result.stderr and "Done." not in result.stdout
    pid = int((tmp_path / "encoder.pid").read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert output.read_bytes() == b"existing video"
    assert not list(tmp_path.glob(".animation-*"))
