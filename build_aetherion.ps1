# =============================================================================
# AetherionEXCAL — Windows Build Script
# =============================================================================
# Builds the AetherionEXCAL wallet for Windows.
#
# Prerequisites:
#   - Python 3.12+ installed
#   - pip install -r requirements.txt
#   - pip install pyinstaller
#
# Usage:
#   .\build_aetherion.ps1
#
# Output:
#   dist\AetherionEXCAL.exe (Windows executable)
# =============================================================================

$ErrorActionPreference = "Stop"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  AetherionEXCAL — Windows Build" -ForegroundColor Cyan
Write-Host "  Version: 2.0.0" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Find Python executable (prefer venv)
$python = "python"
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
    Write-Host "Using venv Python: $venvPython" -ForegroundColor Green
}

# Check Python version
$pythonVersion = & $python --version 2>&1
Write-Host "Python version: $pythonVersion" -ForegroundColor Green

# Check required packages
Write-Host "`nChecking dependencies..." -ForegroundColor Yellow

try {
    & $python -c "import customtkinter" 2>$null
} catch {
    Write-Host "Installing customtkinter..." -ForegroundColor Yellow
    & $python -m pip install customtkinter
}

try {
    & $python -c "import cryptography" 2>$null
} catch {
    Write-Host "Installing cryptography..." -ForegroundColor Yellow
    & $python -m pip install cryptography
}

try {
    & $python -c "import numpy" 2>$null
} catch {
    Write-Host "Installing numpy..." -ForegroundColor Yellow
    & $python -m pip install numpy
}

try {
    & $python -c "import pyinstaller" 2>$null
} catch {
    Write-Host "Installing pyinstaller..." -ForegroundColor Yellow
    & $python -m pip install pyinstaller
}

# Run tests if test directory exists
if (Test-Path "sphinx_os\tests") {
    Write-Host "`nRunning tests..." -ForegroundColor Yellow
    & $python -m unittest discover -s sphinx_os\tests
    Write-Host "Tests passed!" -ForegroundColor Green
}

# Build React GUI if source exists
if (Test-Path "gui\package.json") {
    Write-Host "`nBuilding React GUI..." -ForegroundColor Cyan
    $nodeExe = Get-Command "node" -ErrorAction SilentlyContinue
    if ($nodeExe) {
        Push-Location gui
        npm install --loglevel=warn
        npm run build
        Pop-Location
        Write-Host "React GUI built successfully!" -ForegroundColor Green
    } else {
        Write-Host "Skipping React GUI — Node.js not found" -ForegroundColor Yellow
    }
}

# Build with PyInstaller
Write-Host "`nBuilding AetherionEXCAL for Windows..." -ForegroundColor Cyan
& $python -m PyInstaller --clean AetherionEXCAL.spec

# Check output
if (Test-Path "dist\AetherionEXCAL.exe") {
    $file = Get-Item "dist\AetherionEXCAL.exe"
    $sizeMB = [math]::Round($file.Length / 1MB, 1)
    
    Write-Host ""
    Write-Host "=============================================" -ForegroundColor Cyan
    Write-Host "  Build successful!" -ForegroundColor Green
    Write-Host "  Executable: dist\AetherionEXCAL.exe" -ForegroundColor Green
    Write-Host "  Size: $sizeMB MB" -ForegroundColor Green
    
    if (Test-Path "gui\build\index.html") {
        Write-Host "  React GUI: gui\build\ (ready to serve)" -ForegroundColor Green
    }
    
    Write-Host "=============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Run wallet: .\dist\AetherionEXCAL.exe" -ForegroundColor White
    Write-Host "Serve GUI:  cd gui; npx serve -s build" -ForegroundColor White
} else {
    Write-Host "ERROR: Build failed — dist\AetherionEXCAL.exe not found" -ForegroundColor Red
    exit 1
}
