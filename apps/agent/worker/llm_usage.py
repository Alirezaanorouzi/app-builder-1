"""Turn a Liara/OpenAI stream chunk into one billable call.

Liara puts the charge on the last streamed chunk (OpenHands already asks for
``stream_options.include_usage``). Cost is taken from Liara's own fields,
never recomputed from token counts, because cached tokens are cheaper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LlmCallUsage:
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
    if number != number:  # NaN
        return None
    return number


def _int(value: Any) -> int:
    number = _num(value)
    if number is None or number < 0:
        return 0
    return int(number)


def _detail(usage: Any, name: str, field: str) -> int:
    details = getattr(usage, name, None)
    if details is None and isinstance(usage, dict):
        details = usage.get(name)
    if details is None:
        return 0
    if isinstance(details, dict):
        return _int(details.get(field))
    return _int(getattr(details, field, None))


def parse_stream_usage(chunk: Any, *, model_fallback: str = "") -> LlmCallUsage | None:
    """Return a call record when this chunk carries a real usage object."""
    usage = getattr(chunk, "usage", None)
    if usage is None and isinstance(chunk, dict):
        usage = chunk.get("usage")
    if not usage:
        return None

    def get(key: str) -> Any:
        if isinstance(usage, dict):
            return usage.get(key)
        return getattr(usage, key, None)

    prompt = _int(get("prompt_tokens") or get("tokens_prompt"))
    completion = _int(get("completion_tokens") or get("tokens_completion"))
    cost_usd = _num(get("total_cost"))
    if cost_usd is None:
        cost_usd = _num(get("cost"))
    if cost_usd is None:
        cost_usd = _num(get("usage"))
    cost_toman = _num(get("total_cost_toman"))
    if prompt == 0 and completion == 0 and not cost_usd and not cost_toman:
        return None

    cached = _detail(usage, "prompt_tokens_details", "cached_tokens")
    if cached == 0:
        cached = _int(get("native_tokens_cached"))
    reasoning = _detail(usage, "completion_tokens_details", "reasoning_tokens")
    if reasoning == 0:
        reasoning = _int(get("native_tokens_reasoning"))

    response_id = str(getattr(chunk, "id", None) or (chunk.get("id") if isinstance(chunk, dict) else "") or "")
    model = str(getattr(chunk, "model", None) or (chunk.get("model") if isinstance(chunk, dict) else "") or model_fallback)
    return LlmCallUsage(
        response_id=response_id,
        model=model[:200],
        prompt_tokens=prompt,
        completion_tokens=completion,
        cache_read_tokens=cached,
        reasoning_tokens=reasoning,
        cost_usd=max(0.0, cost_usd or 0.0),
        cost_toman=max(0.0, cost_toman or 0.0),
    )


class UsageRecorder:
    """Drop repeated chunks of the same Liara response inside one run."""

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._anon = 0

    def observe(self, chunk: Any, *, model_fallback: str = "") -> LlmCallUsage | None:
        parsed = parse_stream_usage(chunk, model_fallback=model_fallback)
        if parsed is None:
            return None
        response_id = parsed.response_id
        if not response_id:
            self._anon += 1
            response_id = f"local-{self._anon}"
            parsed = LlmCallUsage(
                response_id=response_id,
                model=parsed.model,
                prompt_tokens=parsed.prompt_tokens,
                completion_tokens=parsed.completion_tokens,
                cache_read_tokens=parsed.cache_read_tokens,
                reasoning_tokens=parsed.reasoning_tokens,
                cost_usd=parsed.cost_usd,
                cost_toman=parsed.cost_toman,
            )
        if response_id in self._seen:
            return None
        self._seen.add(response_id)
        return parsed
