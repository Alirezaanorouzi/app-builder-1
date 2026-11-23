import json

from worker.events_sanitize import normalize_for_json, sanitize_event_payload


def test_normalize_set_in_payload():
    payload = {"tags": {"a", "b"}, "n": 1}
    safe = sanitize_event_payload(payload, max_bytes=65536)
    json.dumps(safe)
    assert isinstance(safe["tags"], list)


def test_normalize_for_json_nested():
    out = normalize_for_json({"x": {1, 2}})
    assert isinstance(out["x"], list)