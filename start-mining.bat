@echo off
REM start-mining.bat — start the full Excalibur fork mining stack on Windows
REM Starts: fork node (RPC:9432) + stratum shim (9434) + CPU miner (non-stop)
REM All three run in separate windows. Close the windows to stop.
setlocal
set "SCRIPT_DIR=%~dp0"
set "PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo ERROR: Python not found at %PYTHON%
  echo Run bootstrap.bat first to set up the environment.
  pause
  exit /b 1
)

if not exist "%SCRIPT_DIR%chain.jsonl" (
  echo ERROR: chain.jsonl not found in %SCRIPT_DIR%
  echo Run bootstrap.bat first to download the chain snapshot.
  pause
  exit /b 1
)

echo Starting Excalibur fork mining stack...
echo.

REM 1. Fork node RPC server (port 9432)
echo [1/3] Starting fork node RPC server on port 9432...
start "Excalibur Fork Node" "%PYTHON%" "%SCRIPT_DIR%fork_node.py"

REM Wait for node to load chain
echo Waiting for node to load chain...
timeout /t 15 /nobreak >nul

REM 2. Stratum shim (port 9434)
echo [2/3] Starting stratum shim on port 9434...
start "Excalibur Stratum Shim" "%PYTHON%" "%SCRIPT_DIR%stratum_fork.py"

REM Wait for stratum to connect to node
echo Waiting for stratum to connect...
timeout /t 5 /nobreak >nul

REM 3. CPU miner (multiprocessing, non-stop, auto-reconnect)
REM Uses cpu_miner_mp.py for true parallel hashing (~22+ MH/s with 4 cores)
echo [3/3] Starting CPU miner (multiprocessing, non-stop, auto-reconnect)...
start "Excalibur CPU Miner" "%PYTHON%" "%SCRIPT_DIR%cpu_miner_mp.py"

echo.
echo Mining stack started!
echo   - Fork node:    RPC on 127.0.0.1:9432
echo   - Stratum shim: 9434
echo   - CPU miner:    connected, hashing
echo.
echo To stop: close the three windows or press Ctrl+C in each.
echo To use a GPU miner instead of the CPU miner, point it at 127.0.0.1:9434
echo and skip step 3.
echo.
pause
