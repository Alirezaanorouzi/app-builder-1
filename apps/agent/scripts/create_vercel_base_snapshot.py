#!/usr/bin/env python3
"""One-time: seed templates/vite-react, npm install, snapshot(expiration=0).

Run from repo root::

    cd apps/agent && set PYTHONPATH=.&& python scripts/create_vercel_base_snapshot.py

Prints the snapshot ID — set VERCEL_BASE_SNAPSHOT_ID in ``.env`` and restart the worker.
"""

from __future__ import annotations

import sys
from pathlib import Path

# apps/agent on path when invoked as documented
_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

from worker.config import Settings
from worker.workspace.vercel_sync import (
    REMOTE_WORKDIR,
    _npm_install_if_needed,
    connect_sandbox,
    upload_tree,
)

BASE_SANDBOX_NAME = "appbuilder-golden-vite-react"


def main() -> int:
    settings = Settings.load()
    if not settings.vercel_token or not settings.vercel_team_id or not settings.vercel_project_id:
        print("Set VERCEL_TOKEN, VERCEL_TEAM_ID, and VERCEL_PROJECT_ID in .env", file=sys.stderr)
        return 1

    template_dir = Path(settings.templates_dir) / "vite-react"
    if not template_dir.is_dir():
        print(f"Missing template: {template_dir}", file=sys.stderr)
        return 1

    client, sandbox, created = connect_sandbox(
        name=BASE_SANDBOX_NAME,
        token=settings.vercel_token,
        team_id=settings.vercel_team_id,
        project_id=settings.vercel_project_id,
    )
    try:
        print(f"Base builder sandbox {BASE_SANDBOX_NAME} (created={created})")
        n = upload_tree(sandbox, template_dir)
        print(f"Uploaded {n} files to {REMOTE_WORKDIR}")
        if not _npm_install_if_needed(sandbox):
            print("npm install failed", file=sys.stderr)
            return 1
        agent_stack = sandbox.run_command(
            "bash",
            args=[
                "-lc",
                (
                    f"cd {REMOTE_WORKDIR} && "
                    "pip install 'openhands-sdk==1.63.1' 'openhands-tools==1.63.1' "
                    "'openhands-workspace==1.63.1' 'openhands-agent-server==1.63.1' "
                    "httpx -q && python -c 'import openhands.agent_server'"
                ),
            ],
            cwd=REMOTE_WORKDIR,
            capture_output=True,
            kill_after=900,
        )
        from worker.workspace.vercel_sync import _command_rc

        if _command_rc(agent_stack) != 0:
            err = (getattr(agent_stack, "stderr", None) or b"").decode("utf-8", errors="replace")
            print("openhands agent stack install failed:", err[:2000], file=sys.stderr)
            return 1
        print("Installed OpenHands agent server stack in golden image")
        snap = sandbox.snapshot(expiration=0)
        snap_id = getattr(snap, "id", None) or getattr(snap, "snapshot_id", None)
        if not snap_id:
            print("snapshot() returned no id", file=sys.stderr)
            return 1
        print()
        print("Golden snapshot created (expiration=0, never expires):")
        print(f"  {snap_id}")
        print()
        print(f"Add to .env: VERCEL_BASE_SNAPSHOT_ID={snap_id}")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())