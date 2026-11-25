#!/usr/bin/env python3
"""One-time: delete excess Vercel sandbox snapshots (keep latest per sandbox).

Preserves ``VERCEL_BASE_SNAPSHOT_ID`` (golden image). Run after Hobby 402 storage errors.

    cd apps/agent
    set PYTHONPATH=.
    python scripts/prune_vercel_snapshots.py

Ref: https://vercel.com/docs/sandbox/concepts/persistent-sandboxes (keepLastSnapshots count=1).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_REPO = Path(__file__).resolve().parents[3]
from dotenv import load_dotenv

load_dotenv(_REPO / ".env")
load_dotenv()

from worker.config import Settings
from worker.vercel_snapshot_retention import (
    ensure_sandbox_snapshot_retention,
    prune_sandbox_snapshots,
)
from vercel.sandbox._internal.models import SandboxCredentials
from vercel.sandbox._internal.options import SyncSandboxServiceOptions
from vercel.sandbox.sync.client import SyncSandboxClient


def main() -> int:
    settings = Settings.load()
    token = settings.vercel_token
    team = settings.vercel_team_id
    project = settings.vercel_project_id
    golden = settings.vercel_base_snapshot_id
    keep = settings.vercel_snapshot_retention_count
    delete_evicted = settings.vercel_snapshot_delete_evicted
    if not token or not team or not project:
        print("Set VERCEL_TOKEN, VERCEL_TEAM_ID, VERCEL_PROJECT_ID", file=sys.stderr)
        return 1

    def factory() -> SandboxCredentials:
        return SandboxCredentials(token=token, team_id=team, project_id=project)

    client = SyncSandboxClient.create(
        options=SyncSandboxServiceOptions(credentials_factory=factory),
    )
    preserve = frozenset({golden}) if golden else frozenset()
    total = 0
    try:
        for box in client.query_sandboxes():
            name = getattr(box, "name", None)
            if not name:
                continue
            ensure_sandbox_snapshot_retention(
                box,
                count=keep,
                delete_evicted=delete_evicted,
            )
            current = getattr(box, "current_snapshot_id", None)
            total += prune_sandbox_snapshots(
                client,
                sandbox_name=str(name),
                keep=keep,
                preserve_ids=preserve,
                current_snapshot_id=str(current) if current else None,
            )
    finally:
        client.close()

    print(f"Pruned {total} snapshot(s); keep={keep}; golden preserved={golden or '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())