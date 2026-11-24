from __future__ import annotations

import os

os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
os.environ.setdefault("LITELLM_LOG", "ERROR")

from worker.liara_env import apply_liara_worker_env  # noqa: E402

apply_liara_worker_env()

import logging
import signal
import sys
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Repo roots on PYTHONPATH when running: apps/agent + packages/archive
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "archive"))
sys.path.insert(0, str(ROOT / "apps" / "agent"))

from conversation_archive.store import ConversationArchiveStore, LocalArchiveBackend  # noqa: E402

from worker.config import Settings  # noqa: E402
from worker.db import Database  # noqa: E402
from worker.logging_config import configure_worker_logging  # noqa: E402
from worker.openhands_runner import run_agent_turn  # noqa: E402
from worker.run_timeline import RunTimeline, prewarm_openhands_sdk  # noqa: E402
from worker.preview_wake import execute_preview_wake  # noqa: E402
from worker.sandbox_stack import ensure_vercel_remote_stack, persist_vercel_stack  # noqa: E402
from worker.remote_control import (  # noqa: E402
    fail_stale_runs_with_remote_teardown,
    fail_worker_runs_on_startup_with_remote_teardown,
    stop_remote_run,
)
from worker.workspace.factory import build_workspace  # noqa: E402
from worker.workspace.vercel_names import vercel_sandbox_display_name  # noqa: E402
from worker.workspace.vercel_ws import VercelWorkspace  # noqa: E402

configure_worker_logging()
logger = logging.getLogger("worker")


class Worker:
    def __init__(self) -> None:
        self.settings = Settings.load()
        self.db = Database(self.settings.database_url)
        self.archive = ConversationArchiveStore(
            LocalArchiveBackend(self.settings.archive_local_dir)
        )
        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        self._shutdown = threading.Event()
        self._active: dict[uuid.UUID, threading.Event] = {}
        self._pool = ThreadPoolExecutor(max_workers=self.settings.worker_concurrency)

    def start(self) -> None:
        fail_worker_runs_on_startup_with_remote_teardown(self.settings, self.db, self.worker_id)
        Path(self.settings.conversation_dir).mkdir(parents=True, exist_ok=True)
        if self.settings.liara_api_key:
            threading.Thread(
                target=prewarm_openhands_sdk,
                name="openhands-prewarm",
                daemon=True,
            ).start()
        logger.info("Worker %s started (concurrency=%s)", self.worker_id, self.settings.worker_concurrency)

        while not self._shutdown.is_set():
            try:
                fail_stale_runs_with_remote_teardown(self.settings, self.db)
                self._idle_sandbox_sweep()
                active = sum(1 for _ in self._active)
                slots = max(0, self.settings.worker_concurrency - active)
                claimed: list[dict] = []
                if slots > 0:
                    claimed = self.db.claim_runs(self.worker_id, slots)
                    for row in claimed:
                        self._active[uuid.UUID(str(row["id"]))] = threading.Event()
                        self._pool.submit(self._execute_run, row)
                        slots -= 1
                busy_projects = {uuid.UUID(str(r["project_id"])) for r in claimed}
                if slots > 0:
                    wake_limit = min(2, slots)
                    for row in self.db.claim_wake_jobs(self.worker_id, wake_limit):
                        pid = uuid.UUID(str(row["project_id"]))
                        if pid in busy_projects:
                            self.db.release_sandbox_wake(uuid.UUID(str(row["id"])))
                            continue
                        busy_projects.add(pid)
                        self._pool.submit(self._execute_wake, row)
            except Exception:
                logger.exception("claim loop error")
            self._shutdown.wait(self.settings.poll_seconds)

        logger.info("Shutting down…")
        for run_id, ev in list(self._active.items()):
            ev.set()
        self._pool.shutdown(wait=True, cancel_futures=False)
        self.db.close()

    def _execute_wake(self, row: dict) -> None:
        try:
            execute_preview_wake(self.settings, self.db, row)
        except Exception:
            logger.exception("preview wake job failed")

    def _idle_sandbox_sweep(self) -> None:
        if self.settings.sandbox_provider != "vercel":
            return
        for row in self.db.sandboxes_due_idle_stop(self.settings.sandbox_idle_seconds):
            ws = build_workspace(self.settings, str(row["project_id"]))
            ws.stop_idle()
            self.db.set_sandbox_status(uuid.UUID(str(row["id"])), "stopped", "idle")

    def _execute_run(self, row: dict) -> None:
        run_id = uuid.UUID(str(row["id"]))
        project_id = uuid.UUID(str(row["project_id"]))
        stop = self._active.get(run_id)
        hb_stop = threading.Event()

        def _heartbeat_loop() -> None:
            while not hb_stop.wait(20):
                self.db.touch_heartbeat(run_id)

        hb_thread = threading.Thread(target=_heartbeat_loop, daemon=True, name=f"hb-{run_id}")
        hb_thread.start()
        timeline = RunTimeline(run_id)
        timeline.mark("run_claimed")
        try:
            ws = build_workspace(self.settings, str(project_id))
            timeline.mark("workspace_ready")
            ws.ensure(str(project_id), row.get("template_id") or "vite-react")
            provider = self.settings.sandbox_provider
            sandbox_label = vercel_sandbox_display_name(
                self.settings.deploy_env, str(project_id)
            )
            preview = None if provider == "vercel" else ws.preview_url()
            self.db.upsert_sandbox(
                project_id,
                name=sandbox_label,
                provider=provider,
                status="running",
                preview_url=preview,
            )
            self.db.touch_sandbox_activity(project_id)

            def cancel_check() -> bool:
                return self.db.is_cancel_requested(run_id) or (stop and stop.is_set())

            if cancel_check():
                stop_remote_run(self.settings, self.db, row, reason="cancelled")
                self.db.finish_run(run_id, "cancelled")
                return

            staging_sync: Callable[[], None] | None = None
            if isinstance(ws, VercelWorkspace):
                remote = self.settings.uses_remote_agent()
                try:
                    stack = ensure_vercel_remote_stack(
                        self.db,
                        ws,
                        project_id,
                        remote_agent=remote,
                        timeline=timeline,
                    )
                    persist_vercel_stack(self.db, project_id, ws, stack)
                    timeline.mark("sandbox_vite_bootstrap")
                except Exception:
                    logger.exception("Vercel stack ensure failed for %s", project_id)
                    raise
                if not remote:
                    staging_sync = ws.request_staging_sync
            else:
                ws.extend_session()

            status, iterations = run_agent_turn(
                self.settings,
                self.db,
                self.archive,
                row,
                ws,
                cancel_check=cancel_check,
                on_staging_sync=staging_sync,
                timeline=timeline,
            )
            if cancel_check():
                status = "cancelled"
            elif status not in ("failed", "cancelled") and isinstance(ws, VercelWorkspace):
                preview, ext_id = ws.publish_to_vercel()
                err = ws.vercel_last_error()
                if preview:
                    self.db.upsert_sandbox(
                        project_id,
                        name=ws.display_name,
                        provider="vercel",
                        status="running",
                        preview_url=preview,
                        external_id=ext_id,
                    )
                elif err:
                    self.db.upsert_sandbox(
                        project_id,
                        name=ws.display_name,
                        provider="vercel",
                        status="failed",
                        preview_url=None,
                        external_id=ext_id,
                    )
            elif self.settings.sandbox_provider == "local":
                preview = ws.preview_url()
                if preview:
                    self.db.upsert_sandbox(
                        project_id,
                        name=sandbox_label,
                        provider="local",
                        status="running",
                        preview_url=preview,
                    )
            timeline.mark("run_finished")
            self.db.finish_run(run_id, status, iterations=iterations)
            self.db.touch_sandbox_activity(project_id)
        except Exception as e:
            logger.exception("run failed")
            self.db.insert_message(
                project_id,
                run_id,
                "assistant",
                f"خطا در اجرا: {e}"[:4000],
            )
            self.db.finish_run(run_id, "failed", error=str(e))
        finally:
            hb_stop.set()
            self._active.pop(run_id, None)


def main() -> None:
    worker = Worker()

    def _handle(sig, frame):  # noqa: ARG001
        worker._shutdown.set()

    signal.signal(signal.SIGINT, _handle)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle)
    worker.start()


if __name__ == "__main__":
    main()