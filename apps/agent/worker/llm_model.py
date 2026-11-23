"""Map run/model env values to names that work with OpenHands LLM + LiteLLM + Liara."""

from __future__ import annotations


def resolve_litellm_model(model: str | None, default: str, *, liara_base_url: str | None = None) -> str:
    """
    Liara serves an OpenAI-compatible API and expects full slugs in the JSON body
    (e.g. ``deepseek/deepseek-v4.1-flash``).

    LiteLLM routes ``deepseek/...`` to Deepseek's native client (wrong for Liara) and
    strips a single ``openai/`` prefix (so ``openai/gpt-4o-mini`` becomes ``gpt-4o-mini``).

    For Liara we force the OpenAI transport and double ``openai/`` so the wire model
    keeps the full slug.
    """
    m = (model or default).strip() or default.strip()
    if liara_base_url and "liara.ir" in liara_base_url:
        if not m.startswith("openai/"):
            m = f"openai/{m}"
        if not m.startswith("openai/openai/"):
            m = f"openai/{m}"
    return m