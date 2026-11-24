import re
import uuid
from unittest.mock import patch

from worker.run_timeline import LOG_PREFIX, RunTimeline


def test_timeline_marks_record_step_and_total_ms() -> None:
    rid = uuid.uuid4()
    with patch("worker.run_timeline.time.perf_counter", side_effect=[0.0, 0.05, 0.2]):
        tl = RunTimeline(rid)
        tl.mark("a")
        tl.mark("b")
    payload = tl.phases_payload()
    assert payload[0]["phase"] == "a"
    assert payload[0]["total_ms"] == 50
    assert payload[1]["step_ms"] == 150


def test_timeline_once_skips_duplicate_first_token() -> None:
    rid = uuid.uuid4()
    with patch("worker.run_timeline.time.perf_counter", side_effect=[0.0, 0.1, 0.11, 0.12]):
        tl = RunTimeline(rid)
        tl.mark("first_token", once=True)
        tl.mark("first_token", once=True)
    names = [p["phase"] for p in tl.phases_payload()]
    assert names.count("first_token") == 1


def test_log_line_format_for_grep() -> None:
    rid = uuid.uuid4()
    with patch("worker.run_timeline.logger") as log:
        with patch("worker.run_timeline.time.perf_counter", side_effect=[1.0, 1.5]):
            tl = RunTimeline(rid)
            tl.mark("sdk_import_done")
    assert log.info.called
    args = log.info.call_args[0]
    assert args[1] == LOG_PREFIX
    assert args[3] == "sdk_import_done"
    assert args[4] == 500.0  # total_ms
    assert args[5] == 500.0  # step_ms
