@echo off
REM AetherionEXCAL SkyNet Beacon — Windows Auto-Start Script
REM This starts the SkyNet beacon as a background process
REM Place this in your Startup folder for auto-start on login:
REM   shell:startup

title SkyNet Beacon

echo ========================================
echo   AetherionEXCAL SkyNet Beacon
echo ========================================
echo.

REM Check if beacon is already running
tasklist /FI "IMAGENAME eq AetherionEXCAL-Beacon.exe" 2>NUL | find /I /N "AetherionEXCAL-Beacon.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo SkyNet Beacon is already running.
    echo.
    pause
    exit /b 0
)

REM Start the beacon in background
echo Starting SkyNet Beacon...
start /B "" "%~dp0dist\AetherionEXCAL-Beacon.exe" --daemon

echo.
echo SkyNet Beacon started in background.
echo Node will be discoverable on SkyNet P2P network.
echo.
echo To check status: AetherionEXCAL-Beacon.exe --status
echo To stop: taskkill /IM AetherionEXCAL-Beacon.exe
echo.
pause
