# Quick status check — does not run migration.
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
& (Join-Path $Root "scripts\run-intel-migration.ps1") -Status