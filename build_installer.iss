; ========================================================
; 千绘莉多功能工具箱 - 原生 Inno Setup 生产级安装包工程脚本 (build_installer.iss)
; 支持使用内置 Inno Setup 编译器组件一键打包
; ========================================================

[Setup]
AppId={{C3F719E8-5182-4EAE-A3C9-1234567890AB}}
AppName=千绘莉多功能工具箱
AppVersion=2.0.0
AppPublisher=Chieri
AppPublisherURL=https://github.com/chieri-toolbox
AppSupportURL=https://github.com/chieri-toolbox
AppUpdatesURL=https://github.com/chieri-toolbox
DefaultDirName={autopf}\ChieriToolbox
DefaultGroupName=千绘莉多功能工具箱
DisableProgramGroupPage=no
OutputDir=dist
OutputBaseFilename=Setup_ChieriToolbox
SetupIconFile=app_icon.ico
UninstallDisplayName=千绘莉多功能工具箱
UninstallDisplayIcon={app}\app_icon.ico
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "default"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式:"; Flags: checkedonce
Name: "autostart"; Description: "开机自动启动并在系统托盘常驻"; GroupDescription: "系统集成:"; Flags: unchecked

[Files]
Source: "dist\ChieriToolbox\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.log,*.tmp,*.m4s,*.bak,smoke_test_report.json,verified_*.png,toolbox_config.json,*.local.json,test_*.txt"

[Icons]
Name: "{group}\千绘莉多功能工具箱"; Filename: "{app}\ChieriToolbox.exe"; IconFilename: "{app}\app_icon.ico"; WorkingDir: "{app}"
Name: "{group}\卸载千绘莉多功能工具箱"; Filename: "{uninstallexe}"
Name: "{autodesktop}\千绘莉多功能工具箱"; Filename: "{app}\ChieriToolbox.exe"; IconFilename: "{app}\app_icon.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ChieriToolbox"; ValueData: """{app}\ChieriToolbox.exe"" --autostart"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\ChieriToolbox.exe"; Description: "立即运行千绘莉多功能工具箱"; Flags: postinstall nowait skipifsilent
