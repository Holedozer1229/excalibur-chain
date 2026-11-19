# AetherionEXCAL P2P Stack - Production Startup Script (PowerShell 5.1 compatible)
# Starts: fork_node (RPC), P2P layer with EREPR, stratum server, and Camelot Game API
#
# Environment variables:
#   EXCAL_WORKSPACE - path to chain.jsonl
#   FORK_RPC_PORT   - RPC port (default: 9432)
#   FORK_RPC_HOST   - RPC bind host (default: 0.0.0.0)
#   STRATUM_HOST    - Stratum bind host (default: 0.0.0.0)
#   STRATUM_PORT    - Stratum port (default: 9434)
#   GAME_API_PORT   - Game API port (default: 9436)

# Resolve project root (directory of this script)
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ProjectRoot

# Find Python executable (prefer .venv)
$PythonExe = ""
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
    Write-Host "[OK] Using virtual environment Python" -ForegroundColor Green
} else {
    try {
        $PythonExe = (Get-Command python.exe -ErrorAction Stop).Source
        Write-Host "[WARN] Using system Python (no .venv found)" -ForegroundColor Yellow
    } catch {
        Write-Host "[ERROR] Python not found. Install Python 3.12+ or create .venv." -ForegroundColor Red
        exit 1
    }
}

# Set default environment variables
if (-not $env:EXCAL_WORKSPACE) { $env:EXCAL_WORKSPACE = $ProjectRoot }
if (-not $env:FORK_RPC_PORT) { $env:FORK_RPC_PORT = "9432" }
if (-not $env:FORK_RPC_HOST) { $env:FORK_RPC_HOST = "0.0.0.0" }
if (-not $env:STRATUM_HOST) { $env:STRATUM_HOST = "0.0.0.0" }
if (-not $env:STRATUM_PORT) { $env:STRATUM_PORT = "9434" }
if (-not $env:GAME_API_PORT) { $env:GAME_API_PORT = "9436" }
if (-not $env:EXCAL_PROMETHEUS_PORT) { $env:EXCAL_PROMETHEUS_PORT = "9438" }

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AetherionEXCAL P2P Stack - Production" -ForegroundColor Cyan
Write-Host "  Version: 2.1.0" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:"
Write-Host "  Workspace: $env:EXCAL_WORKSPACE"
Write-Host "  RPC: $env:FORK_RPC_HOST`:$env:FORK_RPC_PORT"
Write-Host "  Stratum: $env:STRATUM_HOST`:$env:STRATUM_PORT"
Write-Host "  Game API: 0.0.0.0`:$env:GAME_API_PORT"
Write-Host ""

# Check chain file
$ChainFile = Join-Path $env:EXCAL_WORKSPACE "chain.jsonl"
if (-not (Test-Path $ChainFile)) {
    Write-Host "[WARN] chain.jsonl not found in $env:EXCAL_WORKSPACE" -ForegroundColor Yellow
    Write-Host "The node will start with an empty chain." -ForegroundColor Yellow
    Write-Host ""
}

# Process list for cleanup
$Processes = @()

# Start a service and return the process object
function Start-ExcalService {
    param(
        [string]$Name,
        [string]$Script,
        [string[]]$Args = @()
    )

    Write-Host "Starting $Name..."

    $fullScript = Join-Path $ProjectRoot $Script
    if (-not (Test-Path $fullScript)) {
        Write-Host "[ERROR] Script not found: $fullScript" -ForegroundColor Red
        return $null
    }

    $argList = @($fullScript)
    if ($Args.Count -gt 0) {
        $argList += $Args
    }

    $process = Start-Process -FilePath $PythonExe `
        -ArgumentList $argList `
        -NoNewWindow `
        -PassThru

    return $process
}

# Cleanup function
function Stop-AllServices {
    Write-Host ""
    Write-Host "Shutting down EXCAL stack..." -ForegroundColor Yellow
    foreach ($proc in $Processes) {
        if ($proc -and -not $proc.HasExited) {
            try {
                $proc.Kill()
                $proc.WaitForExit()
                Write-Host "[OK] Stopped process: $($proc.Id)" -ForegroundColor Green
            } catch {
                Write-Host "[ERROR] Failed to stop process: $($proc.Id)" -ForegroundColor Red
            }
        }
    }
    Write-Host "All services stopped." -ForegroundColor Green
}

try {
    # Start fork node (RPC server)
    $forkProc = Start-ExcalService -Name "EXCAL Fork Node" -Script "fork_node.py"
    if ($forkProc) { $Processes += $forkProc }

    # Wait for RPC to be ready
    Write-Host "Waiting for RPC server..."
    Start-Sleep -Seconds 5

    # Start P2P layer
    $p2pProc = Start-ExcalService -Name "EXCAL P2P Layer" -Script "p2p_layer.py" -Args @("--rpc-port", $env:FORK_RPC_PORT)
    if ($p2pProc) { $Processes += $p2pProc }

    # Start stratum server
    $stratumProc = Start-ExcalService -Name "EXCAL Stratum" -Script "stratum_fork.py"
    if ($stratumProc) { $Processes += $stratumProc }

    # Start Camelot Game API
    $gameProc = Start-ExcalService -Name "Camelot Game API" -Script "camelot_api.py"
    if ($gameProc) { $Processes += $gameProc }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  AetherionEXCAL Stack Started" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Services:"
    Write-Host "  RPC:            $env:FORK_RPC_HOST`:$env:FORK_RPC_PORT"
    Write-Host "  P2P (EREPR):    0.0.0.0:9433"
    Write-Host "  Bitcoin Bridge: 0.0.0.0:8333"
    Write-Host "  Stratum:        $env:STRATUM_HOST`:$env:STRATUM_PORT"
    Write-Host "  Beacon/Health:  0.0.0.0:9435"
    Write-Host "  Game API:       0.0.0.0`:$env:GAME_API_PORT"
    Write-Host "  Prometheus:     127.0.0.1`:$env:EXCAL_PROMETHEUS_PORT/metrics"
    Write-Host ""
    Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Yellow
    Write-Host ""

    # Keep script running and monitor processes
    $running = $true
    while ($running) {
        Start-Sleep -Seconds 2

        # Check if any process has exited unexpectedly
        foreach ($proc in $Processes) {
            if ($proc.HasExited) {
                Write-Host "[WARN] Process exited: $($proc.Id)" -ForegroundColor Red
            }
        }
    }
}
catch {
    if ($_.Exception.Message -notlike "*The operation was canceled*") {
        Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    }
}
finally {
    Stop-AllServices
}
