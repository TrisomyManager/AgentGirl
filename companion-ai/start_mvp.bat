@echo off
REM ============================================================
REM  Companion AI — MVP Startup Script (Windows)
REM  Uses unified main.py — all modules in one Python process
REM ============================================================

cd /d "%~dp0"

echo.
echo  =============================================
echo   Companion AI MVP Starting...
echo  =============================================
echo.
echo  [1/2] Starting backend (unified mode, port 8000)
echo.

set COMPANION_LITE_MODE=true
set COMPANION_MONOLITHIC=true
set COMPANION_ENABLE_VOICE=false
set COMPANION_ENABLE_ACTION_2D=false
set COMPANION_ENABLE_DEVICE_COORDINATION=false
set COMPANION_ENABLE_MEMORY_PIPELINE=false
set COMPANION_ENABLE_KNOWLEDGE_GRAPH=false

start "Companion AI Backend" cmd /k "cd /d "%~dp0" && set COMPANION_LITE_MODE=true && set COMPANION_MONOLITHIC=true && set COMPANION_ENABLE_VOICE=false && set COMPANION_ENABLE_ACTION_2D=false && set COMPANION_ENABLE_DEVICE_COORDINATION=false && set COMPANION_ENABLE_MEMORY_PIPELINE=false && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

echo  Waiting 3 seconds for backend to start...
timeout /t 3 /nobreak >nul

echo.
echo  [2/2] Starting Vue frontend dev server
echo        Open: http://localhost:5173
echo.

start "Companion AI Frontend" cmd /k "cd /d "%~dp0\frontend_app" && set VITE_API_BASE_URL=http://127.0.0.1:8000 && npm run dev"

echo.
echo  =============================================
echo   All services started!
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8000/health
echo  =============================================
echo.
pause
