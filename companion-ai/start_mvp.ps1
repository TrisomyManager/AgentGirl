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

# Start frontend
Write-Host "[2/2] Starting Vue dev server..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$Root\frontend_app'; " +
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
