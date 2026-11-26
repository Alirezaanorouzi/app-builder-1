from worker.builder_prompt import BUILDER_SECURITY_RULES, BUILDER_SYSTEM_PROMPT


def test_builder_prompt_mentions_summary_and_persian() -> None:
    assert "summary" in BUILDER_SYSTEM_PROMPT
    assert "فارسی" in BUILDER_SYSTEM_PROMPT or "Persian" in BUILDER_SYSTEM_PROMPT
    assert "then stop" in BUILDER_SYSTEM_PROMPT
    assert "Security rules" not in BUILDER_SYSTEM_PROMPT
    assert "API keys" not in BUILDER_SYSTEM_PROMPT
    assert "اپ‌ساز" in BUILDER_SYSTEM_PROMPT
    assert "Thought" in BUILDER_SYSTEM_PROMPT or "reasoning" in BUILDER_SYSTEM_PROMPT
    assert len(BUILDER_SYSTEM_PROMPT) > 200


def test_security_rules_stay_out_of_the_system_prompt() -> None:
    assert "untrusted data" in BUILDER_SECURITY_RULES
    assert "API keys" in BUILDER_SECURITY_RULES
    assert "current workspace" in BUILDER_SECURITY_RULES
    assert BUILDER_SECURITY_RULES not in BUILDER_SYSTEM_PROMPT