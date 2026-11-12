# Excalibur bootstrap (Windows) — clone/update the repo, fetch the chain snapshot, verify it.
# Double-click bootstrap.bat, or run:
#   powershell -NoProfile -ExecutionPolicy Bypass -File bootstrap.ps1 [-InstallDir <path>] [-Force] [-SkipVerify]
# What it does:
#   1. clones https://github.com/Holedozer1229/excalibur-chain (or git-pulls if present)
#   2. checks for Python 3.10+
#   3. downloads the fork chain snapshot (chain.jsonl.gz, GitHub release) and decompresses it
#   4. runs genealogy_verify.py — full-sync verification from the BTC-968698 anchor
# Nothing is signed, spent, or broadcast. No keys are needed.
param(
  [string]$InstallDir = "",
  [switch]$Force,
  [switch]$SkipVerify
)
$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/Holedozer1229/excalibur-chain.git"
$ReleaseLatest = "https://github.com/Holedozer1229/excalibur-chain/releases/latest/download/chain.jsonl.gz"
$ReleaseTagged = "https://github.com/Holedozer1229/excalibur-chain/releases/download/chain-snapshot-2026-11-12/chain.jsonl.gz"

function Fail($msg) { Write-Host "BOOTSTRAP FAILED: $msg" -ForegroundColor Red; exit 1 }

Write-Host "== Excalibur bootstrap =="

# 1. Install dir: this script's folder if it is already a repo checkout, else ~/excalibur-chain
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $InstallDir) {
  if (Test-Path (Join-Path $ScriptDir ".git")) { $InstallDir = $ScriptDir }
  else { $InstallDir = Join-Path $env:USERPROFILE "excalibur-chain" }
}
Write-Host "install dir: $InstallDir"

# 2. git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Fail "git not found. Install Git for Windows (https://git-scm.com/download/win) and re-run."
}

# 3. clone or update
if (Test-Path (Join-Path $InstallDir ".git")) {
  Write-Host "repo present — pulling latest..."
  & git -C $InstallDir pull --ff-only
  if ($LASTEXITCODE -ne 0) { Write-Host "git pull failed (local changes?); continuing with the checkout as-is." -ForegroundColor Yellow }
} else {
  Write-Host "cloning $RepoUrl ..."
  & git clone $RepoUrl $InstallDir
  if ($LASTEXITCODE -ne 0) { Fail "git clone failed." }
}

# 4. python 3.10+
$PyCmd = $null; $PyArgs = @()
foreach ($cand in @(@("py", @("-3")), @("python", @()))) {
  try {
    $v = & $cand[0] @($cand[1]) --version 2>&1
    if ($LASTEXITCODE -eq 0 -and $v -match "Python 3\.(\d+)") {
      if ([int]$Matches[1] -ge 10) { $PyCmd = $cand[0]; $PyArgs = $cand[1]; break }
    }
  } catch {}
}
if (-not $PyCmd) { Fail "Python 3.10+ not found. Install from https://www.python.org/downloads/ (tick 'Add python to PATH') and re-run." }
Write-Host "python: $PyCmd $(& $PyCmd @PyArgs --version)"

# 5. chain snapshot — skip if already present (unless -Force)
$ChainGz = Join-Path $InstallDir "chain.jsonl.gz"
$ChainFile = Join-Path $InstallDir "chain.jsonl"
if ((Test-Path $ChainFile) -and -not $Force) {
  Write-Host "chain.jsonl already present — skipping download (use -Force to re-fetch)."
} else {
  Write-Host "downloading chain snapshot (several hundred MB; this takes a while)..."
  $downloaded = $false
  foreach ($url in @($ReleaseLatest, $ReleaseTagged)) {
    try {
      Write-Host "  from $url"
      Invoke-WebRequest -Uri $url -OutFile $ChainGz -UseBasicParsing
      $downloaded = $true; break
    } catch { Write-Host "  failed: $($_.Exception.Message)" -ForegroundColor Yellow }
  }
  if (-not $downloaded) { Fail "could not download the chain snapshot from either release URL." }
  Write-Host "decompressing..."
  & $PyCmd @PyArgs -c "import gzip, shutil; shutil.copyfileobj(gzip.open(r'$ChainGz','rb'), open(r'$ChainFile','wb'))"
  if ($LASTEXITCODE -ne 0) { Fail "decompression failed." }
}
$sizeMB = [math]::Round((Get-Item $ChainFile).Length / 1MB, 1)
Write-Host "chain file: $ChainFile ($sizeMB MB)"

# 6. verify — full-sync from the BTC-968698 anchor (takes a few minutes)
if (-not $SkipVerify) {
  Write-Host "verifying the chain from the anchor..."
  $env:EXCAL_CHAIN_FILE = $ChainFile
  $env:EXCAL_CHECKPOINT_FILE = Join-Path $InstallDir "genealogy_checkpoint.json"
  & $PyCmd @PyArgs (Join-Path $InstallDir "genealogy_verify.py")
  if ($LASTEXITCODE -ne 0) { Fail "genealogy_verify.py reported FAILED." }
}

Write-Host "BOOTSTRAP OK — repo at $InstallDir, chain verified." -ForegroundColor Green
Write-Host "Re-run the verifier any time: $PyCmd genealogy_verify.py"
