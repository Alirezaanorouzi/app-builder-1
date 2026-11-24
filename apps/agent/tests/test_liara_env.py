import os

from worker.liara_env import apply_liara_worker_env


def test_no_proxy_includes_liara(monkeypatch):
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.setenv("OPENAI_API_BASE", "https://example.com/v1")
    apply_liara_worker_env()
    assert "ai.liara.ir" in os.environ["NO_PROXY"]
    assert "OPENAI_API_BASE" not in os.environ