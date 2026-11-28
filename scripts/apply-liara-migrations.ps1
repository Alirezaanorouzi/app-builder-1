# Apply incremental db/migrations (0002+) to Liara/production Postgres via repo .env.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
. (Join-Path $Root "scripts\Load-Env.ps1")

$dbUrl = Get-RepoDatabaseUrl -RepoRoot $Root
if (-not $dbUrl) {
    Write-Error "Set DATABASE_URL in .env (repo root)"
}
$env:DATABASE_URL = $dbUrl
Write-Host "Applying incremental migrations (0002+) to remote database..."
python (Join-Path $Root "scripts\apply_migrations.py") --from 0002