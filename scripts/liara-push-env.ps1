# Push env from apps/web/.env.local to Liara web + worker apps (CLI: liara login or LIARA_CLI_TOKEN).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$envFile = Join-Path $Root "apps\web\.env.local"
$webApp = "appbuilder1-web"
$workerApp = "appbuilder1-worker"
. (Join-Path $Root "scripts\LiaraCli.ps1")

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
$aiKey = (Get-Content $envFile | Where-Object { $_ -match '^LIARA_API_KEY=' } | Select-Object -First 1) -replace '^LIARA_API_KEY=',''
$cli = Get-LiaraCliAuthArgs -RepoRoot $Root

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
  "WORKER_WAKE_CONCURRENCY=$(if ($e['WORKER_WAKE_CONCURRENCY']) { $e['WORKER_WAKE_CONCURRENCY'] } else { '2' })",
  "SANDBOX_STACK_WAIT_SECONDS=$(if ($e['SANDBOX_STACK_WAIT_SECONDS']) { $e['SANDBOX_STACK_WAIT_SECONDS'] } else { '180' })",
  "SANDBOX_LOCK_TIMEOUT_SECONDS=$(if ($e['SANDBOX_LOCK_TIMEOUT_SECONDS']) { $e['SANDBOX_LOCK_TIMEOUT_SECONDS'] } else { '300' })",
  "REMOTE_CONVERSATION_OPEN_TIMEOUT_SECONDS=$(if ($e['REMOTE_CONVERSATION_OPEN_TIMEOUT_SECONDS']) { $e['REMOTE_CONVERSATION_OPEN_TIMEOUT_SECONDS'] } else { '120' })",
  "REMOTE_CONVERSATION_ROTATE_AFTER_MESSAGES=$(if ($e['REMOTE_CONVERSATION_ROTATE_AFTER_MESSAGES']) { $e['REMOTE_CONVERSATION_ROTATE_AFTER_MESSAGES'] } else { '12' })",
  "RUN_STALE_HEARTBEAT_SECONDS=$(if ($e['RUN_STALE_HEARTBEAT_SECONDS']) { $e['RUN_STALE_HEARTBEAT_SECONDS'] } else { '180' })",
  "WORKER_POLL_SECONDS=$($e['WORKER_POLL_SECONDS'])",
  "RUN_EVENT_MAX_BYTES=$($e['RUN_EVENT_MAX_BYTES'])",
  "SANDBOX_PROVIDER=$($e['SANDBOX_PROVIDER'])",
  "SANDBOX_IDLE_SECONDS=$($e['SANDBOX_IDLE_SECONDS'])",
  "SANDBOX_EXTEND_WHEN_REMAINING_SECONDS=$($e['SANDBOX_EXTEND_WHEN_REMAINING_SECONDS'])",
  "VERCEL_SANDBOX_MAX_SESSION_SECONDS=$(if ($e['VERCEL_SANDBOX_MAX_SESSION_SECONDS']) { $e['VERCEL_SANDBOX_MAX_SESSION_SECONDS'] } else { '2700' })",
  "VERCEL_SNAPSHOT_RETENTION_COUNT=$(if ($e['VERCEL_SNAPSHOT_RETENTION_COUNT']) { $e['VERCEL_SNAPSHOT_RETENTION_COUNT'] } else { '1' })",
  "VERCEL_SNAPSHOT_DELETE_EVICTED=$(if ($e['VERCEL_SNAPSHOT_DELETE_EVICTED']) { $e['VERCEL_SNAPSHOT_DELETE_EVICTED'] } else { '1' })",
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