from datetime import datetime, timedelta, timezone

from worker.session_expiry import measured_session_deadline, stored_lease_is_fresh
from worker.vercel_lease import (
    max_extend_headroom,
    runtime_session_remaining_seconds,
    seconds_to_extend,
)


class _FakeSession:
    def __init__(self, started_ms: int, limit: timedelta) -> None:
        self.started_at = started_ms
        self.execution_time_limit = limit


def test_seconds_to_extend_when_remaining_high():
    assert (
        seconds_to_extend(
            remaining=400.0,
            idle_seconds=600,
            when_remaining_below=300,
            force=False,
        )
        is None
    )


def test_seconds_to_extend_force_tops_up_runway():
    add = seconds_to_extend(
        remaining=400.0,
        idle_seconds=600,
        when_remaining_below=300,
        force=True,
    )
    assert add is not None
    assert add == 201


def test_seconds_to_extend_force_skips_when_already_fresh():
    assert (
        seconds_to_extend(
            remaining=598.0,
            idle_seconds=600,
            when_remaining_below=300,
            force=True,
        )
        is None
    )


def test_seconds_to_extend_tops_up_runway():
    add = seconds_to_extend(
        remaining=100.0,
        idle_seconds=600,
        when_remaining_below=300,
        force=False,
    )
    assert add is not None
    assert add >= 500


def test_seconds_to_extend_respects_session_cap():
    assert (
        seconds_to_extend(
            remaining=100.0,
            idle_seconds=600,
            when_remaining_below=300,
            force=True,
            max_session_seconds=2700,
            current_limit_seconds=2690,
        )
        == 10
    )


def test_max_extend_headroom_at_cap():
    import time

    now_ms = int(time.time() * 1000)
    s = _FakeSession(now_ms - 60_000, timedelta(seconds=2700))
    assert max_extend_headroom(s, max_session_seconds=2700) == 0


def test_runtime_session_remaining():
    import time

    now_ms = int(time.time() * 1000)
    started = now_ms - 60_000
    s = _FakeSession(started, timedelta(seconds=600))
    rem = runtime_session_remaining_seconds(s)
    assert rem is not None
    assert 520 < rem < 560


def test_measured_deadline_is_started_plus_capped_limit():
    now_ms = 1_700_000_000_000
    session = _FakeSession(now_ms, timedelta(seconds=5000))
    deadline = measured_session_deadline(session, max_session_seconds=2700)
    assert deadline == datetime.fromtimestamp(now_ms / 1000.0 + 2700, tz=timezone.utc)


def test_stored_lease_fresh_uses_real_deadline():
    future = datetime.now(timezone.utc) + timedelta(seconds=400)
    assert stored_lease_is_fresh(future, renew_when_remaining_below=300) is True
    soon = datetime.now(timezone.utc) + timedelta(seconds=100)
    assert stored_lease_is_fresh(soon, renew_when_remaining_below=300) is False
    assert stored_lease_is_fresh(None, renew_when_remaining_below=300) is False