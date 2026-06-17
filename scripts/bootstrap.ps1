# Bootstrap Ariadne's Thread dev environment (run automatically on first python app.py)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "[bootstrap] Creating root .venv at $Root\.venv"
Set-Location $Root

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[bootstrap] ERROR: uv not found. Install from https://docs.astral.sh/uv/"
    exit 1
}

uv venv .venv
uv pip install --python .venv\Scripts\python.exe -e backend

Write-Host "[bootstrap] Done. Run: python app.py"