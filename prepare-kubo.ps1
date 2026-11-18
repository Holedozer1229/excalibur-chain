$ErrorActionPreference = "Stop"

$version = "0.43.1"
$expectedSha256 = "c25871516dec4d97ce1d160a26c1e3fdad294cb0eea065c0c0343bcfca86c524"
$assetName = "kubo_v$($version)_windows-amd64.zip"
$downloadUrl = "https://github.com/ipfs/kubo/releases/download/v$version/$assetName"
$buildDir = Join-Path $PSScriptRoot "build\kubo"
$archivePath = Join-Path $buildDir $assetName
$extractDir = Join-Path $buildDir "extract"
$ipfsPath = Join-Path $buildDir "ipfs.exe"

if (Test-Path $ipfsPath) {
    Write-Host "Verified Kubo $version binary already prepared."
    exit 0
}

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
Write-Host "Downloading official Kubo $version Windows AMD64 release..."
Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath

$actualSha256 = (Get-FileHash -Path $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualSha256 -ne $expectedSha256) {
    throw "Kubo archive SHA-256 mismatch. Expected $expectedSha256, received $actualSha256."
}

if (Test-Path $extractDir) {
    Remove-Item -LiteralPath $extractDir -Recurse -Force
}
Expand-Archive -LiteralPath $archivePath -DestinationPath $extractDir
$archiveBinary = Join-Path $extractDir "kubo\ipfs.exe"
if (-not (Test-Path $archiveBinary)) {
    throw "The verified Kubo archive does not contain kubo\ipfs.exe."
}
Copy-Item -LiteralPath $archiveBinary -Destination $ipfsPath
Write-Host "Prepared verified Kubo binary at $ipfsPath."
