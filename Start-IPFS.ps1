param(
    [switch]$ConfigureOnly
)

$ErrorActionPreference = "Stop"
$ipfsExe = Join-Path $PSScriptRoot "ipfs\ipfs.exe"
if (-not (Test-Path $ipfsExe)) {
    throw "IPFS binary not found: $ipfsExe"
}

if (-not $env:IPFS_PATH) {
    $env:IPFS_PATH = Join-Path $env:USERPROFILE ".ipfs"
}
$configPath = Join-Path $env:IPFS_PATH "config"

if (-not (Test-Path $configPath)) {
    & $ipfsExe init
    if ($LASTEXITCODE -ne 0) {
        throw "IPFS repository initialization failed with exit code $LASTEXITCODE."
    }

    & $ipfsExe config Addresses.API "/ip4/127.0.0.1/tcp/5001"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not restrict the IPFS API to localhost."
    }
    & $ipfsExe config Addresses.Gateway "/ip4/127.0.0.1/tcp/8080"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not restrict the IPFS gateway to localhost."
    }
}

if ($ConfigureOnly) {
    Write-Host "Local IPFS repository configured at $env:IPFS_PATH"
    Write-Host "API and gateway are bound to localhost; no daemon was started."
    exit 0
}

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:5001/api/v0/id" -Method Post -TimeoutSec 2 | Out-Null
    exit 0
} catch {
    # No local IPFS daemon is responding; start this user's daemon below.
}

$logDir = Join-Path $env:LOCALAPPDATA "AetherionEXCAL"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stdoutLog = Join-Path $logDir "ipfs-daemon.log"
$stderrLog = Join-Path $logDir "ipfs-daemon-error.log"
$daemon = Start-Process -FilePath $ipfsExe -ArgumentList "daemon" -WindowStyle Hidden `
    -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

for ($attempt = 0; $attempt -lt 15; $attempt++) {
    Start-Sleep -Seconds 1
    if ($daemon.HasExited) {
        throw "IPFS daemon exited with code $($daemon.ExitCode). See $stderrLog"
    }
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:5001/api/v0/id" -Method Post -TimeoutSec 2 | Out-Null
        Write-Host "Local IPFS daemon is ready (PID $($daemon.Id))."
        exit 0
    } catch {
        # Wait for the daemon API to become ready.
    }
}

throw "IPFS daemon did not become ready. See $stderrLog"
