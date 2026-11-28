# Apply phone-auth migrations (DATABASE_URL or last DATABASE_URL in apps/web/.env.local).
# If connection times out, enable public access on Liara Postgres or run liara-migrate-remote.ps1 after deploy.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (-not $env:DATABASE_URL) {
  $envFile = Join-Path $Root "apps\web\.env.local"
  if (Test-Path $envFile) {
    $line = Get-Content $envFile | Where-Object { $_ -match '^\s*DATABASE_URL=' } | Select-Object -Last 1
    if ($line) {
      $env:DATABASE_URL = ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
    }
  }
}
if (-not $env:DATABASE_URL) {
  Write-Error "Set DATABASE_URL or add it to apps/web/.env.local"
}

$py = @"
import os
from pathlib import Path
import psycopg

url = os.environ['DATABASE_URL']
root = Path(r'$($Root.Replace("'", "''"))')
for name in ('0010_user_phone.sql', '0011_phone_otp.sql'):
    sql = (root / 'db' / 'migrations' / name).read_text(encoding='utf-8')
    print(f'Applying {name}...')
    with psycopg.connect(url, connect_timeout=25, autocommit=True) as conn:
        conn.execute(sql)
    print(f'OK {name}')
print('Migrations done.')
"@

python -c $py