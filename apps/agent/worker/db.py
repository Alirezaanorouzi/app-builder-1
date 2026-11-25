from __future__ import annotations

import hashlib
import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class Database:
    def __init__(self, url: str) -> None:
        self.pool = ConnectionPool(
            url,
            min_size=1,
            max_size=5,
            open=True,
            kwargs={"row_factory": dict_row},
        )

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def conn(self) -> Iterator[psycopg.Connection]:
        with self.pool.connection() as connection:
            yield connection

    def claim_runs(self, worker_id: str, limit: int) -> list[dict[str, Any]]:
        with self.conn() as c:
            with c.transaction():
                rows = c.execute(
                    """
                    SELECT ar.*, p.conversation_id, p.template_id, p.title, p.owner_id
                    FROM agent_runs ar
                    JOIN projects p ON p.id = ar.project_id
                    WHERE ar.status = 'queued'
                      AND NOT EXISTS (
                        SELECT 1 FROM sandbox_wake_requests wr
                        WHERE wr.project_id = ar.project_id
                          AND wr.status IN ('queued', 'running')
                      )
                    ORDER BY ar.created_at
                    LIMIT %s
                    FOR UPDATE OF ar SKIP LOCKED
                    """,
                    (limit,),
                ).fetchall()
                claimed = []
                now = datetime.now(timezone.utc)
                for row in rows:
                    c.execute(
                        """
                        UPDATE agent_runs
                        SET status = 'running', worker_id = %s, started_at = %s, heartbeat_at = %s
                        WHERE id = %s
                        """,
                        (worker_id, now, now, row["id"]),
                    )
                    claimed.append(dict(row))
                return claimed

    def mark_run_execution_started(self, run_id: uuid.UUID) -> None:
        with self.conn() as c:
            c.execute(
                """
                UPDATE agent_runs
                SET execution_started_at = %s, heartbeat_at = %s
                WHERE id = %s AND execution_started_at IS NULL
                """,
                (datetime.now(timezone.utc), datetime.now(timezone.utc), run_id),
            )

    def touch_heartbeat(self, run_id: uuid.UUID) -> None:
        with self.conn() as c:
            c.execute(
                "UPDATE agent_runs SET heartbeat_at = %s WHERE id = %s",
                (datetime.now(timezone.utc), run_id),
            )

    def fail_stale_runs(self, worker_id: str, older_than_seconds: int = 180) -> None:
        with self.conn() as c:
            c.execute(
                """
                UPDATE agent_runs
                SET status = 'failed', finished_at = now(),
                    error_message = 'heartbeat lost'
                WHERE status = 'running'
                  AND heartbeat_at < now() - (%s || ' seconds')::interval
                """,
                (str(older_than_seconds),),
            )

    def fail_worker_runs_on_startup(self, worker_id: str) -> None:
        """Mark any in-flight runs failed when a new worker process starts (orphan cleanup)."""
        del worker_id  # kept for call-site compatibility
        with self.conn() as c:
            c.execute(
                """
                UPDATE agent_runs
                SET status = 'failed', finished_at = now(), error_message = 'worker restarted'
                WHERE status = 'running'
                """,
            )

    def finish_run(
        self,
        run_id: uuid.UUID,
        status: str,
        error: str | None = None,
        iterations: int = 0,
    ) -> None:
        with self.conn() as c:
            c.execute(
                """
                UPDATE agent_runs
                SET status = %s, finished_at = %s, error_message = %s, iteration_count = %s,
                    live_output = NULL
                WHERE id = %s
                """,
                (status, datetime.now(timezone.utc), error, iterations, run_id),
            )

    def clear_run_live_output(self, run_id: uuid.UUID) -> None:
        with self.conn() as c:
            c.execute(
                "UPDATE agent_runs SET live_output = NULL WHERE id = %s",
                (run_id,),
            )

    def append_run_live_output(self, run_id: uuid.UUID, text: str) -> None:
        if not text:
            return
        with self.conn() as c:
            c.execute(
                """
                UPDATE agent_runs
                SET live_output = COALESCE(live_output, '') || %s
                WHERE id = %s
                """,
                (text, run_id),
            )

    def requeue_run(self, run_id: uuid.UUID) -> None:
        with self.conn() as c:
            c.execute(
                """
                UPDATE agent_runs
                SET status = 'queued', worker_id = NULL, started_at = NULL
                WHERE id = %s AND status = 'running'
                """,
                (run_id,),
            )

    def is_cancel_requested(self, run_id: uuid.UUID) -> bool:
        with self.conn() as c:
            row = c.execute(
                "SELECT cancel_requested_at IS NOT NULL AS cancel FROM agent_runs WHERE id = %s",
                (run_id,),
            ).fetchone()
            return bool(row and row["cancel"])

    def insert_message(
        self, project_id: uuid.UUID, run_id: uuid.UUID, role: str, content: str
    ) -> None:
        with self.conn() as c:
            c.execute(
                """
                INSERT INTO messages (project_id, run_id, role, content)
                VALUES (%s, %s, %s, %s)
                """,
                (project_id, run_id, role, content),
            )

    def insert_run_event(
        self,
        run_id: uuid.UUID,
        seq: int,
        event_class: str,
        payload: dict[str, Any],
        sdk_event_id: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        with self.conn() as c:
            c.execute(
                """
                INSERT INTO run_events (run_id, seq, sdk_event_id, event_class, tool_name, payload)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (run_id, seq) DO NOTHING
                """,
                (
                    run_id,
                    seq,
                    sdk_event_id,
                    event_class,
                    tool_name,
                    json.dumps(payload, default=str),
                ),
            )

    def next_event_seq(self, run_id: uuid.UUID) -> int:
        with self.conn() as c:
            row = c.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 AS n FROM run_events WHERE run_id = %s",
                (run_id,),
            ).fetchone()
            return int(row["n"])

    def save_archive_meta(
        self,
        project_id: uuid.UUID,
        run_id: uuid.UUID,
        conversation_id: uuid.UUID,
        sdk_version: str,
        storage_key: str,
        sha256: str,
        byte_size: int,
    ) -> None:
        with self.conn() as c:
            c.execute(
                """
                INSERT INTO conversation_archives
                  (project_id, run_id, conversation_id, openhands_sdk_version,
                   storage_key, sha256, byte_size)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (project_id, run_id, conversation_id, sdk_version, storage_key, sha256, byte_size),
            )

    def latest_archive(self, project_id: uuid.UUID) -> dict[str, Any] | None:
        with self.conn() as c:
            return c.execute(
                """
                SELECT * FROM conversation_archives
                WHERE project_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()

    def update_project_conversation(self, project_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
        with self.conn() as c:
            c.execute(
                "UPDATE projects SET conversation_id = %s, updated_at = now() WHERE id = %s",
                (conversation_id, project_id),
            )

    def get_sandbox_row(self, project_id: uuid.UUID) -> dict[str, Any] | None:
        with self.conn() as c:
            return c.execute(
                "SELECT * FROM sandboxes WHERE project_id = %s", (project_id,)
            ).fetchone()

    def upsert_sandbox(
        self,
        project_id: uuid.UUID,
        *,
        name: str,
        provider: str,
        status: str,
        preview_url: str | None = None,
        external_id: str | None = None,
        agent_server_url: str | None = None,
        agent_session_api_key: str | None = None,
        agent_server_status: str | None = None,
        session_expires_at: datetime | None = None,
    ) -> uuid.UUID:
        with self.conn() as c:
            row = c.execute(
                "SELECT id FROM sandboxes WHERE project_id = %s", (project_id,)
            ).fetchone()
            now = datetime.now(timezone.utc)
            if row:
                c.execute(
                    """
                    UPDATE sandboxes SET name = %s, provider = %s, status = %s,
                      preview_url = COALESCE(%s, preview_url),
                      external_id = COALESCE(%s, external_id),
                      agent_server_url = COALESCE(%s, agent_server_url),
                      agent_session_api_key = COALESCE(%s, agent_session_api_key),
                      agent_server_status = COALESCE(%s, agent_server_status),
                      session_expires_at = COALESCE(%s, session_expires_at),
                      last_active_at = %s, updated_at = %s
                    WHERE project_id = %s
                    RETURNING id
                    """,
                    (
                        name,
                        provider,
                        status,
                        preview_url,
                        external_id,
                        agent_server_url,
                        agent_session_api_key,
                        agent_server_status,
                        session_expires_at,
                        now,
                        now,
                        project_id,
                    ),
                )
            else:
                c.execute(
                    """
                    INSERT INTO sandboxes
                      (project_id, name, provider, status, preview_url, external_id,
                       agent_server_url, agent_session_api_key, agent_server_status,
                       session_expires_at, last_active_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        project_id,
                        name,
                        provider,
                        status,
                        preview_url,
                        external_id,
                        agent_server_url,
                        agent_session_api_key,
                        agent_server_status,
                        session_expires_at,
                        now,
                    ),
                )
            return c.execute(
                "SELECT id FROM sandboxes WHERE project_id = %s", (project_id,)
            ).fetchone()["id"]

    def touch_sandbox_activity(self, project_id: uuid.UUID) -> None:
        with self.conn() as c:
            c.execute(
                "UPDATE sandboxes SET last_active_at = now() WHERE project_id = %s",
                (project_id,),
            )

    def sandboxes_due_idle_stop(self, idle_seconds: int) -> list[dict[str, Any]]:
        """Legacy worker idle stop query (Vercel uses execution_time_limit + extend instead)."""
        with self.conn() as c:
            return c.execute(
                """
                SELECT s.*
                FROM sandboxes s
                WHERE s.status = 'running'
                  AND s.last_active_at < now() - (%s || ' seconds')::interval
                  AND NOT EXISTS (
                    SELECT 1 FROM agent_runs ar
                    WHERE ar.project_id = s.project_id
                      AND ar.status IN ('queued', 'running')
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM sandbox_wake_requests wr
                    WHERE wr.project_id = s.project_id
                      AND wr.status IN ('queued', 'running')
                  )
                """,
                (str(idle_seconds),),
            ).fetchall()

    def set_sandbox_status(self, sandbox_id: uuid.UUID, status: str, reason: str) -> None:
        with self.conn() as c:
            row = c.execute("SELECT status FROM sandboxes WHERE id = %s", (sandbox_id,)).fetchone()
            from_status = row["status"] if row else None
            c.execute(
                "UPDATE sandboxes SET status = %s, updated_at = now() WHERE id = %s",
                (status, sandbox_id),
            )
            c.execute(
                """
                INSERT INTO sandbox_events (sandbox_id, from_status, to_status, reason)
                VALUES (%s, %s, %s, %s)
                """,
                (sandbox_id, from_status, status, reason),
            )

    def count_project_messages(self, project_id: uuid.UUID) -> int:
        with self.conn() as c:
            row = c.execute(
                "SELECT COUNT(*)::int AS n FROM messages WHERE project_id = %s",
                (project_id,),
            ).fetchone()
            return int(row["n"]) if row else 0

    def touch_sandbox_session_expires(
        self,
        project_id: uuid.UUID,
        *,
        expires_at: datetime,
    ) -> None:
        with self.conn() as c:
            c.execute(
                """
                UPDATE sandboxes
                SET session_expires_at = %s, updated_at = now()
                WHERE project_id = %s
                """,
                (expires_at, project_id),
            )

    def clear_sandbox_session_expires(self, project_id: uuid.UUID) -> None:
        with self.conn() as c:
            c.execute(
                """
                UPDATE sandboxes
                SET session_expires_at = NULL, updated_at = now()
                WHERE project_id = %s
                """,
                (project_id,),
            )

    def list_prior_messages(self, project_id: uuid.UUID, limit: int = 20) -> list[dict[str, Any]]:
        with self.conn() as c:
            return c.execute(
                """
                SELECT role, content FROM messages
                WHERE project_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (project_id, limit),
            ).fetchall()[::-1]

    def get_run_user_message(self, run_id: uuid.UUID) -> str | None:
        with self.conn() as c:
            row = c.execute(
                """
                SELECT content FROM messages
                WHERE run_id = %s AND role = 'user'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            return row["content"] if row else None

    def get_project_conversation_id(self, project_id: uuid.UUID) -> uuid.UUID | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT conversation_id FROM projects WHERE id = %s",
                (project_id,),
            ).fetchone()
            if not row:
                return None
            return uuid.UUID(str(row["conversation_id"]))

    def set_run_llm_proxy_key_id(self, run_id: uuid.UUID, key_id: str) -> None:
        with self.conn() as c:
            c.execute(
                "UPDATE agent_runs SET llm_proxy_key_id = %s WHERE id = %s",
                (key_id, run_id),
            )

    def mark_remote_stopped(self, run_id: uuid.UUID) -> None:
        with self.conn() as c:
            c.execute(
                "UPDATE agent_runs SET remote_stopped_at = now() WHERE id = %s",
                (run_id,),
            )

    def fail_run(self, run_id: uuid.UUID, error_message: str) -> None:
        with self.conn() as c:
            c.execute(
                """
                UPDATE agent_runs
                SET status = 'failed', finished_at = now(), error_message = %s
                WHERE id = %s AND status = 'running'
                """,
                (error_message, run_id),
            )

    def list_running_runs(self) -> list[dict[str, Any]]:
        with self.conn() as c:
            return c.execute(
                """
                SELECT ar.*, p.conversation_id
                FROM agent_runs ar
                JOIN projects p ON p.id = ar.project_id
                WHERE ar.status = 'running'
                """
            ).fetchall()

    def list_stale_running_runs(self, older_than_seconds: int) -> list[dict[str, Any]]:
        with self.conn() as c:
            return c.execute(
                """
                SELECT ar.*, p.conversation_id
                FROM agent_runs ar
                JOIN projects p ON p.id = ar.project_id
                WHERE ar.status = 'running'
                  AND ar.execution_started_at IS NOT NULL
                  AND ar.heartbeat_at < now() - (%s || ' seconds')::interval
                """,
                (str(older_than_seconds),),
            ).fetchall()

    def enqueue_sandbox_wake(self, project_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
        with self.conn() as c:
            row = c.execute(
                """
                INSERT INTO sandbox_wake_requests (project_id, user_id, status)
                VALUES (%s, %s, 'queued')
                RETURNING id
                """,
                (project_id, user_id),
            ).fetchone()
            return uuid.UUID(str(row["id"]))

    def get_active_sandbox_wake(self, project_id: uuid.UUID) -> dict[str, Any] | None:
        with self.conn() as c:
            return c.execute(
                """
                SELECT * FROM sandbox_wake_requests
                WHERE project_id = %s AND status IN ('queued', 'running')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()

    def project_has_active_run(self, project_id: uuid.UUID) -> bool:
        with self.conn() as c:
            row = c.execute(
                """
                SELECT 1 FROM agent_runs
                WHERE project_id = %s AND status = 'running'
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            return row is not None

    def release_sandbox_wake(self, wake_id: uuid.UUID) -> None:
        """Return a claimed wake job to the queue (e.g. project already running an agent)."""
        with self.conn() as c:
            c.execute(
                """
                UPDATE sandbox_wake_requests
                SET status = 'queued', worker_id = NULL, started_at = NULL
                WHERE id = %s AND status = 'running'
                """,
                (wake_id,),
            )

    def claim_wake_jobs(self, worker_id: str, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        with self.conn() as c:
            with c.transaction():
                rows = c.execute(
                    """
                    SELECT wr.*
                    FROM sandbox_wake_requests wr
                    WHERE wr.status = 'queued'
                      AND NOT EXISTS (
                        SELECT 1 FROM agent_runs ar
                        WHERE ar.project_id = wr.project_id
                          AND ar.status IN ('queued', 'running')
                      )
                    ORDER BY wr.created_at
                    LIMIT %s
                    FOR UPDATE OF wr SKIP LOCKED
                    """,
                    (limit,),
                ).fetchall()
                claimed = []
                now = datetime.now(timezone.utc)
                for row in rows:
                    c.execute(
                        """
                        UPDATE sandbox_wake_requests
                        SET status = 'running', worker_id = %s, started_at = %s
                        WHERE id = %s
                        """,
                        (worker_id, now, row["id"]),
                    )
                    claimed.append(dict(row))
                return claimed

    def finish_sandbox_wake(
        self,
        wake_id: uuid.UUID,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        with self.conn() as c:
            c.execute(
                """
                UPDATE sandbox_wake_requests
                SET status = %s, finished_at = %s, error_message = %s
                WHERE id = %s
                """,
                (status, datetime.now(timezone.utc), error, wake_id),
            )

    @staticmethod
    def project_advisory_key(project_id: str | uuid.UUID) -> int:
        material = f"builder_sandbox:{project_id}".encode()
        digest = hashlib.sha256(material).digest()
        return int.from_bytes(digest[:4], "big") % (2**31)

    @contextmanager
    def project_advisory_lock(
        self, project_id: str | uuid.UUID, *, timeout_sec: float = 300.0
    ) -> Iterator[None]:
        """Cross-replica mutex for Vercel stack bootstrap (session-scoped PG lock)."""
        from worker.sandbox_project_lock import SandboxLockTimeout

        key = self.project_advisory_key(project_id)
        deadline = time.monotonic() + max(0.0, timeout_sec)
        with self.pool.connection() as connection:
            acquired = False
            try:
                while not acquired:
                    row = connection.execute(
                        "SELECT pg_try_advisory_lock(%s) AS ok", (key,)
                    ).fetchone()
                    acquired = bool(row and row["ok"])
                    if acquired:
                        break
                    if time.monotonic() >= deadline:
                        raise SandboxLockTimeout(
                            f"Timed out after {timeout_sec:.0f}s waiting for "
                            f"advisory sandbox lock on {project_id}"
                        )
                    time.sleep(0.2)
                yield
            finally:
                if acquired:
                    connection.execute("SELECT pg_advisory_unlock(%s)", (key,))