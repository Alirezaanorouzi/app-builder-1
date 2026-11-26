"""Vercel sandbox lifecycle: Vite preview + OpenHands Agent Server on the same VM."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import shlex
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Callable
from typing import TYPE_CHECKING, Iterator
from uuid import UUID

from worker.agent_constants import (
    AGENT_SERVER_KILL_AFTER_SECONDS,
    AGENT_SERVER_PORT,
    PREVIEW_PORT,
    REMOTE_WORKDIR,
)
from worker.agent_server_client import ready_ok
from worker.config import Settings
from worker.workspace.vercel_names import vercel_sandbox_api_name, vercel_sandbox_display_name
from worker.workspace.vercel_sync import (
    VercelSandboxSession,
    agent_server_url_from_sandbox,
    preview_url_from_sandbox,
    reload_sandbox_routes,
)

if TYPE_CHECKING:
    from openhands.sdk.workspace.base import BaseWorkspace

logger = logging.getLogger(__name__)

_AGENT_ENTRY_REMOTE = ".openhands/agent_server_entry.py"


def local_agent_entry_sha() -> str | None:
    local = Path(__file__).with_name("agent_server_entry.py")
    if not local.is_file():
        return None
    return hashlib.sha256(local.read_bytes()).hexdigest()


def _ensure_agent_server_entry_on_vm(
    sandbox: object,
    settings: Settings,
    *,
    stored_sha: str | None,
    force: bool,
) -> str | None:
    """Upload the entry file only when its hash differs from the last upload."""
    del settings
    local = Path(__file__).with_name("agent_server_entry.py")
    if not local.is_file():
        return stored_sha
    data = local.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if not force and stored_sha == sha:
        return sha
    fs = getattr(sandbox, "fs", None)
    if fs is None:
        return sha
    with fs.batch(cwd=REMOTE_WORKDIR) as batch:
        batch.write_bytes(_AGENT_ENTRY_REMOTE, data)
    logger.info("Uploaded agent server entry sha=%s", sha[:12])
    return sha


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
        "OH_MAX_CMD_OUTPUT_CHARS": str(settings.oh_max_cmd_output_chars),
    }


def spawn_agent_and_vite(sandbox: object, env: dict[str, str]) -> None:
    """Start the agent and Vite as tracked commands that outlive this API call.

    ``run_command`` waits until the command's process group exits. A shell that
    backgrounds both servers never finishes, so the worker holds the project
    lock, stops heartbeating, and the run is failed as "heartbeat lost" before
    ``/ready`` is ever polled. ``create_command`` returns immediately and Vercel
    keeps each process until ``kill_after``.
    """
    agent_script = (
        f"cd {shlex.quote(REMOTE_WORKDIR)} && mkdir -p .openhands && "
        f"exec python {_AGENT_ENTRY_REMOTE} --host 0.0.0.0 --port {AGENT_SERVER_PORT} "
        f">>/tmp/agent-server.log 2>&1"
    )
    vite_script = (
        f"cd {shlex.quote(REMOTE_WORKDIR)} && "
        f"exec nice npm run dev -- --host 0.0.0.0 --port {PREVIEW_PORT} "
        f">>/tmp/vite.log 2>&1"
    )
    common = {
        "cwd": REMOTE_WORKDIR,
        "env": env,
        "kill_after": AGENT_SERVER_KILL_AFTER_SECONDS,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    sandbox.create_command("bash", args=["-lc", agent_script], **common)  # type: ignore[attr-defined]
    sandbox.create_command("bash", args=["-lc", vite_script], **common)  # type: ignore[attr-defined]
    logger.info("Spawned agent server and Vite as detached commands")


def tail_remote_log(sandbox: object, path: str, *, lines: int = 40) -> str:
    """Best-effort last lines of a VM log. Used when /ready never succeeds."""
    try:
        result = sandbox.run_command(  # type: ignore[attr-defined]
            "bash",
            args=["-lc", f"tail -n {int(lines)} {shlex.quote(path)}"],
            cwd=REMOTE_WORKDIR,
            capture_output=True,
            kill_after=8,
        )
    except Exception:
        logger.debug("could not read %s", path, exc_info=True)
        return ""
    out = getattr(result, "stdout", b"") or b""
    if isinstance(out, bytes):
        out = out.decode("utf-8", errors="replace")
    return str(out)[-2000:]


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
        self._runtime_session_id: str | None = None
        self._entry_sha: str | None = None

    def seed_agent_url_hint(self, url: str | None) -> None:
        """Last-known public Agent Server URL (verified again before reuse)."""
        if url:
            self._agent_url = url.rstrip("/")

    def adopt_warm_agent(self, agent_url: str, *, status: str = "ready") -> None:
        """Trust a live Agent Server after an HTTP /ready check (skip VM ensure)."""
        self._agent_url = agent_url.rstrip("/")
        self._agent_status = status

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
                idle_seconds=self.settings.sandbox_idle_seconds,
                extend_when_remaining_seconds=self.settings.sandbox_extend_when_remaining_seconds,
                max_session_seconds=self.settings.vercel_sandbox_max_session_seconds,
                snapshot_retention_count=self.settings.vercel_snapshot_retention_count,
                snapshot_delete_evicted=self.settings.vercel_snapshot_delete_evicted,
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

    def connected_sandbox(self) -> object | None:
        session = self._sandbox_session
        if session is None:
            return None
        return session._sandbox  # noqa: SLF001

    def _wait_public_ready(self, public: str, *, attempts: int = 30, sleep_s: float = 0.4) -> bool:
        public = public.rstrip("/")
        for attempt in range(attempts):
            if ready_ok(public, self.session_api_key, timeout=1.5):
                self._agent_url = public
                self._agent_status = "ready"
                return True
            if attempt < attempts - 1:
                time.sleep(sleep_s)
        return False

    def bring_up(
        self,
        *,
        stored_session_id: str | None,
        stored_entry_sha: str | None,
        on_connected: Callable[[], None] | None = None,
        on_spawned: Callable[[], None] | None = None,
        on_ready: Callable[[], None] | None = None,
        on_retention: Callable[[], None] | None = None,
    ) -> tuple[str | None, str, str | None, str | None]:
        """Connect once. Spawn only when the runtime session changed or /ready fails.

        Returns (agent_url, status, runtime_session_id, entry_sha).
        """
        from worker.session_expiry import runtime_session_id

        session = self._open()
        if session is None:
            self._agent_status = "failed"
            return None, self._agent_status, None, stored_entry_sha
        if on_retention is not None:
            session.on_retention = lambda _sandbox: on_retention()
        if session._sandbox is None and not session._connect():  # noqa: SLF001
            self._agent_status = "failed"
            return None, self._agent_status, None, stored_entry_sha
        sandbox = session._sandbox  # noqa: SLF001
        client = session._client  # noqa: SLF001
        if sandbox is None or client is None:
            self._agent_status = "failed"
            return None, self._agent_status, None, stored_entry_sha
        if on_connected is not None:
            on_connected()
        current_id = runtime_session_id(sandbox)
        self._runtime_session_id = current_id
        public = agent_server_url_from_sandbox(sandbox) or self._agent_url
        same_session = bool(stored_session_id and current_id and stored_session_id == current_id)
        if same_session and public and ready_ok(public, self.session_api_key, timeout=3.0):
            self._agent_url = public
            self._agent_status = "ready"
            self._entry_sha = stored_entry_sha
            if on_ready is not None:
                on_ready()
            return public, "ready", current_id, stored_entry_sha

        created = bool(getattr(session, "_created", False))
        entry_sha = _ensure_agent_server_entry_on_vm(
            sandbox,
            self.settings,
            stored_sha=stored_entry_sha,
            force=created,
        )
        self._entry_sha = entry_sha
        if on_spawned is not None:
            on_spawned()
        env = _agent_server_env(self.settings, self.session_api_key)
        spawn_agent_and_vite(sandbox, env)
        if not public:
            try:
                sandbox = reload_sandbox_routes(client, self.api_name)
                session._sandbox = sandbox  # noqa: SLF001
                public = agent_server_url_from_sandbox(sandbox)
            except Exception:
                logger.warning("Route reload after agent spawn failed", exc_info=True)
        if not public:
            self._agent_status = "failed"
            return None, self._agent_status, current_id, entry_sha
        if not self._wait_public_ready(public):
            log_tail = tail_remote_log(sandbox, "/tmp/agent-server.log")
            logger.warning(
                "Agent Server public /ready failed for %s\n%s",
                public,
                log_tail or "(no agent-server log)",
            )
            self._agent_status = "failed"
            return None, self._agent_status, current_id, entry_sha
        if on_ready is not None:
            on_ready()
        return self._agent_url, self._agent_status, current_id, entry_sha

    def ensure_agent_server(self) -> tuple[str | None, str]:
        url, status, _sid, _sha = self.bring_up(
            stored_session_id=self._runtime_session_id,
            stored_entry_sha=self._entry_sha,
        )
        return url, status

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

    def extend_idle_deadline(self, *, force: bool = False) -> bool:
        session = self._sandbox_session
        if session is None:
            opened = self._open()
            session = opened
        if session is None:
            return False
        return session.extend_idle_deadline(force=force)

    def stop_idle(self) -> bool:
        """No-op: Vercel stops the VM at execution deadline (see vercel_lease)."""
        return False

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