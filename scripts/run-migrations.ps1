# Apply workflow Alembic migrations (intel tables use run-intel-migration.ps1).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw ".venv missing — run scripts\bootstrap.ps1 first" }
Push-Location (Join-Path $Root "backend")
try {
    & $Python -c "from thread.db.migrate import run_workflow_migrations; print(run_workflow_migrations())"
} finally {
    Pop-Location
}