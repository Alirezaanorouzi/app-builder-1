"""Push local staging tree to a Vercel Sandbox (sync worker; agent edits local disk).

Aligned with https://vercel.com/docs/sandbox/sdk/python — use ``sandbox.fs``, not
``session.filesystem``; reload routes via ``client.get_sandbox(..., include_system_routes=True)``
(not ``SyncSandbox.refresh``, which exists only on runtime session handles).
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from vercel.sandbox._internal.errors import SandboxApiError
from vercel.sandbox._internal.models import SnapshotSource
from vercel.sandbox._internal.options import SandboxCredentials, SyncSandboxServiceOptions
from vercel.sandbox.sync.client import SyncSandboxClient

if TYPE_CHECKING:
    from vercel.sandbox._internal.sync_runtime import SyncSandbox

logger = logging.getLogger(__name__)

from worker.agent_constants import (
    AGENT_SERVER_PORT,
    PREVIEW_PORT,
    REMOTE_WORKDIR,
)

SKIP_DIRS = {"node_modules", ".git", "dist", ".next"}
MAX_FILE_BYTES = 2_000_000
MAX_FILES_PER_SYNC = 400
PREVIEW_WAIT_SECONDS = 120
# Vercel API: process timeout (ms) must be <= 18_000_000 (~5h)
VITE_KILL_AFTER_SECONDS = 18_000


def _credentials(token: str, team_id: str, project_id: str) -> SandboxCredentials:
    return SandboxCredentials(token=token, team_id=team_id, project_id=project_id)


def connect_sandbox(
    *,
    name: str,
    token: str,
    team_id: str,
    project_id: str,
    base_snapshot_id: str | None = None,
) -> tuple[SyncSandboxClient, object, bool]:
    """Return (client, sandbox, created). ``name`` must match ``^[a-zA-Z0-9_-]+$``."""

    def factory() -> SandboxCredentials:
        return _credentials(token, team_id, project_id)

    client = SyncSandboxClient.create(
        options=SyncSandboxServiceOptions(credentials_factory=factory),
    )
    create_kwargs: dict[str, object] = {
        "name": name,
        "persistent": True,
        "ports": [PREVIEW_PORT, AGENT_SERVER_PORT],
        "resume": True,
        "include_system_routes": True,
        "env": {"PORT": str(PREVIEW_PORT)},
    }
    if base_snapshot_id:
        create_kwargs["source"] = SnapshotSource(snapshot_id=base_snapshot_id)
    sandbox, created = client.get_or_create_sandbox(**create_kwargs)  # type: ignore[arg-type]
    if base_snapshot_id and created:
        logger.info(
            "Vercel sandbox %s created from golden snapshot %s",
            name,
            base_snapshot_id,
        )
    return client, sandbox, created


def stop_persistent_sandbox(
    *,
    name: str,
    token: str,
    team_id: str,
    project_id: str,
) -> bool:
    """Stop a persistent sandbox (auto-snapshots filesystem + node_modules on stop)."""

    def factory() -> SandboxCredentials:
        return _credentials(token, team_id, project_id)

    client = SyncSandboxClient.create(
        options=SyncSandboxServiceOptions(credentials_factory=factory),
    )
    try:
        sandbox = client.get_sandbox(name=name, include_system_routes=True)
        sandbox.stop()
        logger.info("Vercel sandbox %s stopped (idle)", name)
        return True
    except SandboxApiError as e:
        logger.warning("Vercel sandbox idle stop for %s: %s", name, e)
        return False
    except Exception:
        logger.exception("Vercel sandbox idle stop failed for %s", name)
        return False
    finally:
        client.close()


def reload_sandbox_routes(client: SyncSandboxClient, api_name: str) -> SyncSandbox:
    """Passive lookup with system routes (official SDK pattern for preview URLs)."""
    return client.get_sandbox(name=api_name, include_system_routes=True)


def _sandbox_routes(sandbox: object) -> tuple:
    routes = getattr(sandbox, "routes", None)
    if not routes:
        state = getattr(sandbox, "state", None) or getattr(sandbox, "_state", None)
        if state is not None:
            routes = getattr(state, "routes", ()) or ()
    return tuple(routes or ())


def url_from_sandbox(sandbox: object, port: int) -> str | None:
    """Public route URL for an exposed sandbox port."""
    for route in _sandbox_routes(sandbox):
        route_port = getattr(route, "port", None)
        url = getattr(route, "url", None)
        if route_port == port and url:
            return str(url)
    return None


def preview_url_from_sandbox(sandbox: object) -> str | None:
    url = url_from_sandbox(sandbox, PREVIEW_PORT)
    if url:
        return url
    for route in _sandbox_routes(sandbox):
        url = getattr(route, "url", None)
        if url:
            return str(url)
    return None


def agent_server_url_from_sandbox(sandbox: object) -> str | None:
    return url_from_sandbox(sandbox, AGENT_SERVER_PORT)


def _command_rc(result: object) -> int:
    rc = getattr(result, "returncode", getattr(result, "exit_code", None))
    if rc is None:
        return 1
    return int(rc)


def _read_vite_log(sandbox: object, *, limit: int = 2000) -> str:
    try:
        r = sandbox.run_command(  # type: ignore[attr-defined]
            "bash",
            args=["-lc", "tail -c 8000 /tmp/vite.log 2>/dev/null || echo '(no vite.log)'"],
            cwd=REMOTE_WORKDIR,
            capture_output=True,
        )
        raw = (getattr(r, "stdout", None) or b"") + (getattr(r, "stderr", None) or b"")
        return raw.decode("utf-8", errors="replace")[-limit:]
    except Exception:
        return ""


def _npm_install_shell() -> str:
    """npm 12 on Vercel blocks lifecycle scripts until ``allowScripts`` (esbuild for Vite)."""
    return (
        f"cd {REMOTE_WORKDIR} && "
        "export NODE_ENV=development && "
        "rm -rf node_modules && "
        "npm install --no-audit || true; "
        "npm install-scripts approve esbuild 2>/dev/null "
        "|| npm install-scripts approve --all; "
        "npm rebuild; "
        "npm install --no-audit; "
        "node_modules/.bin/vite --version"
    )


def _npm_install_if_needed(sandbox: object) -> bool:
    """We never upload ``node_modules``; ensure deps exist on the VM."""
    check = sandbox.run_command(  # type: ignore[attr-defined]
        "bash",
        args=[
            "-lc",
            f"test -x {REMOTE_WORKDIR}/node_modules/.bin/vite",
        ],
        cwd=REMOTE_WORKDIR,
        capture_output=True,
    )
    if _command_rc(check) == 0:
        return True
    logger.info("Vercel sandbox: running npm install in %s", REMOTE_WORKDIR)
    install = sandbox.run_command(  # type: ignore[attr-defined]
        "bash",
        args=["-lc", _npm_install_shell()],
        cwd=REMOTE_WORKDIR,
        capture_output=True,
        kill_after=600,
    )
    if _command_rc(install) != 0:
        stderr = (getattr(install, "stderr", None) or b"").decode("utf-8", errors="replace")
        stdout = (getattr(install, "stdout", None) or b"").decode("utf-8", errors="replace")
        combined = (stderr + "\n" + stdout).strip()
        logger.error("npm install failed: %s", combined[:2000])
        return False
    return True


def _start_vite_dev_server(sandbox: object) -> None:
    """Start Vite bound to the exposed sandbox port (must match ``ports=[5173]``)."""
    sandbox.run_command(  # type: ignore[attr-defined]
        "bash",
        args=["-lc", "pkill -f '[v]ite' 2>/dev/null || true"],
        cwd=REMOTE_WORKDIR,
        capture_output=True,
    )
    env = {"PORT": str(PREVIEW_PORT), "HOST": "0.0.0.0"}
    create_cmd = getattr(sandbox, "create_command", None)
    if callable(create_cmd):
        try:
            create_cmd(
                "npm",
                args=["run", "dev", "--", "--host", "0.0.0.0", "--port", str(PREVIEW_PORT)],
                cwd=REMOTE_WORKDIR,
                env=env,
                kill_after=VITE_KILL_AFTER_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            logger.info("Vercel sandbox: Vite started (create_command)")
            return
        except SandboxApiError as e:
            logger.warning("create_command for Vite failed, using nohup fallback: %s", e)
    sandbox.run_command(  # type: ignore[attr-defined]
        "bash",
        args=[
            "-lc",
            (
                f"cd {REMOTE_WORKDIR} && "
                f"export PORT={PREVIEW_PORT} HOST=0.0.0.0; "
                f"nohup npm run dev -- --host 0.0.0.0 --port {PREVIEW_PORT} "
                f">/tmp/vite.log 2>&1 &"
            ),
        ],
        cwd=REMOTE_WORKDIR,
        capture_output=True,
    )


def _wait_vite_http(sandbox: object, *, timeout_sec: float = PREVIEW_WAIT_SECONDS) -> bool:
    """
    Vercel exposes ``*.vercel.run`` routes before anything listens.
    Wait until Vite answers on the VM port.
    """
    attempts = max(5, int(timeout_sec // 2))
    probe = sandbox.run_command(  # type: ignore[attr-defined]
        "bash",
        args=[
            "-lc",
            (
                f"for i in $(seq 1 {attempts}); do "
                f"curl -sf -o /dev/null http://127.0.0.1:{PREVIEW_PORT}/ && exit 0; "
                f"sleep 2; "
                f"done; "
                f"exit 1"
            ),
        ],
        cwd=REMOTE_WORKDIR,
        capture_output=True,
        kill_after=timeout_sec + 30,
    )
    if _command_rc(probe) == 0:
        return True
    log = _read_vite_log(sandbox)
    logger.warning(
        "Vite not listening on port %s after %.0fs. Log tail:\n%s",
        PREVIEW_PORT,
        timeout_sec,
        log,
    )
    return False


def wait_for_preview_url(
    client: SyncSandboxClient,
    api_name: str,
    sandbox: object,
    *,
    timeout_sec: float = PREVIEW_WAIT_SECONDS,
) -> tuple[str | None, object]:
    """Return public preview URL only after the dev server responds over HTTP."""
    if not _wait_vite_http(sandbox, timeout_sec=timeout_sec):
        return None, sandbox
    try:
        current = reload_sandbox_routes(client, api_name)
    except SandboxApiError as e:
        logger.warning("Route reload for %s: %s", api_name, e)
        current = sandbox
    return preview_url_from_sandbox(current), current


def upload_tree(sandbox: object, local_root: Path, *, remote_cwd: str = REMOTE_WORKDIR) -> int:
    """Upload project files (excludes node_modules). Returns file count."""
    local_root = local_root.resolve()
    files: list[tuple[str, bytes]] = []
    for fp in local_root.rglob("*"):
        if not fp.is_file():
            continue
        if any(part in SKIP_DIRS for part in fp.parts):
            continue
        if fp.stat().st_size > MAX_FILE_BYTES:
            continue
        rel = fp.relative_to(local_root).as_posix()
        files.append((rel, fp.read_bytes()))
        if len(files) >= MAX_FILES_PER_SYNC:
            break
    if not files:
        return 0

    # Use sandbox.fs — do NOT use ``with sandbox.session()`` (exiting stops the session).
    fs = getattr(sandbox, "fs", None)
    if fs is None:
        raise AttributeError("sandbox has no .fs filesystem handle")
    with fs.batch(cwd=remote_cwd) as batch:
        for rel, data in files:
            batch.write_bytes(rel, data)
    return len(files)


def _bootstrap_dev_server(sandbox: object) -> bool:
    if not _npm_install_if_needed(sandbox):
        return False
    _start_vite_dev_server(sandbox)
    return True


class VercelSandboxSession:
    """Keeps a Vercel sandbox alive for the duration of one agent run (sync + HMR)."""

    def __init__(
        self,
        *,
        api_name: str,
        token: str,
        team_id: str,
        project_id: str,
        local_root: Path,
        base_snapshot_id: str | None = None,
    ) -> None:
        self.api_name = api_name
        self.token = token
        self.team_id = team_id
        self.project_id = project_id
        self.local_root = local_root
        self.base_snapshot_id = base_snapshot_id
        self._client: SyncSandboxClient | None = None
        self._sandbox: object | None = None
        self._created: bool = False
        self._dev_bootstrapped = False
        self._golden_fresh = False
        self._golden_upload_done = False
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _connect(self) -> bool:
        if self._sandbox is not None:
            return True
        try:
            self._client, self._sandbox, self._created = connect_sandbox(
                name=self.api_name,
                token=self.token,
                team_id=self.team_id,
                project_id=self.project_id,
                base_snapshot_id=self.base_snapshot_id,
            )
            self._golden_fresh = bool(self._created and self.base_snapshot_id)
            logger.info(
                "Vercel sandbox %s connected (created=%s, golden_fresh=%s)",
                self.api_name,
                self._created,
                self._golden_fresh,
            )
            return True
        except SandboxApiError as e:
            self._last_error = str(e)
            logger.error("Vercel sandbox API error for %s: %s", self.api_name, e)
            return False
        except Exception as e:
            self._last_error = str(e)
            logger.exception("Vercel sandbox connect failed for %s", self.api_name)
            return False

    def sync_and_preview(
        self,
        *,
        start_dev: bool = True,
        http_wait_seconds: float = PREVIEW_WAIT_SECONDS,
        skip_upload: bool = False,
    ) -> tuple[str | None, str | None]:
        """
        Upload staging tree, optionally start Vite, return (preview_url, sandbox_id).
        """
        if not self._connect() or self._sandbox is None:
            return None, None
        try:
            if (
                self._golden_fresh
                and not self._golden_upload_done
                and not skip_upload
            ):
                skip_upload = True
                self._golden_upload_done = True
                logger.info(
                    "Vercel sandbox %s: skip initial upload (golden snapshot)",
                    self.api_name,
                )
            if not skip_upload:
                count = upload_tree(self._sandbox, self.local_root)
                logger.info("Vercel sandbox %s: uploaded %s files", self.api_name, count)
            assert self._client is not None
            if start_dev:
                if not self._dev_bootstrapped:
                    if not _bootstrap_dev_server(self._sandbox):
                        self._last_error = "npm install or vite start failed"
                        return None, None
                    self._dev_bootstrapped = True
                    time.sleep(0.5)
                if http_wait_seconds > 0:
                    url, self._sandbox = wait_for_preview_url(
                        self._client,
                        self.api_name,
                        self._sandbox,
                        timeout_sec=http_wait_seconds,
                    )
                else:
                    self._sandbox = reload_sandbox_routes(self._client, self.api_name)
                    url = preview_url_from_sandbox(self._sandbox)
            else:
                if not _wait_vite_http(self._sandbox, timeout_sec=15):
                    if not _bootstrap_dev_server(self._sandbox):
                        self._last_error = "vite not running on final sync"
                        return None, None
                    self._dev_bootstrapped = True
                    url, self._sandbox = wait_for_preview_url(
                        self._client, self.api_name, self._sandbox
                    )
                else:
                    self._sandbox = reload_sandbox_routes(self._client, self.api_name)
                    url = preview_url_from_sandbox(self._sandbox)
            sid = getattr(self._sandbox, "name", None) or self.api_name
            if url:
                logger.info("Vercel preview URL for %s: %s", self.api_name, url)
            else:
                logger.warning("No Vercel preview URL for %s after sync", self.api_name)
            return url, str(sid)
        except Exception as e:
            self._last_error = str(e)
            logger.exception("Vercel sync failed for %s", self.api_name)
            return None, None

    def wait_for_preview(
        self,
        *,
        http_wait_seconds: float = PREVIEW_WAIT_SECONDS,
    ) -> tuple[str | None, str | None]:
        """Wait until Vite answers (or timeout); refresh routes for preview URL."""
        if not self._connect() or self._sandbox is None or self._client is None:
            return None, None
        if not self._dev_bootstrapped:
            return self.sync_and_preview(
                start_dev=True,
                http_wait_seconds=http_wait_seconds,
            )
        url, self._sandbox = wait_for_preview_url(
            self._client,
            self.api_name,
            self._sandbox,
            timeout_sec=http_wait_seconds,
        )
        sid = getattr(self._sandbox, "name", None) or self.api_name
        if url:
            logger.info("Vercel preview ready for %s: %s", self.api_name, url)
        return url, str(sid)

    def sync_files_only(self) -> bool:
        """Push file updates mid-run for Vite HMR on the sandbox preview."""
        if not self._connect() or self._sandbox is None:
            return False
        try:
            upload_tree(self._sandbox, self.local_root)
            return True
        except Exception:
            logger.exception("Vercel mid-run sync failed for %s", self.api_name)
            return False

    def stop_persistent(self) -> bool:
        """Stop the VM session; persistent sandboxes auto-snapshot on stop."""
        if self._sandbox is not None and hasattr(self._sandbox, "stop"):
            try:
                self._sandbox.stop()  # type: ignore[union-attr]
                self._dev_bootstrapped = False
                logger.info("Vercel sandbox %s stopped", self.api_name)
                return True
            except Exception:
                logger.exception("Vercel stop failed for %s", self.api_name)
                return False
        return stop_persistent_sandbox(
            name=self.api_name,
            token=self.token,
            team_id=self.team_id,
            project_id=self.project_id,
        )

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self._sandbox = None


def sync_staging_to_vercel(
    local_root: Path,
    *,
    name: str,
    token: str | None,
    team_id: str | None,
    project_id: str | None,
) -> tuple[str | None, str | None]:
    """One-shot sync (creates connection, uploads, closes). Prefer ``VercelSandboxSession`` per run."""
    if not token or not team_id or not project_id:
        return None, None
    session = VercelSandboxSession(
        api_name=name,
        token=token,
        team_id=team_id,
        project_id=project_id,
        local_root=local_root,
    )
    try:
        return session.sync_and_preview(start_dev=True)
    finally:
        session.close()