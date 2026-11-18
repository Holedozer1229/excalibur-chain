@echo off
REM SkyNet Temporal Node Beacon - Deployment Script
REM
REM This script deploys the SkyNet beacon to Cloudflare Workers.
REM
REM Prerequisites:
REM   - Cloudflare account (free)
REM   - Node.js installed
REM   - wrangler CLI installed (npm install -g wrangler)

echo.
echo ========================================
echo   SkyNet Temporal Node Beacon Deploy
echo   AetherionEXCAL P2P Bootstrap Server
echo ========================================
echo.

REM Check if wrangler is installed
where wrangler >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] wrangler not found. Install it:
    echo   npm install -g wrangler
    echo.
    pause
    exit /b 1
)

REM Check if logged in
wrangler whoami >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Not logged in to Cloudflare. Opening browser...
    wrangler login
    if %errorlevel% neq 0 (
        echo [ERROR] Login failed.
        pause
        exit /b 1
    )
)

REM Create KV namespace if it doesn't exist
echo.
echo [INFO] Creating KV namespace...
wrangler kv:namespace create SKYNET_KV --preview >nul 2>&1
echo [INFO] KV namespace created.

REM Deploy
echo.
echo [INFO] Deploying SkyNet Beacon...
wrangler deploy
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Deployment failed. Check wrangler.toml for correct KV namespace IDs.
    echo.
    echo To fix:
    echo   1. Run: wrangler kv:namespace create SKYNET_KV
    echo   2. Copy the ID from output
    echo   3. Update wrangler.toml with the ID
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   SkyNet Beacon deployed successfully!
echo ========================================
echo.
echo Your beacon is now available at:
echo   https://skynet-beacon.YOUR_ACCOUNT.workers.dev
echo.
echo Next steps:
echo   1. Update sphinx_os/nexus/p2p_bootstrap_server.py
echo   2. Replace CENTRAL_BOOTSTRAP_SERVERS with your URL
echo   3. Rebuild: pyinstaller AetherionEXCAL.spec
echo.
pause
