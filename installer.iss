#define MyAppName "Despectus"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "Despectus"
#define MyAppExeName "Despectus.exe"

[Setup]
AppId={{9B7B36E0-6C77-4C56-AE1B-8D0DAD2D88F1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_out
OutputBaseFilename=Despectus-Setup-1.0.1
Compression=lzma
SolidCompression=yes
SetupIconFile=assets\despectus.ico

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop icon"; GroupDescription: "Additional icons:"; Flags: checkedonce

[Dirs]
Name: "{userappdata}\Despectus"

[Files]
; Main app files (PyInstaller onedir output)
Source: "dist\Despectus\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

; Template config to AppData (only if not already there)
Source: "config_template\.env"; DestDir: "{userappdata}\Despectus"; DestName: ".env"; Flags: onlyifdoesntexist ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
