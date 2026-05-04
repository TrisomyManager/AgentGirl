@echo off
chcp 65001 > nul
echo ==========================================================
echo  Companion AI — Lite Mode Local Launcher
echo ==========================================================
echo.

if not exist ".env" (
    echo ERROR: .env file not found.
    echo Please copy .env.lite to .env and fill in your API keys.
    pause
    exit /b 1
)

echo Starting 5 core services in separate windows...
echo.

start "Companion AI — core_orchestrator (:8000)" powershell -NoExit -Command "$Host.UI.RawUI.WindowTitle = 'Companion AI — core_orchestrator (:8000)'; uvicorn core_orchestrator.main:app --host 127.0.0.1 --port 8000 --log-level info"
timeout /t 1 /nobreak > nul

start "Companion AI — persona_engine (:8001)" powershell -NoExit -Command "$Host.UI.RawUI.WindowTitle = 'Companion AI — persona_engine (:8001)'; uvicorn persona_engine.main:app --host 127.0.0.1 --port 8001 --log-level info"
timeout /t 1 /nobreak > nul

start "Companion AI — memory_system (:8002)" powershell -NoExit -Command "$Host.UI.RawUI.WindowTitle = 'Companion AI — memory_system (:8002)'; uvicorn memory_system.main:app --host 127.0.0.1 --port 8002 --log-level info"
timeout /t 1 /nobreak > nul

start "Companion AI — voice_layer (:8003)" powershell -NoExit -Command "$Host.UI.RawUI.WindowTitle = 'Companion AI — voice_layer (:8003)'; uvicorn voice_layer.main:app --host 127.0.0.1 --port 8003 --log-level info"
timeout /t 1 /nobreak > nul

start "Companion AI — action_layer (:8004)" powershell -NoExit -Command "$Host.UI.RawUI.WindowTitle = 'Companion AI — action_layer (:8004)'; uvicorn action_layer.main:app --host 127.0.0.1 --port 8004 --log-level info"
timeout /t 1 /nobreak > nul

echo.
echo All services launched!
echo   Core Orchestrator: http://127.0.0.1:8000/docs
echo   Persona Engine:    http://127.0.0.1:8001/docs
echo   Memory System:     http://127.0.0.1:8002/docs
echo   Voice Layer:       http://127.0.0.1:8003/docs
echo   Action Layer:      http://127.0.0.1:8004/docs
echo.
echo Close each window to stop the corresponding service.
pause
