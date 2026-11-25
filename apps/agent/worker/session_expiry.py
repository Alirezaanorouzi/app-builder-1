"""Persist approximate Vercel session deadline to sandboxes.session_expires_at."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from worker.db import Database


def record_sandbox_session_expiry(
    db: Database,
    project_id: uuid.UUID,
    *,
    lease_seconds: int,
) -> None:
    if lease_seconds < 1:
        return
    expires = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
    db.touch_sandbox_session_expires(project_id, expires_at=expires)