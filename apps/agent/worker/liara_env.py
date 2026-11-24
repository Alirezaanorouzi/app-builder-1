"""Process env for Liara as the only LLM provider (no OpenAI cloud bleed-through)."""

from __future__ import annotations

import os

LIARA_NO_PROXY = "ai.liara.ir,.liara.ir,localhost,127.0.0.1,::1"

# LiteLLM / OpenAI SDK must not pick up a global OpenAI cloud base URL or key.
_UNSET_LITELLM_CONFLICT_KEYS = (
    "OPENAI_API_BASE",
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_ORGANIZATION",
    "OPENAI_PROJECT",
)


def apply_liara_worker_env() -> None:
    """
    - Route Liara directly (bypass broken local VPN proxy when VPN is off).
    - Drop conflicting OPENAI_* env vars so base_url + LIARA_API_KEY are authoritative.
    """
    for key in _UNSET_LITELLM_CONFLICT_KEYS:
        os.environ.pop(key, None)

    for var in ("NO_PROXY", "no_proxy"):
        current = os.environ.get(var, "").strip()
        parts = [p.strip() for p in current.split(",") if p.strip()]
        for host in LIARA_NO_PROXY.split(","):
            if host not in parts:
                parts.append(host)
        os.environ[var] = ",".join(parts)