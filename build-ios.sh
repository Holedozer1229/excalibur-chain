#!/bin/bash
# ========================================================================
#  AetherionEXCAL iOS Build Script
# ========================================================================
#  Builds the iOS app using kivy-ios toolchain.
#
#  Prerequisites:
#    - macOS with Xcode installed
#    - Python 3.10+
#    - kivy-ios: pip install kivy-ios
#    - Xcode Command Line Tools: xcode-select --install
#    - CocoaPods: sudo gem install cocoapods
#    - cython: pip install cython
#
#  Usage:
#    chmod +x build-ios.sh
#    ./build-ios.sh              # Build for simulator
#    ./build-ios.sh device       # Build for physical device
#    ./build-ios.sh archive      # Create archive for App Store
# ========================================================================

set -euo pipefail

APP_NAME="AetherionEXCAL"
APP_VERSION="3.0.0"
BUNDLE_ID="org.aetherion.aetherionexcal"
BUILD_MODE="${1:-simulator}"
TOOLCHAIN_DIR="toolchain"
IOSAPP_DIR="iosapp"

echo "========================================"
echo "  ${APP_NAME} iOS Build"
echo "  Version: ${APP_VERSION}"
echo "  Mode: ${BUILD_MODE}"
echo "  Bundle ID: ${BUNDLE_ID}"
echo "========================================"
echo ""

# ─── Step 1: Check prerequisites ──────────────────────────────────────────

if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: This script must be run on macOS."
    exit 1
fi

if ! command -v xcodebuild &> /dev/null; then
    echo "ERROR: Xcode not found. Install Xcode from the Mac App Store."
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found."
    exit 1
fi

# ─── Step 2: Setup kivy-ios toolchain ─────────────────────────────────────

if [[ ! -d "$TOOLCHAIN_DIR" ]]; then
    echo "Cloning kivy-ios toolchain..."
    git clone https://github.com/kivy/kivy-ios.git "$TOOLCHAIN_DIR"
fi

cd "$TOOLCHAIN_DIR"
git pull --ff-only || true
cd ..

echo "✓ kivy-ios toolchain ready"

# ─── Step 3: Create iOS app project ───────────────────────────────────────

if [[ ! -d "$IOSAPP_DIR" ]]; then
    echo ""
    echo "Creating iOS project..."
    python3 "${TOOLCHAIN_DIR}/toolchain.py" newapp --appname="${APP_NAME}" \
        --bundle="${BUNDLE_ID}" \
        --package="aetherionexcal" \
        --orientation="portrait" \
        --orientation-tablet="portrait" \
        --appjson="${IOSAPP_DIR}/app.json" \
        "${IOSAPP_DIR}"

    # Create app.json with proper configuration
    cat > "${IOSAPP_DIR}/app.json" << 'APPJSON_EOF'
{
    "title": "AetherionEXCAL",
    "author": "Aetherion Oracle",
    "orientation": "portrait",
    "orientation_tablet": "portrait",
    "fullscreen": 0,
    "with_logs": 1,
    "domain": "org.aetherion",
    "bundle": "org.aetherion.aetherionexcal",
    "package": "aetherionexcal",
    "entry_point": "kivy_wallet.main",
    "modules": [
        "kivy"
    ]
}
APPJSON_EOF

    echo "✓ iOS project created"
else
    echo "✓ iOS project already exists"
fi

# ─── Step 4: Build dependencies ───────────────────────────────────────────

echo ""
echo "Building dependencies with kivy-ios..."
echo ""

cd "$TOOLCHAIN_DIR"

if [[ "$BUILD_MODE" == "device" || "$BUILD_MODE" == "archive" ]]; then
    echo "Building for device (arm64)..."
    python3 toolchain.py build kivy
else
    echo "Building for simulator (x86_64)..."
    python3 toolchain.py build kivy
fi

cd ..

echo "✓ Dependencies built"

# ─── Step 5: Build the Xcode project ──────────────────────────────────────

echo ""
echo "Building Xcode project..."
echo ""

cd "$IOSAPP_DIR"

if [[ "$BUILD_MODE" == "archive" ]]; then
    # Create archive for App Store distribution
    xcodebuild archive \
        -scheme "${APP_NAME}" \
        -configuration Release \
        -archivePath "${APP_NAME}.xcarchive" \
        CODE_SIGN_IDENTITY="-" \
        CODE_SIGNING_REQUIRED=NO \
        CODE_SIGNING_ALLOWED=NO

    echo ""
    echo "========================================"
    echo "  Archive created!"
    echo "========================================"
    echo ""
    echo "Archive location: ${APP_NAME}.xcarchive"
    echo ""
    echo "To export for App Store:"
    echo "  xcodebuild -exportArchive \\"
    echo "    -archivePath ${APP_NAME}.xcarchive \\"
    echo "    -exportPath ./export \\"
    echo "    -exportOptionsPlist ExportOptions.plist"
else
    if [[ "$BUILD_MODE" == "device" ]]; then
        CONFIG="Release"
        DESTINATION="generic/platform=iOS"
    else
        CONFIG="Debug"
        DESTINATION="generic/platform=iOS Simulator"
    fi

    xcodebuild \
        -scheme "${APP_NAME}" \
        -configuration "${CONFIG}" \
        -destination "${DESTINATION}" \
        CODE_SIGN_IDENTITY="-" \
        CODE_SIGNING_REQUIRED=NO \
        CODE_SIGNING_ALLOWED=NO

    echo ""
    echo "========================================"
    echo "  Build complete!"
    echo "========================================"
    echo ""
    echo "To run on simulator:"
    echo "  open ${APP_NAME}.app"
    echo ""
    echo "To run on device, connect via USB and use:"
    echo "  xcodebuild -scheme ${APP_NAME} -destination 'platform=iOS,name=YourDevice' -configuration Release"
fi

cd ..
