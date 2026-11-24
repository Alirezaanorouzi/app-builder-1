"""Monotonic phase timing for agent runs (logs + optional DB snapshot)."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

LOG_PREFIX = "RUN_TIMELINE"


@dataclass
class RunTimeline:
    run_id: uuid.UUID
    t0: float | None = None
    marks: list[tuple[str, float]] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.t0 is None:
            self.t0 = time.perf_counter()

    def has_phase(self, phase: str) -> bool:
        return phase in self._seen

    def mark(self, phase: str, *, once: bool = False) -> float:
        if once and phase in self._seen:
            return self.elapsed_ms(phase)
        self._seen.add(phase)
        now = time.perf_counter()
        self.marks.append((phase, now))
        assert self.t0 is not None
        prev = self.marks[-2][1] if len(self.marks) > 1 else self.t0
        logger.info(
            "%s run=%s phase=%s total_ms=%.0f step_ms=%.0f",
            LOG_PREFIX,
            self.run_id,
            phase,
            (now - self.t0) * 1000,
            (now - prev) * 1000,
        )
        return now

    def elapsed_ms(self, phase: str) -> float:
        assert self.t0 is not None
        for name, t in self.marks:
            if name == phase:
                return (t - self.t0) * 1000
        return -1.0

    def phases_payload(self) -> list[dict[str, Any]]:
        assert self.t0 is not None
        out: list[dict[str, Any]] = []
        prev = self.t0
        for name, t in self.marks:
            out.append(
                {
                    "phase": name,
                    "total_ms": round((t - self.t0) * 1000),
                    "step_ms": round((t - prev) * 1000),
                }
            )
            prev = t
        return out

    def log_summary(self) -> None:
        logger.info(
            "%s run=%s SUMMARY %s",
            LOG_PREFIX,
            self.run_id,
            " | ".join(
                f"{p['phase']}={p['total_ms']}ms(+{p['step_ms']})" for p in self.phases_payload()
            ),
        )

    def persist(self, db: Any, run_id: uuid.UUID, event_seq: int) -> int:
        """Store timeline on run_events for UI/debug; returns next seq."""
        try:
            db.insert_run_event(
                run_id,
                event_seq,
                "RunTimelineEvent",
                {
                    "summary": "زمان‌بندی مسیر اجرا",
                    "phases": self.phases_payload(),
                },
                tool_name=None,
            )
            return event_seq + 1
        except Exception:
            logger.exception("RunTimelineEvent insert failed")
            return event_seq


def prewarm_openhands_sdk() -> float:
    """Import heavy OpenHands modules once at worker startup."""
    t0 = time.perf_counter()
    try:
        from openhands.sdk import Conversation, LLM  # noqa: F401
        from openhands.tools.preset.default import get_default_agent  # noqa: F401
    except ImportError:
        logger.warning("OpenHands SDK not installed; skipping prewarm")
        return 0.0
    elapsed = time.perf_counter() - t0
    logger.info("OpenHands SDK prewarm completed in %.2fs", elapsed)
    return elapsed