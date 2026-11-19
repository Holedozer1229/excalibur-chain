@echo off
REM AetherionEXCAL P2P Stack - Production Startup Script
REM Starts: fork_node (RPC), P2P layer with EREPR, stratum server, and Camelot Game API
REM
REM Environment variables:
REM   EXCAL_WORKSPACE - path to chain.jsonl
REM   FORK_RPC_PORT   - RPC port (default: 9432)
REM   FORK_RPC_HOST   - RPC bind host (default: 0.0.0.0)
REM   STRATUM_HOST    - Stratum bind host (default: 0.0.0.0)
REM   STRATUM_PORT    - Stratum port (default: 9434)
REM   GAME_API_PORT   - Game API port (default: 9436)

echo ========================================
echo   ⚔️ AetherionEXCAL P2P Stack - Production
echo   Version: 2.0.0
echo ========================================
echo.

REM Set default environment variables
if not defined EXCAL_WORKSPACE set EXCAL_WORKSPACE=%~dp0
if not defined FORK_RPC_PORT set FORK_RPC_PORT=9432
if not defined FORK_RPC_HOST set FORK_RPC_HOST=0.0.0.0
if not defined STRATUM_HOST set STRATUM_HOST=0.0.0.0
if not defined STRATUM_PORT set STRATUM_PORT=9434
if not defined GAME_API_PORT set GAME_API_PORT=9436
if not defined EXCAL_PROMETHEUS_PORT set EXCAL_PROMETHEUS_PORT=9438

echo Configuration:
echo   Workspace: %EXCAL_WORKSPACE%
echo   RPC: %FORK_RPC_HOST%:%FORK_RPC_PORT%
echo   Stratum: %STRATUM_HOST%:%STRATUM_PORT%
echo   Game API: 0.0.0.0:%GAME_API_PORT%
echo   Prometheus: 127.0.0.1:%EXCAL_PROMETHEUS_PORT%/metrics
echo.

REM Check chain file
if not exist "%EXCAL_WORKSPACE%\chain.jsonl" (
    echo WARNING: chain.jsonl not found in %EXCAL_WORKSPACE%
    echo The node will start with an empty chain.
    echo.
)

REM Start fork node (RPC server)
echo Starting fork node RPC server...
start "EXCAL Fork Node" python fork_node.py

REM Wait for RPC to be ready
echo Waiting for RPC server...
timeout /t 5 /nobreak >nul

REM Start P2P layer
echo Starting P2P layer...
start "EXCAL P2P Layer" python p2p_layer.py --rpc-port %FORK_RPC_PORT%

REM Start stratum server
echo Starting stratum server...
start "EXCAL Stratum" python stratum_fork.py

REM Start Camelot Game API
echo Starting Camelot Game API...
start "Camelot Game API" python camelot_api.py

echo.
echo ========================================
echo   ⚔️ AetherionEXCAL Stack Started
echo ========================================
echo.
echo Services:
echo   RPC:            %FORK_RPC_HOST%:%FORK_RPC_PORT%
echo   P2P (EREPR):    0.0.0.0:9433
echo   Bitcoin Bridge: 0.0.0.0:8333
echo   Stratum:        %STRATUM_HOST%:%STRATUM_PORT%
echo   Beacon/Health:  0.0.0.0:9435
echo   Game API:       0.0.0.0:%GAME_API_PORT%
echo   Prometheus:     127.0.0.1:%EXCAL_PROMETHEUS_PORT%/metrics
echo.
echo Press Ctrl+C to stop all services
echo.

REM Keep script running
timeout /t -1
