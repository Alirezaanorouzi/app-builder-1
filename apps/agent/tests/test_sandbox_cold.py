from datetime import datetime, timedelta, timezone

from worker.sandbox_cold import is_session_expired, stack_considered_warm


def test_session_expired():
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    row = {"session_expires_at": past, "status": "running", "agent_server_status": "ready"}
    assert is_session_expired(row)
    assert not stack_considered_warm(row)


def test_session_active():
    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    row = {
        "session_expires_at": future,
        "status": "running",
        "agent_server_status": "ready",
        "preview_url": "https://x",
        "agent_server_url": "https://y",
        "agent_session_api_key": "k",
    }
    assert not is_session_expired(row)