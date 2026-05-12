# Start backend (Lite Mode) from repo root or any cwd
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Backend = Join-Path $RepoRoot "apps\backend"
Set-Location $Backend
$env:COMPANION_LITE_MODE = "true"
Write-Host "Starting backend from $Backend (port 8000)..."
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
