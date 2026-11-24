# Windows setup (PowerShell). Run from repo root: .\scripts\setup.ps1
$ErrorActionPreference = "Stop"
function Invoke-Quiet($ScriptBlock) {
    & $ScriptBlock 2>$null | Out-Null
}
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

$envContent = Get-Content ".env" -Raw
$envContent = $envContent -replace ":5432/", ":15432/"
$envContent = $envContent -replace "@localhost:", "@127.0.0.1:"
Set-Content ".env" $envContent -NoNewline

# Next.js reads .env.local in apps/web
Copy-Item ".env" "apps\web\.env.local" -Force

New-Item -ItemType Directory -Force -Path "data\conversations", "data\archives", "data\workspace-staging" | Out-Null

Write-Host "Starting Postgres on host port 15432..."
Invoke-Quiet { docker compose down }
docker compose up -d postgres
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

Write-Host "Waiting for Postgres..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    $h = docker compose exec -T postgres pg_isready -U appbuilder -d appbuilder 2>$null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $ready) {
    Write-Warning "Postgres not ready yet. Check: docker compose logs postgres"
} else {
    & (Join-Path $Root "scripts\apply-migrations.ps1")
}

Write-Host "Installing Python worker dependencies..."
pip install -e "packages/archive"
pip install -e "apps/agent[dev]"

Write-Host "Installing web dependencies..."
Set-Location "apps\web"
npm install
Set-Location $Root

Write-Host ""
Write-Host "Done. In two terminals:"
Write-Host "  1) cd apps\web; npm run dev"
Write-Host "  2) cd apps\agent; `$env:PYTHONPATH='.'; python -m worker"
Write-Host "Open http://localhost:3000/register"