from __future__ import annotations

import logging
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from pydantic import SecretStr

from worker.config import Settings
from worker.liara_models import (
    liara_user_error_message,
    pick_allowed_model,
    resolve_litellm_model,
    warn_liara_models_misconfigured,
)
from worker.persistence_paths import sdk_conversation_dir
from worker.db import Database
from worker.events_sanitize import sanitize_event_payload
from worker.llm_proxy import mint_run_llm_credential, revoke_run_llm_key
from worker.workspace.base import WorkspaceAdapter
from worker.builder_prompt import BUILDER_SYSTEM_PROMPT
from worker.remote_conversation_sync import ensure_conversation_id_matches_remote_llm
from worker.run_lifecycle import CancelMonitor
from worker.run_timeline import RunTimeline
from worker.stream_tokens import RunLiveStreamAppender
from worker.workspace.vercel_ws import VercelWorkspace

logger = logging.getLogger(__name__)


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
    on_staging_sync: Callable[[], None] | None = None,
    timeline: RunTimeline | None = None,
) -> tuple[str, int]:
    project_id = uuid.UUID(str(run_row["project_id"]))
    run_id = uuid.UUID(str(run_row["id"]))
    conversation_id = uuid.UUID(str(run_row["conversation_id"]))
    if timeline is None:
        timeline = RunTimeline(run_id)

    seed = db.get_run_user_message(run_id) or ""
    try:
        restore_conversation_dir(settings, db, archive_store, project_id, conversation_id)
    except RuntimeError as e:
        if str(e) == "sdk_version_mismatch":
            conversation_id, seed = seed_fallback(db, project_id, ws)
            seed = f"{seed}\n\nUser request: {db.get_run_user_message(run_id) or ''}"
        else:
            raise
    timeline.mark("conversation_restore_done")

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
    timeline.mark("sdk_import_done")

    warn_liara_models_misconfigured(settings)
    liara_model = pick_allowed_model(
        run_row.get("model"),
        settings.liara_default_model,
        settings.liara_models,
    )
    model = resolve_litellm_model(
        liara_model,
        settings.liara_default_model,
        liara_base_url=settings.liara_base_url,
    )
    logger.info(
        "LLM for run %s: liara_id=%s litellm=%s base=%s",
        run_id,
        liara_model,
        model,
        settings.liara_base_url,
    )
    llm_credential = None
    use_remote = (
        settings.uses_remote_agent()
        and isinstance(ws, VercelWorkspace)
        and ws.project_session is not None
        and bool(ws.agent_server_url())
    )
    if settings.uses_remote_agent() and isinstance(ws, VercelWorkspace) and not use_remote:
        msg = "Agent Server did not become ready on the Vercel sandbox"
        db.insert_message(project_id, run_id, "assistant", msg)
        return "failed", 0
    if (
        use_remote
        and settings.remote_conversation_rotate_after_messages > 0
        and db.count_project_messages(project_id) >= settings.remote_conversation_rotate_after_messages
    ):
        conversation_id, rotate_seed = seed_fallback(db, project_id, ws)
        seed = f"{rotate_seed}\n\nUser request: {seed}" if seed else rotate_seed
        logger.info(
            "Rotated remote conversation for project %s (messages >= %s)",
            project_id,
            settings.remote_conversation_rotate_after_messages,
        )
    if use_remote:
        try:
            llm_credential = mint_run_llm_credential(
                settings,
                run_id=run_id,
                project_id=project_id,
                model=liara_model,
            )
            db.set_run_llm_proxy_key_id(run_id, llm_credential.key_id)
        except RuntimeError as e:
            logger.error("remote LLM credential: %s", e)
            db.insert_message(project_id, run_id, "assistant", str(e)[:4000])
            return "failed", 0
        llm = LLM(
            model=model,
            api_key=SecretStr(llm_credential.api_key),
            base_url=llm_credential.base_url,
            reasoning_effort="low",
            drop_params=True,
            stream=True,
        )
    else:
        llm = LLM(
            model=model,
            api_key=SecretStr(settings.liara_api_key),
            base_url=settings.liara_base_url,
            reasoning_effort="low",
            drop_params=True,
            stream=True,
        )
    agent = get_default_agent(llm=llm, cli_mode=True).model_copy(
        update={"system_prompt": BUILDER_SYSTEM_PROMPT}
    )
    timeline.mark("llm_agent_ready")

    db.clear_run_live_output(run_id)
    stream_appender = RunLiveStreamAppender(db, run_id)
    event_seq_holder = {"n": db.next_event_seq(run_id)}
    assistant_chunks: list[str] = []
    agent_run_armed = threading.Event()

    def on_event(event: Any) -> None:
        if cancel_check():
            return
        if not agent_run_armed.is_set():
            return
        db.touch_heartbeat(run_id)
        payload = event.model_dump() if hasattr(event, "model_dump") else {"raw": str(event)}
        safe = sanitize_event_payload(payload, settings.run_event_max_bytes)
        cls = type(event).__name__
        try:
            db.insert_run_event(
                run_id,
                event_seq_holder["n"],
                cls,
                safe,
                tool_name=getattr(event, "tool_name", None),
            )
            event_seq_holder["n"] += 1
        except Exception:
            logger.exception("run_event insert failed (seq=%s)", event_seq_holder["n"])
            event_seq_holder["n"] += 1
        if cls not in ("RunBootstrapEvent", "RunTimelineEvent"):
            if not timeline.has_phase("first_agent_event"):
                logger.info(
                    "RUN_TIMELINE run=%s first_agent_event_class=%s",
                    run_id,
                    cls,
                )
            timeline.mark("first_agent_event", once=True)
        if on_staging_sync and not use_remote:
            cls = type(event).__name__
            tool = getattr(event, "tool_name", None)
            if tool == "file_editor" or cls == "FileEditorAction" or cls.endswith("ActionEvent"):
                try:
                    on_staging_sync()
                except Exception:
                    logger.exception("staging sync callback failed")
        if cls == "MessageEvent" and getattr(event, "source", None) == "agent":
            try:
                from openhands.sdk.llm import content_to_str

                parts = content_to_str(event.llm_message.content)
                text = "\n".join(parts).strip()
                if text:
                    assistant_chunks.append(text)
            except Exception:
                pass

    def on_token(chunk: Any) -> None:
        if cancel_check() or not agent_run_armed.is_set():
            return
        timeline.mark("first_token", once=True)
        stream_appender.feed(chunk)
        if on_assistant_token:
            from worker.stream_tokens import extract_stream_delta

            content, _ = extract_stream_delta(chunk)
            if content:
                on_assistant_token(content)

    remote_cm = None
    workspace_handle: object
    if use_remote:
        assert isinstance(ws, VercelWorkspace)
        session = ws.project_session
        assert session is not None
        try:
            db.insert_run_event(
                run_id,
                event_seq_holder["n"],
                "RunBootstrapEvent",
                {"summary": "در حال آماده‌سازی agent و همگام‌سازی تاریخچه"},
                tool_name=None,
            )
            event_seq_holder["n"] += 1
        except Exception:
            logger.exception("bootstrap run_event insert failed")
        agent_url = ws.agent_server_url()
        if agent_url and llm_credential:
            conversation_id = ensure_conversation_id_matches_remote_llm(
                db,
                project_id,
                conversation_id,
                agent_url=agent_url,
                session_api_key=session.session_api_key,
                expected_liara_model=liara_model,
                expected_litellm_model=model,
                llm=llm,
            )
        timeline.mark("remote_llm_sync_done")
        remote_cm = session.remote_workspace()
        workspace_handle = remote_cm.__enter__()
        timeline.mark("remote_workspace_open")
    else:
        workspace_handle = str(getattr(ws, "root", Path(".")))
    conv_kwargs: dict[str, Any] = {
        "agent": agent,
        "workspace": workspace_handle,
        "conversation_id": conversation_id,
        "max_iteration_per_run": settings.max_iterations,
        "delete_on_close": False,
        "visualizer": None,
        "callbacks": [on_event],
        "token_callbacks": [on_token],
    }
    if not use_remote:
        conv_kwargs["persistence_dir"] = str(Path(settings.conversation_dir))
    # Remote SDK: REST sync paginates conversation history + WS handshake here.
    # User callbacks are NOT replayed for history (see RemoteConversation.__init__);
    # agent_run_armed gates DB writes until POST /run.
    conversation: Any
    open_err: list[BaseException] = []

    def _open_conversation() -> None:
        try:
            nonlocal conversation
            conversation = Conversation(**conv_kwargs)
        except BaseException as e:
            open_err.append(e)

    timeline.mark("remote_conversation_begin")
    open_timeout = (
        settings.remote_conversation_open_timeout_seconds if use_remote else 0.0
    )
    if use_remote and open_timeout > 0:
        opener = threading.Thread(target=_open_conversation, name=f"conv-open-{run_id}")
        opener.start()
        opener.join(timeout=open_timeout)
        if opener.is_alive():
            if remote_cm is not None:
                remote_cm.__exit__(None, None, None)
            raise TimeoutError(
                f"Remote conversation open exceeded {open_timeout:.0f}s (history sync)"
            )
        if open_err:
            if remote_cm is not None:
                remote_cm.__exit__(None, None, None)
            raise open_err[0]
    else:
        try:
            conversation = Conversation(**conv_kwargs)
        except Exception:
            if remote_cm is not None:
                remote_cm.__exit__(None, None, None)
            raise
    timeline.mark("conversation_constructed")

    if seed:
        conversation.send_message(seed)
        timeline.mark("user_message_sent")
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
    stall_stop = threading.Event()

    def _stall_watch() -> None:
        while not stall_stop.wait(45):
            if timeline.has_phase("first_token"):
                return
            wait_s = max(0.0, timeline.elapsed_ms("conversation_run_start") / 1000)
            logger.warning(
                "RUN_TIMELINE run=%s agent still running (no first_token after %.0fs) — "
                "Liara/Agent Server may be slow; not necessarily stuck",
                run_id,
                wait_s,
            )

    stall_thread = threading.Thread(target=_stall_watch, name=f"stall-{run_id}", daemon=True)
    cancel_mon = CancelMonitor(
        settings,
        db,
        run_row,
        cancel_check=cancel_check,
    )
    try:
        timeline.mark("conversation_run_start")
        agent_run_armed.set()
        stall_thread.start()
        cancel_mon.start()
        conversation.run()
        timeline.mark("conversation_run_done")
    except Exception as e:
        if cancel_mon.cancelled.is_set() or cancel_check():
            final_status = "cancelled"
        else:
            logger.exception("conversation.run failed")
            final_status = "failed"
            db.insert_message(
                project_id,
                run_id,
                "assistant",
                liara_user_error_message(e, liara_model=liara_model),
            )
    finally:
        stall_stop.set()
        cancel_mon.stop()
        stream_appender.flush()
        if llm_credential:
            revoke_run_llm_key(settings, llm_credential.key_id)
        if remote_cm is not None:
            remote_cm.__exit__(None, None, None)
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
    if cancel_check() and final_status == "succeeded":
        final_status = "cancelled"
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
    timeline.log_summary()
    seq = db.next_event_seq(run_id)
    timeline.persist(db, run_id, seq)
    return final_status, iterations