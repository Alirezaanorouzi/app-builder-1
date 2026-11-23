"""Best-effort truncation of run_events payloads for UI — not used for SDK rebuild."""

from __future__ import annotations

import json
from typing import Any


def normalize_for_json(obj: Any) -> Any:
    """Make OpenHands model_dump() trees safe for json.dumps / Postgres JSONB."""
    if isinstance(obj, dict):
        return {str(k): normalize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [normalize_for_json(x) for x in obj]
    if isinstance(obj, set):
        return [normalize_for_json(x) for x in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _truncate_strings(obj: Any, max_str: int, budget: list[int]) -> Any:
    if budget[0] <= 0:
        return "[truncated]"
    if isinstance(obj, str):
        if len(obj) > max_str:
            obj = obj[-max_str:] + "\n…[truncated for UI]"
        budget[0] -= len(obj)
        return obj
    if isinstance(obj, dict):
        return {k: _truncate_strings(v, max_str, budget) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate_strings(x, max_str, budget) for x in obj]
    return obj


def sanitize_event_payload(payload: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    normalized = normalize_for_json(payload)
    if not isinstance(normalized, dict):
        normalized = {"value": normalized}
    text = json.dumps(normalized, default=str)
    if len(text.encode("utf-8")) <= max_bytes:
        return normalized
    trimmed: Any = _truncate_strings(normalized, max_str=8192, budget=[max_bytes])
    if not isinstance(trimmed, dict):
        trimmed = {"_ui_truncated": True, "preview": str(trimmed)[:1024]}
    out = json.dumps(trimmed, default=str)
    if len(out.encode("utf-8")) > max_bytes:
        trimmed = {
            "event_class": payload.get("kind") or payload.get("type"),
            "_ui_truncated": True,
        }
    return trimmed