# Run USAspending intel migration in a dedicated window (bulk zip/CSV COPY → PG).
#
# Usage (from repo root in a separate PowerShell window):
#   .\scripts\run-intel-migration.ps1
#   .\scripts\run-intel-migration.ps1 -Status
#   .\scripts\run-intel-migration.ps1 -Force
#   .\scripts\run-intel-migration.ps1 -IndexesOnly
#
# Re-run to resume after interrupt. Progress: .thread/intel_migration_state.json
# Source: capture-insights/data/raw/10year_bulk/{prime,sub}

param(
    [switch]$Status,
    [switch]$Force,
    [switch]$SkipSubawards,
    [switch]$SkipIndexes,
    [switch]$IndexesOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$MigrateScript = Join-Path $Root "backend\scripts\migrate_intel_from_bulk.py"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[intel] .venv missing - running bootstrap..."
    & (Join-Path $Root "scripts\bootstrap.ps1")
}

if (-not (Test-Path (Join-Path $Root ".env"))) {
    Write-Host "[intel] ERROR: .env not found at repo root"
    exit 1
}

$pyArgs = @()
if ($Status) { $pyArgs += "--status" }
if ($Force) { $pyArgs += "--force" }
if ($SkipSubawards) { $pyArgs += "--skip-subawards" }
if ($SkipIndexes) { $pyArgs += "--skip-indexes" }
if ($IndexesOnly) { $pyArgs += "--indexes-only" }

if (-not $Status) {
    Write-Host "[intel] Ensuring PostgreSQL container is up..."
    try {
        docker compose -f (Join-Path $Root "docker-compose.yml") up -d postgres | Out-Null
    }
    catch {
        Write-Host "[intel] WARN: docker compose failed - ensure Postgres is running on THREAD_POSTGRES_PORT"
    }
    Write-Host "[intel] Starting bulk COPY migration (one zip/csv per step)..."
    Write-Host "[intel] Tail log: Get-Content .thread\intel_migration.log -Wait"
}

& $VenvPython $MigrateScript @pyArgs
exit $LASTEXITCODE