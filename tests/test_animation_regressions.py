"""Regression coverage for animation correctness and encoder lifecycle."""
import io
import math
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import Image
import pytest

import config as style
from src import animator
from src.renderer import StravaRenderer


def config(**overrides):
    values = dict(
        ANIMATION_FPS=4, ANIMATION_OUTPUT_RESOLUTION=(64, 80),
        ANIMATION_DRAWING_SPEED=5, ANIMATION_DRAWING_SPEED_SLOW=5,
        ANIMATION_SPEED_RAMP_RUNS=2, ANIMATION_DOT_RADIUS=1,
        ANIMATION_DOT_BLUR=0, ANIMATION_DOT_BRIGHTNESS=2,
        ANIMATION_HOLD_SECONDS=0.25, ANIMATION_PARALLEL_DURATION_S=2,
        ANIMATION_PARALLEL_HOLD_S=0.25,
    )
    return SimpleNamespace(**(values | overrides))


def run(coords=None, date="2020-01-01T00:00:00Z"):
    return dict(
        coords=coords or [(37.75, -122.49), (37.81, -122.41),
                          (37.75, -122.49), (37.75, -122.49)],
        start_date=date, distance=4000,
    )


class FakeInput:
    def __init__(self):
        self.buffer = io.BytesIO()

    def write(self, value):
        return self.buffer.write(value)

    def getvalue(self):
        return self.buffer.getvalue()

    def close(self):
        self.was_closed = True


class FakeProc:
    def __init__(self, path, status=0):
        Path(path).write_bytes(b"synthetic video")
        self.stdin = FakeInput()
        self.status = status
        self.waited = False
        self.terminated = False
        self.killed = False

    def wait(self, timeout=None):
        self.waited = True
        return self.status

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


@pytest.fixture
def capture(monkeypatch, tmp_path):
    import src.tiles
    import src.typography

    monkeypatch.setattr(animator, "check_ffmpeg", lambda: None)
    monkeypatch.setattr(src.tiles, "fetch_map_tile",
                        lambda **kw: Image.new("RGB", kw["target_size"], (40, 40, 40)))
    monkeypatch.setattr(src.typography, "_download_font", lambda *a: None)
    monkeypatch.setattr(src.typography, "render_legend", lambda img, **kw: img)
    monkeypatch.setattr(animator, "render_animation_typography", lambda img, *a, **kw: img)
    for key in ("MAP_TILE_OPACITY", "DENSITY_EXPAND_STRENGTH",
                "HOT_BLOOM_STRENGTH", "HOT_BLOOM_SIGMA_MULT"):
        monkeypatch.setattr(style, key, 0)
    monkeypatch.setattr(style, "BG_COLOR", [0, 0, 0])

    original = animator.canvas_to_rgb

    def perform(mode, runs, cfg=None, stats=None):
        cfg = cfg or config()
        snapshots, anchors, procs = [], [], []

        def record(canvas, log_max, *args, **kwargs):
            snapshots.append(canvas.copy())
            anchors.append(log_max)
            return original(canvas, log_max, *args, **kwargs)

        def encoder(path, *args):
            proc = FakeProc(path)
            procs.append(proc)
            return proc

        monkeypatch.setattr(animator, "canvas_to_rgb", record)
        monkeypatch.setattr(animator, "open_ffmpeg_pipe", encoder)
        output = tmp_path / f"{mode}.mp4"
        entry = animator.run_animation if mode == "sequential" else animator.run_parallel_animation
        typography = animator.render_animation_typography

        def observe(image, date, count, miles, *args, **kwargs):
            if stats is not None:
                stats.append((date, count, miles))
            return typography(image, date, count, miles, *args, **kwargs)

        with monkeypatch.context() as local:
            local.setattr(animator, "render_animation_typography", observe)
            entry(runs, output, cfg)
        w, h = cfg.ANIMATION_OUTPUT_RESOLUTION
        frames = np.frombuffer(procs[0].stdin.getvalue(), np.uint8).reshape(-1, h, w, 3)
        assert procs[0].waited and procs[0].stdin.was_closed
        assert output.read_bytes() == b"synthetic video"
        return snapshots, anchors, frames

    return perform


def static_reference(runs, width, height, thickness):
    """Independent full-frame OpenCV masks: one union per run, added together."""
    renderer = StravaRenderer(width=width, height=height)
    expected = np.zeros((height, width), np.float32)
    for record in runs:
        points = [renderer.project(*point) for point in record["coords"]]
        mask = np.zeros_like(expected)
        for a, b in zip(points, points[1:]):
            cv2.line(mask, a, b, 1.0, thickness, lineType=cv2.LINE_AA)
        expected += mask
    return expected


@pytest.mark.parametrize("thickness", [1, 2, 3, 4, 7])
def test_sparse_raster_matches_full_canvas_including_clipping(thickness):
    rng = np.random.default_rng(714)
    for _ in range(30):
        points = [tuple(map(int, p)) for p in rng.integers(-20, 90, (8, 2))]
        points += [points[-1], points[0]]
        mask = np.zeros((80, 64), np.float32)
        for a, b in zip(points, points[1:]):
            cv2.line(mask, a, b, 1.0, thickness, lineType=cv2.LINE_AA)
        pixels = animator._rasterize_route(points, 64, 80, thickness)
        canvas = np.zeros_like(mask)
        for distance in np.linspace(0, animator._path_length_px(points), 17):
            before = canvas.copy()
            pixels.reveal(canvas, distance)
            assert np.all(canvas >= before)
            assert np.all(canvas <= mask)
        pixels.reveal(canvas, 0, complete=True)
        np.testing.assert_array_equal(canvas, mask)


@pytest.mark.parametrize("mode", ["sequential", "parallel"])
@pytest.mark.parametrize("speed", [1, 5, 160])
@pytest.mark.parametrize("fps", [2, 10])
def test_final_density_and_anchor_independent_of_speed_and_fps(capture, mode, speed, fps):
    records = [run(), run(date="2021-01-01T00:00:00Z")]
    cfg = config(ANIMATION_FPS=fps, ANIMATION_DRAWING_SPEED=speed,
                 ANIMATION_DRAWING_SPEED_SLOW=speed, ANIMATION_PARALLEL_DURATION_S=10 / fps,
                 ANIMATION_HOLD_SECONDS=1 / fps, ANIMATION_PARALLEL_HOLD_S=1 / fps)
    snapshots, anchors, _ = capture(mode, records, cfg)
    thickness = max(1, round(style.ROUTE_LINE_THICKNESS * 64 / style.CANVAS_WIDTH_PX))
    expected = static_reference(records, 64, 80, thickness)
    assert expected.max() == 2  # identical routes remain separate visits
    np.testing.assert_array_equal(snapshots[-1], expected)
    assert anchors == pytest.approx([math.log1p(2)] * len(anchors))
    for before, after in zip(snapshots, snapshots[1:]):
        assert np.all(after >= before)
        assert np.all(after <= expected)


@pytest.mark.parametrize("mode", ["sequential", "parallel"])
def test_completed_frame_matches_same_resolution_static_effects_reference(capture, mode):
    from src.typography import render_attribution

    records = [run(), run(date="2021-01-01T00:00:00Z")]
    snapshots, _, frames = capture(mode, records)
    renderer = StravaRenderer(width=64, height=80)
    renderer.canvas[:] = static_reference(records, 64, 80, 1)
    rgb = renderer.to_image(
        bloom=False, glow=False, vignette=False, grain=False,
        hot_bloom=False, density_expand=False,
    )
    # The reference bypasses both the animation sparse rasterizer and color mapper.
    expected = np.array(render_attribution(
        Image.fromarray(rgb), style.MAP_ATTRIBUTION, style.MAP_FONT_PATH,
    ))
    np.testing.assert_array_equal(snapshots[-1], renderer.canvas)
    np.testing.assert_array_equal(frames[-1], expected)


def test_cursor_finishes_after_ten_single_pixel_steps():
    seg, t = 0, 0.0
    for _ in range(10):
        seg, t, _ = animator.advance_cursor([(0, 0), (10, 0)], seg, t, 1)
    assert (seg, t) == (0, 1.0)


@pytest.mark.parametrize("hold_frames", [0, 1, 4])
def test_parallel_final_stats_visible_for_zero_one_and_many_holds(capture, monkeypatch, hold_frames):
    def stats(image, *args, **kwargs):
        image.putpixel((1, 1), (255, 0, 0))
        return image

    monkeypatch.setattr(animator, "render_animation_typography", stats)
    cfg = config(ANIMATION_PARALLEL_HOLD_S=hold_frames / 4)
    _, _, frames = capture("parallel", [run()], cfg)
    np.testing.assert_array_equal(frames[-1, 1, 1], [255, 0, 0])
    assert len(frames) == 1 + 8 + hold_frames
    np.testing.assert_array_equal(frames[0, 1, 1], [0, 0, 0])


@pytest.mark.parametrize("mode", ["sequential", "parallel"])
def test_map_opacity_zero_and_attribution_on_every_frame(capture, mode):
    from src.typography import render_attribution

    _, _, frames = capture(mode, [run()])
    overlay = np.asarray(render_attribution(
        Image.new("RGBA", (64, 80)), style.MAP_ATTRIBUTION, style.MAP_FONT_PATH,
    ))
    foreground = np.any(overlay[:, :, :3] > 0, axis=2) & (overlay[:, :, 3] > 0)
    assert foreground.any()
    baseline = np.asarray(render_attribution(
        Image.new("RGB", (64, 80)), style.MAP_ATTRIBUTION, style.MAP_FONT_PATH,
    ))
    assert baseline.max() > 100
    for frame in frames:
        assert np.all(frame[foreground] >= baseline[foreground])
    assert np.all(frames[0, 0, 0] == 0)  # not the synthetic map's RGB 40


@pytest.mark.parametrize("mode", ["sequential", "parallel"])
def test_collapsed_projected_route_preserves_cached_mileage(capture, mode):
    coords = [(37.77, -122.45), (37.770001, -122.450001),
              (37.770002, -122.450002)]
    renderer = StravaRenderer(width=64, height=80)
    assert len({renderer.project(*p) for p in coords}) == 1
    measured = []
    record = run(coords)
    record["distance"] = 4023.36  # 2.5 cached miles, despite a near-zero GPS path
    snapshots, _, _ = capture(mode, [record], stats=measured)
    assert measured[-1][1:] == (1, 2)
    assert snapshots[-1].sum() == 1


@pytest.mark.parametrize("fps", [1, 4])
@pytest.mark.parametrize("speed", [1, 160])
@pytest.mark.parametrize("hold_frames", [0, 1, 3])
@pytest.mark.parametrize("trailing_coords", [[], [(37.77, -122.45)]])
def test_modes_share_final_cached_distance_count_and_activity_population(
    capture, fps, speed, hold_frames, trailing_coords,
):
    records = [
        run([(37.77, -122.45)], date="2018-01-01"),
        run(date="2020-01-01"),
        run([(37.77, -122.45), (37.77, -122.45)], date="2021-01-01"),
        run([(37.77, -122.45)], date="2023-01-01"),
    ]
    for record, meters in zip(records, [2000, 5000, 7000, 3000]):
        record["distance"] = meters
    records[-1]["coords"] = trailing_coords
    expected = math.floor(17000 / animator.METERS_PER_MILE)
    cfg = config(
        ANIMATION_FPS=fps, ANIMATION_DRAWING_SPEED=speed, ANIMATION_DRAWING_SPEED_SLOW=speed,
        ANIMATION_HOLD_SECONDS=hold_frames / fps, ANIMATION_PARALLEL_HOLD_S=hold_frames / fps,
    )
    sequential, parallel = [], []
    capture("sequential", records, cfg, stats=sequential)
    capture("parallel", records, cfg, stats=parallel)
    assert sequential[0][1:] == (0, 0)
    assert sequential[-1] == ("Jan 2023", 4, expected)
    assert parallel[-1] == ("2018 – 2023", 4, expected)
    miles = [row[2] for row in sequential]
    assert miles == sorted(miles)
    assert all(0 <= value <= expected for value in miles)
    # The first single-point run is included by the next drawing frame.
    assert sequential[1][1] == 2
    assert sequential[1][2] >= math.floor(2000 / animator.METERS_PER_MILE)


def test_sequential_cached_mileage_advances_with_route_progress(capture, monkeypatch):
    monkeypatch.setattr(StravaRenderer, "project", lambda self, lat, lng: (int(lng), int(lat)))
    record = run([(10, 4), (10, 24)])
    record["distance"] = 10 * animator.METERS_PER_MILE
    stats = []
    capture("sequential", [record], config(), stats=stats)
    # First step covers five of twenty pixels: 2.5 of ten cached miles.
    assert stats[0][1:] == (0, 0)
    assert stats[1][1:] == (1, 2)
    assert stats[-1][1:] == (1, 10)
    assert any(2 < miles < 10 for _, _, miles in stats)


def test_sequential_fade_and_hold_reuse_completed_frame_and_font(capture, monkeypatch):
    calls = dict(frame=0, stats=0, font=0)
    for name, key in (("frame", "frame"), ("stats", "stats")):
        original = getattr(animator._AnimationScene, name)

        def count(*args, _original=original, _key=key, **kwargs):
            calls[_key] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(animator._AnimationScene, name, count)
    load_font = animator._load_font

    def font(*args):
        calls["font"] += 1
        return load_font(*args)

    monkeypatch.setattr(animator, "_load_font", font)
    record = run([(37.77, -122.45), (37.77, -122.45)])
    cfg = config(ANIMATION_FPS=60, ANIMATION_HOLD_SECONDS=3)
    _, _, frames = capture("sequential", [record], cfg)
    assert len(frames) == 212  # opening + drawing + 30 fade + 180 hold
    assert calls == dict(frame=3, stats=3, font=1)
    # Reusing a credited array must not paint antialiased attribution repeatedly.
    np.testing.assert_array_equal(frames[-180:], np.repeat(frames[-1:], 180, axis=0))


@pytest.mark.parametrize("mode", ["sequential", "parallel"])
def test_reported_frame_counts_match_actual_output(capture, capsys, mode):
    cfg = config(ANIMATION_DRAWING_SPEED=8, ANIMATION_DRAWING_SPEED_SLOW=2)
    _, _, frames = capture(mode, [run(), run(date="2021-01-01")], cfg)
    output = capsys.readouterr().out
    assert int(re.search(r"\((\d+) frames at", output)[1]) == len(frames)
    assert int(re.search(r"Done\. (\d+) frames", output)[1]) == len(frames)


@pytest.mark.parametrize("name,value,mode", [
    ("ANIMATION_DRAWING_SPEED", 0, "sequential"),
    ("ANIMATION_DRAWING_SPEED_SLOW", 0, "sequential"),
    ("ANIMATION_DRAWING_SPEED", float("inf"), "sequential"),
    ("ANIMATION_DRAWING_SPEED_SLOW", float("nan"), "sequential"),
    ("ANIMATION_FPS", 0, "parallel"),
    ("ANIMATION_FPS", float("nan"), "sequential"),
    ("ANIMATION_FPS", float("inf"), "parallel"),
    ("ANIMATION_OUTPUT_RESOLUTION", (64, 79), "parallel"),
    ("ANIMATION_OUTPUT_RESOLUTION", (0, 80), "sequential"),
    ("ANIMATION_OUTPUT_RESOLUTION", (64.0, 80), "parallel"),
    ("ANIMATION_OUTPUT_RESOLUTION", None, "sequential"),
    ("ANIMATION_PARALLEL_DURATION_S", 0, "parallel"),
    ("ANIMATION_PARALLEL_DURATION_S", 0.01, "parallel"),
    ("ANIMATION_PARALLEL_HOLD_S", -1, "parallel"),
    ("ANIMATION_HOLD_SECONDS", -1, "sequential"),
    ("ANIMATION_DOT_RADIUS", -1, "sequential"),
    ("ANIMATION_DOT_BLUR", -1, "parallel"),
    ("ANIMATION_DOT_BRIGHTNESS", float("inf"), "sequential"),
    ("ANIMATION_SPEED_RAMP_RUNS", 1.5, "sequential"),
])
def test_invalid_config_rejected_before_assets_or_encoder(monkeypatch, tmp_path, name, value, mode):
    def unexpected(*args, **kwargs):
        raise AssertionError("Validation must happen before checking assets/encoder")
    monkeypatch.setattr(animator, "check_ffmpeg", unexpected)
    entry = animator.run_animation if mode == "sequential" else animator.run_parallel_animation
    with pytest.raises(ValueError, match=name):
        entry([run()], tmp_path / "output.mp4", config(**{name: value}))


@pytest.mark.parametrize("failure", [
    "status", "close", "write", "cancel", "empty", "timeout", "cancel_close", "cancel_wait",
])
def test_encoder_failures_reap_process_and_preserve_existing_output(monkeypatch, tmp_path, failure):
    output = tmp_path / "nested/movie.mp4"
    output.parent.mkdir()
    output.write_bytes(b"existing video")
    procs = []

    def encoder(path, *args):
        proc = FakeProc(path, status=7 if failure == "status" else 0)
        if failure == "empty":
            Path(path).write_bytes(b"")
        if failure == "close":
            def broken_close():
                raise BrokenPipeError("encoder exited")
            proc.stdin.close = broken_close
        if failure == "timeout":
            def timeout_wait(timeout=None):
                proc.waited = True
                if not proc.killed:
                    raise subprocess.TimeoutExpired("ffmpeg", timeout)
                return -9
            proc.wait = timeout_wait
        if failure == "cancel_close":
            real_close = proc.stdin.close
            def cancel_close():
                proc.stdin.close = real_close
                raise KeyboardInterrupt
            proc.stdin.close = cancel_close
        if failure == "cancel_wait":
            real_wait = proc.wait
            def cancel_wait(timeout=None):
                proc.wait = real_wait
                raise KeyboardInterrupt
            proc.wait = cancel_wait
        procs.append(proc)
        return proc

    monkeypatch.setattr(animator, "open_ffmpeg_pipe", encoder)
    expected = KeyboardInterrupt if failure.startswith("cancel") else (
        BrokenPipeError if failure == "write" else RuntimeError
    )
    with pytest.raises(expected):
        with animator._video_pipe(output, 64, 80, 4) as pipe:
            if failure == "write":
                raise BrokenPipeError("write failed")
            if failure == "cancel":
                raise KeyboardInterrupt
            pipe.write(b"frame")
    assert procs[0].waited
    assert output.read_bytes() == b"existing video"
    assert list(output.parent.glob(".animation-*")) == []
    if failure == "write" or failure.startswith("cancel"):
        assert procs[0].terminated
    if failure == "timeout":
        assert procs[0].killed

@pytest.mark.parametrize("brightness", [0.5, 2.0])
@pytest.mark.parametrize("alpha", [0.0, 0.25, 1.0])
@pytest.mark.parametrize("blur", [0, 2])
def test_shared_dot_renderer_preserves_brightness_then_alpha(brightness, alpha, blur):
    from scipy.ndimage import gaussian_filter

    expected = np.full((24, 24, 3), 37, np.uint8)
    actual = expected.copy()
    if alpha > 0:
        layer = np.zeros((24, 24), np.float32)
        cv2.circle(layer, (12, 12), 3, 255.0, thickness=-1)
        if blur:
            layer = gaussian_filter(layer, sigma=blur)
        layer = np.clip(layer * brightness, 0, 255) * alpha
        for channel in range(3):
            values = expected[:, :, channel].astype(np.float32)
            expected[:, :, channel] = np.clip(
                255 - (255 - values) * (255 - layer) / 255, 0, 255,
            ).astype(np.uint8)
    animator.paint_dot(actual, 12, 12, 3, blur, brightness, alpha)
    np.testing.assert_array_equal(actual, expected)
