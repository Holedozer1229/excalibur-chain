# AetherionEXCAL SkyNet Beacon — Windows PowerShell Auto-Start Script
# This starts the SkyNet beacon as a background process
# Place this in your Startup folder for auto-start on login:
#   shell:startup

$ErrorActionPreference = "Continue"

Write-Host "========================================"
Write-Host "  AetherionEXCAL SkyNet Beacon"
Write-Host "========================================"
Write-Host ""

# Check if beacon is already running
$beaconProcess = Get-Process -Name "AetherionEXCAL-Beacon" -ErrorAction SilentlyContinue
if ($beaconProcess) {
    Write-Host "SkyNet Beacon is already running (PID: $($beaconProcess.Id))."
    Write-Host ""
    Write-Host "Press any key to exit..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 0
}

# Start the beacon in background
Write-Host "Starting SkyNet Beacon..."
$beaconPath = Join-Path $PSScriptRoot "dist\AetherionEXCAL-Beacon.exe"

if (Test-Path $beaconPath) {
    Start-Process -FilePath $beaconPath -ArgumentList "--daemon" -WindowStyle Hidden
    Start-Sleep -Seconds 2

    $check = Get-Process -Name "AetherionEXCAL-Beacon" -ErrorAction SilentlyContinue
    if ($check) {
        Write-Host ""
        Write-Host "SkyNet Beacon started in background (PID: $($check.Id))."
        Write-Host "Node will be discoverable on SkyNet P2P network."
        Write-Host ""
        Write-Host "To check status: AetherionEXCAL-Beacon.exe --status"
        Write-Host "To stop: taskkill /IM AetherionEXCAL-Beacon.exe"
        Write-Host ""
    }
    else {
        Write-Host ""
        Write-Host "ERROR: Failed to start SkyNet Beacon."
        Write-Host "Try running manually: dist\AetherionEXCAL-Beacon.exe"
        Write-Host ""
    }
}
else {
    Write-Host ""
    Write-Host "ERROR: Beacon executable not found at:"
    Write-Host "  $beaconPath"
    Write-Host ""
    Write-Host "Build it first: pyinstaller AetherionEXCAL-Beacon.spec"
    Write-Host ""
}

Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
