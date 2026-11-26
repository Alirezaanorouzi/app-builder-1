from unittest.mock import MagicMock, patch

from worker.vercel_snapshot_retention import (
    prune_sandbox_snapshots,
    snapshot_retention_policy,
)


def test_snapshot_retention_policy_bounds_count() -> None:
    p = snapshot_retention_policy(count=0, delete_evicted=True)
    assert p.count == 1
    p2 = snapshot_retention_policy(count=99, delete_evicted=False)
    assert p2.count == 10
    assert p2.delete_evicted is False


def test_prune_deletes_oldest_only() -> None:
    client = MagicMock()
    old = MagicMock(status="created", created_at=1_000_000_000_000)
    old.id = "snap_old"
    old.delete = MagicMock()
    new = MagicMock(status="created", created_at=2_000_000_000_000)
    new.id = "snap_new"
    new.delete = MagicMock()

    client.query_snapshots.return_value = [old, new]

    deleted = prune_sandbox_snapshots(
        client,
        sandbox_name="dev_proj",
        keep=1,
        preserve_ids=frozenset(),
    )
    assert deleted == 1
    old.delete.assert_called_once()
    new.delete.assert_not_called()


@patch("worker.workspace.vercel_sync.ensure_sandbox_snapshot_retention", return_value=True)
@patch("worker.workspace.vercel_sync.prune_sandbox_snapshots", return_value=0)
@patch("worker.workspace.vercel_sync.SyncSandboxClient")
def test_connect_applies_retention_once_until_interval(
    mock_client_cls: MagicMock,
    _prune: MagicMock,
    _ensure: MagicMock,
) -> None:
    from worker.workspace.vercel_sync import (
        connect_sandbox,
        reset_retention_schedule,
        reset_thread_sandbox_clients,
    )

    reset_thread_sandbox_clients()
    reset_retention_schedule()
    client = MagicMock()
    mock_client_cls.create.return_value = client
    box = MagicMock(current_snapshot_id="snap_live")
    client.get_or_create_sandbox.return_value = (box, False)

    connect_sandbox(
        name="dev-test",
        token="t",
        team_id="team",
        project_id="prj",
        base_snapshot_id="snap_golden",
        snapshot_retention_count=1,
    )

    _ensure.assert_called_once()
    _prune.assert_called_once()
    preserve = _prune.call_args.kwargs["preserve_ids"]
    assert "snap_golden" in preserve

    connect_sandbox(
        name="dev-test",
        token="t",
        team_id="team",
        project_id="prj",
        base_snapshot_id="snap_golden",
        snapshot_retention_count=1,
    )
    _ensure.assert_called_once()
    _prune.assert_called_once()