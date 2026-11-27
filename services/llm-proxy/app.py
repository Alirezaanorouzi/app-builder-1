"""Public OpenAI-compatible proxy.

One shared HTTP client talks to Liara. Chat streams are forwarded with
``send(stream=True)`` and each chunk is yielded before it is inspected, so the
sandbox is not waiting on the rest of the generation or on a fresh TLS handshake.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from usage_stream import CallUsage, UsageTap, rewrite_upstream_body, usage_from_completion

# read is the wait for the next chunk, not a cap on the whole generation.
_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)
_LIMITS = httpx.Limits(max_keepalive_connections=20, max_connections=100, keepalive_expiry=30.0)

_ADMIN_KEY = os.environ.get("LLM_PROXY_ADMIN_KEY", "")
_UPSTREAM_BASE = (os.environ.get("LIARA_BASE_URL") or "").rstrip("/")
_UPSTREAM_KEY = os.environ.get("LIARA_API_KEY", "")
_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_KEYS: dict[str, dict[str, Any]] = {}
_client: httpx.AsyncClient | None = None
_db_warned = False


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    global _client
    _client = httpx.AsyncClient(timeout=_TIMEOUT, limits=_LIMITS)
    try:
        yield
    finally:
        await _client.aclose()
        _client = None


app = FastAPI(title="App Builder LLM Proxy", lifespan=_lifespan)


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
        "user_id": body.get("user_id"),
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


def _lookup_virtual(auth_header: str | None) -> dict[str, Any]:
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = auth_header[7:]
    meta = _KEYS.get(token)
    if not meta:
        raise HTTPException(401, "invalid key")
    if meta["expires_at"] < time.time():
        del _KEYS[token]
        raise HTTPException(401, "expired key")
    return meta


def _upstream() -> httpx.AsyncClient:
    if _client is None:
        raise HTTPException(503, "upstream client is not ready")
    return _client


async def iter_upstream_bytes(upstream: Any, on_done: Any) -> AsyncIterator[bytes]:
    """Yield each upstream chunk immediately, then record usage after the stream."""
    tap = UsageTap()
    try:
        async for chunk in upstream.aiter_bytes():
            yield chunk
            tap.feed(chunk)
    finally:
        await upstream.aclose()
    tap.finish()
    try:
        await on_done(tap.call)
    except Exception:
        print("llm_proxy usage record failed", flush=True)


def _store_usage(meta: dict[str, Any], call: CallUsage | None) -> None:
    global _db_warned
    if call is None or not call.response_id:
        return
    user_id = meta.get("user_id")
    run_id = meta.get("run_id")
    if not user_id or not run_id:
        return
    if not _DATABASE_URL:
        if not _db_warned:
            _db_warned = True
            print("llm_proxy usage not stored: DATABASE_URL is unset", flush=True)
        return
    import psycopg

    with psycopg.connect(_DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO usage_ledger (
              user_id, run_id, model, prompt_tokens, completion_tokens,
              cache_read_tokens, reasoning_tokens, cost_usd, cost_toman,
              provider_response_id, source
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'agent')
            ON CONFLICT (run_id, provider_response_id)
              WHERE provider_response_id IS NOT NULL AND provider_response_id <> ''
              DO NOTHING
            """,
            (
                user_id,
                run_id,
                call.model or str(meta.get("model") or "unknown"),
                call.prompt_tokens,
                call.completion_tokens,
                call.cache_read_tokens,
                call.reasoning_tokens,
                call.cost_usd,
                call.cost_toman,
                call.response_id,
            ),
        )


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def forward_v1(path: str, request: Request) -> Any:
    meta = _lookup_virtual(request.headers.get("Authorization"))
    if not _UPSTREAM_BASE or not _UPSTREAM_KEY:
        raise HTTPException(503, "upstream not configured")
    client = _upstream()
    url = f"{_UPSTREAM_BASE}/{path}"
    raw_body = await request.body()
    body = rewrite_upstream_body(
        raw_body,
        request.headers.get("Content-Type"),
        end_user=str(meta.get("user_id") or "") or None,
        chat=path.rstrip("/").endswith("chat/completions"),
    )
    headers = {
        "Authorization": f"Bearer {_UPSTREAM_KEY}",
        "Content-Type": request.headers.get("Content-Type", "application/json"),
    }
    started = time.perf_counter()
    print(f"llm_proxy request path={path}", flush=True)
    try:
        upstream = await client.send(
            client.build_request(request.method, url, content=body, headers=headers),
            stream=True,
        )
    except Exception:
        print(f"llm_proxy upstream_error path={path}", flush=True)
        raise
    content_type = upstream.headers.get("content-type", "")
    if content_type.startswith("text/event-stream"):

        async def _on_done(call: CallUsage | None) -> None:
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(f"llm_proxy stream_done_ms={elapsed_ms:.0f} path={path}", flush=True)
            await asyncio.to_thread(_store_usage, meta, call)

        async def _chunks() -> AsyncIterator[bytes]:
            first = True
            async for chunk in iter_upstream_bytes(upstream, _on_done):
                if first:
                    first = False
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    print(f"llm_proxy first_chunk_ms={elapsed_ms:.0f} path={path}", flush=True)
                yield chunk

        return StreamingResponse(
            _chunks(),
            status_code=upstream.status_code,
            media_type="text/event-stream",
        )
    try:
        payload = await upstream.aread()
    finally:
        await upstream.aclose()
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"llm_proxy response_ms={elapsed_ms:.0f} path={path}", flush=True)
    if not payload:
        return JSONResponse({}, status_code=upstream.status_code)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        data = {"error": payload.decode("utf-8", errors="replace")[:500]}
    if isinstance(data, dict):
        try:
            await asyncio.to_thread(_store_usage, meta, usage_from_completion(data))
        except Exception:
            print("llm_proxy usage record failed", flush=True)
    return JSONResponse(data, status_code=upstream.status_code)


@app.get("/")
@app.get("/health")
@app.get("/ready")
async def health() -> dict[str, str]:
    return {"status": "ok"}
