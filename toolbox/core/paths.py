"""
工具箱 (Toolbox) - 统一运行环境与路径管理器 (Paths)
提供源码开发态与 PyInstaller 打包冻结态 (OneDir / OneFile) 下无缝透明的路径解析。
支持二进制工具 (bin/)、配置文件 (config)、插件包 (plugins/) 等路径的一体化自适应定位。
"""

import os
import re
import shutil
import subprocess
import sys
from typing import Optional, List, Dict


def is_frozen() -> bool:
    """判断当前进程是否运行在打包冻结环境中 (如 PyInstaller 打包生成的 exe)"""
    return getattr(sys, "frozen", False)


def get_bundle_dir() -> str:
    """
    获取打包运行时的内部解压/资源根目录。
    - PyInstaller 冻结环境: 优先使用 sys._MEIPASS (OneFile/OneDir 内部资源根路径)
    - 源码运行环境: 工程根目录 (即包含 main.py, toolbox/, bin/ 的目录)
    """
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    # 本文件路径: toolbox/core/paths.py -> 上溯三层得到工程根目录
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_app_root() -> str:
    """
    获取应用程序持久化宿主目录。
    - 打包环境: 可执行文件 (.exe) 所在的磁盘目录 (便于绿色便携部署及保存配置文件)
    - 源码环境: 工程根目录
    """
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_bin_dir() -> str:
    """
    获取存放外部命令行二进制工具 (ffmpeg, 7z 等) 的目录。
    按如下优先级智能探测：
    1. exe 所在目录下的 bin/ (绿色便携部署)
    2. 打包内部 bundle_dir 下的 bin/ (含 sys._MEIPASS/bin)
    3. 打包内部 _internal/bin/
    4. 源码工程根目录下的 bin/
    """
    candidates = [
        os.path.join(get_app_root(), "bin"),
        os.path.join(get_bundle_dir(), "bin"),
        os.path.join(get_app_root(), "_internal", "bin"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


def get_bin_path(binary_name: str) -> Optional[str]:
    """
    获取指定外部工具的绝对执行路径 (如 ffmpeg.exe, 7z.exe, ffprobe.exe, ffplay.exe)。
    优先级：
    1. app_root/bin/{binary_name}
    2. bundle_dir/bin/{binary_name}
    3. app_root/_internal/bin/{binary_name}
    4. app_root/{binary_name}
    5. bundle_dir/{binary_name}
    6. 系统 PATH (shutil.which)
    自动支持 Windows 无后缀名传入时的 .exe 兜底探测。
    """
    names = [binary_name]
    if sys.platform == "win32" and not binary_name.lower().endswith(".exe"):
        names.append(f"{binary_name}.exe")

    search_roots = [
        os.path.join(get_app_root(), "bin"),
        os.path.join(get_bundle_dir(), "bin"),
        os.path.join(get_app_root(), "_internal", "bin"),
        get_app_root(),
        get_bundle_dir(),
    ]

    for name in names:
        for r in search_roots:
            candidate = os.path.join(r, name)
            if os.path.isfile(candidate):
                return os.path.normpath(candidate)

    # 尝试系统 PATH
    for name in names:
        which_p = shutil.which(name)
        if which_p:
            return os.path.normpath(which_p)

    return None


def get_config_path(filename: str = "toolbox_config.json") -> str:
    """
    获取配置文件的存放路径。
    统一放置于持久化 app_root 目录下，确保打包后用户配置不会随临时目录被清空。
    """
    return os.path.normpath(os.path.join(get_app_root(), filename))


def get_plugins_search_dirs() -> list:
    """
    获取所有有效的插件扫描目录集合。
    支持内置插件 (bundle_dir/toolbox/plugins) 与外部扩展插件目录 (app_root/plugins)。
    """
    dirs = []
    candidates = [
        os.path.join(get_bundle_dir(), "toolbox", "plugins"),
        os.path.join(get_app_root(), "toolbox", "plugins"),
        os.path.join(get_bundle_dir(), "_internal", "toolbox", "plugins"),
        os.path.join(get_app_root(), "_internal", "toolbox", "plugins"),
        os.path.join(get_app_root(), "plugins"),
    ]
    for c in candidates:
        norm = os.path.normpath(c)
        if os.path.isdir(norm) and norm not in dirs:
            dirs.append(norm)
    return dirs


def get_plugins_dir() -> str:
    """
    获取默认主插件目录。
    """
    dirs = get_plugins_search_dirs()
    if dirs:
        return dirs[0]
    return os.path.normpath(os.path.join(get_bundle_dir(), "toolbox", "plugins"))


def find_ffmpeg_executable() -> Optional[str]:
    """寻找可用的 ffmpeg 可执行文件路径"""
    # 1. 检查配置文件中是否指定了自定义 ffmpeg 路径
    try:
        from toolbox.core.config_manager import ConfigManager
        custom_ffmpeg = ConfigManager().get("ffmpeg_path", "").strip()
        if custom_ffmpeg and os.path.isfile(custom_ffmpeg):
            return custom_ffmpeg
    except Exception:
        pass

    # 2. 检查工具箱自带的 bin 目录或打包环境中的 ffmpeg
    try:
        local_ffmpeg = get_bin_path("ffmpeg.exe")
        if local_ffmpeg and os.path.isfile(local_ffmpeg):
            return local_ffmpeg
    except Exception:
        pass

    # 3. 检查系统环境变量 PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    return None


WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}


def sanitize_filename(name: str, max_length: int = 120) -> str:
    """清理 Windows 文件名非法字符、保留设备名及限制长度防止 MAX_PATH 溢出"""
    clean = re.sub(r'[\\/*?:"<>|\r\n\t]', "_", name).strip(". ")
    if not clean:
        return "video"
    base, ext = os.path.splitext(clean)
    if base.upper() in WINDOWS_RESERVED_NAMES:
        base = f"_{base}"
    if len(base + ext) > max_length:
        max_base_len = max(1, max_length - len(ext))
        base = base[:max_base_len].rstrip(". ")
    result = base + ext
    return result if result else "video"


def get_audio_input_devices() -> List[str]:
    """探测系统所有可用的音频录入/麦克风设备名称"""
    devices = []
    # 1. 尝试通过 PySide6.QtMultimedia 探测
    try:
        from PySide6.QtCore import QCoreApplication
        _app = QCoreApplication.instance()
        if _app:
            from PySide6.QtMultimedia import QMediaDevices
            for dev in QMediaDevices.audioInputs():
                desc = dev.description().strip()
                if desc and desc not in devices:
                    devices.append(desc)
    except Exception:
        pass

    # 2. 若未探测到，尝试从 FFmpeg dshow 设备列表解析
    if not devices:
        ffmpeg_bin = find_ffmpeg_executable()
        if ffmpeg_bin and os.path.isfile(ffmpeg_bin):
            try:
                cmd = [ffmpeg_bin, "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=creationflags,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )
                in_audio_section = False
                for line in proc.stderr.splitlines():
                    if "DirectShow audio devices" in line:
                        in_audio_section = True
                        continue
                    if "DirectShow video devices" in line:
                        in_audio_section = False
                        continue
                    if in_audio_section and '"]' in line and '"' in line:
                        parts = line.split('"')
                        if len(parts) >= 2:
                            d_name = parts[1].strip()
                            if d_name and not d_name.startswith("@") and d_name not in devices:
                                devices.append(d_name)
            except Exception:
                pass

    if not devices:
        devices = ["默认音频输入设备"]
    return devices


def scan_registry_installed_apps() -> List[Dict[str, str]]:
    """
    扫描 Windows 注册表已安装软件 (HKLM & HKCU, 包含 32/64 位)。
    提取应用名称、版本、安装目录、主执行程序与卸载命令，便于强制解除占用与顽固卸载粉碎。
    """
    if sys.platform != "win32":
        return []

    try:
        import winreg
    except ImportError:
        return []

    apps = []
    seen = set()

    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0)),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_READ),
    ]

    for hkey, subkey_path, access_mask in roots:
        try:
            with winreg.OpenKey(hkey, subkey_path, 0, access_mask) as root_key:
                num_subkeys, _, _ = winreg.QueryInfoKey(root_key)
                for i in range(num_subkeys):
                    try:
                        sub_name = winreg.EnumKey(root_key, i)
                        with winreg.OpenKey(root_key, sub_name, 0, access_mask) as app_key:
                            def _get_val(k):
                                try:
                                    v, _ = winreg.QueryValueEx(app_key, k)
                                    return str(v).strip()
                                except Exception:
                                    return ""

                            disp_name = _get_val("DisplayName")
                            if not disp_name or _get_val("SystemComponent") == "1":
                                continue

                            disp_ver = _get_val("DisplayVersion")
                            pub = _get_val("Publisher")
                            inst_loc = _get_val("InstallLocation")
                            disp_icon = _get_val("DisplayIcon")
                            uninst_str = _get_val("UninstallString")

                            exe_path = ""
                            if disp_icon:
                                raw_icon = disp_icon.split(",")[0].strip('"')
                                if raw_icon.lower().endswith(".exe") and os.path.isfile(raw_icon):
                                    exe_path = raw_icon

                            if not exe_path and inst_loc and os.path.isdir(inst_loc):
                                try:
                                    for f in os.listdir(inst_loc):
                                        if f.lower().endswith(".exe"):
                                            candidate = os.path.join(inst_loc, f)
                                            if os.path.isfile(candidate):
                                                exe_path = candidate
                                                break
                                except Exception:
                                    pass

                            if not inst_loc and exe_path:
                                inst_loc = os.path.dirname(exe_path)
                            elif not inst_loc and uninst_str:
                                m = re.search(r'["\']?([^"\']+\.exe)["\']?', uninst_str, re.IGNORECASE)
                                if m and os.path.isfile(m.group(1)):
                                    inst_loc = os.path.dirname(m.group(1))

                            key_id = f"{disp_name}_{disp_ver}".lower()
                            if key_id not in seen:
                                seen.add(key_id)
                                apps.append({
                                    "name": disp_name,
                                    "version": disp_ver,
                                    "publisher": pub,
                                    "install_location": inst_loc,
                                    "exe_path": exe_path,
                                    "uninstall_string": uninst_str,
                                    "registry_key": sub_name
                                })
                    except Exception:
                        continue
        except Exception:
            continue

    apps.sort(key=lambda x: x["name"].lower())
    return apps

