"""Wake the claim loop from a dedicated LISTEN connection.

The channel is agent_run_queued / sandbox_wake_queued, not builder_project_stream.
LISTEN needs a direct Postgres connection (not a transaction-mode pooler).
"""

from __future__ import annotations

import logging
import threading

import psycopg

logger = logging.getLogger(__name__)


def listen_for_work(database_url: str, wake: threading.Event, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            with psycopg.connect(database_url, autocommit=True) as conn:
                conn.execute("LISTEN agent_run_queued")
                conn.execute("LISTEN sandbox_wake_queued")
                logger.info("Listening for queued runs and preview wakes")
                while not stop.is_set():
                    notified = False
                    for _note in conn.notifies(timeout=1.0):
                        notified = True
                        break
                    if notified:
                        wake.set()
        except Exception:
            logger.warning("Claim LISTEN dropped; falling back to poll", exc_info=True)
            if stop.wait(2.0):
                return
