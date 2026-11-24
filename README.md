# App Builder MVP (FA mobile-first)

Stack: **Next.js** (web + queue insert), **Python worker** (OpenHands SDK + Vercel/local sandbox), **Postgres**, **tar.gz conversation archives**.

## Quick start (Windows PowerShell)

```powershell
.\scripts\setup.ps1

# Terminal 1
cd apps\web
npm run dev

# Terminal 2
cd apps\agent
$env:PYTHONPATH = "."
python -m worker
```

Postgres listens on **host port 15432** (change `docker-compose.yml` if needed).

On Windows, use **`127.0.0.1`** in `DATABASE_URL` (not `localhost`) so the Python worker’s connection pool can reach Postgres.

**LLM (Liara only):** Set `LIARA_BASE_URL`, `LIARA_API_KEY`, and `LIARA_MODELS` in `.env` (comma-separated catalog IDs, same as [Liara chat completions](https://developers.liara.ir/ai-chat-completions/chat-completions/create-a-chat-completion)). The worker clears conflicting `OPENAI_*` env vars and bypasses HTTP proxies for `ai.liara.ir` so a dead local VPN proxy (`127.0.0.1:10809`) does not break the agent when the VPN is off. Turn off Windows “Use a proxy server” if it stays enabled without the VPN client.

**Sandbox:** `SANDBOX_PROVIDER=local` runs Vite on your machine. With `vercel`, the default `AGENT_RUNTIME=auto` runs the **OpenHands Agent Server inside the sandbox VM** (ports 5173 + 8000) and uses a public **`LLM_PROXY_PUBLIC_URL`** for per-run virtual keys (see `.env.example`). Set `AGENT_RUNTIME=embedded` to keep the older worker staging + upload path. Golden snapshot: `apps/agent/scripts/create_vercel_base_snapshot.py` → `VERCEL_BASE_SNAPSHOT_ID`. Idle stop: `SANDBOX_IDLE_SECONDS` (default 300). `MAX_ITERATIONS=80` by default.

## Quick start (macOS / Linux)

```bash
cp .env.example .env
docker compose up -d postgres
pip install -e packages/archive
pip install -e "apps/agent[dev]"
cd apps/web && npm install && npm run dev
# other terminal: cd apps/agent && PYTHONPATH=. python -m worker
```

Apply schema via Docker init or:

```bash
psql $DATABASE_URL -f db/migrations/0001_init.sql
psql $DATABASE_URL -f db/migrations/0002_agent_server.sql
```

Windows (after `docker compose up -d postgres`): `.\scripts\apply-migrations.ps1`

## Layout

- `apps/web` — RTL Persian UI, auth, SSE chat, queues `agent_runs`
- `apps/agent` — polling worker (no HTTP wake)
- `packages/archive` — conversation tar store (local / S3)
- `templates/vite-react` — sandbox starter
- `docs/openhands-sdk.md`, `docs/vercel-sandbox-verify.md`

## Tests

```bash
cd apps/agent && PYTHONPATH=. python -m pytest tests -q
```

## Fonts

Place `Vazirmatn-Regular.woff2` in `apps/web/public/fonts/` or rely on system UI fallback in `globals.css`.