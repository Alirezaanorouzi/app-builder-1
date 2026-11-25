"""One sandbox bootstrap at a time per project (in-process + optional Postgres advisory)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worker.db import Database

_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _lock_for(project_id: str) -> threading.Lock:
    with _guard:
        if project_id not in _locks:
            _locks[project_id] = threading.Lock()
        return _locks[project_id]


class SandboxLockTimeout(TimeoutError):
    """Per-project bootstrap lock held too long (wake vs run)."""


@contextmanager
def _thread_project_lock(project_id: str, *, timeout_sec: float) -> Iterator[None]:
    lock = _lock_for(project_id)
    if timeout_sec > 0:
        acquired = lock.acquire(timeout=timeout_sec)
        if not acquired:
            raise SandboxLockTimeout(
                f"Timed out after {timeout_sec:.0f}s waiting for sandbox lock on {project_id}"
            )
    else:
        lock.acquire()
    try:
        yield
    finally:
        lock.release()


@contextmanager
def project_sandbox_lock(
    project_id: str,
    *,
    timeout_sec: float = 300.0,
    db: Database | None = None,
) -> Iterator[None]:
    """
    Serialize Vercel preview + Agent Server work per project.

    Thread lock covers one worker process; optional ``db`` adds ``pg_advisory_lock``
    for multiple worker replicas.
    """
    if db is not None:
        with db.project_advisory_lock(project_id, timeout_sec=timeout_sec):
            with _thread_project_lock(project_id, timeout_sec=timeout_sec):
                yield
    else:
        with _thread_project_lock(project_id, timeout_sec=timeout_sec):
            yield