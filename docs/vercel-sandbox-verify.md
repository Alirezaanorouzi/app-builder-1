# Vercel Sandbox verification checklist

**Sandbox `name` (API):** must match `^[a-zA-Z0-9_-]+$` — use `worker.workspace.vercel_names.vercel_sandbox_api_name`
(e.g. `dev-f162723e751d42d4a68d73d6a3981e63`), not `dev:uuid`.

## Golden snapshot (recommended)

1. **Once:** `cd apps/agent && $env:PYTHONPATH='.'; python scripts/create_vercel_base_snapshot.py`  
   Seeds `templates/vite-react`, runs `npm install`, calls `snapshot(expiration=0)`. Copy the printed ID into root `.env` as `VERCEL_BASE_SNAPSHOT_ID`.
2. **Per project (first create):** worker calls `get_or_create_sandbox(..., source=SnapshotSource(snapshot_id=...), persistent=True)`.
3. **During agent work:** staging tree uploads (no `node_modules`); extra packages via `npm install` on the VM only.
4. **Idle:** Vercel ends the session at `execution_time_limit`; worker calls `extend_execution_time_limit` from the run heartbeat (no global `stop()` sweep).
5. **Resume:** `get_or_create_sandbox(..., resume=True)` restores files; worker re-uploads deltas, **restarts Vite**, waits for HTTP before returning the preview URL.

Do **not** call `snapshot()` mid-run (it stops the session); use it only for the base image or manual checkpoints.

| Need | Where |
|------|--------|
| React, Vite, Tailwind | Base golden snapshot |
| Project-only npm deps | Agent / `run_command` on that project's sandbox |
| System (apt) packages | Base snapshot or one-off admin snapshot |

**Python SDK (sync) patterns we use** ([SDK reference](https://vercel.com/docs/sandbox/sdk/python)):

| Operation | Correct API |
|-----------|-------------|
| Upload files | `sandbox.fs.batch(cwd=REMOTE_WORKDIR)` then `batch.write_bytes(...)` |
| Run commands | `sandbox.run_command(...)` — avoid `with sandbox.session()` for uploads (exits stop the session) |
| Preview URLs | `client.get_sandbox(name=..., include_system_routes=True)` → read `sandbox.routes` **after** `curl` to `127.0.0.1:5173` succeeds (route exists before Vite listens) |
| Dependencies | Never upload `node_modules`; restore from snapshot or run `npm install` in `/vercel/sandbox` (npm 12: `install-scripts approve esbuild` + `npm rebuild` — handled in `vercel_sync._npm_install_if_needed`) |
| Create/resume | `get_or_create_sandbox(..., ports=[5173, 8000], include_system_routes=True)`; optional `source=SnapshotSource(...)` |
| Agent Server | `python -m openhands.agent_server --host 0.0.0.0 --port 8000`; public route on **8000**; health via worker `GET /health` with `X-Session-API-Key` |
| Remote agent | `AGENT_RUNTIME=remote` (default with `SANDBOX_PROVIDER=vercel`); no mid-run staging upload — tools run on VM |

## Phase 0 — Agent Server + LLM egress

1. **`cd apps/agent && PYTHONPATH=. python -m pytest tests -q`** — runtime, Agent Server reuse, sandbox URLs.
2. **Manual:** open a project, wait for sandbox wake, send one prompt; worker logs should show stack reuse and `Agent Server already ready` when warm.
3. **Go/no-go:** `AGENT_RUNTIME=remote` only if Agent Server `/ready` works **and** Liara is reachable from the VM (direct or `LLM_PROXY_PUBLIC_URL`).

Complete against the **pinned** Python `vercel` package before production.

- [x] **Session extend:** `SyncSandbox.extend_execution_time_limit(timedelta)` (see `worker/vercel_lease.py`).
- [ ] **Snapshot retention:** create with `count=1, delete_evicted=True`; `update(snapshot_retention=…)` on existing sandbox.
- [ ] **Preview hosts:** record real hostname; update `templates/vite-react/vite.config.js` `allowedHosts`.
- [ ] **Plan limits:** Hobby ~45m session max vs Pro; align `MAX_ITERATIONS` and extend calls.

## Post-MVP

- [ ] Orphan reconcile — list/metadata only, env-prefixed names `{DEPLOY_ENV}:{uuid}`.