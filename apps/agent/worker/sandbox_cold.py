"""When a Vercel VM session ends, DB rows can still say ready — treat as cold."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return None


def is_session_expired(sb_row: dict[str, Any] | None, *, now: datetime | None = None) -> bool:
    if sb_row is None:
        return False
    expires = parse_utc(sb_row.get("session_expires_at"))
    if expires is None:
        return False
    now = now or datetime.now(timezone.utc)
    return expires <= now


def stack_considered_warm(sb_row: dict[str, Any] | None) -> bool:
    """False when lease expired even if agent_server_status still says ready."""
    if sb_row is None:
        return False
    if is_session_expired(sb_row):
        return False
    if sb_row.get("status") == "stopped":
        return False
    return True