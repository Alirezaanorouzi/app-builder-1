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

**Sandbox:** `SANDBOX_PROVIDER=local` runs Vite on your machine; `vercel` keeps editing on local staging but **uploads to Vercel Sandbox after each run** for the preview URL (needs `VERCEL_TOKEN`, team, project). Agent steps are in `run_events` in the DB, not the worker console. Default `MAX_ITERATIONS=80` (raise in `.env` for big builds).

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
```

## Layout

- `apps/web` — RTL Persian UI, auth, SSE chat, queues `agent_runs`
- `apps/agent` — polling worker (no HTTP wake)
- `packages/archive` — conversation tar store (local / S3)
- `templates/vite-react` — sandbox starter
- `docs/openhands-sdk.md`, `docs/vercel-sandbox-verify.md`

## Tests

```bash
python apps/agent/tests/test_archive_roundtrip.py
```

## Fonts

Place `Vazirmatn-Regular.woff2` in `apps/web/public/fonts/` or rely on system UI fallback in `globals.css`.