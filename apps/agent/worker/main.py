from __future__ import annotations

import os

os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
os.environ.setdefault("LITELLM_LOG", "ERROR")

import logging
import signal
import sys
import threading
import time
import uuid
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
from worker.workspace.factory import build_workspace  # noqa: E402
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
        self.db.fail_worker_runs_on_startup(self.worker_id)
        Path(self.settings.conversation_dir).mkdir(parents=True, exist_ok=True)
        logger.info("Worker %s started (concurrency=%s)", self.worker_id, self.settings.worker_concurrency)

        while not self._shutdown.is_set():
            try:
                self.db.fail_stale_runs(self.worker_id)
                self._idle_sandbox_sweep()
                active = sum(1 for _ in self._active)
                slots = max(0, self.settings.worker_concurrency - active)
                if slots > 0:
                    claimed = self.db.claim_runs(self.worker_id, slots)
                    for row in claimed:
                        self._active[uuid.UUID(str(row["id"]))] = threading.Event()
                        self._pool.submit(self._execute_run, row)
            except Exception:
                logger.exception("claim loop error")
            self._shutdown.wait(self.settings.poll_seconds)

        logger.info("Shutting down…")
        for run_id, ev in list(self._active.items()):
            ev.set()
        self._pool.shutdown(wait=True, cancel_futures=False)
        self.db.close()

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
        try:
            ws = build_workspace(self.settings, str(project_id))
            ws.ensure(str(project_id), row.get("template_id") or "vite-react")
            provider = self.settings.sandbox_provider
            preview = None if provider == "vercel" else ws.preview_url()
            self.db.upsert_sandbox(
                project_id,
                name=f"{self.settings.deploy_env}:{project_id}",
                provider=provider,
                status="running",
                preview_url=preview,
            )
            self.db.touch_sandbox_activity(project_id)

            def cancel_check() -> bool:
                return self.db.is_cancel_requested(run_id) or (stop and stop.is_set())

            if cancel_check():
                self.db.finish_run(run_id, "cancelled")
                return

            ws.extend_session()

            status, iterations = run_agent_turn(
                self.settings,
                self.db,
                self.archive,
                row,
                ws,
                cancel_check=cancel_check,
            )
            if cancel_check():
                status = "cancelled"
            elif status not in ("failed", "cancelled") and isinstance(ws, VercelWorkspace):
                preview, ext_id = ws.publish_to_vercel()
                if preview:
                    self.db.upsert_sandbox(
                        project_id,
                        name=f"{self.settings.deploy_env}:{project_id}",
                        provider="vercel",
                        status="running",
                        preview_url=preview,
                        external_id=ext_id,
                    )
            elif self.settings.sandbox_provider == "local":
                preview = ws.preview_url()
                if preview:
                    self.db.upsert_sandbox(
                        project_id,
                        name=f"{self.settings.deploy_env}:{project_id}",
                        provider="local",
                        status="running",
                        preview_url=preview,
                    )
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