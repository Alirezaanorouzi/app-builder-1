"""Finish-tool text is the reply when the agent never emits a chat message."""

from types import SimpleNamespace

from openhands.sdk.llm.message import TextContent

from worker.openhands_runner import agent_visible_reply


def test_message_event_text() -> None:
    class MessageEvent:
        source = "agent"
        llm_message = SimpleNamespace(content=[TextContent(text="سلام")])

    kind, text = agent_visible_reply(MessageEvent())  # type: ignore[arg-type]
    assert kind == "message"
    assert text == "سلام"


def test_finish_action_message() -> None:
    class ActionEvent:
        tool_name = "finish"
        action = SimpleNamespace(message="خواهش می‌کنم")

    kind, text = agent_visible_reply(ActionEvent())  # type: ignore[arg-type]
    assert kind == "finish"
    assert text == "خواهش می‌کنم"


def test_terminal_action_is_not_a_reply() -> None:
    class ActionEvent:
        tool_name = "terminal"
        action = SimpleNamespace(message="ls")

    assert agent_visible_reply(ActionEvent()) is None  # type: ignore[arg-type]
