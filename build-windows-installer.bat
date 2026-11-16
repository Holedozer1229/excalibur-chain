@echo off
REM ========================================================================
REM  AetherionEXCAL Windows Installer Build Script
REM ========================================================================
REM  This script builds the PyInstaller executables and then creates the
REM  Inno Setup installer package.
REM
REM  Prerequisites:
REM    - Python 3.10+ with pip
REM    - PyInstaller: pip install pyinstaller
REM    - Inno Setup 6+: https://jrsoftware.org/isdl.php
REM    - Required Python packages installed
REM
REM  Usage:
REM    build-windows-installer.bat
REM ========================================================================

setlocal enabledelayedexpansion

echo ========================================
echo   AetherionEXCAL Windows Installer Build
echo   Version 3.0.0
echo ========================================
echo.

REM Check if executables already exist (skip rebuild if present)
set EXES_EXIST=1
if not exist "dist\AetherionEXCAL.exe" set EXES_EXIST=0
if not exist "dist\AetherionEXCAL-Beacon.exe" set EXES_EXIST=0
if not exist "dist\AetherionEXCAL-StratumMiner.exe" set EXES_EXIST=0
if not exist "dist\AetherionEXCAL-P2P.exe" set EXES_EXIST=0

if !EXES_EXIST! == 1 (
    echo [OK] All executables already exist in dist\ - skipping rebuild.
    goto CHECK_INNO
)

REM Check for Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Install Python 3.10+ and try again.
    exit /b 1
)

REM Check for PyInstaller
where pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

:CHECK_INNO

REM Check for Inno Setup
set INNO_SETUP=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if not exist "%INNO_SETUP%" (
    echo WARNING: Inno Setup not found at default location.
    echo Please install Inno Setup 6 from https://jrsoftware.org/isdl.php
    echo Or set the INNO_SETUP environment variable to the ISCC.exe path.
    echo.
    set INNO_SETUP=
    for /f "tokens=2*" %%A in ('reg query "HKLM\SOFTWARE\WOW6432NODE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6" /v InstallLocation 2^>nul') do set "INNO_SETUP=%%B\ISCC.exe"
)

if not defined INNO_SETUP (
    if not exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
        echo ERROR: Inno Setup not found. Cannot build installer.
        echo Build executables only...
        goto BUILD_EXE
    ) else (
        set "INNO_SETUP=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    )
)

echo.
echo [1/4] Building main wallet executable...
pyinstaller --clean AetherionEXCAL.spec
if %errorlevel% neq 0 (
    echo ERROR: Failed to build main executable.
    exit /b 1
)
echo [OK] Main wallet built.

echo.
echo [2/4] Building SkyNet Beacon executable...
pyinstaller --clean --onefile --windowed --name "AetherionEXCAL-Beacon" ^
    --add-data "sphinx_os;sphinx_os" ^
    skynet_beacon.py
if %errorlevel% neq 0 (
    echo WARNING: Failed to build Beacon executable. Continuing...
)
echo [OK] Beacon built.

echo.
echo [3/4] Building Stratum Miner executable...
pyinstaller --clean --onefile --windowed --name "AetherionEXCAL-StratumMiner" ^
    stratum_miner.py
if %errorlevel% neq 0 (
    echo WARNING: Failed to build Stratum Miner executable. Continuing...
)
echo [OK] Stratum Miner built.

echo.
echo [4/4] Building P2P Client executable...
pyinstaller --clean --onefile --windowed --name "AetherionEXCAL-P2P" ^
    p2p_layer.py
if %errorlevel% neq 0 (
    echo WARNING: Failed to build P2P Client executable. Continuing...
)
echo [OK] P2P Client built.

:BUILD_EXE
echo.
echo ========================================
echo   Executables built successfully!
echo ========================================
echo.
echo Output directory: dist\
dir /b dist\AetherionEXCAL*.exe 2>nul
echo.

REM Build Inno Setup installer
if defined INNO_SETUP (
    if exist "%INNO_SETUP%" (
        echo ========================================
        echo   Building Inno Setup Installer...
        echo ========================================
        echo.

        if not exist "installer-icon.ico" (
            echo WARNING: installer-icon.ico not found. Installer will use default icon.
        )

        "%INNO_SETUP%" "AetherionEXCAL-installer.iss"
        if %errorlevel% neq 0 (
            echo ERROR: Inno Setup build failed.
            exit /b 1
        )

        echo.
        echo ========================================
        echo   Installer built successfully!
        echo ========================================
        echo.
        if exist "installer\AetherionEXCAL-Setup-3.0.0.exe" (
            for %%I in ("installer\AetherionEXCAL-Setup-3.0.0.exe") do (
                echo Size: %%~zI bytes
            )
            echo Location: installer\AetherionEXCAL-Setup-3.0.0.exe
        )
    )
) else (
    echo.
    echo Skipping Inno Setup installer (Inno Setup not installed).
    echo To build the installer, install Inno Setup 6 and re-run this script.
)

echo.
echo Done!
