# OpenHands SDK integration (pinned)

**Pin:** `openhands-sdk==1.63.1`, `openhands-tools==1.63.1`, `openhands-workspace==1.63.1`, `openhands-agent-server==1.63.1` (see `apps/agent/pyproject.toml`).

## Used in MVP

| Class / method | Purpose |
|--------------|---------|
| `LLM(..., stream=True)` | Streaming completions; `token_callbacks` receive `ModelResponseStream` deltas |
| `LLM(model, api_key, base_url)` | Liara OpenAI-compatible API |
| `get_default_agent(llm, cli_mode=True)` + `system_prompt` | Builder agent — see `worker/builder_prompt.py` (Persian tool `summary` labels for UI) |
| `Conversation(agent, workspace, persistence_dir, conversation_id, max_iteration_per_run, callbacks, token_callbacks)` | Local in-process **or** `RemoteConversation` when `workspace` is `Workspace(host=..., api_key=...)` |
| `Workspace(host, working_dir, api_key)` | Agent Server on Vercel sandbox (`AGENT_RUNTIME=remote`) |
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

## Vercel remote runtime (`AGENT_RUNTIME=remote`)

- **Agent Server** runs inside the project Vercel sandbox (port **8000**); worker orchestrates via HTTPS + `X-Session-API-Key`.
- **LLM:** per-run virtual keys via public **`LLM_PROXY_PUBLIC_URL`** — primary `LIARA_API_KEY` never enters the sandbox.
- **Local dev:** `SANDBOX_PROVIDER=local` or `AGENT_RUNTIME=embedded` keeps the in-process loop on the worker.

Golden snapshot: `apps/agent/scripts/create_vercel_base_snapshot.py`.

## Not used

`DockerWorkspace`, browser tool, MCP.

## Upgrade procedure

1. Bump pins in `pyproject.toml` and `OPENHANDS_SDK_VERSION`.
2. Run `apps/agent/tests/test_archive_roundtrip.py`.
3. Deploy worker; next user runs with old archives trigger seed fallback automatically.