# Build all release binaries and Inno Setup installer package
$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Building All AetherionEXCAL Release Binaries" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# 1. Main Wallet
Write-Host "`n[1/5] Building AetherionEXCAL.exe (Main Wallet)..." -ForegroundColor Yellow
& $python -m PyInstaller --clean --noconfirm AetherionEXCAL.spec
if ($LASTEXITCODE -ne 0) { throw "Failed to build AetherionEXCAL.exe." }

# 2. SkyNet Beacon
Write-Host "`n[2/5] Building AetherionEXCAL-Beacon.exe (SkyNet Beacon)..." -ForegroundColor Yellow
& $python -m PyInstaller --clean --noconfirm AetherionEXCAL-Beacon.spec
if ($LASTEXITCODE -ne 0) { throw "Failed to build AetherionEXCAL-Beacon.exe." }

# 3. Stratum Miner
Write-Host "`n[3/5] Building AetherionEXCAL-StratumMiner.exe (Stratum Miner)..." -ForegroundColor Yellow
& $python -m PyInstaller --clean --noconfirm AetherionEXCAL-StratumMiner.spec
if ($LASTEXITCODE -ne 0) { throw "Failed to build AetherionEXCAL-StratumMiner.exe." }

# 4. P2P Client
Write-Host "`n[4/5] Building AetherionEXCAL-P2P.exe (P2P Client)..." -ForegroundColor Yellow
& $python -m PyInstaller --clean --noconfirm AetherionEXCAL-P2P.spec
if ($LASTEXITCODE -ne 0) { throw "Failed to build AetherionEXCAL-P2P.exe." }

# 5. Inno Setup Installer
Write-Host "`n[5/5] Building Inno Setup Installer..." -ForegroundColor Yellow
$prepareKubo = Join-Path $PSScriptRoot "prepare-kubo.ps1"
& $prepareKubo
if ($LASTEXITCODE -ne 0) {
    throw "Failed to prepare the verified Kubo IPFS binary."
}

$iscc = "C:\Program Files\Inno Setup 7\ISCC.exe"
if (-not (Test-Path $iscc)) {
    throw "Inno Setup compiler not found: $iscc"
}
& $iscc "AetherionEXCAL-installer.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
}

$artifacts = @(
    "dist\AetherionEXCAL.exe",
    "dist\AetherionEXCAL-Beacon.exe",
    "dist\AetherionEXCAL-StratumMiner.exe",
    "dist\AetherionEXCAL-P2P.exe",
    "installer\AetherionEXCAL-Setup-3.0.0.exe"
)
foreach ($artifact in $artifacts) {
    if (-not (Test-Path $artifact) -or (Get-Item $artifact).Length -eq 0) {
        throw "Expected build artifact is missing or empty: $artifact"
    }
}

Write-Host "`n=============================================" -ForegroundColor Green
Write-Host "  All Release Binaries Built Successfully!" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
$artifacts | ForEach-Object {
    $item = Get-Item $_
    Write-Host ("{0} ({1:N0} bytes)" -f $item.FullName, $item.Length) -ForegroundColor Green
}
