# OpenHands SDK integration (pinned)

**Pin:** `openhands-sdk==1.63.1` and `openhands-tools==1.63.1` (see `apps/agent/pyproject.toml`).

## Used in MVP

| Class / method | Purpose |
|--------------|---------|
| `LLM(model, api_key, base_url)` | Liara OpenAI-compatible API |
| `get_default_agent(llm, cli_mode=True)` | Agent without browser tools |
| `Conversation(agent, workspace, persistence_dir, conversation_id, max_iteration_per_run, callbacks, token_callbacks)` | In-process loop |
| `conversation.send_message(text)` | User turn |
| `conversation.run()` | Blocking until done / pause |
| `conversation.pause()` | Cancel / shutdown (between steps) |
| `conversation.close()` | Cleanup |

## Resume (archive-only)

We **do not** rebuild SDK state from `run_events`.

1. After each run: tar.gz `persistence_dir/<conversation_id>/` → `ConversationArchiveStore`.
2. On claim: extract latest archive if local dir missing; if `archive.openhands_sdk_version` ≠ worker pin → **seed fallback**.
3. Seed: new `conversation_id`, summary of `messages` + `glob` file list.

## Liara + LiteLLM (worker)

- Set `LIARA_MODELS` to the **full slug** Liara shows (e.g. `deepseek/deepseek-v4.1-flash`).
- The worker rewrites models to `openai/openai/<slug>` so LiteLLM uses the OpenAI client and Liara receives the full slug in the JSON body.
- Persistence lives at `CONVERSATION_DIR/<conversation_id.hex>/` (no dashes). Archives must pack that directory.
- Run the worker with repo-root data paths; `Settings.load()` resolves `CONVERSATION_DIR` and `ARCHIVE_LOCAL_DIR` under the repository root even when `cwd` is `apps/agent`.

## Not used

Agent Server, `DockerWorkspace`, `RemoteConversation`, browser tool, MCP — avoids a second integration style.

## Upgrade procedure

1. Bump pins in `pyproject.toml` and `OPENHANDS_SDK_VERSION`.
2. Run `apps/agent/tests/test_archive_roundtrip.py`.
3. Deploy worker; next user runs with old archives trigger seed fallback automatically.