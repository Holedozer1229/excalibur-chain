# AetherionEXCAL — Multi-Platform Build Guide

This guide covers building the AetherionEXCAL wallet for **Windows**, **macOS**, **Android**, and **iOS**.

## Project Structure

```
excalibur-chain/
├── excal_wallet.py              # Desktop wallet (PySide6)
├── kivy_wallet/                 # Cross-platform mobile wallet (Kivy)
│   ├── __init__.py
│   ├── __main__.py              # Module entry point
│   ├── main.py                  # Main app with 7 screens
│   ├── rpc_client.py            # JSON-RPC client
│   ├── wallet_manager.py        # Wallet operations
│   ├── android_icon.png         # Android app icon (512x512)
│   └── ios_icon.png             # iOS app icon (1024x1024)
├── excalibur_wallet/            # Core wallet library
├── AetherionEXCAL.spec          # PyInstaller spec for desktop
├── AetherionEXCAL-installer.iss # Inno Setup script (Windows)
├── buildozer.spec               # Buildozer config (Android)
├── iosapp/
│   └── app.json                 # iOS app configuration
├── installer-icon.ico           # Windows installer icon
├── installer-bg.png             # macOS installer background
├── LICENSE
├── build-windows-installer.bat  # Windows build script
├── build-macos-installer.sh     # macOS build script
├── build-android.sh             # Android build script
└── build-ios.sh                 # iOS build script
```

---

## Windows Installer

### Prerequisites
- Python 3.10+
- PyInstaller: `pip install pyinstaller`
- Inno Setup 6+: [Download](https://jrsoftware.org/isdl.php)

### Build
```batch
build-windows-installer.bat
```

This script:
1. Builds `AetherionEXCAL.exe` (main wallet)
2. Builds `AetherionEXCAL-Beacon.exe` (SkyNet Beacon)
3. Builds `AetherionEXCAL-StratumMiner.exe` (Stratum Miner)
4. Builds `AetherionEXCAL-P2P.exe` (P2P Client)
5. Creates the installer via Inno Setup

### Output
- `installer\AetherionEXCAL-Setup-3.0.0.exe`

### Manual Build
```batch
pyinstaller --clean AetherionEXCAL.spec
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" AetherionEXCAL-installer.iss
```

---

## macOS Installer

### Prerequisites
- macOS with Xcode installed
- Xcode Command Line Tools: `xcode-select --install`
- Python 3.10+
- PyInstaller: `pip install pyinstaller`

### Build
```bash
chmod +x build-macos-installer.sh
./build-macos-installer.sh
```

This script:
1. Checks for `productbuild` (Xcode tools)
2. Builds `AetherionEXCAL.app` with PyInstaller
3. Stages the app bundle
4. Creates postinstall script
5. Creates distribution.xml and welcome page
6. Builds the `.pkg` installer

### Output
- `installer/AetherionEXCAL-Setup-3.0.0.pkg`

### Manual Build
```bash
pyinstaller --clean --windowed --name "AetherionEXCAL" excal_wallet.py
productbuild --distribution installer/distribution.xml \
    --resources installer \
    --package-path dist \
    installer/AetherionEXCAL-Setup-3.0.0.pkg
```

---

## Android App

### Prerequisites
- Linux (Ubuntu 20.04+ recommended) or macOS
- Python 3.10+
- Buildozer: `pip install buildozer`
- JDK 17+: `sudo apt install openjdk-17-jdk`
- System dependencies:
```bash
sudo apt install python3-pip build-essential git python3-dev \
    ffmpeg libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev \
    libsdl2-ttf-dev libportmidi-dev libswscale-dev libavformat-dev \
    libavcodec-dev zlib1g-dev libgstreamer1.0 gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good zip unzip openjdk-17-jdk wget curl
```

### Build Debug APK
```bash
chmod +x build-android.sh
./build-android.sh
```

### Build Release APK
```bash
# Create keystore first
keytool -genkey -v -keystore release-key.keystore \
    -alias alias_name -keyalg RSA -keysize 2048 -validity 10000

# Set environment variables
export ANDROID_KEYSTORE_PATH=$(pwd)/release-key.keystore
export ANDROID_KEYSTORE_PASSWORD=your_password
export ANDROID_KEY_ALIAS=alias_name
export ANDROID_KEY_PASSWORD=your_password

# Build
./build-android.sh release
```

### Output
- `bin/*.apk`

### Install on Device
```bash
adb install bin/*.apk
```

### Configuration
Edit `buildozer.spec` to customize:
- `title` — App display name
- `package.name` — Package name
- `package.domain` — Reverse domain
- `version` — App version
- `android.permissions` — Required permissions
- `android.icon` — Icon path

---

## iOS App

### Prerequisites
- macOS with Xcode installed
- Python 3.10+
- kivy-ios: `pip install kivy-ios`
- Xcode Command Line Tools: `xcode-select --install`
- CocoaPods: `sudo gem install cocoapods`
- Cython: `pip install cython`

### Build for Simulator
```bash
chmod +x build-ios.sh
./build-ios.sh
```

### Build for Device
```bash
./build-ios.sh device
```

### Build Archive (App Store)
```bash
./build-ios.sh archive
```

### Output
- `iosapp/AetherionEXCAL.xcarchive` (for App Store)
- Built app in Xcode DerivedData

### Configuration
Edit `iosapp/app.json` to customize:
- `title` — App display name
- `bundle` — Bundle identifier
- `package` — Package name
- `entry_point` — Python module entry point
- `modules` — Kivy modules to include

### App Store Distribution
```bash
xcodebuild -exportArchive \
    -archivePath iosapp/AetherionEXCAL.xcarchive \
    -exportPath ./export \
    -exportOptionsPlist ExportOptions.plist
```

---

## Mobile App Features

The Kivy wallet (`kivy_wallet/`) provides full-featured mobile access:

| Screen | Features |
|--------|----------|
| **Dashboard** | Chain height, mempool, peers, mining status |
| **Wallet** | Create/import wallet, view address, check balance |
| **Send** | Build and broadcast transactions |
| **Receive** | Show receive address |
| **Explorer** | Block and transaction browsing |
| **Locks** | HTLC, QHTLC lock operations |
| **Settings** | RPC endpoint, network selection |

### Architecture
- `rpc_client.py` — JSON-RPC client connecting to `node_rpc.py` (port 9432)
- `wallet_manager.py` — Local wallet operations (BIP-39, key derivation, tx building)
- `main.py` — Kivy UI with 7 screens and bottom tab navigation

### Running Locally
```bash
# Desktop testing
pip install kivy
python -m kivy_wallet

# Or directly
python kivy_wallet/main.py
```

---

## Version

All platforms target version **3.0.0**.

Update the version in these files when releasing:
- `AetherionEXCAL-installer.iss` — `#define AppVersion`
- `build-macos-installer.sh` — `APP_VERSION`
- `buildozer.spec` — `version`
- `build-ios.sh` — `APP_VERSION`
