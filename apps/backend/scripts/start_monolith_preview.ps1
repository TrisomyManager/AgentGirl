#requires -Version 5.1
<#
.SYNOPSIS
    Monolithic Lite preview: uvicorn main:app + Vite + device sim_client (3 PowerShell windows).
.EXAMPLE
    cd d:\DeskTop\AgentGril\apps\backend
    .\scripts\start_monolith_preview.ps1
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$AppsRoot = Split-Path $Root -Parent
Set-Location $Root

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Missing $py - create .venv and pip install -e .[dev] + aiosqlite" -ForegroundColor Red
    exit 1
}

$fe = Join-Path $AppsRoot "web"
if (-not (Test-Path (Join-Path $fe "node_modules"))) {
    Write-Host "Running npm install in apps/web ..." -ForegroundColor Yellow
    Set-Location $fe
    npm install
    Set-Location $Root
}

Write-Host "Starting backend http://127.0.0.1:8000 ..." -ForegroundColor Cyan
Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-Command",
    "`$Host.UI.RawUI.WindowTitle = 'Companion backend :8000'; Set-Location '$Root'; `$env:COMPANION_LITE_MODE='true'; & '$py' -m uvicorn main:app --reload --host 127.0.0.1 --port 8000"
)

Start-Sleep -Seconds 2

Write-Host "Starting frontend http://127.0.0.1:5173 ..." -ForegroundColor Cyan
Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-Command",
    "`$Host.UI.RawUI.WindowTitle = 'Companion frontend :5173'; Set-Location '$fe'; `$env:VITE_API_BASE_URL='http://127.0.0.1:8000'; npx vite --host 127.0.0.1 --port 5173 --strictPort"
)

Start-Sleep -Seconds 2

$pcClient = Join-Path $AppsRoot "pc-client"
Write-Host "Starting device sim_client (user_001 / pc-sim-001) ..." -ForegroundColor Cyan
Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-Command",
    "`$Host.UI.RawUI.WindowTitle = 'Device sim_client'; Set-Location '$pcClient'; & '$py' sim_client.py"
)

Start-Sleep -Seconds 5
Write-Host "Opening browser ..." -ForegroundColor Green
try {
    Start-Process "http://127.0.0.1:5173/"
} catch {
    Write-Host "Open manually: http://127.0.0.1:5173/" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done. Three windows opened; close a window to stop that service." -ForegroundColor Green
Write-Host "If port 5173 is in use, stop the old Vite first." -ForegroundColor DarkGray
