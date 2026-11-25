# Deploy worker from REPO ROOT (Docker build needs full tree + deploy/Dockerfile.worker).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$envFile = Join-Path $Root "apps\web\.env.local"
$teamId = "6acce5116de510a731393ee5"
$authToken = (Get-Content $envFile | Where-Object { $_ -match '^LIARA_API_KEY=' } | Select-Object -Last 1) -replace '^LIARA_API_KEY=',''

Push-Location $Root
try {
  Write-Host "Deploying appbuilder1-worker from $Root"
  & liara deploy -a appbuilder1-worker --port 8080 --platform docker `
    --team-id $teamId --api-token $authToken --liara-json liara.json @args
} finally {
  Pop-Location
}