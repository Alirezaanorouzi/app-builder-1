"""Shared Vercel preview + Agent Server warm / reuse (wake jobs and agent runs)."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from worker.agent_server_client import ready_ok
from worker.sandbox_cold import stack_considered_warm

if TYPE_CHECKING:
    from worker.db import Database
    from worker.run_timeline import RunTimeline
    from worker.workspace.vercel_ws import VercelWorkspace

logger = logging.getLogger(__name__)

_WAKE_POLL_INTERVAL_SEC = 0.5
_DEFAULT_WAKE_WAIT_SEC = 180.0


@dataclass(frozen=True)
class VercelStackEnsureResult:
    reused_warm_stack: bool
    preview_url: str | None
    agent_server_url: str | None
    agent_server_status: str | None
    external_id: str | None
    session_api_key: str | None


def is_db_stack_warm(sb_row: dict[str, Any] | None) -> bool:
    if sb_row is None:
        return False
    if not stack_considered_warm(sb_row):
        return False
    provider = sb_row.get("provider")
    if provider not in (None, "vercel"):
        return False
    if sb_row.get("status") != "running":
        return False
    if sb_row.get("agent_server_status") != "ready":
        return False
    if not sb_row.get("preview_url") or not sb_row.get("agent_server_url"):
        return False
    return bool(sb_row.get("agent_session_api_key"))


def verify_agent_server_live(sb_row: dict[str, Any], *, timeout: float = 5.0) -> bool:
    url = str(sb_row.get("agent_server_url") or "").rstrip("/")
    key = str(sb_row.get("agent_session_api_key") or "")
    if not url or not key:
        return False
    return ready_ok(url, key, timeout=timeout)


def wait_for_inflight_wake(
    db: Database,
    project_id: uuid.UUID,
    *,
    max_wait_sec: float = _DEFAULT_WAKE_WAIT_SEC,
) -> None:
    """Let a queued/running preview-wake finish before run bootstrap (avoids duplicate work)."""
    deadline = time.monotonic() + max_wait_sec
    while time.monotonic() < deadline:
        if db.get_active_sandbox_wake(project_id) is None:
            return
        time.sleep(_WAKE_POLL_INTERVAL_SEC)
    logger.warning(
        "Timed out after %.0fs waiting for sandbox wake on project %s",
        max_wait_sec,
        project_id,
    )


def _mark_stale_agent_status(db: Database, project_id: uuid.UUID, sb_row: dict[str, Any]) -> None:
    db.upsert_sandbox(
        project_id,
        name=str(sb_row.get("name") or "sandbox"),
        provider=str(sb_row.get("provider") or "vercel"),
        status=str(sb_row.get("status") or "running"),
        preview_url=sb_row.get("preview_url"),
        external_id=sb_row.get("external_id"),
        agent_server_url=sb_row.get("agent_server_url"),
        agent_session_api_key=sb_row.get("agent_session_api_key"),
        agent_server_status="starting",
    )
    db.clear_sandbox_session_expires(project_id)


def ensure_vercel_remote_stack(
    db: Database,
    ws: VercelWorkspace,
    project_id: uuid.UUID,
    *,
    remote_agent: bool,
    timeline: RunTimeline | None = None,
    wait_wake_sec: float | None = None,
) -> VercelStackEnsureResult:
    if wait_wake_sec is None:
        wait_wake_sec = _DEFAULT_WAKE_WAIT_SEC
    """
    Reuse a live stack from DB when possible; otherwise resume sandbox + warm Agent Server.
    Used by preview-wake jobs and agent runs.
    """
    wait_for_inflight_wake(db, project_id, max_wait_sec=wait_wake_sec)
    sb_row = db.get_sandbox_row(project_id)
    if sb_row:
        ws.apply_persisted_agent_state(
            session_api_key=sb_row.get("agent_session_api_key"),
            agent_server_url=sb_row.get("agent_server_url"),
        )

    if remote_agent and sb_row and is_db_stack_warm(sb_row):
        if verify_agent_server_live(sb_row):
            ws.attach_from_sandbox_row(sb_row)
            if timeline is not None:
                timeline.mark("sandbox_stack_reused")
            logger.info("Reusing warm Vercel stack for %s (skip bootstrap)", project_id)
            session = ws.project_session
            return VercelStackEnsureResult(
                reused_warm_stack=True,
                preview_url=ws.preview_url(),
                agent_server_url=ws.agent_server_url(),
                agent_server_status="ready",
                external_id=ws.external_sandbox_id() or sb_row.get("external_id"),
                session_api_key=session.session_api_key if session else sb_row.get("agent_session_api_key"),
            )
        logger.info("DB said stack ready but Agent Server /ready failed for %s", project_id)
        _mark_stale_agent_status(db, project_id, sb_row)

    if timeline is not None:
        timeline.mark("sandbox_stack_bootstrap_start")

    preview, external_id = ws.wake_preview_only()
    if not preview:
        err = ws.vercel_last_error() or "preview URL not available"
        raise RuntimeError(err)

    agent_url: str | None = None
    agent_status: str | None = None
    if remote_agent:
        agent_url, agent_status = ws.ensure_remote_agent_server()
        if timeline is not None:
            timeline.mark("agent_server_ready")
        if agent_status != "ready":
            raise RuntimeError(ws.vercel_last_error() or "Agent Server not ready")

    session = ws.project_session
    result = VercelStackEnsureResult(
        reused_warm_stack=False,
        preview_url=preview,
        agent_server_url=agent_url,
        agent_server_status=agent_status or (session.agent_server_status() if session else None),
        external_id=external_id or ws.external_sandbox_id(),
        session_api_key=session.session_api_key if session else None,
    )
    return result


def persist_vercel_stack(db: Database, project_id: uuid.UUID, ws: VercelWorkspace, result: VercelStackEnsureResult) -> None:
    db.upsert_sandbox(
        project_id,
        name=ws.display_name,
        provider="vercel",
        status="running",
        preview_url=result.preview_url,
        external_id=result.external_id,
        agent_server_url=result.agent_server_url,
        agent_session_api_key=result.session_api_key,
        agent_server_status=result.agent_server_status,
    )