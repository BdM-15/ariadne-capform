# Drop prime intel tables + clear prime chunk log. Subawards untouched.
#
# Usage (repo root):
#   .\scripts\reset-intel-prime-only.ps1
# Then in a separate window:
#   .\scripts\run-intel-migration.ps1 -SkipSubawards

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "[intel] .venv missing - running bootstrap..."
    & (Join-Path $Root "scripts\bootstrap.ps1")
}

Write-Host "[intel] Ensuring PostgreSQL container is up..."
try {
    docker compose -f (Join-Path $Root "docker-compose.yml") up -d postgres | Out-Null
}
catch {
    Write-Host "[intel] WARN: docker compose failed - ensure Postgres is running"
}

& $VenvPython (Join-Path $Root "backend\scripts\reset_intel_prime_only.py")
exit $LASTEXITCODE