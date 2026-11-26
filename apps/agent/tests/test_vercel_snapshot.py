from unittest.mock import MagicMock, patch

from vercel.sandbox._internal.models import SnapshotRetention, SnapshotSource

from worker.workspace.vercel_sync import (
    connect_sandbox,
    reset_retention_schedule,
    reset_thread_sandbox_clients,
)


def setup_function() -> None:
    reset_thread_sandbox_clients()
    reset_retention_schedule()


def _client() -> MagicMock:
    client = MagicMock()
    client.get_sandbox.side_effect = RuntimeError("missing")
    client.get_or_create_sandbox.return_value = (MagicMock(), True)
    return client


@patch("worker.workspace.vercel_sync.SyncSandboxClient")
def test_connect_passes_snapshot_source_on_create(mock_client_cls: MagicMock) -> None:
    client = _client()
    mock_client_cls.create.return_value = client

    connect_sandbox(
        name="dev-test",
        token="t",
        team_id="team",
        project_id="prj",
        base_snapshot_id="snap_abc123",
    )

    kwargs = client.get_or_create_sandbox.call_args.kwargs
    assert isinstance(kwargs["source"], SnapshotSource)
    assert kwargs["source"].snapshot_id == "snap_abc123"
    assert kwargs["persistent"] is True
    assert kwargs["resume"] is True
    assert isinstance(kwargs["snapshot_retention"], SnapshotRetention)
    assert kwargs["snapshot_retention"].count == 1
    assert kwargs["snapshot_retention"].delete_evicted is True


@patch("worker.workspace.vercel_sync.SyncSandboxClient")
def test_running_sandbox_skips_lifecycle_hooks(mock_client_cls: MagicMock) -> None:
    client = MagicMock()
    mock_client_cls.create.return_value = client
    existing = MagicMock()
    existing.status = "running"
    client.get_sandbox.return_value = existing
    client.get_or_create_sandbox.return_value = (existing, False)
    created_hook = MagicMock()
    resumed_hook = MagicMock()

    connect_sandbox(
        name="dev-test",
        token="t",
        team_id="team",
        project_id="prj",
        on_create=created_hook,
        on_resume=resumed_hook,
    )

    created_hook.assert_not_called()
    resumed_hook.assert_not_called()


@patch("worker.workspace.vercel_sync.SyncSandboxClient")
def test_stopped_sandbox_runs_on_resume_only(mock_client_cls: MagicMock) -> None:
    client = MagicMock()
    mock_client_cls.create.return_value = client
    existing = MagicMock()
    existing.status = "stopped"
    woken = MagicMock()
    client.get_sandbox.return_value = existing
    client.get_or_create_sandbox.return_value = (woken, False)
    created_hook = MagicMock()
    resumed_hook = MagicMock()

    connect_sandbox(
        name="dev-test",
        token="t",
        team_id="team",
        project_id="prj",
        on_create=created_hook,
        on_resume=resumed_hook,
    )

    created_hook.assert_not_called()
    resumed_hook.assert_called_once_with(woken)


@patch("worker.workspace.vercel_sync.SyncSandboxClient")
def test_new_sandbox_runs_on_create_only(mock_client_cls: MagicMock) -> None:
    client = _client()
    mock_client_cls.create.return_value = client
    box = client.get_or_create_sandbox.return_value[0]
    created_hook = MagicMock()
    resumed_hook = MagicMock()

    connect_sandbox(
        name="dev-test",
        token="t",
        team_id="team",
        project_id="prj",
        on_create=created_hook,
        on_resume=resumed_hook,
    )

    created_hook.assert_called_once_with(box)
    resumed_hook.assert_not_called()