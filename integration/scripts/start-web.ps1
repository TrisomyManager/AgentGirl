# Start Vite dev server for apps/web
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Web = Join-Path $RepoRoot "apps\web"
Set-Location $Web
if (-not $env:VITE_API_BASE_URL) {
    $env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
}
Write-Host "Starting web from $Web ; VITE_API_BASE_URL=$($env:VITE_API_BASE_URL)"
npm run dev
