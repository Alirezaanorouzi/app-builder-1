"""Vercel sandbox lifecycle: Vite preview + OpenHands Agent Server on the same VM."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import subprocess
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator
from uuid import UUID

from worker.agent_constants import (
    AGENT_SERVER_KILL_AFTER_SECONDS,
    AGENT_SERVER_PORT,
    REMOTE_WORKDIR,
)
from worker.agent_server_client import health_ok, ready_ok
from worker.config import Settings
from worker.workspace.vercel_names import vercel_sandbox_api_name, vercel_sandbox_display_name
from worker.workspace.vercel_sync import (
    VercelSandboxSession,
    _command_rc,
    agent_server_url_from_sandbox,
    preview_url_from_sandbox,
    reload_sandbox_routes,
)

if TYPE_CHECKING:
    from openhands.sdk.workspace.base import BaseWorkspace

logger = logging.getLogger(__name__)


def _derive_session_api_key(settings: Settings, project_id: str) -> str:
    if settings.oh_session_api_key:
        return settings.oh_session_api_key
    material = (
        f"oh-session:v1:{settings.deploy_env}:{project_id}:"
        f"{settings.oh_secret_key or 'local-dev'}"
    )
    digest = hashlib.sha256(material.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _agent_server_env(
    settings: Settings,
    session_api_key: str,
) -> dict[str, str]:
    secret = settings.oh_secret_key or secrets.token_urlsafe(24)
    return {
        "OH_SESSION_API_KEYS_0": session_api_key,
        "OH_SECRET_KEY": secret,
        "PORT": str(AGENT_SERVER_PORT),
        "OPENHANDS_SUPPRESS_BANNER": "1",
        "LITELLM_LOG": "ERROR",
    }


def _stop_agent_server_process(sandbox: object) -> None:
    sandbox.run_command(  # type: ignore[attr-defined]
        "bash",
        args=["-lc", "pkill -f '[o]penhands.agent_server' 2>/dev/null || true"],
        cwd=REMOTE_WORKDIR,
        capture_output=True,
    )


def _wait_agent_health_on_vm(sandbox: object, *, attempts: int = 30) -> bool:
    probe = sandbox.run_command(  # type: ignore[attr-defined]
        "bash",
        args=[
            "-lc",
            (
                f"for i in $(seq 1 {attempts}); do "
                f"curl -sf http://127.0.0.1:{AGENT_SERVER_PORT}/ready && exit 0; "
                f"sleep 2; done; exit 1"
            ),
        ],
        cwd=REMOTE_WORKDIR,
        capture_output=True,
        kill_after=90,
    )
    return _command_rc(probe) == 0


def _start_agent_server_process(
    sandbox: object,
    env: dict[str, str],
) -> None:
    _stop_agent_server_process(sandbox)
    create_cmd = getattr(sandbox, "create_command", None)
    cmd_args = [
        "-m",
        "openhands.agent_server",
        "--host",
        "0.0.0.0",
        "--port",
        str(AGENT_SERVER_PORT),
    ]
    if callable(create_cmd):
        try:
            create_cmd(
                "python",
                args=cmd_args,
                cwd=REMOTE_WORKDIR,
                env=env,
                kill_after=AGENT_SERVER_KILL_AFTER_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("Agent Server started via create_command on port %s", AGENT_SERVER_PORT)
            return
        except Exception as e:
            logger.warning("create_command for Agent Server failed, using nohup: %s", e)
    sandbox.run_command(  # type: ignore[attr-defined]
        "bash",
        args=[
            "-lc",
            (
                f"cd {REMOTE_WORKDIR} && "
                f"export OH_SESSION_API_KEYS_0='{env['OH_SESSION_API_KEYS_0']}' "
                f"OH_SECRET_KEY='{env['OH_SECRET_KEY']}' PORT={AGENT_SERVER_PORT}; "
                f"pkill -f '[o]penhands.agent_server' 2>/dev/null || true; "
                f"nohup python -m openhands.agent_server --host 0.0.0.0 "
                f"--port {AGENT_SERVER_PORT} >/tmp/agent-server.log 2>&1 &"
            ),
        ],
        cwd=REMOTE_WORKDIR,
        capture_output=True,
    )


class VercelProjectSession:
    """One project's persistent Vercel VM (preview + agent server)."""

    def __init__(
        self,
        settings: Settings,
        project_id: str,
        *,
        session_api_key: str | None = None,
    ) -> None:
        self.settings = settings
        self.project_id = project_id
        self.api_name = vercel_sandbox_api_name(settings.deploy_env, project_id)
        self.display_name = vercel_sandbox_display_name(settings.deploy_env, project_id)
        self.session_api_key = session_api_key or _derive_session_api_key(settings, project_id)
        self._sandbox_session: VercelSandboxSession | None = None
        self._agent_url: str | None = None
        self._agent_status = "starting"

    def seed_agent_url_hint(self, url: str | None) -> None:
        """Last-known public Agent Server URL (verified again before reuse)."""
        if url:
            self._agent_url = url.rstrip("/")

    def _open(self) -> VercelSandboxSession | None:
        if not self.settings.vercel_token or not self.settings.vercel_team_id:
            return None
        if self._sandbox_session is None:
            # Remote runtime: agent files live on VM; no staging uploads mid-run.
            staging = settings_staging_placeholder(self.settings, self.project_id)
            self._sandbox_session = VercelSandboxSession(
                api_name=self.api_name,
                token=self.settings.vercel_token,
                team_id=self.settings.vercel_team_id,
                project_id=self.settings.vercel_project_id or "",
                local_root=staging,
                base_snapshot_id=self.settings.vercel_base_snapshot_id,
            )
        return self._sandbox_session

    def extend_preview(self, *, fast: bool = False) -> tuple[str | None, str | None]:
        session = self._open()
        if session is None:
            return None, None
        wait = 0.0 if fast else float(self.settings.vercel_preview_wait_seconds)
        return session.sync_and_preview(
            start_dev=True,
            http_wait_seconds=wait,
            skip_upload=True,
        )

    def warm_preview(self) -> tuple[str | None, str | None]:
        session = self._sandbox_session
        if session is None:
            return None, None
        return session.wait_for_preview(
            http_wait_seconds=float(self.settings.vercel_preview_wait_seconds),
        )

    def _reuse_if_ready(self, public: str) -> tuple[str | None, str] | None:
        """Return (url, status) when an existing Agent Server answers /ready; else None."""
        public = public.rstrip("/")
        if self._agent_url == public and self._agent_status == "ready":
            if ready_ok(public, self.session_api_key, timeout=5.0):
                return public, "ready"
        if ready_ok(public, self.session_api_key, timeout=8.0):
            logger.info("Agent Server already ready at %s (skip restart)", public)
            self._agent_url = public
            self._agent_status = "ready"
            return public, self._agent_status
        return None

    def _wait_public_ready(self, public: str, *, attempts: int, sleep_s: float) -> bool:
        public = public.rstrip("/")
        for attempt in range(attempts):
            timeout = 10.0 if attempt == 0 else 15.0
            if ready_ok(public, self.session_api_key, timeout=timeout):
                self._agent_url = public
                self._agent_status = "ready"
                return True
            if attempt < attempts - 1:
                time.sleep(sleep_s)
        return False

    def ensure_agent_server(self) -> tuple[str | None, str]:
        session = self._open()
        if session is None:
            self._agent_status = "failed"
            return None, self._agent_status
        if session._sandbox is None:  # noqa: SLF001
            logger.info("Sandbox not connected yet; connecting before Agent Server ensure")
            self.extend_preview(fast=True)
        if session._sandbox is None:  # noqa: SLF001
            self._agent_status = "failed"
            return None, self._agent_status
        sandbox = session._sandbox  # noqa: SLF001
        client = session._client  # noqa: SLF001
        if client is None:
            self._agent_status = "failed"
            return None, self._agent_status
        sandbox = reload_sandbox_routes(client, self.api_name)
        session._sandbox = sandbox  # noqa: SLF001
        public = agent_server_url_from_sandbox(sandbox)
        if not public and self._agent_url:
            public = self._agent_url
        if public:
            reused = self._reuse_if_ready(public)
            if reused:
                return reused
            if _wait_agent_health_on_vm(sandbox, attempts=2):
                sandbox = reload_sandbox_routes(client, self.api_name)
                session._sandbox = sandbox  # noqa: SLF001
                public = agent_server_url_from_sandbox(sandbox) or public
                reused = self._reuse_if_ready(public)
                if reused:
                    return reused

        logger.info("Agent Server cold start for project %s", self.project_id)
        env = _agent_server_env(self.settings, self.session_api_key)
        _start_agent_server_process(sandbox, env)
        time.sleep(1.0)
        if not _wait_agent_health_on_vm(sandbox):
            logger.warning("Agent Server did not answer on VM port %s", AGENT_SERVER_PORT)
            self._agent_status = "failed"
            return None, self._agent_status
        sandbox = reload_sandbox_routes(client, self.api_name)
        session._sandbox = sandbox  # noqa: SLF001
        public = agent_server_url_from_sandbox(sandbox)
        if not public:
            self._agent_status = "failed"
            return None, self._agent_status
        if not self._wait_public_ready(public, attempts=12, sleep_s=1.5):
            logger.warning("Agent Server public /ready failed for %s", public)
            self._agent_status = "failed"
            return None, self._agent_status
        return self._agent_url, self._agent_status

    def agent_server_url(self) -> str | None:
        return self._agent_url

    def agent_server_status(self) -> str:
        return self._agent_status

    def preview_url(self) -> str | None:
        session = self._sandbox_session
        if session is None or session._sandbox is None:  # noqa: SLF001
            return None
        return preview_url_from_sandbox(session._sandbox)  # noqa: SLF001

    def external_sandbox_id(self) -> str | None:
        session = self._sandbox_session
        if session is None or session._sandbox is None:  # noqa: SLF001
            return None
        sid = getattr(session._sandbox, "name", None) or self.api_name  # noqa: SLF001
        return str(sid)

    def last_error(self) -> str | None:
        session = self._sandbox_session
        return session.last_error if session else None

    @contextmanager
    def remote_workspace(self) -> Iterator["BaseWorkspace"]:
        from openhands.sdk import Workspace

        host = self._agent_url
        if not host:
            raise RuntimeError("agent server URL not ready")
        ws = Workspace(
            host=host,
            working_dir=REMOTE_WORKDIR,
            api_key=self.session_api_key,
        )
        try:
            yield ws
        finally:
            close = getattr(ws, "close", None)
            if callable(close):
                close()

    def stop_idle(self) -> bool:
        session = self._sandbox_session
        if session is None:
            return False
        return session.stop_persistent()

    def close(self) -> None:
        if self._sandbox_session is not None:
            self._sandbox_session.close()
        self._sandbox_session = None


def settings_staging_placeholder(settings: Settings, project_id: str) -> "Path":
    from pathlib import Path

    root = Path(settings.workspace_staging_dir) / "sandboxes" / project_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def interrupt_conversation(
    agent_url: str,
    session_api_key: str,
    conversation_id: UUID,
) -> bool:
    from worker.agent_server_client import interrupt_conversation as _interrupt

    return _interrupt(agent_url, session_api_key, conversation_id)