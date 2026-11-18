#!/bin/bash
# AetherionEXCAL SkyNet Beacon — Mac Build Script
# Builds the standalone SkyNet Beacon executable for macOS

set -e

echo "========================================"
echo "  AetherionEXCAL SkyNet Beacon Build"
echo "========================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found. Install from https://www.python.org/"
    exit 1
fi

PYTHON=$(which python3)
echo "Using Python: $PYTHON"
$PYTHON --version

# Check PyInstaller
if ! $PYTHON -m pip show pyinstaller &> /dev/null; then
    echo "Installing PyInstaller..."
    $PYTHON -m pip install pyinstaller
fi

# Install dependencies
echo "Installing dependencies..."
$PYTHON -m pip install -r requirements.txt

# Clean previous build
echo "Cleaning previous build..."
rm -rf build/Beacon dist/AetherionEXCAL-Beacon

# Build
echo "Building SkyNet Beacon..."
$PYTHON -m PyInstaller --clean AetherionEXCAL-Beacon.spec

echo ""
echo "========================================"
echo "  Build Complete!"
echo "========================================"
echo ""
echo "Executable: dist/AetherionEXCAL-Beacon"
echo ""
echo "To run: ./dist/AetherionEXCAL-Beacon"
echo "To auto-start: see com.aetherion.skynet-beacon.plist"
echo ""
