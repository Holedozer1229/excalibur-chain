#!/bin/bash
# =============================================================================
# AetherionEXCAL — Mac / Linux Build Script
# =============================================================================
# Builds the AetherionEXCAL wallet for macOS and Linux.
#
# Prerequisites:
#   - Python 3.12+ installed (via pyenv, Homebrew, or system)
#   - pip install -r requirements.txt
#   - pip install pyinstaller
#
# Usage:
#   ./build_aetherion.sh
#
# Output:
#   dist/AetherionEXCAL (macOS/Linux executable)
#   gui/build/ (React GUI static files)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================="
echo "  AetherionEXCAL — Mac / Linux Build"
echo "  Version: 2.0.0"
echo "============================================="
echo ""

# Find Python executable (prefer venv)
PYTHON="python3"
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
    echo "Using venv Python: $PYTHON"
fi

# Check Python version
PYTHON_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# Check required packages
echo "Checking dependencies..."
$PYTHON -c "import customtkinter" 2>/dev/null || {
    echo "Installing customtkinter..."
    $PYTHON -m pip install customtkinter
}
$PYTHON -c "import cryptography" 2>/dev/null || {
    echo "Installing cryptography..."
    $PYTHON -m pip install cryptography
}
$PYTHON -c "import numpy" 2>/dev/null || {
    echo "Installing numpy..."
    $PYTHON -m pip install numpy
}
$PYTHON -c "import pyinstaller" 2>/dev/null || {
    echo "Installing pyinstaller..."
    $PYTHON -m pip install pyinstaller
}

# Run tests if test directory exists
if [ -d "sphinx_os/tests" ]; then
    echo ""
    echo "Running tests..."
    $PYTHON -m unittest discover -s sphinx_os/tests
    echo "Tests passed!"
fi

# Build React GUI if source exists
if [ -f "gui/package.json" ]; then
    echo ""
    echo "Building React GUI..."
    if command -v node >/dev/null 2>&1; then
        pushd gui >/dev/null
        npm install --loglevel=warn
        npm run build
        popd >/dev/null
        echo "React GUI built successfully!"
    else
        echo "Skipping React GUI — Node.js not found"
    fi
fi

# Build with PyInstaller
echo ""
echo "Building AetherionEXCAL for macOS/Linux..."
$PYTHON -m PyInstaller --clean AetherionEXCAL.spec

# Check output
if [ -f "dist/AetherionEXCAL" ]; then
    SIZE=$(du -h dist/AetherionEXCAL | awk '{print $1}')
    echo ""
    echo "============================================="
    echo "  Build successful!"
    echo "  Executable: dist/AetherionEXCAL"
    echo "  Size: $SIZE"
    if [ -f "gui/build/index.html" ]; then
        echo "  React GUI: gui/build/ (ready to serve)"
    fi
    echo "============================================="
    echo ""
    echo "Run wallet: ./dist/AetherionEXCAL"
    echo "Serve GUI:  cd gui && npx serve -s build"
else
    echo "ERROR: Build failed — dist/AetherionEXCAL not found"
    exit 1
fi
