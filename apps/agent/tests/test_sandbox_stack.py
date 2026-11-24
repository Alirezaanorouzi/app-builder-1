from __future__ import annotations

from worker.sandbox_stack import is_db_stack_warm, verify_agent_server_live


def test_is_db_stack_warm_requires_all_fields():
    assert is_db_stack_warm(None) is False
    assert is_db_stack_warm({"provider": "local", "status": "running"}) is False
    warm = {
        "provider": "vercel",
        "status": "running",
        "agent_server_status": "ready",
        "preview_url": "https://preview.example",
        "agent_server_url": "https://agent.example",
        "agent_session_api_key": "secret",
    }
    assert is_db_stack_warm(warm) is True
    assert is_db_stack_warm({**warm, "agent_server_status": "starting"}) is False


def test_verify_agent_server_live_requires_credentials(monkeypatch):
    called: list[tuple] = []

    def fake_ready(url, key, timeout=5.0):
        called.append((url, key, timeout))
        return True

    monkeypatch.setattr("worker.sandbox_stack.ready_ok", fake_ready)
    row = {
        "agent_server_url": "https://agent.example/",
        "agent_session_api_key": "k",
    }
    assert verify_agent_server_live(row) is True
    assert called == [("https://agent.example", "k", 5.0)]
    assert verify_agent_server_live({"agent_server_url": "", "agent_session_api_key": "k"}) is False