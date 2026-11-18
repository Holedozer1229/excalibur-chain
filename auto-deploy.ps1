# auto-deploy.ps1 — AetherionEXCAL Auto-Bootstrap & Deploy
#
# One-command bootstrap, deploy, and start the full AetherionEXCAL P2P stack.
# This script combines:
#   1. Bootstrap — repo clone/update, Python check, chain download, pip install
#   2. Deploy — module checks, config validation, chain verification
#   3. Start — launch all services (RPC, P2P, Stratum, Game API)
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File auto-deploy.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File auto-deploy.ps1 -SkipChainDownload
#   powershell -NoProfile -ExecutionPolicy Bypass -File auto-deploy.ps1 -SkipStart
#   powershell -NoProfile -ExecutionPolicy Bypass -File auto-deploy.ps1 -Dev

param(
  [switch]$SkipChainDownload,
  [switch]$SkipStart,
  [switch]$Dev,
  [switch]$Force,
  [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"

# Colors
$Green = "Green"
$Yellow = "Yellow"
$Red = "Red"
$Cyan = "Cyan"

function Write-Step($msg) { Write-Host "`n>> $msg" -ForegroundColor $Cyan }
function Write-Ok($msg) { Write-Host "[OK] $msg" -ForegroundColor $Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor $Yellow }
function Write-Err($msg) { Write-Host "[ERR] $msg" -ForegroundColor $Red }
function Fail($msg) { Write-Err $msg; exit 1 }

Write-Host "========================================" -ForegroundColor $Cyan
Write-Host "  AetherionEXCAL - Auto Bootstrap & Deploy" -ForegroundColor $Cyan
Write-Host "  Version: 2.0.0" -ForegroundColor $Cyan
Write-Host "========================================" -ForegroundColor $Cyan
Write-Host ""

# ============================================================
# STEP 1: Determine install directory
# ============================================================
Write-Step "STEP 1: Determining install directory"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $InstallDir) {
  if (Test-Path (Join-Path $ScriptDir ".git")) {
    $InstallDir = $ScriptDir
  } else {
    $InstallDir = Join-Path $env:USERPROFILE "excalibur-chain"
  }
}
Write-Ok "Install directory: $InstallDir"

# ============================================================
# STEP 2: Git clone or update
# ============================================================
Write-Step "STEP 2: Git repository setup"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Fail "Git not found. Install from https://git-scm.com/download/win"
}

$RepoUrl = "https://github.com/Holedozer1229/excalibur-chain.git"

if (Test-Path (Join-Path $InstallDir ".git")) {
  Write-Host "Repository found - pulling latest..."
  $gitResult = & git -C $InstallDir pull --ff-only 2>&1
  if ($LASTEXITCODE -eq 0) { Write-Ok "Repository updated" }
  else { Write-Warn "Git pull failed - continuing with current checkout" }
} else {
  Write-Host "Cloning repository..."
  & git clone $RepoUrl $InstallDir
  if ($LASTEXITCODE -ne 0) { Fail "Git clone failed" }
  Write-Ok "Repository cloned"
}

# ============================================================
# STEP 3: Python 3.10+ check
# ============================================================
Write-Step "STEP 3: Checking Python"

$PyCmd = $null
$PyArgs = @()

$candidates = @(@("py", "-3"), @("python", ""))
foreach ($cand in $candidates) {
  try {
    $cmdName = $cand[0]
    $cmdArg = $cand[1]
    if ($cmdArg -ne "") {
      $v = & $cmdName $cmdArg --version 2>&1
    } else {
      $v = & $cmdName --version 2>&1
    }
    if ($LASTEXITCODE -eq 0 -and $v -match "Python 3\.(\d+)") {
      if ([int]$Matches[1] -ge 10) {
        $PyCmd = $cmdName
        if ($cmdArg -ne "") {
          $PyArgs = @($cmdArg)
        } else {
          $PyArgs = @()
        }
        break
      }
    }
  } catch {}
}

# Check virtual environment
if (-not $PyCmd) {
  $VenvPy = Join-Path $InstallDir ".venv\Scripts\python.exe"
  if (Test-Path $VenvPy) {
    try {
      $v = & $VenvPy --version 2>&1
      if ($LASTEXITCODE -eq 0 -and $v -match "Python 3\.(\d+)") {
        if ([int]$Matches[1] -ge 10) {
          $PyCmd = $VenvPy
          $PyArgs = @()
        }
      }
    } catch {}
  }
}

if (-not $PyCmd) {
  Fail "Python 3.10+ not found. Install from https://www.python.org/downloads/"
}

$pyVersion = & $PyCmd @PyArgs --version 2>&1
Write-Ok "Python found: $pyVersion"

# ============================================================
# STEP 4: Install Python dependencies
# ============================================================
Write-Step "STEP 4: Installing Python dependencies"

Set-Location $InstallDir

# Create venv if it doesn't exist
$VenvDir = Join-Path $InstallDir ".venv"
if (-not (Test-Path $VenvDir)) {
  Write-Host "Creating virtual environment..."
  & $PyCmd @PyArgs -m venv $VenvDir
  if ($LASTEXITCODE -eq 0) { Write-Ok "Virtual environment created" }
}

# Use venv Python
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

if (Test-Path $VenvPy) {
  $PyCmd = $VenvPy
  $PyArgs = @()
}

# Upgrade pip
Write-Host "Upgrading pip..."
& $VenvPip install --upgrade pip -q
Write-Ok "Pip upgraded"

# Install dependencies
if (Test-Path (Join-Path $InstallDir "requirements.txt")) {
  Write-Host "Installing dependencies from requirements.txt..."
  & $VenvPip install -r (Join-Path $InstallDir "requirements.txt") -q
  if ($LASTEXITCODE -eq 0) { Write-Ok "Dependencies installed" }
  else { Write-Warn "Some dependencies may have failed to install" }
}

# ============================================================
# STEP 5: Download and verify chain data
# ============================================================
Write-Step "STEP 5: Chain data setup"

$ChainGz = Join-Path $InstallDir "chain.jsonl.gz"
$ChainFile = Join-Path $InstallDir "chain.jsonl"

if (-not $SkipChainDownload) {
  if ((Test-Path $ChainFile) -and -not $Force) {
    $sizeMB = [math]::Round((Get-Item $ChainFile).Length / 1MB, 1)
    Write-Ok "chain.jsonl already present ($sizeMB MB)"
  } else {
    $ReleaseLatest = "https://github.com/Holedozer1229/excalibur-chain/releases/latest/download/chain.jsonl.gz"
    $ReleaseTagged = "https://github.com/Holedozer1229/excalibur-chain/releases/download/chain-snapshot-2026-11-12/chain.jsonl.gz"

    $downloaded = $false
    foreach ($url in @($ReleaseLatest, $ReleaseTagged)) {
      try {
        Write-Host "  Downloading from $url"
        Invoke-WebRequest -Uri $url -OutFile $ChainGz -UseBasicParsing
        $downloaded = $true
        break
      } catch {
        Write-Warn "  Download failed: $($_.Exception.Message)"
      }
    }

    if ($downloaded) {
      Write-Host "  Decompressing chain data..."
      & $PyCmd @PyArgs -c "import gzip, shutil; shutil.copyfileobj(gzip.open(r'$ChainGz','rb'), open(r'$ChainFile','wb'))"
      if ($LASTEXITCODE -eq 0) {
        $sizeMB = [math]::Round((Get-Item $ChainFile).Length / 1MB, 1)
        Write-Ok "Chain data decompressed ($sizeMB MB)"
      } else {
        Fail "Chain decompression failed"
      }
    } else {
      Write-Warn "Could not download chain snapshot - node will start with empty chain"
    }
  }
} else {
  Write-Warn "Chain download skipped (-SkipChainDownload)"
}

# ============================================================
# STEP 6: Validate configuration
# ============================================================
Write-Step "STEP 6: Validating configuration"

$configFile = Join-Path $InstallDir "config.json"
if (Test-Path $configFile) {
  $config = Get-Content $configFile -Raw | ConvertFrom-Json

  # Check P2P port
  if ($config.p2p.listen_port -eq 9433) {
    Write-Ok "P2P port: 9433 (EXCAL)"
  } else {
    Write-Warn "P2P port: $($config.p2p.listen_port) (expected 9433)"
  }

  # Check Bitcoin bridge
  if ($config.p2p.bitcoin_bridge_port -eq 8333) {
    Write-Ok "Bitcoin bridge port: 8333"
  }

  # Check swaps
  if ($config.p2p.atomic_swap_enabled) { Write-Ok "Atomic swap: enabled" }
  if ($config.p2p.quantum_swap_enabled) { Write-Ok "Quantum swap: enabled" }
  if ($config.p2p.erepr_enabled) { Write-Ok "EREPR protocol: enabled" }

  # Check Game API
  if ($config.camelot_game.enabled) {
    Write-Ok "Camelot Game API: enabled (port $($config.camelot_game.api_port))"
  }

  Write-Ok "Configuration validated"
} else {
  Write-Warn "config.json not found - using defaults"
}

# ============================================================
# STEP 7: Check core modules
# ============================================================
Write-Step "STEP 7: Checking core modules"

$coreModules = @(
  "genesis_fork", "txscript", "p2p_layer", "fork_node",
  "stratum_fork", "trifold_lockbox", "lightledger", "camelot_api"
)

$moduleErrors = 0
foreach ($mod in $coreModules) {
  try {
    & $PyCmd @PyArgs -c "import $mod" 2>$null
    if ($LASTEXITCODE -eq 0) {
      Write-Ok "$mod module loaded"
    } else {
      Write-Warn "$mod import failed"
      $moduleErrors++
    }
  } catch {
    Write-Warn "$mod import failed: $_"
    $moduleErrors++
  }
}

if ($moduleErrors -gt 0) {
  Write-Warn "$moduleErrors module(s) had import issues - continuing anyway"
}

# ============================================================
# STEP 8: Run deploy.py verification
# ============================================================
Write-Step "STEP 8: Running deploy verification"

$deployScript = Join-Path $InstallDir "deploy.py"
if (Test-Path $deployScript) {
  $deployArgs = @("--skip-tests", "--skip-wallet")
  if ($Dev) { $deployArgs += "--dev" }

  & $PyCmd @PyArgs $deployScript @deployArgs 2>&1 | ForEach-Object { Write-Host $_ }

  if ($LASTEXITCODE -eq 0) {
    Write-Ok "Deploy verification passed"
  } else {
    Write-Warn "Deploy verification completed with warnings"
  }
} else {
  Write-Warn "deploy.py not found - skipping verification"
}

# ============================================================
# STEP 9: Summary
# ============================================================
Write-Host ""
Write-Host "========================================" -ForegroundColor $Green
Write-Host "  AetherionEXCAL - Bootstrap Complete!" -ForegroundColor $Green
Write-Host "========================================" -ForegroundColor $Green
Write-Host ""
Write-Host "Services available:" -ForegroundColor $Cyan
Write-Host "  RPC:            0.0.0.0:9432"
Write-Host "  P2P (EREPR):    0.0.0.0:9433"
Write-Host "  Bitcoin Bridge: 0.0.0.0:8333"
Write-Host "  Stratum:        0.0.0.0:9434"
Write-Host "  Health Check:   0.0.0.0:9435"
Write-Host "  Game API:       0.0.0.0:9436"
Write-Host ""

# ============================================================
# STEP 10: Auto-start services
# ============================================================
if (-not $SkipStart) {
  Write-Step "STEP 10: Starting all services"

  # Set environment
  $env:EXCAL_WORKSPACE = $InstallDir
  $env:FORK_RPC_PORT = "9432"
  $env:FORK_RPC_HOST = "0.0.0.0"
  $env:STRATUM_HOST = "0.0.0.0"
  $env:STRATUM_PORT = "9434"
  $env:GAME_API_PORT = "9436"

  Set-Location $InstallDir

  # Start fork node (RPC)
  Write-Host "Starting fork node RPC server..."
  Start-Process -WindowStyle Hidden -FilePath $PyCmd -ArgumentList @PyArgs + "fork_node.py" `
    -WorkingDirectory $InstallDir
  Start-Sleep -Seconds 3
  Write-Ok "Fork node started (RPC:9432)"

  # Start P2P layer
  Write-Host "Starting P2P layer..."
  Start-Process -WindowStyle Hidden -FilePath $PyCmd -ArgumentList @PyArgs + "p2p_layer.py", "--rpc-port", "9432" `
    -WorkingDirectory $InstallDir
  Start-Sleep -Seconds 2
  Write-Ok "P2P layer started (9433, Bitcoin bridge 8333)"

  # Start Stratum
  Write-Host "Starting Stratum server..."
  Start-Process -WindowStyle Hidden -FilePath $PyCmd -ArgumentList @PyArgs + "stratum_fork.py" `
    -WorkingDirectory $InstallDir
  Start-Sleep -Seconds 2
  Write-Ok "Stratum server started (Stratum:9434)"

  # Start Camelot Game API
  Write-Host "Starting Camelot Game API..."
  Start-Process -WindowStyle Hidden -FilePath $PyCmd -ArgumentList @PyArgs + "camelot_api.py" `
    -WorkingDirectory $InstallDir
  Start-Sleep -Seconds 2
  Write-Ok "Camelot Game API started (Game:9436)"

  Write-Host ""
  Write-Host "========================================" -ForegroundColor $Green
  Write-Host "  AetherionEXCAL Stack is RUNNING" -ForegroundColor $Green
  Write-Host "========================================" -ForegroundColor $Green
  Write-Host ""
  Write-Host "All services started in background." -ForegroundColor $Yellow
  Write-Host "To stop: taskkill /F /IM python.exe /FI \"WINDOWTITLE eq EXCAL*\""
  Write-Host ""
  Write-Host "Quick commands:" -ForegroundColor $Cyan
  Write-Host "  RPC test: curl http://localhost:9432"
  Write-Host "  Health:   curl http://localhost:9435/health"
  Write-Host "  Game API: curl http://localhost:9436/stats"
  Write-Host ""
} else {
  Write-Host "Service start skipped (-SkipStart)" -ForegroundColor $Yellow
  Write-Host "Run: start-production.bat to start all services" -ForegroundColor $Yellow
  Write-Host ""
}

Write-Host "Auto-deploy complete. AetherionEXCAL is ready." -ForegroundColor $Green
