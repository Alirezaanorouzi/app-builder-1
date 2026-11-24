"""HTTP client for OpenHands Agent Server (health, interrupt, conversation state)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0


def _headers(session_api_key: str) -> dict[str, str]:
    return {"X-Session-API-Key": session_api_key}


def _base(host_url: str) -> str:
    return host_url.rstrip("/")


def ready_ok(host_url: str, session_api_key: str, *, timeout: float = 15.0) -> bool:
    try:
        r = httpx.get(
            f"{_base(host_url)}/ready",
            headers=_headers(session_api_key),
            timeout=timeout,
        )
        return r.status_code == 200
    except Exception:
        logger.debug("agent server ready check failed for %s", host_url, exc_info=True)
        return False


def health_ok(host_url: str, session_api_key: str, *, timeout: float = 10.0) -> bool:
    try:
        r = httpx.get(
            f"{_base(host_url)}/health",
            headers=_headers(session_api_key),
            timeout=timeout,
        )
        if r.status_code != 200:
            return False
        data = r.json()
        return str(data.get("status", "")).lower() in ("ok", "healthy")
    except Exception:
        logger.debug("agent server health check failed for %s", host_url, exc_info=True)
        return False


def interrupt_conversation(
    host_url: str,
    session_api_key: str,
    conversation_id: UUID,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    try:
        r = httpx.post(
            f"{_base(host_url)}/api/conversations/{conversation_id}/interrupt",
            headers=_headers(session_api_key),
            timeout=timeout,
        )
        if r.status_code in (200, 204, 404):
            return True
        logger.warning(
            "interrupt conversation %s returned %s: %s",
            conversation_id,
            r.status_code,
            r.text[:500],
        )
        return False
    except Exception:
        logger.exception("interrupt conversation %s failed", conversation_id)
        return False


def switch_conversation_llm(
    host_url: str,
    session_api_key: str,
    conversation_id: UUID,
    llm_payload: dict[str, Any],
    *,
    timeout: float = 60.0,
) -> bool:
    """POST /api/conversations/{id}/switch_llm — update in-place LLM on Agent Server."""
    try:
        r = httpx.post(
            f"{_base(host_url)}/api/conversations/{conversation_id}/switch_llm",
            headers=_headers(session_api_key),
            json={"llm": llm_payload},
            timeout=timeout,
        )
        if r.status_code in (200, 204):
            return True
        logger.warning(
            "switch_llm conversation %s returned %s: %s",
            conversation_id,
            r.status_code,
            r.text[:500],
        )
        return False
    except Exception:
        logger.exception("switch_llm conversation %s failed", conversation_id)
        return False


def get_conversation(
    host_url: str,
    session_api_key: str,
    conversation_id: UUID,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any] | None:
    try:
        r = httpx.get(
            f"{_base(host_url)}/api/conversations/{conversation_id}",
            headers=_headers(session_api_key),
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        logger.debug("get conversation %s failed", conversation_id, exc_info=True)
        return None