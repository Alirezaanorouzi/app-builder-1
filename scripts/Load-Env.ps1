# Shared .env loader for scripts (repo root .env, then apps/web/.env.local).

function Read-DotenvFile {
    param([Parameter(Mandatory)][string]$Path)
    $map = [ordered]@{}
    if (-not (Test-Path $Path)) { return $map }
    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.TrimEnd("`r")
        if ($line -match '^\s*#' -or $line -match '^\s*$') { return }
        $i = $line.IndexOf('=')
        if ($i -lt 1) { return }
        $k = $line.Substring(0, $i).Trim()
        $v = $line.Substring($i + 1).Trim().Trim('"').Trim("'")
        $map[$k] = $v
    }
    return $map
}

function Get-RepoDatabaseUrl {
    param([string]$RepoRoot)
    if ($env:DATABASE_URL) {
        return $env:DATABASE_URL.Trim().Trim('"').Trim("'")
    }
    foreach ($rel in @(".env", "apps\web\.env.local")) {
        $path = Join-Path $RepoRoot $rel
        $map = Read-DotenvFile $path
        if ($map["DATABASE_URL"]) {
            return [string]$map["DATABASE_URL"]
        }
    }
    return $null
}