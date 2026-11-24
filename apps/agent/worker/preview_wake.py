"""Resume Vercel sandbox + Vite (+ Agent Server when remote)."""

from __future__ import annotations

import logging
import uuid

from worker.config import Settings
from worker.db import Database
from worker.sandbox_stack import ensure_vercel_remote_stack, persist_vercel_stack
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

        if isinstance(ws, VercelWorkspace):
            remote = settings.uses_remote_agent()
            stack = ensure_vercel_remote_stack(
                db,
                ws,
                project_id,
                remote_agent=remote,
                wait_wake_sec=0.0,
            )
            persist_vercel_stack(db, project_id, ws, stack)
            preview = stack.preview_url
            external_id = stack.external_id
            provider = "vercel"
            db.finish_sandbox_wake(wake_id, "succeeded")
            logger.info(
                "Preview wake succeeded for %s: %s (reused=%s)",
                project_id,
                preview,
                stack.reused_warm_stack,
            )
            return

        if isinstance(ws, LocalWorkspace):
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
            db.finish_sandbox_wake(wake_id, "failed", error="preview URL not available after wake")
            logger.warning("Preview wake failed for %s", project_id)
    except Exception as e:
        logger.exception("Preview wake error for %s", project_id)
        db.finish_sandbox_wake(wake_id, "failed", error=str(e)[:500])