"""Keep remote Agent Server LLM config aligned with worker runs."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from worker.agent_server_client import get_conversation, switch_conversation_llm
from worker.db import Database
from worker.liara_models import liara_wire_model_id

logger = logging.getLogger(__name__)


def _remote_llm_model(conversation_info: dict[str, Any]) -> str | None:
    agent = conversation_info.get("agent")
    if not isinstance(agent, dict):
        return None
    llm = agent.get("llm")
    if not isinstance(llm, dict):
        return None
    raw = llm.get("model")
    return str(raw).strip() if raw else None


def remote_llm_matches_run(
    remote_litellm_model: str,
    *,
    expected_liara_model: str,
    expected_litellm_model: str,
) -> bool:
    if remote_litellm_model == expected_litellm_model:
        return True
    return liara_wire_model_id(remote_litellm_model, expected_liara_model) == expected_liara_model


def _remote_matches_expected(
    conversation_info: dict[str, Any] | None,
    *,
    expected_liara_model: str,
    expected_litellm_model: str,
) -> bool:
    if conversation_info is None:
        return False
    remote_model = _remote_llm_model(conversation_info)
    if not remote_model:
        return False
    return remote_llm_matches_run(
        remote_model,
        expected_liara_model=expected_liara_model,
        expected_litellm_model=expected_litellm_model,
    )


def ensure_conversation_id_matches_remote_llm(
    db: Database,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    agent_url: str,
    session_api_key: str,
    expected_liara_model: str,
    expected_litellm_model: str,
    llm: Any,
) -> uuid.UUID:
    """
    Remote conversations keep the LLM baked in on the Agent Server.

    Prefer ``switch_llm`` on the existing conversation id so we do not pay the
    cost of creating a brand-new remote conversation (slow / 502 on Vercel).
    """
    info = get_conversation(agent_url, session_api_key, conversation_id)
    if info is None:
        return conversation_id
    remote_model = _remote_llm_model(info)
    if not remote_model:
        return conversation_id
    if remote_llm_matches_run(
        remote_model,
        expected_liara_model=expected_liara_model,
        expected_litellm_model=expected_litellm_model,
    ):
        return conversation_id

    from openhands.sdk.utils.pydantic_secrets import client_context

    llm_payload = llm.model_dump(mode="json", context=client_context("plaintext"))
    if switch_conversation_llm(agent_url, session_api_key, conversation_id, llm_payload):
        after = get_conversation(agent_url, session_api_key, conversation_id)
        if _remote_matches_expected(
            after,
            expected_liara_model=expected_liara_model,
            expected_litellm_model=expected_litellm_model,
        ):
            logger.info(
                "Switched remote conversation %s LLM from %r to Liara %s",
                conversation_id,
                remote_model,
                expected_liara_model,
            )
            return conversation_id
        logger.warning(
            "switch_llm for conversation %s returned OK but remote model still stale",
            conversation_id,
        )

    new_id = uuid.uuid4()
    logger.warning(
        "Remote conversation %s uses stale LLM %r (want Liara %s); "
        "rotating project conversation to %s",
        conversation_id,
        remote_model,
        expected_liara_model,
        new_id,
    )
    db.update_project_conversation(project_id, new_id)
    return new_id