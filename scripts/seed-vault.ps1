# Idempotent Karpathy LLM-wiki vault seed (never overwrites existing pages).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw ".venv missing. Run scripts\bootstrap.ps1 first." }
Push-Location (Join-Path $Root "backend")
try {
    & $Python -c "from thread.bootstrap.vault import bootstrap_vault; from thread.config import get_settings; r=bootstrap_vault(get_settings()); print('path:', r['path']); print('created:', len(r.get('created') or [])); [print(' +', p) for p in (r.get('created') or [])[:25]]"
} finally {
    Pop-Location
}