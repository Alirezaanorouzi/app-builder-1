"""Vercel sandbox session deadline (idle) via extend_execution_time_limit — no worker stop()."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)


def runtime_session_remaining_seconds(session: Any) -> float | None:
    """Seconds until the current runtime session hits its execution time limit."""
    started = getattr(session, "started_at", None)
    limit = getattr(session, "execution_time_limit", None)
    if started is None or limit is None:
        return None
    if isinstance(limit, timedelta):
        limit_sec = limit.total_seconds()
    else:
        return None
    deadline = (int(started) / 1000.0) + limit_sec
    return deadline - time.time()


def seconds_to_extend(
    *,
    remaining: float | None,
    idle_seconds: int,
    when_remaining_below: int,
    force: bool,
) -> int | None:
    """Return how many seconds to add, or None if extend is unnecessary."""
    if idle_seconds < 1:
        return None
    below = max(1, min(when_remaining_below, idle_seconds))
    if force:
        return idle_seconds
    if remaining is None:
        return idle_seconds
    if remaining >= below:
        return None
    need = idle_seconds - remaining
    return max(1, int(need) + 1)


def extend_sandbox_idle_deadline(
    sandbox: Any,
    *,
    idle_seconds: int,
    when_remaining_below: int,
    force: bool = False,
) -> bool:
    """
    Call Vercel ``extend_execution_time_limit`` when remaining time is low.

    Does not touch DB activity timestamps (renewal is not user activity).
    """
    extend = getattr(sandbox, "extend_execution_time_limit", None)
    if not callable(extend):
        return False
    session = getattr(sandbox, "current_session", None)
    remaining = runtime_session_remaining_seconds(session) if session is not None else None
    add_sec = seconds_to_extend(
        remaining=remaining,
        idle_seconds=idle_seconds,
        when_remaining_below=when_remaining_below,
        force=force,
    )
    if add_sec is None:
        return False
    try:
        extend(timedelta(seconds=add_sec))
        logger.info(
            "Vercel lease +%ss (remaining≈%.0fs, idle=%ss)",
            add_sec,
            remaining if remaining is not None else -1,
            idle_seconds,
        )
        return True
    except Exception:
        logger.warning("Vercel extend_execution_time_limit failed", exc_info=True)
        return False