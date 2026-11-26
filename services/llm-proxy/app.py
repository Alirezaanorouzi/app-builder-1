"""Minimal public OpenAI-compatible proxy: virtual keys in memory, upstream Liara with primary key."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="App Builder LLM Proxy")

_ADMIN_KEY = os.environ.get("LLM_PROXY_ADMIN_KEY", "")
_UPSTREAM_BASE = (os.environ.get("LIARA_BASE_URL") or "").rstrip("/")
_UPSTREAM_KEY = os.environ.get("LIARA_API_KEY", "")
_KEYS: dict[str, dict[str, Any]] = {}

_LITELLM_VENDOR_PREFIXES = ("deepseek/", "anthropic/", "google/", "meta/", "mistral/")


def _liara_wire_model(model: str) -> str:
    m = model.strip()
    while m.startswith("openai/openai/"):
        m = m[len("openai/") :]
    if m.startswith("openai/"):
        rest = m[len("openai/") :]
        if any(rest.startswith(v) for v in _LITELLM_VENDOR_PREFIXES):
            return rest
    return m


def _rewrite_upstream_body(body: bytes, content_type: str | None) -> bytes:
    if not body or "json" not in (content_type or "").lower():
        return body
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body
    if not isinstance(payload, dict):
        return body
    model = payload.get("model")
    if isinstance(model, str) and model.strip():
        payload["model"] = _liara_wire_model(model)
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _require_admin(request: Request) -> None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != _ADMIN_KEY:
        raise HTTPException(401, "unauthorized")


@app.post("/admin/keys")
async def create_key(request: Request) -> JSONResponse:
    _require_admin(request)
    body = await request.json()
    key_id = str(body["key_id"])
    api_key = str(body.get("api_key") or "")
    ttl = int(body.get("ttl_seconds", 7200))
    _KEYS[api_key] = {
        "key_id": key_id,
        "run_id": body.get("run_id"),
        "project_id": body.get("project_id"),
        "model": body.get("model"),
        "allowed_models": body.get("allowed_models") or [],
        "expires_at": time.time() + ttl,
    }
    return JSONResponse({"key_id": key_id, "api_key": api_key})


@app.delete("/admin/keys/{key_id}")
async def delete_key(key_id: str, request: Request) -> JSONResponse:
    _require_admin(request)
    for token, meta in list(_KEYS.items()):
        if meta.get("key_id") == key_id:
            del _KEYS[token]
            break
    return JSONResponse({"ok": True})


def _lookup_virtual(auth_header: str | None) -> None:
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = auth_header[7:]
    meta = _KEYS.get(token)
    if not meta:
        raise HTTPException(401, "invalid key")
    if meta["expires_at"] < time.time():
        del _KEYS[token]
        raise HTTPException(401, "expired key")


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def forward_v1(path: str, request: Request) -> Any:
    _lookup_virtual(request.headers.get("Authorization"))
    if not _UPSTREAM_BASE or not _UPSTREAM_KEY:
        raise HTTPException(503, "upstream not configured")
    url = f"{_UPSTREAM_BASE}/{path}"
    raw_body = await request.body()
    body = _rewrite_upstream_body(raw_body, request.headers.get("Content-Type"))
    headers = {
        "Authorization": f"Bearer {_UPSTREAM_KEY}",
        "Content-Type": request.headers.get("Content-Type", "application/json"),
    }
    started = time.perf_counter()
    print(f"llm_proxy request path={path}", flush=True)
    client = httpx.AsyncClient(timeout=120.0)
    try:
        upstream = await client.send(
            client.build_request(request.method, url, content=body, headers=headers),
            stream=True,
        )
    except Exception:
        await client.aclose()
        raise
    content_type = upstream.headers.get("content-type", "")
    if content_type.startswith("text/event-stream"):

        async def _chunks():
            first = True
            try:
                async for chunk in upstream.aiter_bytes():
                    if first:
                        first = False
                        elapsed_ms = (time.perf_counter() - started) * 1000
                        print(f"llm_proxy first_chunk_ms={elapsed_ms:.0f} path={path}", flush=True)
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        return StreamingResponse(
            _chunks(),
            status_code=upstream.status_code,
            media_type="text/event-stream",
        )
    try:
        payload = await upstream.aread()
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(f"llm_proxy response_ms={elapsed_ms:.0f} path={path}", flush=True)
        if not payload:
            return JSONResponse({}, status_code=upstream.status_code)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {"error": payload.decode("utf-8", errors="replace")[:500]}
        return JSONResponse(data, status_code=upstream.status_code)
    finally:
        await upstream.aclose()
        await client.aclose()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}