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
from worker.workspace.vercel_sync import VercelSandboxSession, stop_persistent_sandbox

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

    def ensure_remote_agent_server(self) -> tuple[str | None, str]:
        with project_sandbox_lock(self.project_id):
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
            )
        return self._legacy_session

    def extend_session(self, *, fast: bool = False) -> None:
        if self._remote:
            with project_sandbox_lock(self.project_id):
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
            with project_sandbox_lock(self.project_id):
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

    def stop_idle(self) -> None:
        token = self.settings.vercel_token
        team_id = self.settings.vercel_team_id
        project_id = self.settings.vercel_project_id
        if self._session is not None:
            self._session.stop_idle()
            self._session.close()
            self._session = None
        if self._legacy_session is not None:
            self._legacy_session.stop_persistent()
            self._legacy_session.close()
            self._legacy_session = None
        elif token and team_id and project_id:
            stop_persistent_sandbox(
                name=self.api_name,
                token=token,
                team_id=team_id,
                project_id=project_id,
            )

    def external_sandbox_id(self) -> str | None:
        return self._external_id

    def vercel_last_error(self) -> str | None:
        if self._session is not None:
            return self._session.last_error()
        if self._legacy_session is None:
            return None
        return self._legacy_session.last_error