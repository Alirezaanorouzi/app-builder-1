"""Resume Vercel sandbox + Vite for preview only (no agent / LLM)."""

from __future__ import annotations

import logging
import uuid

from worker.config import Settings
from worker.db import Database
from worker.workspace.factory import build_workspace
from worker.workspace.local import LocalWorkspace
from worker.workspace.vercel_names import vercel_sandbox_display_name
from worker.workspace.vercel_ws import VercelWorkspace

logger = logging.getLogger(__name__)


def execute_preview_wake(
    settings: Settings,
    db: Database,
    row: dict,
) -> None:
    wake_id = uuid.UUID(str(row["id"]))
    project_id = uuid.UUID(str(row["project_id"]))
    label = vercel_sandbox_display_name(settings.deploy_env, str(project_id))
    db.touch_sandbox_activity(project_id)

    try:
        ws = build_workspace(settings, str(project_id))
        preview: str | None = None
        external_id: str | None = None
        provider = settings.sandbox_provider

        agent_url: str | None = None
        agent_status: str | None = None
        session_api_key: str | None = None
        if isinstance(ws, VercelWorkspace):
            preview, external_id = ws.wake_preview_only()
            if settings.uses_remote_agent():
                sb_row = db.get_sandbox_row(project_id)
                if sb_row:
                    ws.apply_persisted_agent_state(
                        session_api_key=sb_row.get("agent_session_api_key"),
                        agent_server_url=sb_row.get("agent_server_url"),
                    )
                try:
                    agent_url, agent_status = ws.ensure_remote_agent_server()
                    session = ws.project_session
                    if agent_url and session:
                        session_api_key = session.session_api_key
                        logger.info(
                            "Preview wake also warmed Agent Server for %s (%s)",
                            project_id,
                            agent_status,
                        )
                except Exception:
                    logger.exception("Agent Server prewarm during preview wake failed for %s", project_id)
            provider = "vercel"
        elif isinstance(ws, LocalWorkspace):
            ws.extend_session()
            preview = ws.preview_url()
            provider = "local"
        else:
            raise RuntimeError(f"unsupported workspace type: {type(ws).__name__}")

        if preview:
            db.upsert_sandbox(
                project_id,
                name=label,
                provider=provider,
                status="running",
                preview_url=preview,
                external_id=external_id,
                agent_server_url=agent_url,
                agent_session_api_key=session_api_key,
                agent_server_status=agent_status,
            )
            db.finish_sandbox_wake(wake_id, "succeeded")
            logger.info("Preview wake succeeded for %s: %s", project_id, preview)
        else:
            db.upsert_sandbox(
                project_id,
                name=label,
                provider=provider,
                status="failed",
                preview_url=None,
                external_id=external_id,
            )
            err = "preview URL not available after wake"
            if isinstance(ws, VercelWorkspace):
                last = ws.vercel_last_error()
                if last:
                    err = last
            db.finish_sandbox_wake(wake_id, "failed", error=err[:500])
            logger.warning("Preview wake failed for %s: %s", project_id, err)
    except Exception as e:
        logger.exception("Preview wake error for %s", project_id)
        db.finish_sandbox_wake(wake_id, "failed", error=str(e)[:500])