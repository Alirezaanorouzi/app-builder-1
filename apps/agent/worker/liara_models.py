"""Liara model IDs (wire format) and LiteLLM transport names.

Liara expects the exact catalog ID in the JSON ``model`` field
(e.g. ``deepseek/deepseek-v4.1-flash``, ``openai/gpt-4o-mini``).
See: https://developers.liara.ir/ai-chat-completions/chat-completions/create-a-chat-completion

LiteLLM wraps Liara errors as ``OpenAIException`` even though traffic goes to
``ai.liara.ir``, not OpenAI cloud.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worker.config import Settings

logger = logging.getLogger(__name__)

_LITELLM_VENDOR_PREFIXES = ("deepseek/", "anthropic/", "google/", "meta/", "mistral/")


def liara_wire_model_id(model: str | None, default: str) -> str:
    """
    Canonical model slug sent to Liara (source of truth for the request body).

    Liara IDs include forms like ``deepseek/deepseek-v4.1-flash`` and ``openai/gpt-4o-mini``.
    LiteLLM may wrap the former as ``openai/deepseek/...`` (one extra ``openai/``); we strip only
    that transport layer, never the ``openai/`` vendor prefix on Liara-native OpenAI models.
    """
    m = (model or default).strip() or default.strip()
    while m.startswith("openai/openai/"):
        m = m[len("openai/") :]
    if m.startswith("openai/"):
        rest = m[len("openai/") :]
        if any(rest.startswith(v) for v in _LITELLM_VENDOR_PREFIXES):
            return rest
    return m


def resolve_litellm_model(
    model: str | None,
    default: str,
    *,
    liara_base_url: str | None = None,
) -> str:
    """
    LiteLLM model string for OpenHands.

    - ``deepseek/...`` alone → DeepSeek native API (wrong for Liara).
    - ``openai/{liara_id}`` → OpenAI-compatible client with wire model ``{liara_id}``.
    """
    wire = liara_wire_model_id(model, default)
    if liara_base_url and "liara.ir" in liara_base_url:
        return f"openai/{wire}"
    return wire


def pick_allowed_model(requested: str | None, default: str, allowed: tuple[str, ...]) -> str:
    """Return a Liara wire model that is in ``allowed`` (from ``LIARA_MODELS``)."""
    wire = liara_wire_model_id(requested, default)
    if not allowed:
        return wire
    if wire in allowed:
        return wire
    if default in allowed:
        return default
    return allowed[0]


def fetch_liara_catalog(settings: "Settings", *, timeout: float = 20.0) -> frozenset[str]:
    """Workspace model IDs from Liara ``GET {base}/models``."""
    base = (settings.liara_base_url or "").rstrip("/")
    key = settings.liara_api_key
    if not base or not key or "liara.ir" not in base:
        return frozenset()
    try:
        import httpx

        r = httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        rows = data.get("data") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return frozenset()
        return frozenset(str(m.get("id")) for m in rows if m.get("id"))
    except Exception:
        logger.debug("Liara model catalog fetch failed", exc_info=True)
        return frozenset()


def warn_liara_models_misconfigured(settings: "Settings") -> None:
    catalog = fetch_liara_catalog(settings)
    if not catalog:
        return
    missing = [m for m in settings.liara_models if m not in catalog]
    for m in missing:
        logger.warning(
            "LIARA_MODELS entry %r is not in this workspace catalog (%s models)",
            m,
            len(catalog),
        )


def liara_user_error_message(exc: BaseException, *, liara_model: str) -> str:
    text = str(exc)
    lower = text.lower()
    if "410 gone" in lower or "polling failed with http 410" in lower:
        return (
            "اتصال agent روی sandbox Vercel وسط کار قطع شد (سرور agent ریستارت یا خاموش شد).\n\n"
            "این خطا مربوط به LLM proxy نیست؛ مدل لیارا تا لحظهٔ قطع کار می‌کرد.\n"
            "یک بار دیگر همان درخواست را بفرستید. اگر تکرار شد، چند دقیقه صبر کنید و دوباره امتحان کنید.\n\n"
            f"جزئیات: {text[:500]}"
        )
    if "502 bad gateway" in lower and "vercel.run" in lower:
        return (
            "sandbox Vercel لحظه‌ای در دسترس نبود (502). معمولاً موقت است.\n"
            "دوباره پیام را ارسال کنید.\n\n"
            f"جزئیات: {text[:500]}"
        )
    if "balance must be higher" in lower or "tomans" in lower:
        return (
            f"اعتبار کیف پول لیارا برای مدل «{liara_model}» کافی نیست. "
            "این پاسخ از ai.liara.ir است (LiteLLM آن را OpenAIException می‌نویسد؛ "
            "به api.openai.com وصل نشده‌اید).\n\n"
            "در console.liara.ir شارژ کنید، یا در .env مدل ارزان‌تری از GET /v1/models "
            "بگذارید (مثلاً deepseek/deepseek-chat-v3-0324).\n\n"
            f"جزئیات: {text[:800]}"
        )
    if "must be one of the supported models" in lower:
        return (
            f"مدل «{liara_model}» در workspace لیارا شما پشتیبانی نمی‌شود. "
            "`LIARA_MODELS` و `NEXT_PUBLIC_DEFAULT_MODEL` را با لیست `GET /v1/models` "
            f"هماهنگ کنید.\n\nجزئیات: {text[:800]}"
        )
    if "internal server error" in lower and "500" in text:
        return (
            "درخواست به مدل لیارا خیلی بزرگ شده (معمولاً بعد از چند نوبت agent با تاریخچهٔ "
            "ابزارها روی sandbox). یک بار دیگر همان پیام را بفرستید؛ worker اکنون برای پیام‌های "
            "بعدی تاریخچهٔ remote را تازه می‌کند.\n\n"
            f"مدل: {liara_model}\n\nجزئیات: {text[:600]}"
        )
    if "openaiexception" in lower and "liara" not in lower:
        return (
            f"خطای API مدل (Liara/OpenAI-compatible): {text[:1200]}\n\n"
            f"مدل درخواستی: {liara_model}"
        )
    return f"خطا: {text}"[:4000]