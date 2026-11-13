@echo off
REM start-node.bat — start the Excalibur fork node RPC server (serve-only, no mining)
REM Uses the project venv Python. Loads chain.jsonl and serves RPC on port 9432.
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

echo Starting fork node RPC server (serve-only, --no-mine)...
echo Chain: %SCRIPT_DIR%chain.jsonl
echo RPC port: 9432
echo.

"%PYTHON%" "%SCRIPT_DIR%fork_node.py"

if errorlevel 1 (
  echo.
  echo Node exited with error.
  pause
)
