from worker.builder_prompt import BUILDER_SYSTEM_PROMPT


def test_builder_prompt_mentions_summary_and_persian() -> None:
    assert "summary" in BUILDER_SYSTEM_PROMPT
    assert "فارسی" in BUILDER_SYSTEM_PROMPT or "Persian" in BUILDER_SYSTEM_PROMPT
    assert len(BUILDER_SYSTEM_PROMPT) > 200