# Push env from apps/web/.env.local to Liara web + worker apps (uses auth token at bottom of file).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$envFile = Join-Path $Root "apps\web\.env.local"
$teamId = "6acce5116de510a731393ee5"
$webApp = "appbuilder1-web"
$workerApp = "appbuilder1-worker"

function Parse-EnvFile($path) {
  $map = @{}
  Get-Content $path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $i = $line.IndexOf("=")
    if ($i -lt 1) { return }
    $k = $line.Substring(0, $i).Trim()
    $v = $line.Substring($i + 1).Trim()
    $map[$k] = $v
  }
  return $map
}

$e = Parse-EnvFile $envFile
$authToken = $e["LIARA_API_KEY"]
if ($authToken -like "*type*auth*" -or $authToken.Length -gt 200) {
  # last line wins in map — but auth overwrites ai key; detect by reading last LIARA_API_KEY line
  $authToken = (Get-Content $envFile | Where-Object { $_ -match '^LIARA_API_KEY=' } | Select-Object -Last 1) -replace '^LIARA_API_KEY=',''
}
$aiKey = (Get-Content $envFile | Where-Object { $_ -match '^LIARA_API_KEY=' } | Select-Object -First 1) -replace '^LIARA_API_KEY=',''
$cli = @("--api-token", $authToken, "--team-id", $teamId)

$dbUrl = $e["DATABASE_URL"]
if ($dbUrl -match "127\.0\.0\.1") {
  $dbUrl = (Get-Content $envFile | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -Last 1) -replace '^DATABASE_URL=',''
}

$sessionSecret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
$webUrl = "https://$webApp.liara.run"

Write-Host "Setting $webApp env..."
& liara env set -a $webApp @cli -f `
  "DATABASE_URL=$dbUrl" `
  "SESSION_SECRET=$sessionSecret" `
  "NEXT_PUBLIC_APP_URL=$webUrl" `
  "NEXT_PUBLIC_DEFAULT_MODEL=$($e['NEXT_PUBLIC_DEFAULT_MODEL'])" `
  | Out-Host

$workerPairs = @(
  "DATABASE_URL=$dbUrl",
  "DEPLOY_ENV=prod",
  "LIARA_API_KEY=$aiKey",
  "LIARA_BASE_URL=$($e['LIARA_BASE_URL'])",
  "LIARA_MODELS=$($e['LIARA_MODELS'])",
  "WORKER_CONCURRENCY=5",
  "WORKER_POLL_SECONDS=$($e['WORKER_POLL_SECONDS'])",
  "RUN_EVENT_MAX_BYTES=$($e['RUN_EVENT_MAX_BYTES'])",
  "SANDBOX_PROVIDER=$($e['SANDBOX_PROVIDER'])",
  "SANDBOX_IDLE_SECONDS=$($e['SANDBOX_IDLE_SECONDS'])",
  "SANDBOX_EXTEND_WHEN_REMAINING_SECONDS=$($e['SANDBOX_EXTEND_WHEN_REMAINING_SECONDS'])",
  "VERCEL_TOKEN=$($e['VERCEL_TOKEN'])",
  "VERCEL_TEAM_ID=$($e['VERCEL_TEAM_ID'])",
  "VERCEL_PROJECT_ID=$($e['VERCEL_PROJECT_ID'])",
  "VERCEL_BASE_SNAPSHOT_ID=$($e['VERCEL_BASE_SNAPSHOT_ID'])",
  "VERCEL_PREVIEW_WAIT_SECONDS=$($e['VERCEL_PREVIEW_WAIT_SECONDS'])",
  "MAX_ITERATIONS=$($e['MAX_ITERATIONS'])",
  "OPENHANDS_SDK_VERSION=$($e['OPENHANDS_SDK_VERSION'])",
  "AGENT_RUNTIME=$($e['AGENT_RUNTIME'])",
  "AGENT_SERVER_PORT=$($e['AGENT_SERVER_PORT'])",
  "OH_SECRET_KEY=$($e['OH_SECRET_KEY'])",
  "OH_SESSION_API_KEYS_0=$($e['OH_SESSION_API_KEYS_0'])",
  "LLM_PROXY_ADMIN_KEY=$($e['LLM_PROXY_ADMIN_KEY'])",
  "LLM_REMOTE_DIRECT_LIARA=$($e['LLM_REMOTE_DIRECT_LIARA'])",
  "RUN_ORPHAN_POLICY=$($e['RUN_ORPHAN_POLICY'])",
  "ARCHIVE_BACKEND=$($e['ARCHIVE_BACKEND'])",
  "CONVERSATION_DIR=/app/data/conversations",
  "ARCHIVE_LOCAL_DIR=/app/data/archives",
  "HEALTH_HTTP_PORT=8080"
)
if ($e["LLM_PROXY_PUBLIC_URL"]) {
  $workerPairs += "LLM_PROXY_PUBLIC_URL=$($e['LLM_PROXY_PUBLIC_URL'])"
}
if ($e["LLM_PROXY_ADMIN_URL"]) {
  $workerPairs += "LLM_PROXY_ADMIN_URL=$($e['LLM_PROXY_ADMIN_URL'])"
}

Write-Host "Setting $workerApp env..."
& liara env set -a $workerApp @cli -f @workerPairs | Out-Host
Write-Host "Env pushed. Web URL: $webUrl"