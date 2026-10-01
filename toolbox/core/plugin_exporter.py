"""
千绘莉多功能工具箱 (Chieri Toolbox) - 独立插件 Setup 安装包与应用导出引擎 (PluginExporter)
支持将 22 个功能模块中的任意插件一键导出为独立应用包 / Setup 安装包。
导出包自带专属独立设置接口、开机自启集成、独立托盘快捷栏及桌面快捷方式安装向导。
"""

import os
import sys
import shutil
import zipfile
import subprocess
from typing import Dict, Any, Optional, List
from toolbox.core.paths import get_app_root, get_bundle_dir, get_bin_dir, get_bin_path
from toolbox.core.plugin_manager import PluginManager


class PluginExporter:
    """
    独立插件安装包与便携包生成引擎 (支持原生 Inno Setup EXE 安装包与绿色便携包)
    """

    @staticmethod
    def find_iscc_executable() -> Optional[str]:
        """
        智能搜寻系统中的 Inno Setup 编译器可执行文件 (ISCC.exe)
        优先使用工程或应用内置的便携版编译器 (bin/InnoSetup/ISCC.exe)，
        若未内置则自适应探测 LocalAppData, ProgramFiles, PATH 环境变量以及 Windows 注册表。
        """
        candidates = [
            os.path.join(get_bin_dir(), "InnoSetup", "ISCC.exe"),
            os.path.join(get_app_root(), "bin", "InnoSetup", "ISCC.exe"),
            os.path.join(get_bundle_dir(), "bin", "InnoSetup", "ISCC.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
            os.path.expandvars(r"%ProgramFiles%\Inno Setup 6\ISCC.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"),
            os.path.expandvars(r"%ProgramFiles%\Inno Setup 5\ISCC.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"),
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
        ]
        for c in candidates:
            if c and os.path.isfile(c):
                return os.path.normpath(c)

        which_iscc = shutil.which("ISCC.exe") or shutil.which("iscc")
        if which_iscc:
            return os.path.normpath(which_iscc)

        try:
            import winreg
            for root_key in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for subkey in (
                    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
                    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 5_is1",
                    r"Software\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe",
                ):
                    try:
                        with winreg.OpenKey(root_key, subkey) as k:
                            try:
                                loc, _ = winreg.QueryValueEx(k, "InstallLocation")
                                iscc = os.path.join(loc, "ISCC.exe")
                                if os.path.isfile(iscc):
                                    return os.path.normpath(iscc)
                            except OSError:
                                pass
                            try:
                                val, _ = winreg.QueryValueEx(k, "")
                                if os.path.isfile(val):
                                    return os.path.normpath(val)
                            except OSError:
                                pass
                    except OSError:
                        pass
        except Exception:
            pass

        return None

    @classmethod
    def generate_inno_setup_iss(
        cls,
        plugin,
        target_dir: str,
        output_dir: str,
        autostart_default: bool = False,
        ico_path: Optional[str] = None
    ) -> str:
        """
        生成适用于 Inno Setup 编译器的 .iss 原生安装工程脚本
        """
        import hashlib
        plugin_id = plugin.id
        plugin_name = plugin.name
        plugin_ver = getattr(plugin, "version", "1.0.0") or "1.0.0"
        h = hashlib.md5(f"chieri_{plugin_id}".encode()).hexdigest().upper()
        app_guid = f"{{{{CHIERI-{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}}}}}"

        norm_target = os.path.abspath(target_dir)
        norm_output = os.path.abspath(output_dir)

        if not ico_path and hasattr(plugin, "get_ico_path"):
            cand_ico = plugin.get_ico_path()
            if cand_ico and os.path.isfile(cand_ico):
                ico_path = os.path.abspath(cand_ico)
        if not ico_path:
            cand_ico = os.path.join(norm_target, "app_icon.ico")
            if os.path.isfile(cand_ico):
                ico_path = os.path.abspath(cand_ico)
        if ico_path:
            ico_path = os.path.abspath(ico_path)

        icon_setup = f'SetupIconFile="{ico_path}"\n' if ico_path and os.path.isfile(ico_path) else ''
        icon_uninst = 'UninstallDisplayIcon="{app}\\app_icon.ico"\n' if ico_path and os.path.isfile(ico_path) else ''
        autostart_flag = 'Flags: unchecked' if not autostart_default else ''

        iss = f"""; ========================================================
; 千绘莉多功能工具箱 - 独立插件原生 Inno Setup 安装包工程脚本
; 插件名称: {plugin_name}
; 插件ID: {plugin_id}
; ========================================================

[Setup]
AppId={app_guid}
AppName={plugin_name}
AppVersion={plugin_ver}
AppPublisher=Chieri
AppPublisherURL=https://github.com/chieri-toolbox
AppSupportURL=https://github.com/chieri-toolbox
AppUpdatesURL=https://github.com/chieri-toolbox
DefaultDirName={{autopf}}\\ChieriPlugins\\{plugin_name}
DefaultGroupName=千绘莉独立应用
DisableProgramGroupPage=yes
OutputDir={norm_output}
OutputBaseFilename=Setup_{plugin_id}
{icon_setup}{icon_uninst}UninstallDisplayName={plugin_name} (千绘莉独立版)
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "default"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式:"; Flags: checkedonce
Name: "autostart"; Description: "开机自动启动并在系统托盘常驻"; GroupDescription: "系统集成:"; {autostart_flag}

[Files]
Source: "{norm_target}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.iss,compile_setup.bat"

[Icons]
Name: "{{group}}\\{plugin_name}"; Filename: "{{app}}\\launch.bat"; IconFilename: "{{app}}\\app_icon.ico"; WorkingDir: "{{app}}"
Name: "{{autodesktop}}\\{plugin_name}"; Filename: "{{app}}\\launch.bat"; IconFilename: "{{app}}\\app_icon.ico"; WorkingDir: "{{app}}"; Tasks: desktopicon
Name: "{{group}}\\卸载 {plugin_name}"; Filename: "{{uninstallexe}}"

[Registry]
Root: HKCU; Subkey: "Software\\Microsoft\\Windows\\CurrentVersion\\Run"; ValueType: string; ValueName: "ChieriPlugin_{plugin_id}"; ValueData: \"\"\"wscript.exe\"\" \"\"{{app}}\\launch.vbs\"\" --autostart\"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{{app}}\\launch.bat"; Description: "立即启动 {plugin_name}"; Flags: shellexec postinstall nowait skipifsilent
"""
        return iss

    @classmethod
    def export_plugin(
        cls,
        plugin_id: str,
        output_dir: str,
        package_type: str = "setup",  # 'setup' 或 'portable'
        create_shortcuts: bool = True,
        autostart_default: bool = False,
        create_archive: bool = True,
        generate_pyinstaller_spec: bool = True,
        compile_inno_setup: bool = True,
    ) -> Dict[str, Any]:
        """
        导出指定插件为独立应用包或 Setup 安装包 (原生 Inno Setup EXE)。
        """
        app_root = get_app_root()
        bundle_dir = get_bundle_dir()
        pm = PluginManager()
        pm.discover_and_load()
        plugin = pm.get_plugin(plugin_id)
        if not plugin:
            return {"success": False, "error": f"未能找到插件 [{plugin_id}]"}

        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        bundle_name = f"ChieriPlugin_{plugin_id}"
        target_dir = os.path.abspath(os.path.join(output_dir, bundle_name))
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir, ignore_errors=True)
        os.makedirs(target_dir, exist_ok=True)

        exported_files = []

        try:
            # 1. 复制必要的 toolbox 核心源码模块
            tb_target = os.path.join(target_dir, "toolbox")
            os.makedirs(tb_target, exist_ok=True)

            source_tb = None
            for cand in [
                os.path.join(bundle_dir, "toolbox"),
                os.path.join(app_root, "toolbox"),
                os.path.join(bundle_dir, "_internal", "toolbox"),
                os.path.join(app_root, "_internal", "toolbox"),
            ]:
                if os.path.isdir(os.path.join(cand, "core")):
                    source_tb = cand
                    break
            if not source_tb:
                source_tb = os.path.join(app_root, "toolbox")

            # 复制 __init__.py, standalone_runner.py, app.py
            for py_file in ["__init__.py", "standalone_runner.py", "app.py"]:
                src_f = os.path.join(source_tb, py_file)
                if os.path.isfile(src_f):
                    shutil.copy2(src_f, os.path.join(tb_target, py_file))

            # 复制 core
            src_core = os.path.join(source_tb, "core")
            if os.path.isdir(src_core):
                shutil.copytree(
                    src_core,
                    os.path.join(tb_target, "core"),
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
                )

            # 复制 ui
            src_ui = os.path.join(source_tb, "ui")
            if os.path.isdir(src_ui):
                shutil.copytree(
                    src_ui,
                    os.path.join(tb_target, "ui"),
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
                )

            # 复制当前插件目录
            plugin_src_dir = os.path.join(source_tb, "plugins", plugin_id)
            if not os.path.isdir(plugin_src_dir):
                for p_base in [bundle_dir, app_root, os.path.join(bundle_dir, "_internal"), os.path.join(app_root, "_internal")]:
                    cand_p = os.path.join(p_base, "toolbox", "plugins", plugin_id)
                    if os.path.isdir(cand_p):
                        plugin_src_dir = cand_p
                        break

            plugin_target_dir = os.path.join(tb_target, "plugins", plugin_id)
            if os.path.exists(plugin_src_dir):
                shutil.copytree(
                    plugin_src_dir,
                    plugin_target_dir,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
                )

            # 插件包 __init__.py
            with open(os.path.join(tb_target, "plugins", "__init__.py"), "w", encoding="utf-8") as f:
                f.write(f"# Standalone plugin package for {plugin_id}\n")

            # 2. 拷贝该插件专属独立图标 (优先使用插件独立生成的 icon.ico 与 icon.png)
            plugin_ico = plugin.get_ico_path() if hasattr(plugin, "get_ico_path") else None
            plugin_png = plugin.get_icon_path() if hasattr(plugin, "get_icon_path") else None

            # 拷贝独立 ICO 为 app_icon.ico 及 icon.ico
            if plugin_ico and os.path.isfile(plugin_ico):
                shutil.copy2(plugin_ico, os.path.join(target_dir, "app_icon.ico"))
                shutil.copy2(plugin_ico, os.path.join(target_dir, "icon.ico"))
            else:
                for base in [bundle_dir, app_root, os.path.join(bundle_dir, "_internal"), os.path.join(app_root, "_internal")]:
                    cand = os.path.join(base, "app_icon.ico")
                    if os.path.isfile(cand):
                        shutil.copy2(cand, os.path.join(target_dir, "app_icon.ico"))
                        break

            # 拷贝独立 PNG 为 app_icon.png 及 icon.png
            if plugin_png and os.path.isfile(plugin_png):
                shutil.copy2(plugin_png, os.path.join(target_dir, "app_icon.png"))
                shutil.copy2(plugin_png, os.path.join(target_dir, "icon.png"))
            else:
                for base in [bundle_dir, app_root, os.path.join(bundle_dir, "_internal"), os.path.join(app_root, "_internal")]:
                    cand = os.path.join(base, "app_icon.png")
                    if os.path.isfile(cand):
                        shutil.copy2(cand, os.path.join(target_dir, "app_icon.png"))
                        break

            # 3. 智能关联并复制所需的二进制依赖 (FFmpeg, 7-Zip 等)
            bin_target = os.path.join(target_dir, "bin")
            os.makedirs(bin_target, exist_ok=True)
            media_plugins = {"media_downloader", "youtube_downloader", "screen_recorder", "video_to_audio", "audio_converter", "audio_cutter", "media_compressor", "frame_extractor", "audio_recorder"}
            archive_plugins = {"archive_manager"}
            if plugin_id in media_plugins:
                for b_tool in ["ffmpeg.exe", "ffprobe.exe", "ffplay.exe"]:
                    b_file = get_bin_path(b_tool)
                    if b_file and os.path.isfile(b_file):
                        shutil.copy2(b_file, os.path.join(bin_target, b_tool))
            if plugin_id in archive_plugins:
                for b_tool in ["7z.exe", "7z.dll"]:
                    b_file = get_bin_path(b_tool)
                    if b_file and os.path.isfile(b_file):
                        shutil.copy2(b_file, os.path.join(bin_target, b_tool))

            # 4. 生成独立应用直达启动入口 standalone_entry.py
            entry_code = f'''"""
千绘莉工具箱 - 「{plugin.name}」独立启动入口
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from toolbox.standalone_runner import launch_standalone

if __name__ == "__main__":
    autostart = "--autostart" in sys.argv
    paths = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    sys.exit(launch_standalone("{plugin_id}", autostart=autostart, initial_paths=paths))
'''
            entry_path = os.path.join(target_dir, "standalone_entry.py")
            with open(entry_path, "w", encoding="utf-8") as f:
                f.write(entry_code)
            exported_files.append(entry_path)

            # 5. 生成 launch.pyw (无控制台启动脚本)
            launch_pyw_code = f'''# -*- coding: utf-8 -*-
import os, sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from toolbox.standalone_runner import launch_standalone

if __name__ == "__main__":
    autostart = "--autostart" in sys.argv
    paths = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    sys.exit(launch_standalone("{plugin_id}", autostart=autostart, initial_paths=paths))
'''
            pyw_path = os.path.join(target_dir, "launch.pyw")
            with open(pyw_path, "w", encoding="utf-8") as f:
                f.write(launch_pyw_code)
            exported_files.append(pyw_path)

            # 6. 生成 launch.bat (快速命令行启动批处理)
            py_exe_cur = sys.executable
            pyw_exe_cur = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            launch_bat_code = f'''@echo off
chcp 65001 >nul
title 正在启动 {plugin.name}...
cd /d "%~dp0"
if exist "%~dp0{plugin.name}.exe" (
    start "" "%~dp0{plugin.name}.exe" %*
    exit /b 0
)
if exist "%~dp0{plugin_id}.exe" (
    start "" "%~dp0{plugin_id}.exe" %*
    exit /b 0
)
if exist "%~dp0dist\\{plugin.name}.exe" (
    start "" "%~dp0dist\\{plugin.name}.exe" %*
    exit /b 0
)
if exist "%~dp0dist\\{plugin_id}.exe" (
    start "" "%~dp0dist\\{plugin_id}.exe" %*
    exit /b 0
)
if exist "{pyw_exe_cur}" (
    start "" "{pyw_exe_cur}" "%~dp0standalone_entry.py" %*
    exit /b 0
)
if exist "{py_exe_cur}" (
    start "" "{py_exe_cur}" "%~dp0standalone_entry.py" %*
    exit /b 0
)
if exist "%~dp0..\..\.venv\Scripts\pythonw.exe" (
    start "" "%~dp0..\..\.venv\Scripts\pythonw.exe" "%~dp0standalone_entry.py" %*
    exit /b 0
)
if exist "%~dp0..\.venv\Scripts\pythonw.exe" (
    start "" "%~dp0..\.venv\Scripts\pythonw.exe" "%~dp0standalone_entry.py" %*
    exit /b 0
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0standalone_entry.py" %*
    exit /b 0
)
where pythonw >nul 2>nul
if %errorlevel% equ 0 (
    start "" pythonw "%~dp0standalone_entry.py" %*
    exit /b 0
)
python "%~dp0standalone_entry.py" %*
'''
            bat_path = os.path.join(target_dir, "launch.bat")
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(launch_bat_code)
            exported_files.append(bat_path)

            # 6.1 生成 launch.vbs (原生隐形启动脚本，杜绝开机自启与快捷方式弹窗闪烁)
            launch_vbs_code = '''Set WshShell = CreateObject("WScript.Shell")
args = ""
For i = 0 To WScript.Arguments.Count - 1
    args = args & " """ & WScript.Arguments(i) & """"
Next
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "cmd /c """"" & scriptDir & "\\launch.bat""" & args & """", 0, False
'''
            vbs_path = os.path.join(target_dir, "launch.vbs")
            with open(vbs_path, "w", encoding="utf-8") as f:
                f.write(launch_vbs_code)
            exported_files.append(vbs_path)

            # 7. 生成 setup.bat 与 installer.py 安装向导 (当为 setup 模式或默认包含)
            installer_template = '''"""
千绘莉工具箱 - 「__PLUGIN_NAME__」独立安装向导
"""
import os
import sys
import shutil
import subprocess
import winreg

PLUGIN_ID = "__PLUGIN_ID__"
PLUGIN_NAME = "__PLUGIN_NAME__"
APP_DIR = os.path.dirname(os.path.abspath(__file__))

def create_shortcut(target, shortcut_path, icon_path=None, description=""):
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.TargetPath = str(target)
        shortcut.WorkingDirectory = str(os.path.dirname(target))
        shortcut.Description = str(description)
        if icon_path and os.path.exists(icon_path):
            shortcut.IconLocation = str(icon_path)
        shortcut.save()
        return True
    except Exception:
        pass

    # 降级使用 PowerShell COM 接口生成快捷方式 (原生支持 Unicode 与中文路径)
    try:
        ps_cmd = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$s = $ws.CreateShortcut(\\'{shortcut_path}\\'); '
            f'$s.TargetPath = \\'{target}\\'; '
            f'$s.WorkingDirectory = \\'{os.path.dirname(target)}\\'; '
            f'$s.Description = \\'{description}\\'; '
        )
        if icon_path and os.path.exists(icon_path):
            ps_cmd += f'$s.IconLocation = \\'{icon_path}\\'; '
        ps_cmd += '$s.Save()'
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd], check=True, capture_output=True)
        return True
    except Exception:
        pass
    return False

def install(install_to=None, create_desktop=True, create_startmenu=True, autostart=__AUTOSTART_DEFAULT__):
    print("=" * 60)
    print(f"正在安装: {PLUGIN_NAME} 独立应用")
    print("=" * 60)

    if not install_to:
        local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        install_to = os.path.join(local_app, "ChieriPlugins", PLUGIN_ID)

    os.makedirs(install_to, exist_ok=True)
    print(f"[1/4] 复制程序文件至: {install_to}...")
    
    # 递归拷贝自身目录内容 (排除自身如果已在目标位置)
    if os.path.normpath(APP_DIR).lower() != os.path.normpath(install_to).lower():
        for item in os.listdir(APP_DIR):
            s = os.path.join(APP_DIR, item)
            d = os.path.join(install_to, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

    target_bat = os.path.join(install_to, "launch.bat")
    ico_path = os.path.join(install_to, "app_icon.ico")

    # 快捷方式生成
    if create_desktop:
        desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        if os.path.exists(desktop):
            sc_path = os.path.join(desktop, f"{PLUGIN_NAME}.lnk")
            print(f"[2/4] 创建桌面快捷方式: {sc_path}...")
            create_shortcut(target_bat, sc_path, icon_path=ico_path, description=f"{PLUGIN_NAME} 独立版")

    if create_startmenu:
        start_menu = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\\Windows\\Start Menu\\Programs"
        )
        if os.path.exists(start_menu):
            sm_dir = os.path.join(start_menu, "千绘莉独立应用")
            os.makedirs(sm_dir, exist_ok=True)
            sc_path = os.path.join(sm_dir, f"{PLUGIN_NAME}.lnk")
            print(f"[3/4] 创建开始菜单快捷方式: {sc_path}...")
            create_shortcut(target_bat, sc_path, icon_path=ico_path, description=f"{PLUGIN_NAME} 独立版")

    if autostart:
        print("[4/4] 注册系统开机自启动...")
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\\Microsoft\\Windows\\CurrentVersion\\Run",
                0,
                winreg.KEY_ALL_ACCESS
            )
            winreg.SetValueEx(key, f"ChieriPlugin_{PLUGIN_ID}", 0, winreg.REG_SZ, f'"{target_bat}" --autostart')
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[-] 注册自启异常: {e}")

    print("\\n[+] 安装完成！您可以随时从桌面快捷方式启动该独立工具。")

if __name__ == "__main__":
    install()
'''
            installer_py_code = (
                installer_template
                .replace("__PLUGIN_ID__", plugin_id)
                .replace("__PLUGIN_NAME__", plugin.name)
                .replace("__AUTOSTART_DEFAULT__", str(autostart_default))
            )
            installer_path = os.path.join(target_dir, "installer.py")
            with open(installer_path, "w", encoding="utf-8") as f:
                f.write(installer_py_code)
            exported_files.append(installer_path)

            setup_bat_code = f'''@echo off
chcp 65001 >nul
title {plugin.name} - 安装程序
cd /d "%~dp0"
echo ======================================================
echo    {plugin.name} - 独立应用安装程序
echo ======================================================
echo.
set "PY_BIN="
if exist "{py_exe_cur}" set "PY_BIN={py_exe_cur}"
if not defined PY_BIN (
    if exist "%~dp0..\..\.venv\Scripts\python.exe" set "PY_BIN=%~dp0..\..\.venv\Scripts\python.exe"
)
if not defined PY_BIN (
    if exist "%~dp0..\.venv\Scripts\python.exe" set "PY_BIN=%~dp0..\.venv\Scripts\python.exe"
)
if not defined PY_BIN (
    where python >nul 2>nul
    if %errorlevel% equ 0 set "PY_BIN=python"
)
if defined PY_BIN (
    "%PY_BIN%" "%~dp0installer.py"
) else (
    python "%~dp0installer.py"
)
echo.
echo 安装已执行完毕。
set /p launch_now=是否立即启动 {plugin.name}？(Y/N): 
if /i "%launch_now%"=="Y" (
    call "%~dp0launch.bat"
)
'''
            setup_bat_path = os.path.join(target_dir, "setup.bat")
            with open(setup_bat_path, "w", encoding="utf-8") as f:
                f.write(setup_bat_code)
            exported_files.append(setup_bat_path)

            # 8. 生成 uninstall.bat 卸载脚本
            uninstall_bat_code = f'''@echo off
chcp 65001 >nul
title 卸载 {plugin.name}
echo 正在卸载 {plugin.name}...

:: 删除快捷方式
del /f /q "%USERPROFILE%\\Desktop\\{plugin.name}.lnk" 2>nul
del /f /q "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\千绘莉独立应用\\{plugin.name}.lnk" 2>nul

:: 注销自启
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "ChieriPlugin_{plugin_id}" /f >nul 2>nul

echo 快捷方式与注册表已清理完毕。若需完全删除程序文件，请手动删除本目录。
pause
'''
            uninstall_path = os.path.join(target_dir, "uninstall.bat")
            with open(uninstall_path, "w", encoding="utf-8") as f:
                f.write(uninstall_bat_code)
            exported_files.append(uninstall_path)

            # 9. 生成 PyInstaller spec 编译规范文件与一键构建批处理
            if generate_pyinstaller_spec:
                # 动态收集 hiddenimports
                hidden_imports = [
                    'toolbox.core.plugin_base',
                    'toolbox.core.config_manager',
                    'toolbox.core.plugin_manager',
                    'toolbox.core.theme',
                    'toolbox.core.paths',
                    'toolbox.core.media_engine',
                    'toolbox.core.window_effects',
                    'toolbox.core.tray_manager',
                    'toolbox.ui.icons',
                    'toolbox.ui.standalone_settings_dialog',
                ]

                # 扫描插件目录下全部 py 模块加入 hiddenimports
                if os.path.exists(plugin_target_dir):
                    for root, _, files in os.walk(plugin_target_dir):
                        for file in files:
                            if file.endswith(".py"):
                                rel_p = os.path.relpath(os.path.join(root, file), target_dir)
                                mod_path = os.path.splitext(rel_p)[0].replace("\\", "/").replace("/", ".")
                                if mod_path.endswith(".__init__"):
                                    mod_path = mod_path[:-9]
                                if mod_path and mod_path not in hidden_imports:
                                    hidden_imports.append(mod_path)

                # 针对第三方依赖补充
                third_party_deps = {
                    "ncm_decryptor": ["mutagen", "Crypto"],
                    "archive_manager": ["lz4", "lz4.frame"],
                    "image_master": ["PIL"],
                    "media_compressor": ["PIL"],
                    "frame_extractor": ["PIL"],
                    "media_downloader": ["requests"],
                    "youtube_downloader": ["yt_dlp"],
                    "translator": ["requests"],
                    "webdav_config": ["requests", "pyperclip"],
                    "screen_capture": ["PIL"],
                    "auto_input": ["keyboard", "pyperclip"],
                }
                for dep in third_party_deps.get(plugin_id, []):
                    if dep not in hidden_imports:
                        hidden_imports.append(dep)

                # 拷贝 rthook_pyside6_fix.py 至 target_dir
                rthook_filename = "rthook_pyside6_fix.py"
                rthook_target = os.path.join(target_dir, rthook_filename)
                rthook_found = False
                for r_base in [bundle_dir, app_root, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))]:
                    cand_rthook = os.path.join(r_base, rthook_filename)
                    if os.path.isfile(cand_rthook):
                        shutil.copy2(cand_rthook, rthook_target)
                        rthook_found = True
                        break
                if not rthook_found:
                    rthook_content = '''import os, sys
if sys.platform == "win32":
    bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    app_root = os.path.dirname(os.path.abspath(sys.executable))
    bases = [bundle_dir, app_root, os.path.join(app_root, "_internal")]
    for base in bases:
        for sub in ["", "PySide6", "shiboken6", "bin"]:
            dll_dir = os.path.join(base, sub)
            if os.path.isdir(dll_dir):
                try:
                    os.add_dll_directory(dll_dir)
                except Exception:
                    pass
'''
                    with open(rthook_target, "w", encoding="utf-8") as f:
                        f.write(rthook_content)
                exported_files.append(rthook_target)

                runtime_hooks_list = ["'rthook_pyside6_fix.py'"]
                hidden_imports_str = ",\n        ".join(f"'{h}'" for h in hidden_imports)
                runtime_hooks_str = ", ".join(runtime_hooks_list)

                spec_code = f'''# -*- mode: python ; coding: utf-8 -*-
import os, sys

block_cipher = None

a = Analysis(
    ['standalone_entry.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('app_icon.ico', '.'),
        ('app_icon.png', '.'),
        ('bin', 'bin'),
    ],
    hiddenimports=[
        {hidden_imports_str}
    ],
    hookspath=[],
    runtime_hooks=[{runtime_hooks_str}],
    excludes=['matplotlib', 'scipy', 'tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='{plugin.name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='app_icon.ico'
)
'''
                spec_path = os.path.join(target_dir, f"build_{plugin_id}.spec")
                with open(spec_path, "w", encoding="utf-8") as f:
                    f.write(spec_code)
                exported_files.append(spec_path)

                build_bat_code = f'''@echo off
chcp 65001 >nul
title 正在使用 PyInstaller 编译 {plugin.name} 独立 EXE...
cd /d "%~dp0"
echo 正在执行 PyInstaller 构建...
pyinstaller --clean -y "build_{plugin_id}.spec"
echo 构建完成，可执行文件位于 dist/{plugin.name}.exe
pause
'''
                build_bat_path = os.path.join(target_dir, f"build_{plugin_id}.bat")
                with open(build_bat_path, "w", encoding="utf-8") as f:
                    f.write(build_bat_code)
                exported_files.append(build_bat_path)

            # 10. 生成自包含配置 config.json
            cfg_code = f'''{{
  "plugin_id": "{plugin_id}",
  "plugin_name": "{plugin.name}",
  "theme": "system",
  "window_opacity": 1.0,
  "bg_opacity": 1.0,
  "component_opacity": 1.0,
  "acrylic_enabled": false,
  "blur_level": 50,
  "autostart": {str(autostart_default).lower()},
  "start_minimized": false,
  "enable_tray": true,
  "close_to_tray": false
}}
'''
            cfg_path = os.path.join(target_dir, "config.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(cfg_code)
            exported_files.append(cfg_path)

            # 11. 生成 Inno Setup 原生安装包工程脚本与一键编译批处理
            iss_code = cls.generate_inno_setup_iss(
                plugin=plugin,
                target_dir=target_dir,
                output_dir=output_dir,
                autostart_default=autostart_default,
                ico_path=os.path.join(target_dir, "app_icon.ico") if os.path.isfile(os.path.join(target_dir, "app_icon.ico")) else None
            )
            iss_path = os.path.join(target_dir, f"setup_{plugin_id}.iss")
            with open(iss_path, "w", encoding="utf-8-sig") as f:
                f.write(iss_code)
            exported_files.append(iss_path)

            compile_bat_code = f'''@echo off
chcp 65001 >nul
title 正在使用 Inno Setup 编译 {plugin.name} 原生 EXE 安装包...
cd /d "%~dp0"

set "ISCC_BIN="
if exist "%~dp0bin\\InnoSetup\\ISCC.exe" set "ISCC_BIN=%~dp0bin\\InnoSetup\\ISCC.exe"
if not defined ISCC_BIN if exist "%~dp0..\\bin\\InnoSetup\\ISCC.exe" set "ISCC_BIN=%~dp0..\\bin\\InnoSetup\\ISCC.exe"
if not defined ISCC_BIN if exist "%~dp0..\\..\\bin\\InnoSetup\\ISCC.exe" set "ISCC_BIN=%~dp0..\\..\\bin\\InnoSetup\\ISCC.exe"
if not defined ISCC_BIN if exist "%LOCALAPPDATA%\\Programs\\Inno Setup 6\\ISCC.exe" set "ISCC_BIN=%LOCALAPPDATA%\\Programs\\Inno Setup 6\\ISCC.exe"
if not defined ISCC_BIN if exist "%ProgramFiles%\\Inno Setup 6\\ISCC.exe" set "ISCC_BIN=%ProgramFiles%\\Inno Setup 6\\ISCC.exe"
if not defined ISCC_BIN if exist "%ProgramFiles(x86)%\\Inno Setup 6\\ISCC.exe" set "ISCC_BIN=%ProgramFiles(x86)%\\Inno Setup 6\\ISCC.exe"
if not defined ISCC_BIN (
    where ISCC >nul 2>nul
    if %errorlevel% equ 0 set "ISCC_BIN=ISCC"
)

if not defined ISCC_BIN (
    echo [提示] 未能在系统中检测到 Inno Setup 命令行编译器 (ISCC.exe)。
    echo 正在为您打开 Inno Setup 官方下载页面 (https://jrsoftware.org/isdl.php)...
    start https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

echo 正在编译 setup_{plugin_id}.iss...
"%ISCC_BIN%" "%~dp0setup_{plugin_id}.iss"
if %errorlevel% equ 0 (
    echo.
    echo ======================================================
    echo  编译成功！原生安装包 Setup_{plugin_id}.exe 已生成！
    echo ======================================================
) else (
    echo.
    echo [错误] Inno Setup 编译失败，返回码: %errorlevel%
)
pause
'''
            compile_bat_path = os.path.join(target_dir, "compile_setup.bat")
            with open(compile_bat_path, "w", encoding="utf-8") as f:
                f.write(compile_bat_code)
            exported_files.append(compile_bat_path)

            installer_exe = None
            compile_error = None
            iscc_bin = cls.find_iscc_executable()
            if compile_inno_setup:
                if iscc_bin:
                    try:
                        proc = subprocess.run(
                            [iscc_bin, iss_path],
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            timeout=120
                        )
                        expected_exe = os.path.join(output_dir, f"Setup_{plugin_id}.exe")
                        if proc.returncode == 0 and os.path.isfile(expected_exe) and os.path.getsize(expected_exe) > 0:
                            installer_exe = expected_exe
                        else:
                            compile_error = f"ISCC 编译未生成有效文件 (返回码 {proc.returncode}): {proc.stderr or proc.stdout[-400:]}"
                    except Exception as ex:
                        compile_error = f"调用 Inno Setup 发生异常: {ex}"
                else:
                    compile_error = "未检测到 Inno Setup 编译器 (ISCC.exe)，已生成 .iss 安装脚本与批处理"

            archive_path = None
            # 12. 如果要求打包压缩包 (ZIP / 7Z 自动化安装包)
            if create_archive:
                zip_filename = f"Setup_{plugin_id}_Standalone.zip"
                archive_path = os.path.join(output_dir, zip_filename)
                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(target_dir):
                        for file in files:
                            full_p = os.path.join(root, file)
                            rel_p = os.path.relpath(full_p, target_dir)
                            zipf.write(full_p, rel_p)

            return {
                "success": True,
                "plugin_id": plugin_id,
                "plugin_name": plugin.name,
                "output_dir": target_dir,
                "archive_path": archive_path,
                "iss_path": iss_path,
                "installer_exe": installer_exe,
                "iscc_found": iscc_bin is not None,
                "compile_error": compile_error,
                "files_count": len(exported_files)
            }

        except Exception as e:
            import traceback
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
