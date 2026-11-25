# Apply db/migrations to DATABASE_URL (e.g. Liara Postgres).
# Usage: $env:DATABASE_URL="postgresql://..."; .\scripts\liara-migrate.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $env:DATABASE_URL) {
  Write-Error "Set DATABASE_URL first"
}
$migrations = Get-ChildItem (Join-Path $Root "db\migrations\*.sql") | Sort-Object Name
foreach ($f in $migrations) {
  Write-Host "Applying $($f.Name)..."
  psql $env:DATABASE_URL -f $f.FullName
}
Write-Host "Migrations done."