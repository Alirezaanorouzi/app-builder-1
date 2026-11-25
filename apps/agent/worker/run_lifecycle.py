"""Per-run heartbeat and cancel polling while agent work is in flight."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from worker.remote_control import stop_remote_run

if TYPE_CHECKING:
    from worker.config import Settings
    from worker.db import Database

logger = logging.getLogger(__name__)


class RunHeartbeat:
    """Touch DB heartbeat on claim; extends Vercel lease once workspace is known."""

    def __init__(
        self,
        db: "Database",
        run_id: uuid.UUID,
        *,
        poll_sec: float = 20.0,
    ) -> None:
        self._db = db
        self._run_id = run_id
        self._poll_sec = poll_sec
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._extend: Callable[[], None] | None = None

    def set_lease_extend(self, fn: Callable[[], None] | None) -> None:
        self._extend = fn

    def start(self) -> None:
        if self._thread is not None:
            return

        def _loop() -> None:
            self._db.touch_heartbeat(self._run_id)
            while not self._stop.wait(self._poll_sec):
                self._db.touch_heartbeat(self._run_id)
                if self._extend is not None:
                    try:
                        self._extend()
                    except Exception:
                        logger.debug("lease extend on heartbeat failed", exc_info=True)

        self._thread = threading.Thread(
            target=_loop,
            name=f"hb-{self._run_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


class CancelMonitor:
    """Poll cancel flag and call Agent Server interrupt (unblocks remote conversation.run)."""

    def __init__(
        self,
        settings: "Settings",
        db: "Database",
        run_row: dict[str, Any],
        *,
        cancel_check: Callable[[], bool],
        poll_sec: float = 2.0,
    ) -> None:
        self._settings = settings
        self._db = db
        self._run_row = run_row
        self._cancel_check = cancel_check
        self._poll_sec = poll_sec
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.cancelled = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        run_id = uuid.UUID(str(self._run_row["id"]))

        def _loop() -> None:
            while not self._stop.wait(self._poll_sec):
                if not self._cancel_check():
                    continue
                stop_remote_run(self._settings, self._db, self._run_row, reason="cancelled")
                self.cancelled.set()
                logger.info("Cancel acknowledged for run %s (remote interrupt sent)", run_id)
                return

        self._thread = threading.Thread(
            target=_loop,
            name=f"cancel-{run_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


class RunCancelled(Exception):
    pass