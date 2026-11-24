from worker.liara_models import (
    liara_wire_model_id,
    pick_allowed_model,
    resolve_litellm_model,
)


def test_liara_wire_strips_litellm_prefix():
    assert (
        liara_wire_model_id(
            "openai/openai/deepseek/deepseek-v4.1-flash",
            "deepseek/deepseek-v4.1-flash",
        )
        == "deepseek/deepseek-v4.1-flash"
    )
    assert (
        liara_wire_model_id("openai/gpt-4o-mini", "deepseek/deepseek-v4.1-flash")
        == "openai/gpt-4o-mini"
    )


def test_liara_litellm_single_openai_prefix():
    out = resolve_litellm_model(
        "deepseek/deepseek-v4.1-flash",
        "deepseek/deepseek-v4.1-flash",
        liara_base_url="https://ai.liara.ir/api/x/v1",
    )
    assert out == "openai/deepseek/deepseek-v4.1-flash"


def test_non_liara_passthrough():
    assert resolve_litellm_model("gpt-4o", "gpt-4o", liara_base_url=None) == "gpt-4o"


def test_pick_allowed_model_falls_back():
    allowed = ("deepseek/deepseek-v4.1-flash", "openai/gpt-4o-mini")
    assert pick_allowed_model("unknown/foo", "deepseek/deepseek-v4.1-flash", allowed) == (
        "deepseek/deepseek-v4.1-flash"
    )
    assert pick_allowed_model("openai/gpt-4o-mini", "deepseek/deepseek-v4.1-flash", allowed) == (
        "openai/gpt-4o-mini"
    )