"""Push local staging tree to a Vercel Sandbox (sync worker; agent edits local disk)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from vercel.sandbox._internal.options import SandboxCredentials, SyncSandboxServiceOptions
from vercel.sandbox.sync.client import SyncSandboxClient

logger = logging.getLogger(__name__)

SKIP_DIRS = {"node_modules", ".git", "dist", ".next"}
MAX_FILE_BYTES = 2_000_000
MAX_FILES_PER_SYNC = 400
REMOTE_WORKDIR = "/vercel/sandbox"
PREVIEW_PORT = 5173


def _credentials(token: str, team_id: str, project_id: str) -> SandboxCredentials:
    return SandboxCredentials(token=token, team_id=team_id, project_id=project_id)


def connect_sandbox(
    *,
    name: str,
    token: str,
    team_id: str,
    project_id: str,
) -> tuple[object, object, bool]:
    """Return (client, sandbox, created)."""

    def factory() -> SandboxCredentials:
        return _credentials(token, team_id, project_id)

    client = SyncSandboxClient.create(
        options=SyncSandboxServiceOptions(credentials_factory=factory),
    )
    sandbox, created = client.get_or_create_sandbox(
        name=name,
        persistent=True,
        ports=[PREVIEW_PORT],
        resume=True,
        env={"PORT": str(PREVIEW_PORT)},
    )
    return client, sandbox, created


def preview_url_from_sandbox(sandbox: object) -> str | None:
    state = getattr(sandbox, "state", None) or getattr(sandbox, "_state", None)
    if state is None:
        return None
    routes = getattr(state, "routes", ()) or ()
    for route in routes:
        port = getattr(route, "port", None)
        url = getattr(route, "url", None)
        if port == PREVIEW_PORT and url:
            return str(url)
    for route in routes:
        url = getattr(route, "url", None)
        if url:
            return str(url)
    return None


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

    with sandbox.session() as session:  # type: ignore[attr-defined]
        fs = session.filesystem
        with fs.batch(cwd=remote_cwd) as batch:
            for rel, data in files:
                batch.write_bytes(rel, data)
    return len(files)


def _run_bg_dev(session: object) -> None:
    session.run_command(  # type: ignore[attr-defined]
        "bash",
        args=["-lc", "npm install"],
        cwd=REMOTE_WORKDIR,
        capture_output=True,
    )
    session.run_command(  # type: ignore[attr-defined]
        "bash",
        args=["-lc", "nohup npm run dev >/tmp/vite.log 2>&1 &"],
        cwd=REMOTE_WORKDIR,
        capture_output=True,
    )


def sync_staging_to_vercel(
    local_root: Path,
    *,
    name: str,
    token: str | None,
    team_id: str | None,
    project_id: str | None,
) -> tuple[str | None, str | None]:
    """
    Connect (or create) sandbox, upload sources, start dev server.
    Returns (preview_url, external_sandbox_id).
    """
    if not token or not team_id or not project_id:
        return None, None
    client = None
    try:
        client, sandbox, created = connect_sandbox(
            name=name,
            token=token,
            team_id=team_id,
            project_id=project_id,
        )
        sid = getattr(getattr(sandbox, "state", None), "id", None) or name
        count = upload_tree(sandbox, local_root)
        logger.info(
            "Vercel sandbox %s (created=%s): uploaded %s files",
            name,
            created,
            count,
        )
        with sandbox.session() as session:  # type: ignore[attr-defined]
            if created:
                _run_bg_dev(session)
            else:
                session.run_command(
                    "bash",
                    args=["-lc", "pkill -f vite || true; nohup npm run dev >/tmp/vite.log 2>&1 &"],
                    cwd=REMOTE_WORKDIR,
                    capture_output=True,
                )
        refreshed = sandbox.refresh(include_system_routes=True)  # type: ignore[attr-defined]
        url = preview_url_from_sandbox(refreshed)
        if url:
            logger.info("Vercel preview URL for %s: %s", name, url)
        else:
            logger.warning("No Vercel preview URL on routes for %s", name)
        return url, str(sid)
    except Exception:
        logger.exception("Vercel sandbox sync failed for %s", name)
        return None, None
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass