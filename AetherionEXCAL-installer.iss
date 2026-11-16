; AetherionEXCAL Windows Installer
; Inno Setup script — creates desktop icon, start menu shortcut, and installs all components

#define AppName "AetherionEXCAL"
#define AppVersion "3.0.0"
#define AppPublisher "Aetherion Oracle"
#define AppURL "https://www.aetherion-oracle.com"
#define AppExeName "AetherionEXCAL.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\AetherionEXCAL
DefaultGroupName={#AppName}
OutputDir=installer
OutputBaseFilename=AetherionEXCAL-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=installer-icon.ico
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop Icon"; GroupDescription: "Shortcuts:"; Checked: true
Name: "quicklaunchicon"; Description: "Create a &Start Menu Icon"; GroupDescription: "Shortcuts:"; Checked: true
Name: "autostart"; Description: "Start &SkyNet Beacon on login"; GroupDescription: "Auto-start:"; Checked: false

[Files]
Source: "dist\AetherionEXCAL.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\AetherionEXCAL-Beacon.exe"; DestDir: "{app}"; Flags: ignoreversion; Components:beacon
Source: "dist\AetherionEXCAL-StratumMiner.exe"; DestDir: "{app}"; Flags: ignoreversion; Components:miner
Source: "dist\AetherionEXCAL-P2P.exe"; DestDir: "{app}"; Flags: ignoreversion; Components:p2p
Source: "start-beacon.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion; Components:docs

[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: quicklaunchicon
Name: "{group}\SkyNet Beacon"; Filename: "{app}\AetherionEXCAL-Beacon.exe"; Tasks: quicklaunchicon; Components:beacon
Name: "{group}\Stratum Miner"; Filename: "{app}\AetherionEXCAL-StratumMiner.exe"; Tasks: quicklaunchicon; Components:miner
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

[Registry]
Root: HKCU; Subkey: "Software\AetherionEXCAL"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\AetherionEXCAL"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"
Root: HKCU; Subkey: "Software\AetherionEXCAL"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\AetherionEXCAL-Beacon.exe"; Description: "Start SkyNet Beacon"; Flags: nowait postinstall; Components:beacon; Tasks:autostart

[Components]
Name: "main"; Description: "AetherionEXCAL Wallet"; Types: custom full; Flags: fixed
Name: "beacon"; Description: "SkyNet Beacon (always-on P2P node)"; Types: full
Name: "miner"; Description: "Stratum Miner (CPU/GPU mining)"; Types: full
Name: "p2p"; Description: "Node.js P2P Client"; Types: full
Name: "docs"; Description: "Documentation"; Types: full

[Code]
function ShouldSkipFile(filename: String): Boolean;
begin
  Result := False;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  beaconStartupPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Auto-start SkyNet Beacon if selected
    if IsTaskSelected('autostart') then
    begin
      beaconStartupPath := ExpandConstant('{userstartup}\AetherionEXCAL-Beacon.lnk');
      CreateShortcut(beaconStartupPath, ExpandConstant('{app}\AetherionEXCAL-Beacon.exe'), '', '', 0, '', '', 0, False);
    end;
  end;
end;
