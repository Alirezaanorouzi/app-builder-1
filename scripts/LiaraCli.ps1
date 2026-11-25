# Shared Liara CLI flags for deploy / env scripts.
# LIARA_API_KEY in .env is for Liara AI — use LIARA_CLI_TOKEN for deploy, or `liara login`.

$Script:LiaraDefaultTeamId = "6acce5116de510a731393ee5"

function Get-LiaraCliAuthArgs {
  param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$TeamId = $env:LIARA_TEAM_ID
  )
  if (-not $TeamId) { $TeamId = $Script:LiaraDefaultTeamId }

  $token = $env:LIARA_CLI_TOKEN
  if (-not $token) {
    $envFile = Join-Path $RepoRoot "apps\web\.env.local"
    if (Test-Path $envFile) {
      foreach ($key in @("LIARA_CLI_TOKEN", "LIARA_DEPLOY_TOKEN")) {
        $line = Get-Content $envFile | Where-Object { $_ -match "^$key=" } | Select-Object -Last 1
        if ($line) {
          $token = ($line -split "=", 2)[1].Trim()
          break
        }
      }
      if (-not $token) {
        $keys = @(Get-Content $envFile | Where-Object { $_ -match "^LIARA_API_KEY=" })
        foreach ($line in $keys) {
          $candidate = ($line -split "=", 2)[1].Trim()
          if ($candidate.Length -gt 80 -or $candidate -match "eyJ") {
            $token = $candidate
            break
          }
        }
      }
    }
  }

  $args = @("--team-id", $TeamId)
  if ($token) {
    $args += @("--api-token", $token)
  } else {
    Write-Host "Liara: using logged-in CLI session (set LIARA_CLI_TOKEN in .env.local or run liara login)."
  }
  return $args
}