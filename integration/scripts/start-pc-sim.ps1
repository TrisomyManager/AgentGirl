# Start PC simulator client
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Pc = Join-Path $RepoRoot "apps\pc-client"
Set-Location $Pc
if (-not $env:XIAONUAN_API_BASE_URL) {
    $env:XIAONUAN_API_BASE_URL = "http://127.0.0.1:8000"
}
$Legacy = Join-Path $Pc "legacy_python"
Set-Location $Legacy
Write-Host "Starting pc-client from $Legacy ; XIAONUAN_API_BASE_URL=$($env:XIAONUAN_API_BASE_URL)"
python -m xiaonuan_pc_client
