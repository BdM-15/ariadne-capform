# Drop intel tables + reset bulk migration state (use before a clean COPY reload).
#
# Usage (repo root):
#   .\scripts\reset-intel-pg.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "[intel] Dropping intel_* tables in PostgreSQL..."
docker compose -f (Join-Path $Root "docker-compose.yml") exec -T postgres psql -U thread -d thread -c @"
DROP TABLE IF EXISTS intel_usaspending_prime_awards CASCADE;
DROP TABLE IF EXISTS intel_prime_staging CASCADE;
DROP TABLE IF EXISTS intel_usaspending_subawards CASCADE;
DROP TABLE IF EXISTS intel_naics_summary_cache CASCADE;
"@ | Out-Host

$statePath = Join-Path $Root ".thread\intel_migration_state.json"
$stateDir = Split-Path $statePath
if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory -Path $stateDir | Out-Null }

@{
    phase = "idle"
    indexes_built = $false
    chunks_loaded = @{ prime = @(); sub = @() }
    prime_files_done = 0
    sub_files_done = 0
    prime_rows_inserted = 0
    sub_rows_inserted = 0
    reset_at = (Get-Date).ToUniversalTime().ToString("o")
    reset_reason = "manual reset — bulk COPY sole ingestion path"
} | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath -Encoding utf8

$ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss UTC")
Add-Content -Path (Join-Path $Root ".thread\intel_migration.log") -Value "[$ts] RESET via reset-intel-pg.ps1"

Write-Host "[intel] Done. Intel tables dropped; state cleared."
Write-Host "[intel] Next: .\scripts\run-intel-migration.ps1"