; Inno Setup 6 — compile after PyInstaller (dist\Mason exists).
; From repo root, with Inno on PATH:
;   ISCC packaging\windows\Mason.iss
; Or open this file in Inno Setup and Build → Compile.

#define MyAppName "Mason"
#define MyAppVersion "0.1.0"
#define MyPublisher "Mason"
; Paths are relative to this .iss file (packaging\windows\).
#define DistDir "..\..\dist\Mason"
#define IconPath "..\..\assets\icons\Mason.ico"

[Setup]
AppId={{E4B2F8A1-6C0D-4F3E-9B7A-1D2E3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\output\installer
OutputBaseFilename=Mason_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile={#IconPath}
UninstallDisplayIcon={app}\Mason.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\Mason.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Mason.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Mason.exe"; Description: "Launch Mason"; Flags: nowait postinstall skipifsilent
