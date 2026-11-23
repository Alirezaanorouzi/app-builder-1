from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from worker.config import Settings
from worker.workspace.base import CommandResult, WorkspaceAdapter
from worker.workspace.local import LocalWorkspace
from worker.workspace.vercel_sync import PREVIEW_PORT, sync_staging_to_vercel

logger = logging.getLogger(__name__)


class VercelWorkspace(WorkspaceAdapter):
    """
    Agent edits a local staging tree (fast, OpenHands-compatible).
    After each run the worker pushes to Vercel Sandbox for a public preview URL.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        project_id: str,
    ) -> None:
        self.project_id = project_id
        self.name = f"{settings.deploy_env}:{project_id}"
        self.settings = settings
        self._staging = LocalWorkspace(
            settings.workspace_staging_dir,
            project_id,
            settings.templates_dir,
        )
        self.root = self._staging.root
        self._preview: str | None = None
        self._external_id: str | None = None

    def ensure(self, project_id: str, template_name: str) -> bool:
        return self._staging.ensure(project_id, template_name)

    def resolve(self, path: str | None) -> Path:
        return self._staging.resolve(path)

    def view_file(self, path: str) -> str:
        return self._staging.view_file(path)

    def str_replace(self, path: str, old: str, new: str) -> str:
        return self._staging.str_replace(path, old, new)

    def insert(self, path: str, line: int, text: str) -> str:
        return self._staging.insert(path, line, text)

    def create_file(self, path: str, content: str) -> str:
        return self._staging.create_file(path, content)

    def grep(self, pattern: str, path: str = ".") -> str:
        return self._staging.grep(pattern, path)

    def glob(self, pattern: str) -> str:
        return self._staging.glob(pattern)

    def run_command(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: int = 120,
        background: bool = False,
    ) -> CommandResult:
        return self._staging.run_command(
            command, cwd=cwd, timeout=timeout, background=background
        )

    def read_command_output(self, command_id: str) -> CommandResult:
        return self._staging.read_command_output(command_id)

    def preview_url(self) -> str | None:
        """Only Vercel Sandbox URL after publish — not local staging."""
        return self._preview

    def publish_to_vercel(self) -> tuple[str | None, str | None]:
        """Upload staging → Vercel Sandbox; return preview URL and sandbox id."""
        url, sid = sync_staging_to_vercel(
            self.root,
            name=self.name,
            token=self.settings.vercel_token,
            team_id=self.settings.vercel_team_id,
            project_id=self.settings.vercel_project_id,
        )
        if url:
            self._preview = url
        if sid:
            self._external_id = sid
        return url, sid

    def stop_idle(self) -> None:
        pass

    def extend_session(self) -> None:
        if not self.settings.vercel_token:
            return
        # Extend is handled on next publish_to_vercel session acquisition.
        logger.debug("extend_session noop for %s (port %s)", self.name, PREVIEW_PORT)

    def external_sandbox_id(self) -> str | None:
        return self._external_id