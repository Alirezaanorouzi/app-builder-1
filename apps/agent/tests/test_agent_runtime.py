from __future__ import annotations

from worker.config import Settings


def _settings(**overrides) -> Settings:
    base = {
        "database_url": "postgresql://x",
        "conversation_dir": "/tmp/c",
        "workspace_staging_dir": "/tmp/w",
        "archive_local_dir": "/tmp/a",
        "worker_concurrency": 1,
        "poll_seconds": 1.0,
        "deploy_env": "dev",
        "sandbox_provider": "vercel",
        "sandbox_idle_seconds": 60,
        "sandbox_extend_when_remaining_seconds": 30,
        "run_event_max_bytes": 4096,
        "openhands_sdk_version": "1.63.1",
        "liara_api_key": "",
        "liara_base_url": "",
        "liara_default_model": "m",
        "liara_models": ("m",),
        "vercel_token": "t",
        "vercel_team_id": "team",
        "vercel_project_id": "prj",
        "vercel_base_snapshot_id": None,
        "vercel_preview_wait_seconds": 30,
        "max_iterations": 10,
        "templates_dir": "/tmp/templates",
        "agent_runtime": "auto",
        "agent_server_port": 8000,
        "oh_secret_key": None,
        "oh_session_api_key": None,
        "llm_proxy_public_url": None,
        "llm_proxy_admin_url": None,
        "llm_proxy_admin_key": None,
        "run_orphan_policy": "interrupt",
        "llm_remote_direct_liara": False,
    }
    base.update(overrides)
    return Settings(**base)


def test_remote_default_for_vercel_auto():
    s = _settings(sandbox_provider="vercel", agent_runtime="auto")
    assert s.uses_remote_agent() is True


def test_embedded_explicit():
    s = _settings(agent_runtime="embedded")
    assert s.uses_remote_agent() is False


def test_local_never_remote():
    s = _settings(sandbox_provider="local", agent_runtime="remote")
    assert s.uses_remote_agent() is False