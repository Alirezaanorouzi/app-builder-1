"""One sandbox bootstrap at a time per project (Vercel + Agent Server)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _lock_for(project_id: str) -> threading.Lock:
    with _guard:
        if project_id not in _locks:
            _locks[project_id] = threading.Lock()
        return _locks[project_id]


@contextmanager
def project_sandbox_lock(project_id: str) -> Iterator[None]:
    lock = _lock_for(project_id)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()