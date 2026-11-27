# Start LLM proxy + public tunnel (localtunnel). Run from repo root in its own terminal.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Read-Dotenv($path) {
    $map = @{}
    Get-Content $path | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $i = $_.IndexOf('=')
        if ($i -lt 1) { return }
        $k = $_.Substring(0, $i).Trim()
        $v = $_.Substring($i + 1).Trim()
        $map[$k] = $v
    }
    return $map
}

$envMap = Read-Dotenv (Join-Path $Root ".env")
if (-not $envMap["LLM_PROXY_ADMIN_KEY"]) { throw "Set LLM_PROXY_ADMIN_KEY in .env" }
if (-not $envMap["DATABASE_URL"]) {
    $webEnv = Join-Path $Root "apps\web\.env.local"
    if (Test-Path $webEnv) {
        $webMap = Read-Dotenv $webEnv
        if ($webMap["DATABASE_URL"]) { $envMap["DATABASE_URL"] = $webMap["DATABASE_URL"] }
    }
}

$port = 8787
Write-Host "Starting LLM proxy on port $port ..."
$proxyJob = Start-Job -ScriptBlock {
    param($root, $admin, $liaraKey, $liaraBase, $databaseUrl, $port)
    Set-Location (Join-Path $root "services\llm-proxy")
    $env:LLM_PROXY_ADMIN_KEY = $admin
    $env:LIARA_API_KEY = $liaraKey
    $env:LIARA_BASE_URL = $liaraBase
    if ($databaseUrl) { $env:DATABASE_URL = $databaseUrl }
    python -m uvicorn app:app --host 127.0.0.1 --port $port
} -ArgumentList $Root, $envMap["LLM_PROXY_ADMIN_KEY"], $envMap["LIARA_API_KEY"], $envMap["LIARA_BASE_URL"], $envMap["DATABASE_URL"], $port

Start-Sleep -Seconds 3
Write-Host "Opening public tunnel (npx localtunnel)..."
$tunnelLog = Join-Path $Root "data\llm-tunnel.log"
New-Item -ItemType Directory -Force -Path (Split-Path $tunnelLog) | Out-Null
$tunnelProc = Start-Process -FilePath "npx" -ArgumentList @("--yes", "localtunnel", "--port", "$port") `
    -RedirectStandardOutput $tunnelLog -RedirectStandardError $tunnelLog -PassThru -NoNewWindow

$publicUrl = $null
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Path $tunnelLog) {
        $txt = Get-Content $tunnelLog -Raw -ErrorAction SilentlyContinue
        if ($txt -match '(https://[a-zA-Z0-9.-]+\.loca\.lt)') {
            $publicUrl = $Matches[1]
            break
        }
        if ($txt -match '(https://[^\s]+)') {
            $publicUrl = $Matches[1]
            break
        }
    }
}
if (-not $publicUrl) {
    Write-Warning "Could not read tunnel URL from $tunnelLog — check manually."
    Write-Host "Proxy job and tunnel are running; leave this window open."
    Wait-Process -Id $tunnelProc.Id
    exit 1
}

$publicUrl = $publicUrl.TrimEnd('/')
Write-Host "Public LLM proxy URL: $publicUrl"

$envPath = Join-Path $Root ".env"
$content = Get-Content $envPath -Raw
$content = $content -replace 'LLM_PROXY_PUBLIC_URL=.*', "LLM_PROXY_PUBLIC_URL=$publicUrl"
$content = $content -replace 'LLM_PROXY_ADMIN_URL=.*', "LLM_PROXY_ADMIN_URL=$publicUrl"
Set-Content $envPath $content.TrimEnd() -NoNewline
Copy-Item $envPath (Join-Path $Root "apps\web\.env.local") -Force
Write-Host "Updated .env and apps/web/.env.local"

Write-Host "Tunnel + proxy running (Ctrl+C to stop tunnel; proxy runs in background job $($proxyJob.Id))."
try {
    Wait-Process -Id $tunnelProc.Id
} finally {
    Stop-Job $proxyJob -ErrorAction SilentlyContinue
    Remove-Job $proxyJob -Force -ErrorAction SilentlyContinue
}