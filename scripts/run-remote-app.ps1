# Terminals to keep open for remote Vercel agent testing:
#   1) (optional) LLM proxy — not needed when LLM_REMOTE_DIRECT_LIARA=1
#   2) Web:  cd apps\web; npm run dev
#   3) Worker: cd apps\agent; $env:PYTHONPATH='.'; python -m worker
#
# Before first run: .\scripts\apply-migrations.ps1
# Tests: cd apps\agent; $env:PYTHONPATH='.'; python -m pytest tests -q

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Copy-Item (Join-Path $Root ".env") (Join-Path $Root "apps\web\.env.local") -Force
Write-Host "Synced .env -> apps/web/.env.local"
Write-Host "Start web and worker in separate terminals (see script header)."