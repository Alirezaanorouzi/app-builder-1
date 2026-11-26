"""Agent Server bring-up probes /ready only when the runtime session id matches."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from worker.config import Settings
from worker.workspace.vercel_agent_session import VercelProjectSession


def _minimal_settings() -> Settings:
    return Settings.load()


def _session(sandbox: MagicMock) -> MagicMock:
    session_obj = MagicMock()
    session_obj._sandbox = sandbox  # noqa: SLF001
    session_obj._client = MagicMock()  # noqa: SLF001
    session_obj._created = False  # noqa: SLF001
    return session_obj


@patch("worker.workspace.vercel_agent_session.spawn_agent_and_vite")
@patch("worker.session_expiry.runtime_session_id", return_value="sess-1")
@patch("worker.workspace.vercel_agent_session.ready_ok", return_value=True)
@patch("worker.workspace.vercel_agent_session.agent_server_url_from_sandbox")
def test_same_session_skips_spawn_when_ready(
    mock_url_from: MagicMock,
    mock_ready: MagicMock,
    _session_id: MagicMock,
    mock_spawn: MagicMock,
) -> None:
    sandbox = MagicMock()
    mock_url_from.return_value = "https://agent.example"
    proj = VercelProjectSession(_minimal_settings(), "proj-1")
    proj._sandbox_session = _session(sandbox)  # noqa: SLF001

    url, status, sid, _sha = proj.bring_up(stored_session_id="sess-1", stored_entry_sha="abc")

    assert status == "ready"
    assert url == "https://agent.example"
    assert sid == "sess-1"
    mock_spawn.assert_not_called()
    mock_ready.assert_called_once()


@patch("worker.workspace.vercel_agent_session.spawn_agent_and_vite")
@patch("worker.workspace.vercel_agent_session._ensure_agent_server_entry_on_vm", return_value="sha")
@patch("worker.session_expiry.runtime_session_id", return_value="sess-new")
@patch("worker.workspace.vercel_agent_session.ready_ok", return_value=True)
@patch("worker.workspace.vercel_agent_session.agent_server_url_from_sandbox")
def test_session_mismatch_spawns_without_prior_ready(
    mock_url_from: MagicMock,
    mock_ready: MagicMock,
    _session_id: MagicMock,
    _entry: MagicMock,
    mock_spawn: MagicMock,
) -> None:
    sandbox = MagicMock()
    mock_url_from.return_value = "https://agent.example"
    proj = VercelProjectSession(_minimal_settings(), "proj-1")
    proj._sandbox_session = _session(sandbox)  # noqa: SLF001

    url, status, sid, sha = proj.bring_up(stored_session_id="sess-old", stored_entry_sha="old")

    assert status == "ready"
    assert url == "https://agent.example"
    assert sid == "sess-new"
    assert sha == "sha"
    mock_spawn.assert_called_once()
    assert mock_ready.call_args.kwargs.get("timeout") == 1.5
