from datetime import timedelta

from worker.vercel_lease import runtime_session_remaining_seconds, seconds_to_extend


class _FakeSession:
    def __init__(self, started_ms: int, limit: timedelta) -> None:
        self.started_at = started_ms
        self.execution_time_limit = limit


def test_seconds_to_extend_when_remaining_high():
    assert seconds_to_extend(remaining=400.0, idle_seconds=600, when_remaining_below=300, force=False) is None


def test_seconds_to_extend_force():
    assert seconds_to_extend(remaining=400.0, idle_seconds=600, when_remaining_below=300, force=True) == 600


def test_seconds_to_extend_tops_up_runway():
    add = seconds_to_extend(remaining=100.0, idle_seconds=600, when_remaining_below=300, force=False)
    assert add is not None
    assert add >= 500


def test_runtime_session_remaining():
    import time

    now_ms = int(time.time() * 1000)
    started = now_ms - 60_000
    s = _FakeSession(started, timedelta(seconds=600))
    rem = runtime_session_remaining_seconds(s)
    assert rem is not None
    assert 520 < rem < 560