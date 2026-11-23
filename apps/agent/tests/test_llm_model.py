from worker.llm_model import resolve_litellm_model


def test_liara_deepseek_model_routing():
    out = resolve_litellm_model(
        "deepseek/deepseek-v4.1-flash",
        "deepseek/deepseek-v4.1-flash",
        liara_base_url="https://ai.liara.ir/api/x/v1",
    )
    assert out == "openai/openai/deepseek/deepseek-v4.1-flash"


def test_non_liara_passthrough():
    assert (
        resolve_litellm_model("gpt-4o", "gpt-4o", liara_base_url=None) == "gpt-4o"
    )