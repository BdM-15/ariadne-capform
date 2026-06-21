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

$MineruInstall = Join-Path $Root "scripts\install-mineru.ps1"
$MineruPython = Join-Path $Root ".venv-mineru\Scripts\python.exe"
if ((Test-Path $MineruInstall) -and -not (Test-Path $MineruPython)) {
    Write-Host "[bootstrap] Installing MinerU GPU parser sidecar (one-time, CUDA)..."
    & powershell -ExecutionPolicy Bypass -File $MineruInstall
}

Write-Host "[bootstrap] Done. Run: python app.py"