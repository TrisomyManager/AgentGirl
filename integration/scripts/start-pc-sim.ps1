# Start PC simulator client
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Pc = Join-Path $RepoRoot "apps\pc-client"
Set-Location $Pc
if (-not $env:XIAONUAN_API_BASE_URL) {
    $env:XIAONUAN_API_BASE_URL = "http://127.0.0.1:8000"
}
Write-Host "Starting pc-client from $Pc ; XIAONUAN_API_BASE_URL=$($env:XIAONUAN_API_BASE_URL)"
python sim_client.py
