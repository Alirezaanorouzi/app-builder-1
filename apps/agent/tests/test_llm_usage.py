from types import SimpleNamespace

from worker.llm_usage import UsageRecorder, parse_stream_usage


def test_parse_liara_stream_usage() -> None:
    chunk = SimpleNamespace(
        id="chatcmpl-1",
        model="deepseek/deepseek-v4.1-flash-1017",
        usage=SimpleNamespace(
            prompt_tokens=8174,
            completion_tokens=142,
            total_cost=0.000088866,
            total_cost_toman=36.41,
            prompt_tokens_details=SimpleNamespace(cached_tokens=7872),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=14),
        ),
        choices=[],
    )
    parsed = parse_stream_usage(chunk)
    assert parsed is not None
    assert parsed.response_id == "chatcmpl-1"
    assert parsed.prompt_tokens == 8174
    assert parsed.completion_tokens == 142
    assert parsed.cache_read_tokens == 7872
    assert parsed.reasoning_tokens == 14
    assert parsed.cost_usd == 0.000088866
    assert parsed.cost_toman == 36.41


def test_ignore_chunks_without_usage() -> None:
    chunk = SimpleNamespace(
        id="chatcmpl-1",
        choices=[SimpleNamespace(delta=SimpleNamespace(content="سلام"))],
        usage=None,
    )
    assert parse_stream_usage(chunk) is None


def test_recorder_keeps_one_row_per_response() -> None:
    recorder = UsageRecorder()
    chunk = {
        "id": "log-1",
        "model": "openai/gpt-4o-mini",
        "usage": {
            "prompt_tokens": 19,
            "completion_tokens": 9,
            "total_cost": 0.00000825,
            "total_cost_toman": 0.99,
            "native_tokens_cached": 0,
            "native_tokens_reasoning": 0,
        },
    }
    first = recorder.observe(chunk)
    second = recorder.observe(chunk)
    assert first is not None
    assert second is None
    assert first.cost_toman == 0.99
