#!/bin/bash
# AetherionEXCAL macOS Installer Package
# Creates a .pkg installer that places the app in /Applications and creates a Dock alias.
#
# Usage:
#   1. Build the app first: pyinstaller AetherionEXCAL.spec  (on macOS)
#   2. Run this script: bash build-macos-installer.sh
#
# This uses the standard macOS `productbuild` tool (Xcode Command Line Tools).
# No third-party dependencies required.

set -euo pipefail

APP_NAME="AetherionEXCAL"
APP_VERSION="3.0.0"
DIST_DIR="dist"
INSTALLER_DIR="installer"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"

echo "========================================"
echo "  ${APP_NAME} macOS Installer Builder"
echo "  Version ${APP_VERSION}"
echo "========================================"

# ─── Step 1: Check prerequisites ──────────────────────────────────────────

if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: This script must be run on macOS."
    exit 1
fi

if ! command -v productbuild &> /dev/null; then
    echo "ERROR: productbuild not found. Install Xcode Command Line Tools:"
    echo "  xcode-select --install"
    exit 1
fi

# ─── Step 2: Build the .app bundle if not already built ────────────────────

if [[ ! -d "$APP_BUNDLE" ]]; then
    echo ""
    echo "Building ${APP_NAME}.app with PyInstaller..."
    pyinstaller --clean --windowed --name "${APP_NAME}" \
        --add-data "sphinx_os:sphinx_os" \
        --hidden-import=sphinx_os.nexus.quantum_spacetime \
        --hidden-import=sphinx_os.nexus.conscious_consensus \
        --hidden-import=sphinx_os.nexus.holographic_p2p \
        --hidden-import=sphinx_os.nexus.self_organizing_treasury \
        --hidden-import=sphinx_os.nexus.bonding_curve \
        --hidden-import=sphinx_os.nexus.zksync_bridge \
        --hidden-import=sphinx_os.nexus.btc_bridge \
        --hidden-import=sphinx_os.nexus.atomic_swap \
        --hidden-import=sphinx_os.nexus.knights_round_table \
        --hidden-import=sphinx_os.nexus.musig2 \
        --hidden-import=sphinx_os.nexus.frost \
        --hidden-import=sphinx_os.nexus.frostgate_python \
        --hidden-import=sphinx_os.nexus.ai_oracle_knight \
        --hidden-import=sphinx_os.nexus.knight_nft \
        --hidden-import=sphinx_os.nexus.orchestrator \
        --hidden-import=sphinx_os.nexus.erepr_protocol \
        --hidden-import=sphinx_os.nexus.opensql \
        --hidden-import=sphinx_os.nexus.genesis_vault \
        --hidden-import=skynet_beacon \
        --hidden-import=skynet_client \
        --hidden-import=p2p_layer \
        --hidden-import=fork_node \
        --hidden-import=genesis_fork \
        --hidden-import=secp256k1 \
        --hidden-import=txscript \
        --hidden-import=utxodb \
        --hidden-import=wallet_crypto \
        --hidden-import=cryptography \
        --hidden-import=prometheus_client \
        --hidden-import=numpy \
        --hidden-import=PIL \
        --hidden-import=PySide6.QtCharts \
        --hidden-import=desktop_shortcut \
        excal_wallet.py
fi

if [[ ! -d "$APP_BUNDLE" ]]; then
    echo "ERROR: ${APP_NAME}.app not found in ${DIST_DIR}/"
    echo "Build it first with: pyinstaller AetherionEXCAL.spec"
    exit 1
fi

echo "✓ Found ${APP_NAME}.app"

# ─── Step 3: Create installer staging directory ────────────────────────────

STAGING="${INSTALLER_DIR}/staging"
rm -rf "$STAGING"
mkdir -p "${STAGING}/Applications"
cp -R "$APP_BUNDLE" "${STAGING}/Applications/"

echo "✓ Staged app bundle"

# ─── Step 4: Create postinstall script (creates Dock alias) ────────────────

POSTINSTALL="${INSTALLER_DIR}/postinstall"
cat > "$POSTINSTALL" << 'POSTINSTALL_EOF'
#!/bin/bash
# Post-installation script for AetherionEXCAL
# Creates a Dock alias and launches the app on first run

APP_NAME="AetherionEXCAL"
APP_PATH="/Applications/${APP_NAME}.app"

# Create Dock alias by adding to Login Items (macOS 10.15+)
# This is done via the app's first-run mechanism instead

# Set proper permissions
chmod -R 755 "$APP_PATH"

# Create first-run marker removal (so desktop shortcut logic runs)
rm -f "$HOME/.excal_wallet/.desktop_shortcuts_created"

echo "AetherionEXCAL installed successfully to /Applications/"
exit 0
POSTINSTALL_EOF

chmod +x "$POSTINSTALL"
echo "✓ Created postinstall script"

# ─── Step 5: Create distribution.xml ───────────────────────────────────────

DISTRIBUTION="${INSTALLER_DIR}/distribution.xml"
cat > "$DISTRIBUTION" << DIST_EOF
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">
    <title>AetherionEXCAL ${APP_VERSION}</title>
    <background file="installer-bg.png" scaling="proportional"/>
    <background-darkAqua file="installer-bg.png" scaling="proportional"/>
    <domains enable_anywhere="false" enable_currentUserHome="false" enable_localSystem="true"/>
    <adminSettings allow-external-scripts="no"/>
    
    <welcome file="welcome.html"/>
    <license file="LICENSE"/>
    
    <options customize="never" require-scripts="false" hostArchitectures="universal,x86_64,arm64"/>
    
    <pkg-ref id="com.aetherion.excal.wallet"/>
</installer-gui-script>
DIST_EOF

echo "✓ Created distribution.xml"

# ─── Step 6: Create welcome page ───────────────────────────────────────────

WELCOME="${INSTALLER_DIR}/welcome.html"
cat > "$WELCOME" << 'WELCOME_EOF'
<!DOCTYPE html>
<html>
<head>
    <style>
        body {
            background: #0a0a1a;
            color: #FFFFFF;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
            text-align: center;
        }
        h1 {
            color: #FFD700;
            font-size: 48px;
            margin-bottom: 10px;
            text-shadow: 0 0 20px rgba(255, 215, 0, 0.5);
        }
        h2 {
            color: #00E5FF;
            font-size: 24px;
            margin-bottom: 30px;
        }
        p {
            color: #B0B0D0;
            font-size: 16px;
            max-width: 500px;
            line-height: 1.6;
        }
        .features {
            margin-top: 30px;
            text-align: left;
        }
        .features li {
            color: #B0B0D0;
            margin: 8px 0;
            font-size: 14px;
        }
        .features li::marker {
            color: #FFD700;
        }
    </style>
</head>
<body>
    <h1>AETHERION</h1>
    <h2>EXCAL — Quantum Oracle P2P Wallet</h2>
    <p>Welcome to the future of decentralized finance. Install AetherionEXCAL to access the SkyNet P2P network.</p>
    <ul class="features">
        <li>Quantum-resistant FROST threshold signing</li>
        <li>SkyNet P2P with EREPR protocol</li>
        <li>BTC Taproot bridge &amp; atomic swaps</li>
        <li>Knights of the Round Table governance</li>
        <li>zkSync Era URUU bonding curve</li>
        <li>CPU/GPU mining with stratum server</li>
    </ul>
    <p style="margin-top: 30px; font-size: 12px; color: #6060A0;">
        www.aetherion-oracle.com
    </p>
</body>
</html>
WELCOME_EOF

echo "✓ Created welcome page"

# ─── Step 7: Build the .pkg installer ──────────────────────────────────────

OUTPUT_PKG="${INSTALLER_DIR}/${APP_NAME}-Setup-${APP_VERSION}.pkg"

productbuild \
    --distribution "$DISTRIBUTION" \
    --resources "$INSTALLER_DIR" \
    --package-path "$STAGING/Applications" \
    --sign "-" \
    "$OUTPUT_PKG" 2>/dev/null || \
productbuild \
    --distribution "$DISTRIBUTION" \
    --resources "$INSTALLER_DIR" \
    --package-path "$STAGING/Applications" \
    "$OUTPUT_PKG"

if [[ -f "$OUTPUT_PKG" ]]; then
    SIZE=$(du -h "$OUTPUT_PKG" | cut -f1)
    echo ""
    echo "========================================"
    echo "  ✓ Installer built successfully!"
    echo "  ${OUTPUT_PKG}"
    echo "  Size: ${SIZE}"
    echo "========================================"
    echo ""
    echo "To install: open ${OUTPUT_PKG}"
    echo "The app will be placed in /Applications/"
else
    echo "ERROR: Failed to build installer"
    exit 1
fi

# ─── Step 8: Clean up staging ──────────────────────────────────────────────

rm -rf "$STAGING"
echo "✓ Cleaned up staging directory"
