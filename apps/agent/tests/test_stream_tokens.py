from types import SimpleNamespace

from worker.stream_tokens import RunLiveStreamAppender, extract_stream_delta


def test_extract_stream_delta_content_and_reasoning() -> None:
    chunk = SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content="سلام",
                    reasoning_content="think",
                )
            )
        ]
    )
    content, reasoning = extract_stream_delta(chunk)
    assert content == "سلام"
    assert reasoning == "think"


def test_run_live_stream_appender_batches() -> None:
    calls: list[str] = []

    class FakeDb:
        def append_run_live_output(self, _run_id, text: str) -> None:
            calls.append(text)

    appender = RunLiveStreamAppender(FakeDb(), "00000000-0000-0000-0000-000000000000", flush_chars=3)
    chunk = SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content="abc", reasoning_content=None))]
    )
    appender.feed(chunk)
    appender.flush()
    assert calls == ["abc"]