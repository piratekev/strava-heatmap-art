import sys

import combo_config
sys.modules["config"] = combo_config

from src.combo_animator import schedule_start_frames, live_lines


def test_schedule_even_and_finishes_on_time():
    starts = schedule_start_frames(5, drawing_frames=100, draw_frames=20)
    assert starts == [0, 20, 40, 60, 80]
    assert starts[-1] + 20 == 100


def test_schedule_edge_cases():
    assert schedule_start_frames(0, 100, 10) == []
    assert schedule_start_frames(1, 100, 10) == [0]
    assert schedule_start_frames(3, 5, 10) == [0, 0, 0]   # draw longer than timeline


def test_live_lines_before_and_after_start():
    s = {"first_year": "2021", "last_year": None, "count": 0, "meters": 0.0}
    assert live_lines(s, "runs") == ["2021", "0 runs", "0 mi"]
    s.update(last_year="2024", count=1234, meters=1609.344 * 2500.4)
    assert live_lines(s, "rides") == ["2021 – 2024", "1,234 rides", "2,500 mi"]
