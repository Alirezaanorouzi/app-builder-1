"""Agent Server ensure path reuses a healthy /ready endpoint without restart."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from worker.config import Settings
from worker.workspace.vercel_agent_session import VercelProjectSession


def _minimal_settings() -> Settings:
    return Settings.load()


@patch("worker.workspace.vercel_agent_session._start_agent_server_process")
@patch("worker.workspace.vercel_agent_session.ready_ok", return_value=True)
@patch("worker.workspace.vercel_agent_session.agent_server_url_from_sandbox")
@patch("worker.workspace.vercel_agent_session.reload_sandbox_routes")
def test_ensure_agent_server_skips_restart_when_ready(
    mock_reload: MagicMock,
    mock_url_from: MagicMock,
    mock_ready: MagicMock,
    mock_start: MagicMock,
) -> None:
    sandbox = MagicMock()
    mock_reload.return_value = sandbox
    mock_url_from.return_value = "https://agent.example"

    session_obj = MagicMock()
    session_obj._sandbox = sandbox  # noqa: SLF001
    session_obj._client = MagicMock()  # noqa: SLF001

    proj = VercelProjectSession(_minimal_settings(), "proj-1")
    proj._sandbox_session = session_obj  # noqa: SLF001

    url, status = proj.ensure_agent_server()

    assert status == "ready"
    assert url == "https://agent.example"
    mock_start.assert_not_called()