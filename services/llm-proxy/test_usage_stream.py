from __future__ import annotations

import asyncio
import json
from pathlib import Path

from usage_stream import UsageTap, rewrite_upstream_body

import app as proxy_app


def test_rewrite_tags_user_and_asks_for_usage():
    raw = json.dumps(
        {"model": "openai/deepseek/deepseek-v4-flash", "stream": True, "messages": []}
    ).encode()
    out = json.loads(
        rewrite_upstream_body(
            raw,
            "application/json",
            end_user="user-1",
            chat=True,
        )
    )
    assert out["model"] == "deepseek/deepseek-v4-flash"
    assert out["user"] == "user-1"
    assert out["stream_options"]["include_usage"] is True


def test_rewrite_keeps_an_existing_user():
    raw = json.dumps({"model": "m", "stream": True, "user": "already", "messages": []}).encode()
    out = json.loads(rewrite_upstream_body(raw, "application/json", end_user="user-1", chat=True))
    assert out["user"] == "already"


def test_tap_reads_usage_split_across_chunks():
    usage = {
        "id": "log-1",
        "model": "deepseek/deepseek-v4-flash",
        "choices": [],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "total_cost": 0.00002,
            "total_cost_toman": 8.5,
            "prompt_tokens_details": {"cached_tokens": 3},
            "completion_tokens_details": {"reasoning_tokens": 1},
        },
    }
    raw = b"data: " + json.dumps(usage).encode() + b"\n\n"
    tap = UsageTap()
    tap.feed(raw[:12])
    assert tap.call is None
    tap.feed(raw[12:])
    tap.finish()
    assert tap.call is not None
    assert tap.call.response_id == "log-1"
    assert tap.call.cost_toman == 8.5
    assert tap.call.cache_read_tokens == 3
    assert tap.call.reasoning_tokens == 1


def test_forward_uses_one_shared_streaming_client():
    text = Path(proxy_app.__file__).read_text(encoding="utf-8")
    assert "stream=True" in text
    assert ".request(" not in text
    assert text.count("httpx.AsyncClient(") == 1


async def _first_chunk_before_rest():
    released = asyncio.Event()
    recorded: list[object] = []

    class FakeUpstream:
        async def aiter_bytes(self):
            yield b"data: {\"id\":\"1\",\"choices\":[{\"delta\":{\"content\":\"a\"}}]}\n\n"
            await released.wait()
            yield b"data: [DONE]\n\n"

        async def aclose(self) -> None:
            return None

    async def on_done(call):
        recorded.append(call)

    stream = proxy_app.iter_upstream_bytes(FakeUpstream(), on_done)
    first = await asyncio.wait_for(stream.__anext__(), timeout=0.2)
    assert b"content" in first
    assert recorded == []
    released.set()
    rest = [chunk async for chunk in stream]
    assert rest[-1].startswith(b"data: [DONE]")
    assert recorded == [None]


def test_stream_yields_before_the_upstream_finishes():
    asyncio.run(_first_chunk_before_rest())
