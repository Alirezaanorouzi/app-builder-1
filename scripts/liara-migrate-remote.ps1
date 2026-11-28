# Run phone-auth migrations inside Liara app (private DB network).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
. (Join-Path $Root "scripts\LiaraCli.ps1")

$auth = Get-LiaraCliAuthArgs -RepoRoot $Root
Write-Host "Running migrations on appbuilder1-web (node scripts/apply-phone-migrations.cjs)..."
& liara shell -a appbuilder1-web -c "node scripts/apply-phone-migrations.cjs" @auth