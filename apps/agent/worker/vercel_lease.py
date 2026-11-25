"""Vercel sandbox session deadline (idle) via extend_execution_time_limit — no worker stop()."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Vercel Hobby cumulative execution limit is ~45 minutes per session.
DEFAULT_MAX_SESSION_SECONDS = 2700


def runtime_session_limit_seconds(session: Any) -> float | None:
    """Configured execution time limit (seconds from session start)."""
    limit = getattr(session, "execution_time_limit", None)
    if limit is None:
        return None
    if isinstance(limit, timedelta):
        return limit.total_seconds()
    return None


def runtime_session_remaining_seconds(session: Any) -> float | None:
    """Seconds until the current runtime session hits its execution time limit."""
    started = getattr(session, "started_at", None)
    limit_sec = runtime_session_limit_seconds(session)
    if started is None or limit_sec is None:
        return None
    deadline = (int(started) / 1000.0) + limit_sec
    return deadline - time.time()


def max_extend_headroom(
    session: Any,
    *,
    max_session_seconds: int,
) -> int | None:
    """How many seconds Vercel allows adding before the plan session cap."""
    if max_session_seconds < 1:
        return None
    limit_sec = runtime_session_limit_seconds(session)
    if limit_sec is None:
        return max_session_seconds
    headroom = int(max_session_seconds - limit_sec)
    return headroom if headroom > 0 else 0


def seconds_to_extend(
    *,
    remaining: float | None,
    idle_seconds: int,
    when_remaining_below: int,
    force: bool,
    max_session_seconds: int = DEFAULT_MAX_SESSION_SECONDS,
    current_limit_seconds: float | None = None,
) -> int | None:
    """Return how many seconds to add, or None if extend is unnecessary."""
    if idle_seconds < 1:
        return None
    below = max(1, min(when_remaining_below, idle_seconds))
    headroom = max_session_seconds
    if current_limit_seconds is not None:
        headroom = max(0, int(max_session_seconds - current_limit_seconds))
    if headroom < 1:
        return None

    if force:
        if remaining is None:
            want = min(idle_seconds, headroom)
            return want if want > 0 else None
        if remaining >= idle_seconds - 5:
            return None
        need = idle_seconds - remaining
        return min(max(1, int(need) + 1), headroom, idle_seconds)

    if remaining is None:
        return min(idle_seconds, headroom)
    if remaining >= below:
        return None
    need = idle_seconds - remaining
    add = max(1, int(need) + 1)
    return min(add, headroom, idle_seconds)


def _extend_invalid_timeout(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "sandbox_timeout_invalid" in text or "maximum execution timeout" in text


def extend_sandbox_idle_deadline(
    sandbox: Any,
    *,
    idle_seconds: int,
    when_remaining_below: int,
    force: bool = False,
    max_session_seconds: int = DEFAULT_MAX_SESSION_SECONDS,
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
    limit_sec = runtime_session_limit_seconds(session) if session is not None else None
    add_sec = seconds_to_extend(
        remaining=remaining,
        idle_seconds=idle_seconds,
        when_remaining_below=when_remaining_below,
        force=force,
        max_session_seconds=max_session_seconds,
        current_limit_seconds=limit_sec,
    )
    if add_sec is None:
        return False

    def _call(seconds: int) -> None:
        extend(timedelta(seconds=seconds))

    try:
        _call(add_sec)
        logger.info(
            "Vercel lease +%ss (remaining≈%.0fs, idle=%ss, cap=%ss)",
            add_sec,
            remaining if remaining is not None else -1,
            idle_seconds,
            max_session_seconds,
        )
        return True
    except Exception as exc:
        if session is not None and _extend_invalid_timeout(exc):
            room = max_extend_headroom(session, max_session_seconds=max_session_seconds)
            if room is not None and 0 < room < add_sec:
                try:
                    _call(room)
                    logger.info(
                        "Vercel lease +%ss (capped retry, requested=%ss)",
                        room,
                        add_sec,
                    )
                    return True
                except Exception:
                    logger.warning(
                        "Vercel extend capped retry failed",
                        exc_info=True,
                    )
            logger.info(
                "Vercel lease at session cap (requested +%ss, headroom=%s)",
                add_sec,
                room,
            )
            return False
        logger.warning("Vercel extend_execution_time_limit failed", exc_info=True)
        return False