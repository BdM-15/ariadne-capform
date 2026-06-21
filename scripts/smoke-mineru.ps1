# MinerU end-to-end smoke — requires parser API on MINERU_LOCAL_ENDPOINT
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
& .\.venv\Scripts\python.exe backend\scripts\smoke_mineru.py
exit $LASTEXITCODE