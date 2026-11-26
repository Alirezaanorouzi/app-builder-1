from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from worker.config import Settings
from worker.workspace.base import CommandResult, WorkspaceAdapter
from worker.workspace.local import LocalWorkspace
from worker.workspace.vercel_agent_session import VercelProjectSession
from worker.workspace.vercel_names import vercel_sandbox_api_name, vercel_sandbox_display_name
from worker.sandbox_project_lock import project_sandbox_lock
from worker.workspace.vercel_sync import VercelSandboxSession
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worker.db import Database

_SYNC_DEBOUNCE_SEC = 25

logger = logging.getLogger(__name__)


class VercelWorkspace(WorkspaceAdapter):
    """
    Vercel sandbox lifecycle for preview + (optional) remote Agent Server execution.

    When ``settings.uses_remote_agent()`` is true, the OpenHands loop runs on the VM via
    Agent Server; this adapter only handles sandbox connectivity (no staging sync).
  """

    def __init__(
        self,
        *,
        settings: Settings,
        project_id: str,
    ) -> None:
        self.project_id = project_id
        self.api_name = vercel_sandbox_api_name(settings.deploy_env, project_id)
        self.display_name = vercel_sandbox_display_name(settings.deploy_env, project_id)
        self.settings = settings
        self._remote = settings.uses_remote_agent()
        self._session: VercelProjectSession | None = None
        self._legacy_session: VercelSandboxSession | None = None
        self._sync_lock = threading.Lock()
        self._last_sync_at = 0.0
        self._staging: LocalWorkspace | None = None
        self._db: Database | None = None
        if not self._remote:
            self._staging = LocalWorkspace(
                settings.workspace_staging_dir,
                project_id,
                settings.templates_dir,
            )
            self.root = self._staging.root
        else:
            self.root = Path(settings.workspace_staging_dir) / "sandboxes" / project_id
            self.root.mkdir(parents=True, exist_ok=True)
        self._preview: str | None = None
        self._external_id: str | None = None
        self._agent_url: str | None = None
        self._persisted_session_api_key: str | None = None
        self._persisted_agent_url: str | None = None

    def apply_persisted_agent_state(
        self,
        *,
        session_api_key: str | None = None,
        agent_server_url: str | None = None,
    ) -> None:
        """Restore DB-stored Agent Server credentials from a prior run."""
        if session_api_key:
            self._persisted_session_api_key = session_api_key
        if agent_server_url:
            self._persisted_agent_url = agent_server_url.rstrip("/")
        if self._session is not None:
            if session_api_key:
                self._session.session_api_key = session_api_key
            if agent_server_url:
                self._session.seed_agent_url_hint(agent_server_url)

    def attach_from_sandbox_row(self, sb_row: dict) -> None:
        """Wire workspace from DB after a live /ready check (no Vercel reconnect)."""
        self.apply_persisted_agent_state(
            session_api_key=sb_row.get("agent_session_api_key"),
            agent_server_url=sb_row.get("agent_server_url"),
        )
        preview = sb_row.get("preview_url")
        if preview:
            self._preview = str(preview)
        external_id = sb_row.get("external_id")
        if external_id:
            self._external_id = str(external_id)
        agent_url = sb_row.get("agent_server_url")
        if agent_url:
            self._agent_url = str(agent_url).rstrip("/")
        session = self._open_session()
        if session is not None and self._agent_url:
            session.adopt_warm_agent(self._agent_url, status="ready")

    @property
    def project_session(self) -> VercelProjectSession | None:
        return self._session

    def _open_session(self) -> VercelProjectSession | None:
        if not self.settings.vercel_token or not self.settings.vercel_team_id:
            return None
        if self._session is None:
            self._session = VercelProjectSession(
                self.settings,
                self.project_id,
                session_api_key=self._persisted_session_api_key,
            )
            if self._persisted_agent_url:
                self._session.seed_agent_url_hint(self._persisted_agent_url)
        return self._session

    def ensure(self, project_id: str, template_name: str) -> bool:
        if self._remote:
            return True
        assert self._staging is not None
        return self._staging.ensure(project_id, template_name)

    def resolve(self, path: str | None) -> Path:
        if self._staging is None:
            return self.root / (path or ".")
        return self._staging.resolve(path)

    def view_file(self, path: str) -> str:
        if self._remote:
            return f"(remote workspace) {path}"
        assert self._staging is not None
        return self._staging.view_file(path)

    def str_replace(self, path: str, old: str, new: str) -> str:
        assert self._staging is not None
        return self._staging.str_replace(path, old, new)

    def insert(self, path: str, line: int, text: str) -> str:
        assert self._staging is not None
        return self._staging.insert(path, line, text)

    def create_file(self, path: str, content: str) -> str:
        assert self._staging is not None
        return self._staging.create_file(path, content)

    def grep(self, pattern: str, path: str = ".") -> str:
        assert self._staging is not None
        return self._staging.grep(pattern, path)

    def glob(self, pattern: str) -> str:
        if self._remote:
            return "(remote workspace — file list on VM)"
        assert self._staging is not None
        return self._staging.glob(pattern)

    def run_command(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: int = 120,
        background: bool = False,
    ) -> CommandResult:
        assert self._staging is not None
        return self._staging.run_command(
            command, cwd=cwd, timeout=timeout, background=background
        )

    def read_command_output(self, command_id: str) -> CommandResult:
        assert self._staging is not None
        return self._staging.read_command_output(command_id)

    def preview_url(self) -> str | None:
        return self._preview

    def agent_server_url(self) -> str | None:
        return self._agent_url

    def bind_database(self, db: Database) -> None:
        self._db = db

    def _sandbox_lock(self):
        return project_sandbox_lock(
            self.project_id,
            timeout_sec=float(self.settings.sandbox_lock_timeout_seconds),
            db=self._db,
        )

    def ensure_remote_agent_server(self) -> tuple[str | None, str]:
        with self._sandbox_lock():
            session = self._open_session()
            if session is None:
                return None, "failed"
            agent_url, status = session.ensure_agent_server()
        self._agent_url = agent_url
        logger.info(
            "Agent server for %s: status=%s url=%s",
            self.project_id,
            status,
            agent_url,
        )
        return agent_url, status

    def _open_legacy_session(self) -> VercelSandboxSession | None:
        if not self.settings.vercel_token or not self.settings.vercel_team_id:
            return None
        assert self._staging is not None
        if self._legacy_session is None:
            self._legacy_session = VercelSandboxSession(
                api_name=self.api_name,
                token=self.settings.vercel_token,
                team_id=self.settings.vercel_team_id,
                project_id=self.settings.vercel_project_id or "",
                local_root=self._staging.root,
                base_snapshot_id=self.settings.vercel_base_snapshot_id,
                idle_seconds=self.settings.sandbox_idle_seconds,
                extend_when_remaining_seconds=self.settings.sandbox_extend_when_remaining_seconds,
                max_session_seconds=self.settings.vercel_sandbox_max_session_seconds,
                snapshot_retention_count=self.settings.vercel_snapshot_retention_count,
                snapshot_delete_evicted=self.settings.vercel_snapshot_delete_evicted,
            )
        return self._legacy_session

    def extend_session(self, *, fast: bool = False) -> None:
        if self._remote:
            with self._sandbox_lock():
                session = self._open_session()
                if session is None:
                    return
                url, sid = session.extend_preview(fast=fast)
            if url:
                self._preview = url
            if sid:
                self._external_id = sid
            if session.last_error():
                logger.warning("Vercel bootstrap: %s", session.last_error())
            return
        legacy = self._open_legacy_session()
        if legacy is None:
            return
        wait = 0.0 if fast else float(self.settings.vercel_preview_wait_seconds)
        url, sid = legacy.sync_and_preview(start_dev=True, http_wait_seconds=wait)
        if url:
            self._preview = url
        if sid:
            self._external_id = sid
        elif legacy.last_error:
            logger.warning("Vercel bootstrap: %s", legacy.last_error)

    def wake_preview_only(self) -> tuple[str | None, str | None]:
        """Resume persistent sandbox and start Vite only (no Agent Server / agent run)."""
        if self._remote:
            with self._sandbox_lock():
                session = self._open_session()
                if session is None:
                    return None, None
                url, sid = session.extend_preview(fast=True)
                if not url:
                    url, sid = session.warm_preview()
            if url:
                self._preview = url
            if sid:
                self._external_id = sid
            return self._preview, self._external_id
        legacy = self._open_legacy_session()
        if legacy is None:
            return None, None
        url, sid = legacy.sync_and_preview(
            start_dev=True,
            http_wait_seconds=float(self.settings.vercel_preview_wait_seconds),
            skip_upload=True,
        )
        if url:
            self._preview = url
        if sid:
            self._external_id = sid
        return self._preview, self._external_id

    def warm_preview_url(self) -> str | None:
        if not self._remote:
            legacy = self._legacy_session
            if legacy is None:
                return None
            url, sid = legacy.wait_for_preview(
                http_wait_seconds=float(self.settings.vercel_preview_wait_seconds),
            )
            if url:
                self._preview = url
            if sid:
                self._external_id = sid
            return url
        session = self._session
        if session is None:
            return None
        url, sid = session.warm_preview()
        if url:
            self._preview = url
        if sid:
            self._external_id = sid
        return url

    def request_staging_sync(self) -> None:
        if self._remote:
            return
        now = time.monotonic()
        with self._sync_lock:
            if now - self._last_sync_at < _SYNC_DEBOUNCE_SEC:
                return
            self._last_sync_at = now
        legacy = self._legacy_session
        if legacy is None:
            return
        if legacy.sync_files_only():
            logger.debug("Vercel mid-run file sync for %s", self.api_name)

    def publish_to_vercel(self) -> tuple[str | None, str | None]:
        session = self._session or self._open_session()
        if session is None:
            return None, None
        if self._remote:
            url = session.preview_url() or self._preview
            if url:
                self._preview = url
            sid = session.external_sandbox_id()
            if sid:
                self._external_id = sid
            return self._preview, self._external_id
        legacy = self._legacy_session or self._open_legacy_session()
        if legacy is None:
            return None, None
        url, sid = legacy.sync_and_preview(start_dev=False)
        if not url:
            url, sid = legacy.sync_and_preview(start_dev=True)
        if url:
            self._preview = url
        if sid:
            self._external_id = sid
        legacy.close()
        self._legacy_session = None
        return self._preview, self._external_id

    def stored_lease_fresh(self) -> bool:
        if self._db is None:
            return False
        import uuid

        from worker.session_expiry import stored_lease_is_fresh

        row = self._db.get_sandbox_row(uuid.UUID(self.project_id))
        if not row or not row.get("runtime_session_id"):
            return False
        expires = row.get("session_expires_at")
        return stored_lease_is_fresh(
            expires,
            renew_when_remaining_below=self.settings.sandbox_extend_when_remaining_seconds,
        )

    def persist_measured_deadline(self) -> None:
        if self._db is None or self._session is None:
            return
        import uuid

        from worker.session_expiry import record_measured_session_expiry, runtime_session_id

        sandbox = self._session.connected_sandbox()
        project_id = uuid.UUID(self.project_id)
        record_measured_session_expiry(
            self._db,
            project_id,
            sandbox,
            max_session_seconds=self.settings.vercel_sandbox_max_session_seconds,
        )
        session_id = runtime_session_id(sandbox)
        if session_id:
            self._db.update_sandbox_runtime(project_id, runtime_session_id=session_id)

    def activate_remote_stack(
        self,
        *,
        stored_session_id: str | None,
        stored_entry_sha: str | None,
        on_connected=None,
        on_spawned=None,
        on_ready=None,
        on_retention=None,
        on_resume=None,
    ) -> tuple[str | None, str | None, str | None, str, str | None, str | None]:
        """One resume. Returns preview, external id, agent url, status, session id, entry sha."""
        with self._sandbox_lock():
            return self._activate_remote_stack_locked(
                stored_session_id=stored_session_id,
                stored_entry_sha=stored_entry_sha,
                on_connected=on_connected,
                on_spawned=on_spawned,
                on_ready=on_ready,
                on_retention=on_retention,
                on_resume=on_resume,
            )

    def _activate_remote_stack_locked(
        self,
        *,
        stored_session_id: str | None,
        stored_entry_sha: str | None,
        on_connected=None,
        on_spawned=None,
        on_ready=None,
        on_retention=None,
        on_resume=None,
    ) -> tuple[str | None, str | None, str | None, str, str | None, str | None]:
        session = self._open_session()
        if session is None:
            return None, None, None, "failed", None, stored_entry_sha
        if on_resume is not None:
            on_resume()
        url, status, runtime_id, entry_sha = session.bring_up(
            stored_session_id=stored_session_id,
            stored_entry_sha=stored_entry_sha,
            on_connected=on_connected,
            on_spawned=on_spawned,
            on_ready=on_ready,
            on_retention=on_retention,
        )
        self._agent_url = url
        sandbox = session.connected_sandbox()
        from worker.workspace.vercel_sync import preview_url_from_sandbox

        preview = preview_url_from_sandbox(sandbox) if sandbox is not None else None
        if preview:
            self._preview = preview
        external = session.external_sandbox_id()
        if external:
            self._external_id = external
        self.persist_measured_deadline()
        return self._preview, self._external_id, url, status, runtime_id, entry_sha

    def extend_vercel_idle_deadline(self, *, force: bool = False) -> bool:
        """Renew only when the stored real deadline is near. Does not connect otherwise."""
        if self.stored_lease_fresh():
            return False
        with self._sandbox_lock():
            if self.stored_lease_fresh():
                return False
            return self._extend_locked(force=force)

    def _extend_locked(self, *, force: bool) -> bool:
        session = self._session or self._open_session()
        if session is not None:
            ok = session.extend_idle_deadline(force=force)
            self.persist_measured_deadline()
            return ok
        if self._legacy_session is not None:
            return self._legacy_session.extend_idle_deadline(force=force)
        return False

    def stop_idle(self) -> None:
        """No-op for Vercel — idle shutdown is Vercel execution_time_limit only."""

    def external_sandbox_id(self) -> str | None:
        return self._external_id

    def vercel_last_error(self) -> str | None:
        if self._session is not None:
            return self._session.last_error()
        if self._legacy_session is None:
            return None
        return self._legacy_session.last_error