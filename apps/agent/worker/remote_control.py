"""Stop orphaned remote Agent Server runs before marking DB rows failed."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from worker.agent_server_client import interrupt_conversation
from worker.config import Settings
from worker.db import Database
from worker.llm_proxy import revoke_run_llm_key

logger = logging.getLogger(__name__)


def _sandbox_credentials(
    db: Database,
    project_id: uuid.UUID,
) -> tuple[str | None, str | None]:
    row = db.get_sandbox_row(project_id)
    if not row:
        return None, None
    url = row.get("agent_server_url")
    key = row.get("agent_session_api_key")
    if url and key:
        return str(url), str(key)
    return None, None


def stop_remote_run(
    settings: Settings,
    db: Database,
    run_row: dict[str, Any],
    *,
    reason: str,
) -> None:
    project_id = uuid.UUID(str(run_row["project_id"]))
    run_id = uuid.UUID(str(run_row["id"]))
    conv_raw = run_row.get("conversation_id")
    if not conv_raw:
        conv_raw = db.get_project_conversation_id(project_id)
    if not conv_raw:
        return
    conversation_id = uuid.UUID(str(conv_raw))
    agent_url, session_key = _sandbox_credentials(db, project_id)
    if agent_url and session_key:
        ok = interrupt_conversation(agent_url, session_key, conversation_id)
        if ok:
            db.mark_remote_stopped(run_id)
            logger.info(
                "Interrupted remote conversation %s for run %s (%s)",
                conversation_id,
                run_id,
                reason,
            )
    revoke_run_llm_key(settings, run_row.get("llm_proxy_key_id"))


def fail_stale_runs_with_remote_teardown(
    settings: Settings,
    db: Database,
    *,
    older_than_seconds: int = 180,
) -> None:
    stale = db.list_stale_running_runs(older_than_seconds)
    for row in stale:
        stop_remote_run(settings, db, row, reason="heartbeat lost")
        db.fail_run(uuid.UUID(str(row["id"])), "heartbeat lost")


def fail_worker_runs_on_startup_with_remote_teardown(
    settings: Settings,
    db: Database,
    worker_id: str,
) -> None:
    del worker_id
    running = db.list_running_runs()
    for row in running:
        stop_remote_run(settings, db, row, reason="worker restarted")
        db.fail_run(uuid.UUID(str(row["id"])), "worker restarted")