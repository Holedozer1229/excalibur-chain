@echo off
REM Excalibur bootstrap — double-click to clone/update the repo, fetch the chain, verify it.
REM Requires: Git for Windows + Python 3.10+ (both with PATH entries).
setlocal
where powershell >nul 2>&1
if errorlevel 1 (
  echo PowerShell is required to run the Excalibur bootstrap.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" %*
if errorlevel 1 (
  echo BOOTSTRAP FAILED — see above.
  pause
  exit /b 1
)
echo BOOTSTRAP OK.
pause
