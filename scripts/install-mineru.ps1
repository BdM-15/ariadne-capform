# Install MinerU GPU sidecar (.venv-mineru, Python 3.13, CUDA torch)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[mineru] ERROR: uv not found. Install from https://docs.astral.sh/uv/"
    exit 1
}

$MineruVenv = Join-Path $Root ".venv-mineru"
$Python = Join-Path $MineruVenv "Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "[mineru] Creating GPU venv at $MineruVenv (Python 3.13)"
    uv venv $MineruVenv --python 3.13
}

Write-Host "[mineru] Installing MinerU 3.4 + dependencies (first run downloads models)..."
uv pip install -U "mineru[all]" -p $Python

Write-Host "[mineru] Installing CUDA PyTorch (cu124) for RTX GPU..."
uv pip install --reinstall torch torchvision --index-url https://download.pytorch.org/whl/cu124 -p $Python

Write-Host "[mineru] Installing pipeline extras (albumentations for formula OCR)..."
uv pip install -U albumentations -p $Python

Write-Host "[mineru] Verifying GPU + pipeline deps..."
& $Python -c @"
import torch
import albumentations
print(f'torch={torch.__version__} cuda={torch.cuda.is_available()} albumentations={albumentations.__version__}')
if torch.cuda.is_available():
    print(f'gpu={torch.cuda.get_device_name(0)}')
else:
    raise SystemExit('CUDA not available — check NVIDIA drivers')
"@

Write-Host "[mineru] Done. Parser autostarts with python app.py when MINERU_ENABLED=true."
Write-Host "[mineru] After app start, verify: powershell -File scripts\smoke-mineru.ps1"