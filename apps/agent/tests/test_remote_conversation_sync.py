import uuid
from unittest.mock import MagicMock, patch

from worker.remote_conversation_sync import (
    ensure_conversation_id_matches_remote_llm,
    remote_llm_matches_run,
)


def test_remote_stale_v41_flash_does_not_match_1017() -> None:
    assert not remote_llm_matches_run(
        "openai/deepseek/deepseek-v4.1-flash",
        expected_liara_model="deepseek/deepseek-v4.1-flash-1017",
        expected_litellm_model="openai/deepseek/deepseek-v4.1-flash-1017",
    )


def test_remote_1017_matches() -> None:
    assert remote_llm_matches_run(
        "openai/deepseek/deepseek-v4.1-flash-1017",
        expected_liara_model="deepseek/deepseek-v4.1-flash-1017",
        expected_litellm_model="openai/deepseek/deepseek-v4.1-flash-1017",
    )


@patch("worker.remote_conversation_sync.switch_conversation_llm", return_value=True)
@patch("worker.remote_conversation_sync.get_conversation")
def test_stale_llm_uses_switch_llm_not_rotation(get_conv, switch_llm) -> None:
    conv_id = uuid.uuid4()
    project_id = uuid.uuid4()
    stale = {
        "agent": {"llm": {"model": "openai/deepseek/deepseek-v4.1-flash"}},
    }
    fresh = {
        "agent": {"llm": {"model": "openai/deepseek/deepseek-v4.1-flash-1017"}},
    }
    get_conv.side_effect = [stale, fresh]
    llm = MagicMock()
    llm.model_dump.return_value = {"model": "openai/deepseek/deepseek-v4.1-flash-1017"}
    db = MagicMock()

    out = ensure_conversation_id_matches_remote_llm(
        db,
        project_id,
        conv_id,
        agent_url="https://agent.example",
        session_api_key="k",
        expected_liara_model="deepseek/deepseek-v4.1-flash-1017",
        expected_litellm_model="openai/deepseek/deepseek-v4.1-flash-1017",
        llm=llm,
    )

    assert out == conv_id
    switch_llm.assert_called_once()
    db.update_project_conversation.assert_not_called()