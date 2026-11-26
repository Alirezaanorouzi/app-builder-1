"""Per-run virtual LLM keys via a public HTTPS proxy (primary Liara key stays on proxy)."""

from __future__ import annotations

import ipaddress
import logging
import secrets
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from worker.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunLlmCredential:
    api_key: str
    base_url: str
    key_id: str


def is_public_https_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme != "https":
        return False
    host = (p.hostname or "").lower()
    if not host or host in ("localhost", "127.0.0.1", "::1"):
        return False
    if host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False
    except ValueError:
        pass
    return True


def llm_base_url_for_sandbox(settings: Settings) -> str:
    public = (settings.llm_proxy_public_url or "").rstrip("/")
    if not public:
        raise RuntimeError("LLM_PROXY_PUBLIC_URL is required for AGENT_RUNTIME=remote on Vercel")
    if not is_public_https_url(public):
        raise RuntimeError(
            "LLM_PROXY_PUBLIC_URL must be a public HTTPS URL reachable from Vercel sandboxes"
        )
    if public.endswith("/v1"):
        return public
    return f"{public}/v1"


def mint_run_llm_credential(
    settings: Settings,
    *,
    run_id: uuid.UUID,
    project_id: uuid.UUID,
    model: str,
    ttl_seconds: int = 7200,
) -> RunLlmCredential:
    key_id = f"run-{run_id.hex}"
    if settings.llm_remote_direct_liara:
        if not settings.liara_api_key or not settings.liara_base_url:
            raise RuntimeError("LIARA_API_KEY and LIARA_BASE_URL required for LLM_REMOTE_DIRECT_LIARA")
        logger.warning(
            "LLM_REMOTE_DIRECT_LIARA=1 — sandbox uses Liara directly (dev only; no virtual keys)"
        )
        return RunLlmCredential(
            api_key=settings.liara_api_key,
            base_url=settings.liara_base_url.rstrip("/"),
            key_id=key_id,
        )
    base_url = llm_base_url_for_sandbox(settings)
    virtual = secrets.token_urlsafe(32)
    admin_url = (settings.llm_proxy_admin_url or settings.llm_proxy_public_url or "").rstrip("/")
    admin_key = settings.llm_proxy_admin_key
    if not admin_url or not admin_key:
        raise RuntimeError(
            "LLM_PROXY_ADMIN_URL and LLM_PROXY_ADMIN_KEY must be set on the worker "
            "(the proxy rejects unregistered virtual keys)."
        )
    try:
        r = httpx.post(
            f"{admin_url}/admin/keys",
            headers={"Authorization": f"Bearer {admin_key}"},
            json={
                "key_id": key_id,
                "api_key": virtual,
                "run_id": str(run_id),
                "project_id": str(project_id),
                "model": model,
                "ttl_seconds": ttl_seconds,
                "allowed_models": list(settings.liara_models),
            },
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        virtual = str(data.get("api_key", virtual))
        key_id = str(data.get("key_id", key_id))
    except Exception as e:
        logger.exception("LLM proxy mint failed for run %s", run_id)
        raise RuntimeError(
            "Virtual LLM key could not be registered on LLM_PROXY (mint /admin/keys failed). "
            "Check LLM_PROXY_ADMIN_URL is reachable from the worker."
        ) from e
    return RunLlmCredential(api_key=virtual, base_url=base_url, key_id=key_id)


def revoke_run_llm_key(settings: Settings, key_id: str | None) -> None:
    if not key_id:
        return
    admin_url = (settings.llm_proxy_admin_url or settings.llm_proxy_public_url or "").rstrip("/")
    admin_key = settings.llm_proxy_admin_key
    if not admin_url or not admin_key:
        return
    try:
        httpx.delete(
            f"{admin_url}/admin/keys/{key_id}",
            headers={"Authorization": f"Bearer {admin_key}"},
            timeout=10.0,
        )
    except Exception:
        logger.debug("revoke llm key %s failed", key_id, exc_info=True)