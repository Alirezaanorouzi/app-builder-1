# Apply phone-auth migrations (0010 + 0011) using DATABASE_URL from repo .env.
# Usage: .\scripts\liara-migrate.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
. (Join-Path $Root "scripts\Load-Env.ps1")

$dbUrl = Get-RepoDatabaseUrl -RepoRoot $Root
if (-not $dbUrl) {
    Write-Error "Set DATABASE_URL in .env (repo root), apps/web/.env.local, or the environment"
}
$env:DATABASE_URL = $dbUrl
Write-Host "Using DATABASE_URL from .env (host not printed)."
python (Join-Path $Root "scripts\apply_migrations.py") --from 0010