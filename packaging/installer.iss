; GitHub-AI-Studio 安装包脚本（Inno Setup 6.7+）
; 编译：ISCC.exe packaging\installer.iss
; 产物：dist-release\Setup-GitHub-AI-Studio-1.0.0.exe
; 说明：按用户级安装（免管理员），默认目录 %LOCALAPPDATA%\Programs\GitHub-AI-Studio；
;      卸载时保留 {app}\data、{app}\.env、{app}\logs 等用户数据。

#define MyAppName "GitHub-AI-Studio"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Tsubasa-Kaede"
#define MyAppExeName "GitHub-AI-Studio.exe"

[Setup]
AppId={{6B9F2A31-58D4-4C7E-9A16-2E84F0C3D7B5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\dist-release
OutputBaseFilename=Setup-GitHub-AI-Studio-{#MyAppVersion}
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist-release\GitHub-AI-Studio.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\.env.example"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
