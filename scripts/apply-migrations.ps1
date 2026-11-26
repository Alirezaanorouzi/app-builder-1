# Apply SQL migrations in order (idempotent). Run from repo root.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

# Fresh Postgres loads 0001 + 0002 from docker-entrypoint-initdb.d (see docker-compose.yml).
# This script applies incremental migrations on existing volumes (idempotent).
$files = @(
    "db\migrations\0002_agent_server.sql",
    "db\migrations\0003_sandbox_wake.sql",
    "db\migrations\0004_run_live_stream.sql",
    "db\migrations\0005_run_execution_sandbox_session.sql",
    "db\migrations\0006_project_stream_notify.sql",
    "db\migrations\0007_run_queue_sandbox_meta.sql",
    "db\migrations\0008_admin_metrics.sql"
)
foreach ($rel in $files) {
    $path = Join-Path $Root $rel
    if (-not (Test-Path $path)) { throw "Missing migration: $path" }
    Write-Host "Applying $rel ..."
    Get-Content $path -Raw | docker compose exec -T postgres psql -U appbuilder -d appbuilder -v ON_ERROR_STOP=1 -f - | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Migration failed: $rel" }
}
Write-Host "Migrations applied."