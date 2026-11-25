# Deploy worker from REPO ROOT (Docker build needs full tree + deploy/Dockerfile.worker).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
. (Join-Path $Root "scripts\LiaraCli.ps1")

Push-Location $Root
try {
  $auth = Get-LiaraCliAuthArgs -RepoRoot $Root
  Write-Host "Deploying appbuilder1-worker from $Root"
  & liara deploy -a appbuilder1-worker --port 8080 --platform docker `
    --liara-json liara.json @auth @args
} finally {
  Pop-Location
}