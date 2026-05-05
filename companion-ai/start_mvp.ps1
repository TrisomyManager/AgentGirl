# ============================================================
# Companion AI — MVP Startup Script (PowerShell)
# Uses unified main.py — all modules in one Python process
# Usage: .\start_mvp.ps1
# ============================================================

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$BackendEnv = @(
    "`$env:COMPANION_LITE_MODE='true'",
    "`$env:COMPANION_MONOLITHIC='true'",
    "`$env:COMPANION_ENABLE_VOICE='false'",
    "`$env:COMPANION_ENABLE_ACTION_2D='false'",
    "`$env:COMPANION_ENABLE_DEVICE_COORDINATION='false'",
    "`$env:COMPANION_ENABLE_MEMORY_PIPELINE='false'",
    "`$env:COMPANION_ENABLE_KNOWLEDGE_GRAPH='false'"
) -join "; "

Write-Host ""
Write-Host "============================================="
Write-Host " Companion AI MVP Starting..."
Write-Host "============================================="

# Start backend in new window
Write-Host "[1/2] Starting backend (unified, port 8000)..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$Root'; $BackendEnv; " +
    "python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
) -WindowStyle Normal

Start-Sleep -Seconds 3

# Ensure frontend deps are installed before launching Vite
$FrontendDir = Join-Path $Root 'frontend_app'
$NodeModules = Join-Path $FrontendDir 'node_modules'
if (-not (Test-Path $NodeModules)) {
    Write-Host "[1.5/2] frontend_app/node_modules not found — running 'npm install' (first run only)..."
    Push-Location $FrontendDir
    & npm install
    $npmExit = $LASTEXITCODE
    Pop-Location
    if ($npmExit -ne 0) {
        Write-Host "  npm install failed (exit $npmExit). Install Node.js >= 18 and re-run this script." -ForegroundColor Red
        return
    }
}

# Start frontend
Write-Host "[2/2] Starting Vue dev server..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$FrontendDir'; " +
    "`$env:VITE_API_BASE_URL='http://127.0.0.1:8000'; " +
    "npm run dev"
) -WindowStyle Normal

Write-Host ""
Write-Host "============================================="
Write-Host " Services started!"
Write-Host " Frontend: http://localhost:5173"
Write-Host " Backend:  http://localhost:8000/health"
Write-Host "  (add COMPANION_OPENAI_API_KEY or"
Write-Host "   COMPANION_ANTHROPIC_API_KEY for real LLM)"
Write-Host "============================================="
