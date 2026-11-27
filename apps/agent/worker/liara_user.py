"""Tag each Liara call with our user id so their log stores external_user.

OpenHands binds ``litellm.completion`` at import time, so the wrapper has to
replace that name. A context var keeps concurrent runs from sharing a user.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Callable

_end_user: ContextVar[str | None] = ContextVar("liara_end_user", default=None)
_installed = False


def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
    def inner(*args: Any, **kwargs: Any) -> Any:
        user_id = _end_user.get()
        if user_id and not kwargs.get("user"):
            kwargs["user"] = user_id
        return fn(*args, **kwargs)

    return inner


def install_liara_end_user() -> None:
    global _installed
    if _installed:
        return
    import litellm
    import openhands.sdk.llm.llm as oh_llm

    litellm.completion = _wrap(litellm.completion)
    oh_llm.litellm_completion = _wrap(oh_llm.litellm_completion)
    if hasattr(oh_llm, "litellm_acompletion"):
        oh_llm.litellm_acompletion = _wrap(oh_llm.litellm_acompletion)
    _installed = True


def bind_liara_end_user(user_id: str) -> Token[str | None]:
    install_liara_end_user()
    return _end_user.set(user_id)


def reset_liara_end_user(token: Token[str | None]) -> None:
    _end_user.reset(token)
