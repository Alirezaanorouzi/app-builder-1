"""Vercel Sandbox API naming — names must match ^[a-zA-Z0-9_-]+$."""

from __future__ import annotations

import re

_VERCEL_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


def vercel_sandbox_api_name(deploy_env: str, project_id: str) -> str:
    """
    Stable, API-valid sandbox name for get_or_create_sandbox.

    Example: ``dev-f162723e751d42d4a68d73d6a3981e63`` (no colons).
    """
    env = re.sub(r"[^a-zA-Z0-9_-]", "_", (deploy_env or "dev").strip())[:24] or "dev"
    pid = re.sub(r"[^a-fA-F0-9]", "", str(project_id))[:32]
    if not pid:
        pid = re.sub(r"[^a-zA-Z0-9_-]", "", str(project_id))[:32]
    name = f"{env}-{pid}"
    assert _VERCEL_NAME.match(name), name
    return name[:63]


def vercel_sandbox_display_name(deploy_env: str, project_id: str) -> str:
    """Human-readable label stored in Postgres (not sent to Vercel API)."""
    return f"{deploy_env}:{project_id}"