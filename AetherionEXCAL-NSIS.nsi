Unicode true
!include "MUI2.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "3.0.0"
!endif

Name "AetherionEXCAL ${APP_VERSION}"
OutFile "installer\AetherionEXCAL-Setup-${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\AetherionEXCAL"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64

!define MUI_ABORTWARNING
!define MUI_ICON "assets\aetherion-logo.ico"
!define MUI_UNICON "assets\aetherion-logo.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "AetherionEXCAL" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File "dist\AetherionEXCAL.exe"
  File "dist\AetherionEXCAL-Beacon.exe"
  File "dist\AetherionEXCAL-StratumMiner.exe"
  File "dist\AetherionEXCAL-P2P.exe"
  File "dist\AetherionEXCAL-AutonomousNode.exe"
  File "assets\aetherion-logo.ico"
  File "Start-IPFS.ps1"
  File "start-beacon.ps1"
  File "README.md"
  File "LICENSE"

  SetOutPath "$INSTDIR\ipfs"
  File "build\kubo\ipfs.exe"
  File /oname=KUBO-LICENSE "build\kubo\extract\kubo\LICENSE"
  File "build\kubo\extract\kubo\LICENSE-APACHE"
  File "build\kubo\extract\kubo\LICENSE-MIT"

  CreateDirectory "$SMPROGRAMS\AetherionEXCAL"
  CreateShortcut "$SMPROGRAMS\AetherionEXCAL\AetherionEXCAL.lnk" "$INSTDIR\AetherionEXCAL.exe" "" "$INSTDIR\aetherion-logo.ico"
  CreateShortcut "$SMPROGRAMS\AetherionEXCAL\SkyNet Beacon.lnk" "$INSTDIR\AetherionEXCAL-Beacon.exe"
  CreateShortcut "$SMPROGRAMS\AetherionEXCAL\Uninstall.lnk" "$INSTDIR\uninstall.exe"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\AetherionEXCAL" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\AetherionEXCAL" "Version" "${APP_VERSION}"
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\AetherionEXCAL\AetherionEXCAL.lnk"
  Delete "$SMPROGRAMS\AetherionEXCAL\SkyNet Beacon.lnk"
  Delete "$SMPROGRAMS\AetherionEXCAL\Uninstall.lnk"
  RMDir "$SMPROGRAMS\AetherionEXCAL"
  DeleteRegKey HKCU "Software\AetherionEXCAL"
  RMDir /r "$INSTDIR"
SectionEnd
