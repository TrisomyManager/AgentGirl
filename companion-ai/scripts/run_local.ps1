#requires -Version 5.1
<#
.SYNOPSIS
    Companion AI — Local Lite Mode Launcher (Windows)
.DESCRIPTION
    Starts the 5 core services in separate PowerShell windows.
    No Docker / Redis / PostgreSQL / Neo4j required.
.PARAMETER Stop
    Stop all running companion-ai Python processes.
.PARAMETER Install
    Install Python dependencies including aiosqlite for SQLite.
.EXAMPLE
    .\scripts\run_local.ps1
    .\scripts\run_local.ps1 -Install
    .\scripts\run_local.ps1 -Stop
#>
param(
    [switch]$Stop,
    [switch]$Install
)

$ErrorActionPreference = "Stop"
$services = @(
    @{ Name = "core_orchestrator"; Port = 8000; Module = "core_orchestrator.main:app" },
    @{ Name = "persona_engine";    Port = 8001; Module = "persona_engine.main:app" },
    @{ Name = "memory_system";     Port = 8002; Module = "memory_system.main:app" },
    @{ Name = "voice_layer";       Port = 8003; Module = "voice_layer.main:app" },
    @{ Name = "action_layer";      Port = 8004; Module = "action_layer.main:app" }
)

# ---------------------------------------------------------------------------
# Install mode
# ---------------------------------------------------------------------------
if ($Install) {
    Write-Host "Installing / upgrading dependencies..." -ForegroundColor Cyan
    python -m pip install --upgrade pip
    pip install -e ".[dev]"
    pip install aiosqlite
    Write-Host "Done. Run '.\scripts\run_local.ps1' to start services." -ForegroundColor Green
    exit 0
}

# ---------------------------------------------------------------------------
# Stop mode
# ---------------------------------------------------------------------------
if ($Stop) {
    Write-Host "Stopping Companion AI services..." -ForegroundColor Cyan
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
        $svcName = $null
        foreach ($svc in $services) {
            if ($_.CommandLine -match $svc.Module) { $svcName = $svc.Name; break }
        }
        $svcName -ne $null
    }
    if ($procs) {
        foreach ($p in $procs) {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "  Stopped PID $($p.ProcessId)" -ForegroundColor DarkGray
        }
        Write-Host "All services stopped." -ForegroundColor Green
    } else {
        Write-Host "No running companion-ai processes found." -ForegroundColor Yellow
    }
    exit 0
}

# ---------------------------------------------------------------------------
# Start mode
# ---------------------------------------------------------------------------

# Check .env
if (-not (Test-Path ".env")) {
    Write-Host "ERROR: .env file not found in project root." -ForegroundColor Red
    Write-Host "Please run the following command first:" -ForegroundColor Yellow
    Write-Host "    Copy-Item .env.lite .env" -ForegroundColor Yellow
    Write-Host "Then edit .env and fill in your API keys."
    exit 1
}

# Check Python version
try {
    $pyVer = python -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}.{v.micro}')"
    if ($pyVer -lt "3.11") {
        Write-Host "ERROR: Python 3.11+ required, found $pyVer" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "ERROR: Python not found in PATH. Please install Python 3.11+." -ForegroundColor Red
    exit 1
}

# Warn if aiosqlite missing
try {
    python -c "import aiosqlite" | Out-Null
} catch {
    Write-Host "WARNING: aiosqlite not installed. memory_system will fail." -ForegroundColor Yellow
    Write-Host "Run '.\scripts\run_local.ps1 -Install' first." -ForegroundColor Yellow
}

Write-Host "===========================================" -ForegroundColor Cyan
Write-Host " Companion AI — Lite Mode Local Launcher" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Starting 5 core services in separate windows..." -ForegroundColor White
Write-Host "(Close each window manually to stop a service)" -ForegroundColor DarkGray
Write-Host ""

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

foreach ($svc in $services) {
    $title = "Companion AI — $($svc.Name) (:$($svc.Port))"
    $cmd = "uvicorn $($svc.Module) --host 127.0.0.1 --port $($svc.Port) --log-level info"

    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-Command", "`$Host.UI.RawUI.WindowTitle = '$title'; $cmd"
    )

    Write-Host "  [OK] $($svc.Name.PadRight(20)) -> http://127.0.0.1:$($svc.Port)" -ForegroundColor Green
    Start-Sleep -Milliseconds 600
}

Write-Host ""
Write-Host "All services launched!" -ForegroundColor Green
Write-Host ""
Write-Host "Quick links:" -ForegroundColor Cyan
Write-Host "  Core Orchestrator API Docs: http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host "  Persona Engine API Docs:    http://127.0.0.1:8001/docs" -ForegroundColor White
Write-Host "  Memory System API Docs:     http://127.0.0.1:8002/docs" -ForegroundColor White
Write-Host "  Voice Layer API Docs:       http://127.0.0.1:8003/docs" -ForegroundColor White
Write-Host "  Action Layer API Docs:      http://127.0.0.1:8004/docs" -ForegroundColor White
Write-Host ""
Write-Host "To stop all services at once, run:" -ForegroundColor Yellow
Write-Host "    .\scripts\run_local.ps1 -Stop" -ForegroundColor Yellow
Write-Host ""
