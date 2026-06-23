# Phase 17e-e - MVP identification funnel smoke (Insights -> Watch -> Track -> packet fill).
# Requires: docker Postgres + intel migration + python app.py on :9622
param(
    [string]$BaseUrl = "http://127.0.0.1:9622"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "[smoke] MVP sign-off - pytest (in-process, no server required for most steps)"
& "$root\.venv\Scripts\python.exe" -m pytest "$root\backend\tests\test_insights_signoff_e2e.py" -v --tb=short
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[smoke] MVP sign-off - live HTTP ($BaseUrl)"
& "$root\.venv\Scripts\python.exe" "$root\backend\scripts\smoke_insights_signoff.py"
exit $LASTEXITCODE