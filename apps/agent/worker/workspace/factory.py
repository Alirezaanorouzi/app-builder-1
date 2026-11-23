from __future__ import annotations

from worker.config import Settings
from worker.workspace.base import WorkspaceAdapter
from worker.workspace.local import LocalWorkspace
from worker.workspace.vercel_ws import VercelWorkspace


def build_workspace(settings: Settings, project_id: str) -> WorkspaceAdapter:
    staging_root = settings.workspace_staging_dir
    if settings.sandbox_provider == "vercel" and settings.vercel_token:
        return VercelWorkspace(settings=settings, project_id=project_id)
    return LocalWorkspace(staging_root, project_id, settings.templates_dir)