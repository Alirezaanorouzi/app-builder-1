"""Rewrite a chat body and pull Liara's usage object out of an SSE stream.

The tap never holds a chunk back. Callers yield the bytes first, then feed them
here, so the sandbox sees tokens while the proxy still learns the cost.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


_LITELLM_VENDOR_PREFIXES = ("deepseek/", "anthropic/", "google/", "meta/", "mistral/")


@dataclass(frozen=True)
class CallUsage:
    response_id: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int
    reasoning_tokens: int
    cost_usd: float
    cost_toman: float


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _int(value: Any) -> int:
    number = _num(value)
    if number is None or number < 0:
        return 0
    return int(number)


def _detail(usage: dict[str, Any], name: str, field: str) -> int:
    details = usage.get(name)
    if isinstance(details, dict):
        return _int(details.get(field))
    return 0


def liara_wire_model(model: str) -> str:
    m = model.strip()
    while m.startswith("openai/openai/"):
        m = m[len("openai/") :]
    if m.startswith("openai/"):
        rest = m[len("openai/") :]
        if any(rest.startswith(v) for v in _LITELLM_VENDOR_PREFIXES):
            return rest
    return m


def usage_from_completion(obj: dict[str, Any]) -> CallUsage | None:
    """Liara's own charge. Token counts are stored beside it, not priced again."""
    usage = obj.get("usage")
    if not isinstance(usage, dict):
        return None
    prompt = _int(usage.get("prompt_tokens") or usage.get("tokens_prompt"))
    completion = _int(usage.get("completion_tokens") or usage.get("tokens_completion"))
    cost_usd = _num(usage.get("total_cost"))
    if cost_usd is None:
        cost_usd = _num(usage.get("cost"))
    cost_toman = _num(usage.get("total_cost_toman"))
    if prompt == 0 and completion == 0 and not cost_usd and not cost_toman:
        return None
    cached = _detail(usage, "prompt_tokens_details", "cached_tokens")
    if cached == 0:
        cached = _int(usage.get("native_tokens_cached"))
    reasoning = _detail(usage, "completion_tokens_details", "reasoning_tokens")
    if reasoning == 0:
        reasoning = _int(usage.get("native_tokens_reasoning"))
    return CallUsage(
        response_id=str(obj.get("id") or ""),
        model=str(obj.get("model") or "")[:200],
        prompt_tokens=prompt,
        completion_tokens=completion,
        cache_read_tokens=cached,
        reasoning_tokens=reasoning,
        cost_usd=max(0.0, cost_usd or 0.0),
        cost_toman=max(0.0, cost_toman or 0.0),
    )


def rewrite_upstream_body(
    body: bytes,
    content_type: str | None,
    *,
    end_user: str | None,
    chat: bool,
) -> bytes:
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
        payload["model"] = liara_wire_model(model)
    if chat:
        if end_user and not payload.get("user"):
            payload["user"] = end_user
        if payload.get("stream") is True:
            options = payload.get("stream_options")
            if not isinstance(options, dict):
                options = {}
            options.setdefault("include_usage", True)
            payload["stream_options"] = options
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class UsageTap:
    """Collect the usage object from SSE events as the bytes pass through."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.call: CallUsage | None = None

    def feed(self, chunk: bytes) -> None:
        self._buf.extend(chunk)
        while True:
            sep, width = _event_sep(self._buf)
            if sep < 0:
                if len(self._buf) > 1_000_000:
                    del self._buf[:-8192]
                return
            raw = bytes(self._buf[:sep])
            del self._buf[: sep + width]
            self._take(raw)

    def finish(self) -> None:
        if self._buf.strip():
            self._take(bytes(self._buf))
        self._buf.clear()

    def _take(self, raw: bytes) -> None:
        for line in raw.splitlines():
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if not data or data == b"[DONE]":
                continue
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                parsed = usage_from_completion(obj)
                if parsed is not None:
                    self.call = parsed


def _event_sep(buf: bytearray) -> tuple[int, int]:
    for marker in (b"\r\n\r\n", b"\n\n"):
        sep = buf.find(marker)
        if sep >= 0:
            return sep, len(marker)
    return -1, 0
