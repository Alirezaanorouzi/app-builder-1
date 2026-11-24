from __future__ import annotations

import pytest

from worker.llm_proxy import is_public_https_url, llm_base_url_for_sandbox
from worker.config import Settings


def test_is_public_https_url_rejects_localhost():
    assert is_public_https_url("https://localhost/v1") is False
    assert is_public_https_url("http://example.com/v1") is False
    assert is_public_https_url("https://llm.example.com") is True


def test_llm_base_url_appends_v1():
    s = Settings(
        database_url="x",
        conversation_dir="/c",
        workspace_staging_dir="/w",
        archive_local_dir="/a",
        worker_concurrency=1,
        poll_seconds=1.0,
        deploy_env="dev",
        sandbox_provider="vercel",
        sandbox_idle_seconds=60,
        run_event_max_bytes=4096,
        openhands_sdk_version="1.63.1",
        liara_api_key="",
        liara_base_url="",
        liara_default_model="m",
        liara_models=("m",),
        vercel_token=None,
        vercel_team_id=None,
        vercel_project_id=None,
        vercel_base_snapshot_id=None,
        vercel_preview_wait_seconds=30,
        max_iterations=10,
        templates_dir="/t",
        agent_runtime="remote",
        agent_server_port=8000,
        oh_secret_key=None,
        oh_session_api_key=None,
        llm_proxy_public_url="https://proxy.example.com",
        llm_proxy_admin_url=None,
        llm_proxy_admin_key=None,
        run_orphan_policy="interrupt",
        llm_remote_direct_liara=False,
    )
    assert llm_base_url_for_sandbox(s) == "https://proxy.example.com/v1"


def test_llm_base_url_requires_public():
    s = Settings(
        database_url="x",
        conversation_dir="/c",
        workspace_staging_dir="/w",
        archive_local_dir="/a",
        worker_concurrency=1,
        poll_seconds=1.0,
        deploy_env="dev",
        sandbox_provider="vercel",
        sandbox_idle_seconds=60,
        run_event_max_bytes=4096,
        openhands_sdk_version="1.63.1",
        liara_api_key="",
        liara_base_url="",
        liara_default_model="m",
        liara_models=("m",),
        vercel_token=None,
        vercel_team_id=None,
        vercel_project_id=None,
        vercel_base_snapshot_id=None,
        vercel_preview_wait_seconds=30,
        max_iterations=10,
        templates_dir="/t",
        agent_runtime="remote",
        agent_server_port=8000,
        oh_secret_key=None,
        oh_session_api_key=None,
        llm_proxy_public_url=None,
        llm_proxy_admin_url=None,
        llm_proxy_admin_key=None,
        run_orphan_policy="interrupt",
        llm_remote_direct_liara=False,
    )
    with pytest.raises(RuntimeError, match="LLM_PROXY_PUBLIC_URL"):
        llm_base_url_for_sandbox(s)