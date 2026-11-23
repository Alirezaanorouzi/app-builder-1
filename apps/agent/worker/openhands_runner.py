from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

from pydantic import SecretStr

from worker.config import Settings
from worker.llm_model import resolve_litellm_model
from worker.persistence_paths import sdk_conversation_dir
from worker.db import Database
from worker.events_sanitize import sanitize_event_payload
from worker.workspace.base import WorkspaceAdapter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You help users build a Vite + React app. Users write in Persian.
Use str_replace for edits; create_file only when missing. Use grep/glob before editing.
Keep the dev server previewable. Do not install unrelated services."""


def _clip_terminal(text: str, limit: int = 8192) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:] + "\n…[output clipped]"


class AdapterTooling:
    """Minimal tool surface backed by WorkspaceAdapter (OpenHands-shaped responses)."""

    def __init__(self, ws: WorkspaceAdapter) -> None:
        self.ws = ws

    def view(self, path: str) -> str:
        return self.ws.view_file(path)

    def str_replace(self, path: str, old: str, new: str) -> str:
        return self.ws.str_replace(path, old, new)

    def run_terminal(self, command: str, cwd: str | None = None, background: bool = False) -> str:
        r = self.ws.run_command(command, cwd=cwd, background=background)
        if r.background:
            return f"Started background command id={r.command_id}"
        return _clip_terminal(
            f"exit={r.exit_code}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )


def restore_conversation_dir(
    settings: Settings,
    db: Database,
    archive_store,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> Path:
    parent = Path(settings.conversation_dir)
    target = sdk_conversation_dir(parent, conversation_id)
    if target.is_dir() and (target / "base_state.json").is_file():
        return target
    meta = db.latest_archive(project_id)
    if not meta:
        return target
    if meta["openhands_sdk_version"] != settings.openhands_sdk_version:
        raise RuntimeError("sdk_version_mismatch")
    archive_store.load_conversation(
        meta["storage_key"], parent, conversation_id.hex
    )
    return target


def seed_fallback(
    db: Database,
    project_id: uuid.UUID,
    ws: WorkspaceAdapter,
) -> tuple[uuid.UUID, str]:
    new_id = uuid.uuid4()
    db.update_project_conversation(project_id, new_id)
    prior = db.list_prior_messages(project_id)
    files = ws.glob("**/*")
    summary = "\n".join(f"- {m['role']}: {m['content'][:500]}" for m in prior)
    seed = (
        "Continue the project. Prior chat:\n"
        f"{summary}\n\nFiles in workspace:\n{files[:4000]}"
    )
    return new_id, seed


def run_agent_turn(
    settings: Settings,
    db: Database,
    archive_store,
    run_row: dict[str, Any],
    ws: WorkspaceAdapter,
    *,
    cancel_check: Callable[[], bool],
    on_assistant_token: Callable[[str], None] | None = None,
) -> tuple[str, int]:
    project_id = uuid.UUID(str(run_row["project_id"]))
    run_id = uuid.UUID(str(run_row["id"]))
    conversation_id = uuid.UUID(str(run_row["conversation_id"]))

    seed = db.get_run_user_message(run_id) or ""
    try:
        restore_conversation_dir(settings, db, archive_store, project_id, conversation_id)
    except RuntimeError as e:
        if str(e) == "sdk_version_mismatch":
            conversation_id, seed = seed_fallback(db, project_id, ws)
            seed = f"{seed}\n\nUser request: {db.get_run_user_message(run_id) or ''}"
        else:
            raise

    conv_dir = sdk_conversation_dir(settings.conversation_dir, conversation_id)

    if not settings.liara_api_key:
        # Dev stub without SDK
        tools = AdapterTooling(ws)
        reply = (
            f"[stub agent] Received: {seed[:200]}. Workspace glob sample:\n{tools.run_terminal('dir') if sys.platform == 'win32' else tools.run_terminal('ls -la')}"
        )
        db.insert_message(project_id, run_id, "assistant", reply)
        (conv_dir / "base_state.json").write_text('{"stub": true}', encoding="utf-8")
        key, sha, size = archive_store.save_conversation(
            str(project_id), str(run_id), conv_dir
        )
        db.save_archive_meta(
            project_id,
            run_id,
            conversation_id,
            settings.openhands_sdk_version,
            key,
            sha,
            size,
        )
        return "succeeded", 1

    try:
        from openhands.sdk import Conversation, LLM
        from openhands.tools.preset.default import get_default_agent
    except ImportError as e:
        logger.error("openhands-sdk not installed: %s", e)
        db.insert_message(project_id, run_id, "assistant", "Agent SDK not installed.")
        return "failed", 0

    model = resolve_litellm_model(
        run_row.get("model"),
        settings.liara_default_model,
        liara_base_url=settings.liara_base_url,
    )
    logger.info("LLM model for run %s: %s", run_id, model)
    llm = LLM(
        model=model,
        api_key=SecretStr(settings.liara_api_key),
        base_url=settings.liara_base_url,
        reasoning_effort="low",
        drop_params=True,
    )
    agent = get_default_agent(llm=llm, cli_mode=True)

    event_seq_holder = {"n": db.next_event_seq(run_id)}
    assistant_chunks: list[str] = []

    def on_event(event: Any) -> None:
        if cancel_check():
            return
        db.touch_heartbeat(run_id)
        payload = event.model_dump() if hasattr(event, "model_dump") else {"raw": str(event)}
        safe = sanitize_event_payload(payload, settings.run_event_max_bytes)
        try:
            db.insert_run_event(
                run_id,
                event_seq_holder["n"],
                type(event).__name__,
                safe,
                tool_name=getattr(event, "tool_name", None),
            )
            event_seq_holder["n"] += 1
        except Exception:
            logger.exception("run_event insert failed (seq=%s)", event_seq_holder["n"])
            event_seq_holder["n"] += 1
        if type(event).__name__ == "MessageEvent" and getattr(event, "source", None) == "agent":
            try:
                from openhands.sdk.llm import content_to_str

                parts = content_to_str(event.llm_message.content)
                text = "\n".join(parts).strip()
                if text:
                    assistant_chunks.append(text)
            except Exception:
                pass

    def on_token(token: str) -> None:
        if on_assistant_token:
            on_assistant_token(token)

    workspace_root = str(getattr(ws, "root", Path(".")))
    conversation = Conversation(
        agent=agent,
        workspace=workspace_root,
        persistence_dir=str(Path(settings.conversation_dir)),
        conversation_id=conversation_id,
        max_iteration_per_run=settings.max_iterations,
        delete_on_close=False,
        visualizer=None,
        callbacks=[on_event],
        token_callbacks=[on_token],
    )

    fresh = not (conv_dir / "base_state.json").is_file()
    if seed:
        if fresh:
            seed = f"{SYSTEM_PROMPT.strip()}\n\n{seed}"
        conversation.send_message(seed)
    def _max_iterations_reached(conv: Any) -> bool:
        for ev in reversed(conv.state.events):
            if type(ev).__name__ == "ConversationErrorEvent":
                return getattr(ev, "code", None) == "MaxIterationsReached"
            if type(ev).__name__ == "MessageEvent":
                break
        return False

    final_status = "succeeded"
    iterations = 0
    hit_max_iterations = False
    try:
        conversation.run()
    except Exception as e:
        logger.exception("conversation.run failed")
        final_status = "failed"
        db.insert_message(project_id, run_id, "assistant", f"خطا: {e}"[:4000])
    finally:
        try:
            from openhands.sdk.conversation.state import ConversationExecutionStatus

            hit_max_iterations = _max_iterations_reached(conversation)
            exec_status = conversation.state.execution_status
            iterations = max(
                0,
                sum(
                    1
                    for ev in conversation.state.events
                    if type(ev).__name__ == "ActionEvent"
                ),
            )
            if hit_max_iterations and final_status != "failed":
                final_status = "succeeded"
            elif (
                exec_status == ConversationExecutionStatus.ERROR
                and not hit_max_iterations
                and final_status == "succeeded"
            ):
                final_status = "failed"
                db.insert_message(
                    project_id,
                    run_id,
                    "assistant",
                    "خطا در اجرای agent (جزئیات در run_events).",
                )
            conversation.close()
        except Exception:
            pass

    if conv_dir.is_dir() and (conv_dir / "base_state.json").is_file():
        key, sha, size = archive_store.save_conversation(
            str(project_id), str(run_id), conv_dir
        )
        db.save_archive_meta(
            project_id,
            run_id,
            conversation_id,
            settings.openhands_sdk_version,
            key,
            sha,
            size,
        )
    if final_status == "succeeded":
        reply = "\n".join(assistant_chunks).strip()
        if hit_max_iterations:
            note = (
                f"\n\n[حداکثر {settings.max_iterations} گام agent تمام شد؛ "
                "برای ادامه یک پیام دیگر بفرستید.]"
            )
            reply = (reply + note) if reply else note.strip()
        if not reply:
            reply = "انجام شد."
        db.insert_message(project_id, run_id, "assistant", reply[:16000])
    return final_status, iterations