from unittest.mock import MagicMock, patch

from vercel.sandbox._internal.models import SnapshotRetention, SnapshotSource

from worker.workspace.vercel_sync import connect_sandbox


@patch("worker.workspace.vercel_sync.SyncSandboxClient")
def test_connect_passes_snapshot_source_on_create(mock_client_cls: MagicMock) -> None:
    client = MagicMock()
    mock_client_cls.create.return_value = client
    client.get_or_create_sandbox.return_value = (MagicMock(), True)

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