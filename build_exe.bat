@echo off
REM Build the EXCAL wallet as a one-file excalibur.exe on Windows.
REM Double-click this file in the repo folder (or run it from cmd).
REM Requires Python 3.10+ — uses the repo .venv if present, else python.
setlocal
cd /d %~dp0
if exist .venv\Scripts\python.exe (
  set PY=.venv\Scripts\python.exe
) else (
  set PY=python
)
%PY% -m pip install --quiet pyinstaller
if errorlevel 1 (
  echo pip install pyinstaller FAILED — check your Python / network.
  pause
  exit /b 1
)
%PY% build_wallet_exe.py
if errorlevel 1 (
  echo BUILD FAILED.
  pause
  exit /b 1
)
echo.
echo Built: excalibur-dist\excalibur.exe
echo Double-click it, or run: excalibur-dist\excalibur.exe --help
pause
