"""Persist the Vercel runtime deadline, not a guessed now + lease."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from worker.db import Database
from worker.sandbox_cold import parse_utc
from worker.vercel_lease import runtime_session_limit_seconds


def measured_session_deadline(
    session: object | None,
    *,
    max_session_seconds: int,
) -> datetime | None:
    """Absolute deadline from started_at + execution_time_limit, capped by the plan."""
    if session is None:
        return None
    started = getattr(session, "started_at", None)
    limit = runtime_session_limit_seconds(session)
    if started is None or limit is None:
        return None
    capped = float(limit)
    if max_session_seconds > 0:
        capped = min(capped, float(max_session_seconds))
    if capped < 0:
        return None
    return datetime.fromtimestamp(int(started) / 1000.0 + capped, tz=timezone.utc)


def record_measured_session_expiry(
    db: Database,
    project_id: uuid.UUID,
    sandbox: object | None,
    *,
    max_session_seconds: int,
) -> datetime | None:
    """Write the live session deadline. Does nothing when the VM clock is unknown."""
    if sandbox is None:
        return None
    session = getattr(sandbox, "current_session", None)
    expires = measured_session_deadline(session, max_session_seconds=max_session_seconds)
    if expires is None:
        return None
    db.touch_sandbox_session_expires(project_id, expires_at=expires)
    return expires


def stored_lease_is_fresh(
    expires_at: Any,
    *,
    renew_when_remaining_below: int,
    now: datetime | None = None,
) -> bool:
    """True when the stored real deadline is far enough out to skip a Vercel connect."""
    expires = parse_utc(expires_at)
    if expires is None:
        return False
    now = now or datetime.now(timezone.utc)
    remaining = (expires - now).total_seconds()
    threshold = max(1, renew_when_remaining_below)
    return remaining > threshold


def runtime_session_id(sandbox: object | None) -> str | None:
    if sandbox is None:
        return None
    session = getattr(sandbox, "current_session", None)
    if session is None:
        return None
    sid = getattr(session, "id", None)
    if not sid:
        return None
    return str(sid)
