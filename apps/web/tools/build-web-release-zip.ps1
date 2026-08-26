#Requires -Version 5.1
<#
.SYNOPSIS
  Build Web test zip: XiaonuanWeb.exe (miniserve static binary) + dist/ + StartWeb.cmd.
.NOTES
  Uses prebuilt miniserve (MIT) from GitHub releases — avoids Node/pkg on tester machines.
#>
param(
  [Parameter(Mandatory = $true)]
  [string] $DistDir,
  [Parameter(Mandatory = $true)]
  [string] $OutputZip,
  [string] $CacheDir = ""
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $DistDir)) {
  throw "Dist not found: $DistDir"
}

$here = $PSScriptRoot
if ($CacheDir -eq "") {
  $CacheDir = Join-Path $here ".cache"
}
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null

$miniserveVer = "0.29.0"
$miniserveName = "miniserve-$miniserveVer-x86_64-pc-windows-msvc.exe"
$miniserveUrl = "https://github.com/svenstaro/miniserve/releases/download/v$miniserveVer/$miniserveName"
$miniserveCached = Join-Path $CacheDir $miniserveName

if (-not (Test-Path -LiteralPath $miniserveCached)) {
  Write-Host "Downloading miniserve $miniserveVer ..." -ForegroundColor Cyan
  Invoke-WebRequest -Uri $miniserveUrl -OutFile $miniserveCached -UseBasicParsing
}

$stageParent = Split-Path -Parent $OutputZip
$stageName = "web-release-stage"
$stage = Join-Path $stageParent $stageName
if (Test-Path -LiteralPath $stage) {
  Remove-Item -LiteralPath $stage -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stage | Out-Null

Copy-Item -LiteralPath $miniserveCached -Destination (Join-Path $stage "XiaonuanWeb.exe") -Force
Copy-Item -LiteralPath $DistDir -Destination (Join-Path $stage "dist") -Recurse -Force

$readme = @"
Xiaonuan Web (static build)
- Double-click StartWeb.cmd: miniserve starts first, then the browser opens (avoids connection refused).
- Manual: XiaonuanWeb.exe -i 127.0.0.1 -p 5173 --spa --index index.html dist
- Do not open dist\index.html via file:// — use the URL above so API calls (CORS) work.
- API base URL was fixed at Vite build time; change backend URL -> rebuild Web from repo.
Static server: miniserve v$miniserveVer (https://github.com/svenstaro/miniserve)
"@
Set-Content -LiteralPath (Join-Path $stage "README.txt") -Value $readme -Encoding UTF8

$startBat = @'
@echo off
setlocal
cd /d "%~dp0"
echo [XiaonuanWeb] Starting miniserve on http://127.0.0.1:5173 ...
start "XiaonuanWeb-miniserve" /MIN "%~dp0XiaonuanWeb.exe" -i 127.0.0.1 -p 5173 --spa --index index.html dist
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "for ($i = 0; $i -lt 40; $i++) { try { Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 250 } }; exit 1"
if errorlevel 1 echo [XiaonuanWeb] WARN: server did not respond in time. Open http://127.0.0.1:5173/ manually.
start "" "http://127.0.0.1:5173/"
echo [XiaonuanWeb] Browser launched. Keep the minimized "XiaonuanWeb-miniserve" window open to stay online.
pause
endlocal
'@
Set-Content -LiteralPath (Join-Path $stage "StartWeb.cmd") -Value $startBat -Encoding ASCII

if (Test-Path -LiteralPath $OutputZip) {
  Remove-Item -LiteralPath $OutputZip -Force
}
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $OutputZip -Force
Remove-Item -LiteralPath $stage -Recurse -Force
Write-Host "Created $OutputZip" -ForegroundColor Green
