#Requires -Version 5.1
<#
.SYNOPSIS
  Build XiaonuanPCSim.exe (PyInstaller onefile) into -OutputDir.
#>
param(
  [Parameter(Mandatory = $true)]
  [string] $OutputDir
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Push-Location $root
try {
  if (Get-Command uv -ErrorAction SilentlyContinue) {
    if (-not (Test-Path -LiteralPath (Join-Path $root ".venv"))) {
      uv venv --python 3.11
    }
    $venvPy = Join-Path $root ".venv\Scripts\python.exe"
    & uv pip install -e ".[build]"
    & $venvPy -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "pc-client.spec")
  }
  else {
    python -m pip install -e ".[build]"
    python -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "pc-client.spec")
  }
}
finally {
  Pop-Location
}

$built = Join-Path $root "dist\XiaonuanPCSim.exe"
if (-not (Test-Path -LiteralPath $built)) {
  throw "PyInstaller did not produce: $built"
}
Copy-Item -LiteralPath $built -Destination (Join-Path $OutputDir "XiaonuanPCSim.exe") -Force
Write-Host "Copied -> $(Join-Path $OutputDir 'XiaonuanPCSim.exe')" -ForegroundColor Green
