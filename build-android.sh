#!/bin/bash
# ========================================================================
#  AetherionEXCAL Android Build Script
# ========================================================================
#  Builds the Android APK using Buildozer (Kivy for Android).
#
#  Prerequisites:
#    - Linux (Ubuntu 20.04+ recommended) or macOS
#    - Python 3.10+
#    - Buildozer: pip install buildozer
#    - JDK 17+: sudo apt install openjdk-17-jdk
#    - Android SDK & NDK (Buildozer auto-installs)
#    - System dependencies:
#      sudo apt install python3-pip build-essential git python3-dev \
#      ffmpeg libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev \
#      libsdl2-ttf-dev libportmidi-dev libswscale-dev libavformat-dev \
#      libavcodec-dev zlib1g-dev libgstreamer1.0 gstreamer1.0-plugins-base \
#      gstreamer1.0-plugins-good zip unzip openjdk-17-jdk wget curl
#
#  Usage:
#    chmod +x build-android.sh
#    ./build-android.sh          # Debug APK
#    ./build-android.sh release  # Release APK (requires keystore)
# ========================================================================

set -euo pipefail

APP_NAME="AetherionEXCAL"
BUILD_MODE="${1:-debug}"

echo "========================================"
echo "  ${APP_NAME} Android Build"
echo "  Mode: ${BUILD_MODE}"
echo "========================================"
echo ""

# ─── Step 1: Check prerequisites ──────────────────────────────────────────

if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found."
    exit 1
fi

if ! command -v buildozer &> /dev/null; then
    echo "Installing Buildozer..."
    pip3 install buildozer
fi

if ! command -v javac &> /dev/null; then
    echo "ERROR: Java JDK not found. Install OpenJDK 17:"
    echo "  sudo apt install openjdk-17-jdk"
    exit 1
fi

# ─── Step 2: Check buildozer.spec ─────────────────────────────────────────

if [[ ! -f "buildozer.spec" ]]; then
    echo "ERROR: buildozer.spec not found in current directory."
    echo "Run this script from the project root."
    exit 1
fi

echo "✓ buildozer.spec found"

# ─── Step 3: Check Android icon ───────────────────────────────────────────

if [[ ! -f "kivy_wallet/android_icon.png" ]]; then
    echo "WARNING: Android icon not found at kivy_wallet/android_icon.png"
    echo "Buildozer will use the default Kivy icon."
fi

# ─── Step 4: Build the APK ────────────────────────────────────────────────

echo ""
echo "Building Android APK..."
echo ""

if [[ "$BUILD_MODE" == "release" ]]; then
    # Release build requires a keystore
    if [[ -z "${ANDROID_KEYSTORE_PATH:-}" ]]; then
        echo "ERROR: Release build requires ANDROID_KEYSTORE_PATH environment variable."
        echo ""
        echo "To create a keystore:"
        echo "  keytool -genkey -v -keystore release-key.keystore -alias alias_name -keyalg RSA -keysize 2048 -validity 10000"
        echo ""
        echo "Then run:"
        echo "  export ANDROID_KEYSTORE_PATH=\$(pwd)/release-key.keystore"
        echo "  export ANDROID_KEYSTORE_PASSWORD=your_password"
        echo "  export ANDROID_KEY_ALIAS=alias_name"
        echo "  export ANDROID_KEY_PASSWORD=your_password"
        echo "  ./build-android.sh release"
        exit 1
    fi

    echo "Building release APK..."
    buildozer android release
else
    echo "Building debug APK..."
    buildozer android debug
fi

# ─── Step 5: Locate the APK ───────────────────────────────────────────────

echo ""
echo "========================================"
echo "  Build complete!"
echo "========================================"
echo ""

# Find the APK
APK_DIR="bin"
if [[ -d "$APK_DIR" ]]; then
    echo "APK location: ${APK_DIR}/"
    ls -lh "${APK_DIR}"/*.apk 2>/dev/null || echo "No APK files found in ${APK_DIR}/"
else
    echo "Build output directory not found. Check buildozer logs:"
    echo "  .buildozer/android/log/build-*.log"
fi

echo ""
echo "To install on a connected Android device:"
echo "  adb install bin/*.apk"
echo ""
echo "To run on a connected device:"
echo "  adb shell am start -n org.aetherion.aetherionexcal/.PythonActivity"
