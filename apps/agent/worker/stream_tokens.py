"""Parse OpenHands / LiteLLM stream chunks and batch-append to DB for SSE."""

from __future__ import annotations

import threading
import time
from typing import Any

from worker.db import Database


def extract_stream_delta(chunk: Any) -> tuple[str, str]:
    """Return (visible_content, reasoning_content) from a ModelResponseStream chunk."""
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return "", ""
    delta = getattr(choices[0], "delta", None)
    if delta is None:
        return "", ""
    content = getattr(delta, "content", None) or ""
    reasoning = getattr(delta, "reasoning_content", None) or ""
    if not isinstance(content, str):
        content = str(content) if content is not None else ""
    if not isinstance(reasoning, str):
        reasoning = str(reasoning) if reasoning is not None else ""
    return content, reasoning


class RunLiveStreamAppender:
    """Debounced writer for agent_runs.live_output."""

    def __init__(
        self,
        db: Database,
        run_id: Any,
        *,
        flush_chars: int = 48,
        flush_interval_s: float = 0.35,
    ) -> None:
        self._db = db
        self._run_id = run_id
        self._flush_chars = flush_chars
        self._flush_interval_s = flush_interval_s
        self._content_buf = ""
        self._lock = threading.Lock()
        self._last_flush = time.monotonic()

    def feed(self, chunk: Any) -> None:
        content, _reasoning = extract_stream_delta(chunk)
        if not content:
            return
        with self._lock:
            self._content_buf += content
            should_flush = len(self._content_buf) >= self._flush_chars
            if not should_flush:
                should_flush = (
                    time.monotonic() - self._last_flush
                ) >= self._flush_interval_s
            if should_flush:
                self._flush_locked()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if not self._content_buf:
            return
        self._db.append_run_live_output(self._run_id, self._content_buf)
        self._content_buf = ""
        self._last_flush = time.monotonic()