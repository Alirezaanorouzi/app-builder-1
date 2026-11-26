"""Short workspace file list stored after a remote run, for the next seed."""

from __future__ import annotations

import logging
import uuid

from worker.agent_constants import REMOTE_WORKDIR
from worker.db import Database

logger = logging.getLogger(__name__)

_MANIFEST_LIMIT = 4000
_FIND = (
    "find . -type f "
    "-not -path './node_modules/*' "
    "-not -path './.git/*' "
    "-not -path './dist/*' "
    "-not -path './.next/*' "
    "| sort | head -n 200"
)


def clip_manifest(text: str, *, limit: int = _MANIFEST_LIMIT) -> str:
    cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def store_workspace_manifest(db: Database, project_id: uuid.UUID, workspace: object) -> None:
    execute = getattr(workspace, "execute_command", None)
    if not callable(execute):
        return
    result = execute(_FIND, cwd=REMOTE_WORKDIR, timeout=15.0)
    stdout = getattr(result, "stdout", "") or ""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    manifest = clip_manifest(str(stdout))
    if not manifest:
        return
    db.update_sandbox_runtime(project_id, workspace_manifest=manifest)
    logger.info("Stored workspace manifest for %s (%s bytes)", project_id, len(manifest))
