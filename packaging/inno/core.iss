; Inno Setup script for Photo Intelligence (SDD §3.14/§12, TASK-098).
; Packages TASK-097's frozen build (packaging/pyinstaller/core.spec's
; output, dist/core) into a single Windows installer. Windows-only for v1;
; cross-platform packaging is v1.1 (TD-10).
;
; Build from the repo root, after producing dist/core via the PyInstaller
; spec:
;     ISCC.exe packaging\inno\core.iss

#define MyAppName "Photo Intelligence"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Photo Intelligence"
#define MyAppExeName "core.exe"
#define MyFrozenDistDir "..\..\dist\core"

[Setup]
AppId={{B5B6D6C1-6E3B-4B7B-9C7A-6E6F0B8D1A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=PhotoIntelligenceSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MyFrozenDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
