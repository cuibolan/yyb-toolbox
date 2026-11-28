; 安卓引擎工具箱 WinUI 版 —— Inno Setup 安装包脚本
; 编译：ISCC.exe YYBToolbox.iss
; 产物：dist\YYBToolbox_Setup_1.3.4.0.exe

#define MyAppName "安卓引擎工具箱"
#define MyAppVersion "1.3.4.0"
#define MyAppPublisher "YYB Toolbox"
#define MyAppExeName "YYBToolbox.WinUI.exe"
#define PublishDir "..\src\YYBToolbox.WinUI\bin\Release\net9.0-windows10.0.19041.0\win-x64\publish"

[Setup]
AppId={{066087B0-0A1C-4F6A-AE2E-20ECFF7C465A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\YYBToolbox
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=YYBToolbox_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标："

[Files]
; 自包含发布目录整体打包；排除运行期生成的配置/日志/截图/缓存/随包下载的 adb
Source: "{#PublishDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs; \
    Excludes: "config.json,startup.log,screenshots\*,cache\*,tools\*"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: "desktopicon"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
