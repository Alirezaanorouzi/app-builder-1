# Deploy on Liara

Two Liara apps: **Next.js web** (public) and **Docker worker** (background). Postgres is a separate Liara database (or external).

## 1. Postgres

1. Create a **PostgreSQL** database in Liara console.
2. Run migrations (from your machine with network access):

```powershell
$env:DATABASE_URL = "postgresql://..."
Get-ChildItem db\migrations\*.sql | Sort-Object Name | ForEach-Object {
  psql $env:DATABASE_URL -f $_.FullName
}
```

Or use `.\scripts\apply-migrations.ps1` after pointing `DATABASE_URL` at Liara Postgres.

## 2. Web (Next.js)

1. `liara create` → platform **next**, app id e.g. `app-builder-web`.
2. Edit `apps/web/liara.json`: set `"app": "app-builder-web"`.
3. In Liara **environment variables** for the web app, set at least:
   - `DATABASE_URL`
   - `SESSION_SECRET` (long random string)
   - `NEXT_PUBLIC_APP_URL` (https URL of this app)
   - `NEXT_PUBLIC_DEFAULT_MODEL`
4. Deploy from `apps/web`:

```powershell
cd apps\web
npm ci
liara deploy
```

Liara runs `npm run build` and `npm start`. Use `.liaraignore` at repo root when deploying from parent; deploying from `apps/web` only uploads that tree (recommended).

## 3. Worker (Docker)

1. `liara create` → platform **docker**, app id e.g. `app-builder-worker`, enable a **disk** mounted at `/app/data` (2GB+).
2. Copy `deploy/liara.worker.json` to repo root as `liara.json` (or pass flags on CLI) and set `"app"`.
3. Set worker env vars from `deploy/.env.liara.example` (Vercel + Liara AI + `LLM_PROXY_*` for remote sandboxes).
4. Deploy from **repository root** (not `apps/agent` — that folder has no Dockerfile and upload is too small):

```powershell
cd c:\Users\LENOVO\app_builder_1
.\scripts\deploy-liara-worker.ps1
# or: liara deploy -a appbuilder1-worker --port 8080 --platform docker --team-id YOUR_TEAM_ID
```

Root `liara.json` must set `"dockerfile": "deploy/Dockerfile.worker"`. Expect a large upload (templates, agent, packages).

Build uses `deploy/Dockerfile.worker`. Worker exposes **8080** for Liara health checks (`HEALTH_HTTP_PORT=8080`).

## 4. Production checklist

| Item | Web | Worker |
|------|-----|--------|
| `DATABASE_URL` | yes | yes |
| Same DB as local migrations | yes | yes |
| `DEPLOY_ENV=prod` | optional | yes |
| Vercel sandbox + Agent Server | — | yes |
| `LLM_PROXY_PUBLIC_URL` (or controlled direct Liara) | — | yes |
| Disk for `/app/data` | — | recommended |

## 5. Vercel agent disconnects (502 / 410)

Remote runs poll **Agent Server** on `https://sb-….vercel.run`. **502** then **410** means the VM or agent process died or restarted mid-run (in-memory conversation is lost). This is **not** fixed by `LLM_PROXY_PUBLIC_URL` if tools and tokens already worked.

Mitigations: retry the user message; avoid redeploying the worker during active runs; watch Liara worker + Vercel sandbox logs; add a public LLM proxy for **security**, not for this error class.

## 6. Optional: LLM proxy

Sandboxes cannot call `127.0.0.1`. Host a small proxy (e.g. `services/llm-proxy`) on a public URL and set `LLM_PROXY_PUBLIC_URL` on the worker. Do **not** set `LLM_REMOTE_DIRECT_LIARA=1` in production unless you accept sandbox-direct Liara keys.

## 7. CLI

```powershell
npm i -g @liara/cli
liara login
```

Docs: [Liara Next.js](https://docs.liara.ir/paas/nextjs/how-tos/deploy-app/) · [Liara Docker](https://docs.liara.ir/paas/docker/how-tos/deploy-app/) · [liara.json](https://docs.liara.ir/paas/liarajson/)