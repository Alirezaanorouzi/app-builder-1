# Deploy Next.js from apps/web (Liara builds on platform).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Web = Join-Path $Root "apps\web"
. (Join-Path $Root "scripts\LiaraCli.ps1")

Push-Location $Web
try {
  $auth = Get-LiaraCliAuthArgs -RepoRoot $Root
  Write-Host "Deploying appbuilder1-web from $Web"
  & liara deploy -a appbuilder1-web --port 3000 --platform next `
    --liara-json liara.json @auth @args
} finally {
  Pop-Location
}