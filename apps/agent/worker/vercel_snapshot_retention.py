"""Vercel persistent sandbox snapshot retention (keep latest only).

See https://vercel.com/docs/sandbox/concepts/snapshots — ``keepLastSnapshots.count: 1``
with ``deleteEvicted: true`` is the recommended setting to keep storage flat.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from vercel.sandbox import SnapshotRetention

if TYPE_CHECKING:
    from vercel.sandbox.sync.client import SyncSandboxClient

logger = logging.getLogger(__name__)


def snapshot_retention_policy(
    *,
    count: int = 1,
    delete_evicted: bool = True,
) -> SnapshotRetention:
    bounded = max(1, min(int(count), 10))
    return SnapshotRetention(count=bounded, delete_evicted=delete_evicted)


def ensure_sandbox_snapshot_retention(
    sandbox: object,
    *,
    count: int = 1,
    delete_evicted: bool = True,
) -> bool:
    """Apply retention on an existing persistent sandbox (``sandbox.update``)."""
    update = getattr(sandbox, "update", None)
    if not callable(update):
        return False
    policy = snapshot_retention_policy(count=count, delete_evicted=delete_evicted)
    try:
        update(snapshot_retention=policy)
        logger.info(
            "Vercel sandbox retention set (count=%s, delete_evicted=%s)",
            policy.count,
            policy.delete_evicted,
        )
        return True
    except Exception:
        logger.warning("Vercel sandbox retention update failed", exc_info=True)
        return False


def _snapshot_sort_key(snap: object) -> tuple[float, str]:
    for attr in ("last_used_at", "updated_at", "created_at"):
        raw = getattr(snap, attr, None)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            continue
        ts = float(raw)
        if ts >= 1e12:
            ts /= 1000.0
        return (ts, str(getattr(snap, "id", "")))
    return (0.0, str(getattr(snap, "id", "")))


def prune_sandbox_snapshots(
    client: SyncSandboxClient,
    *,
    sandbox_name: str,
    keep: int = 1,
    preserve_ids: frozenset[str] | None = None,
    current_snapshot_id: str | None = None,
) -> int:
    """
    Delete older snapshots for one named sandbox (one-time / catch-up cleanup).

    Keeps the ``keep`` newest snapshots plus any ID in ``preserve_ids`` or ``current_snapshot_id``.
  """
    keep_n = max(1, min(int(keep), 10))
    preserve = set(preserve_ids or ())
    if current_snapshot_id:
        preserve.add(current_snapshot_id)

    try:
        snaps = list(client.query_snapshots(name=sandbox_name))
    except Exception:
        logger.warning("Vercel snapshot list failed for %s", sandbox_name, exc_info=True)
        return 0

    if len(snaps) <= keep_n:
        return 0

    snaps.sort(key=_snapshot_sort_key, reverse=True)
    keep_ids = {getattr(s, "id", None) for s in snaps[:keep_n]}
    keep_ids.discard(None)
    deleted = 0
    for snap in snaps[keep_n:]:
        sid = getattr(snap, "id", None)
        if not sid or sid in preserve or sid in keep_ids:
            continue
        status = str(getattr(snap, "status", "") or "")
        if status == "deleted":
            continue
        delete = getattr(snap, "delete", None)
        if not callable(delete):
            continue
        try:
            delete()
            deleted += 1
            logger.info("Vercel snapshot deleted %s (sandbox=%s)", sid, sandbox_name)
        except Exception:
            logger.warning("Vercel snapshot delete failed %s", sid, exc_info=True)
    if deleted:
        logger.info(
            "Vercel pruned %s snapshot(s) for %s (keep=%s)",
            deleted,
            sandbox_name,
            keep_n,
        )
    return deleted