"""
系统增强与右键助手 - 注册表与系统配置操作
优先写入当前用户 HKCU，无需强制管理员提权，安全可靠。
"""

import os
import sys
import winreg
from typing import Tuple, Dict, Any
import shutil


APP_KEY_NAME = "ChieriToolbox"
APP_DISPLAY_NAME = "千绘莉的多功能工具箱"


def get_toolbox_main_command(prefer_pythonw: bool = True) -> str:
    """获取启动工具箱的完整执行命令，优先使用 pythonw.exe 避免控制台黑框弹出，冻结打包后直接使用 exe"""
    from toolbox.core.paths import is_frozen, get_app_root
    if is_frozen():
        return f'"{os.path.normpath(sys.executable)}"'

    base_dir = get_app_root()
    venv_pythonw = os.path.join(base_dir, ".venv", "Scripts", "pythonw.exe")
    venv_python = os.path.join(base_dir, ".venv", "Scripts", "python.exe")
    
    if prefer_pythonw and os.path.isfile(venv_pythonw):
        python_exe = venv_pythonw
    elif os.path.isfile(venv_python):
        python_exe = venv_python
    else:
        python_exe = sys.executable
    main_py = os.path.join(base_dir, "main.py")
    return f'"{python_exe}" "{main_py}"'


def is_context_menu_registered() -> bool:
    """检查是否已注册当前用户的右键菜单"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Classes\Directory\Background\shell\{APP_KEY_NAME}"
        )
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def register_context_menu() -> Tuple[bool, str]:
    """为当前用户写入 Windows 资源管理器右键快捷菜单"""
    from toolbox.core.paths import get_app_root, get_bundle_dir, is_frozen
    main_cmd = get_toolbox_main_command(prefer_pythonw=True)

    icon_path = ""
    if is_frozen():
        icon_path = os.path.normpath(sys.executable)
    else:
        for b in [get_app_root(), get_bundle_dir()]:
            cand = os.path.join(b, "app_icon.ico")
            if os.path.isfile(cand):
                icon_path = os.path.normpath(cand)
                break

    # Background 右键传入 %V (当前背景目录)；Directory 与 * 右键传入 %1 (所选目录或文件)
    target_configs = [
        (rf"Software\Classes\Directory\Background\shell\{APP_KEY_NAME}", f'{main_cmd} "%V"'),
        (rf"Software\Classes\Directory\shell\{APP_KEY_NAME}", f'{main_cmd} "%1"'),
        (rf"Software\Classes\*\shell\{APP_KEY_NAME}", f'{main_cmd} "%1"'),
    ]
    try:
        for p, cmd_str in target_configs:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, p)
            winreg.SetValue(key, "", winreg.REG_SZ, APP_DISPLAY_NAME)
            if icon_path:
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, icon_path)
            cmd_key = winreg.CreateKey(key, "command")
            winreg.SetValue(cmd_key, "", winreg.REG_SZ, cmd_str)
            winreg.CloseKey(cmd_key)
            winreg.CloseKey(key)
        return True, "已成功添加右键菜单「千绘莉的多功能工具箱」！"
    except Exception as e:
        return False, f"写入右键菜单失败: {e}"


def unregister_context_menu() -> Tuple[bool, str]:
    """移除当前用户的右键菜单"""
    target_paths = [
        rf"Software\Classes\Directory\Background\shell\{APP_KEY_NAME}",
        rf"Software\Classes\Directory\shell\{APP_KEY_NAME}",
        rf"Software\Classes\*\shell\{APP_KEY_NAME}",
        rf"Software\Classes\Directory\Background\shell\ChieriFileManager",
        rf"Software\Classes\Directory\shell\ChieriFileManager",
    ]
    try:
        for p in target_paths:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{p}\command")
            except FileNotFoundError:
                pass
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, p)
            except FileNotFoundError:
                pass
        return True, "右键快捷菜单已安全移除。"
    except Exception as e:
        return False, f"移除右键菜单异常: {e}"


def is_autostart_enabled() -> bool:
    """检查是否已加入开机自启动"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ
        )
        val, _ = winreg.QueryValueEx(key, APP_KEY_NAME)
        winreg.CloseKey(key)
        return bool(val)
    except Exception:
        return False


def set_autostart(enable: bool) -> Tuple[bool, str]:
    """设置或取消开机自启动"""
    run_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key_path, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            cmd = f'{get_toolbox_main_command()} --autostart'
            winreg.SetValueEx(key, APP_KEY_NAME, 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(key)
            return True, "开机自启已成功启用！"
        else:
            try:
                winreg.DeleteValue(key, APP_KEY_NAME)
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
            return True, "已取消开机自启动。"
    except Exception as e:
        return False, f"修改自启动设置失败: {e}"


def run_system_health_check() -> Dict[str, Any]:
    """执行环境自检诊断"""
    # 查找 FFmpeg
    from toolbox.core.paths import find_ffmpeg_executable
    ffmpeg_p = find_ffmpeg_executable()

    return {
        "python_version": sys.version.split()[0],
        "python_path": sys.executable,
        "ffmpeg_status": "已就绪" if ffmpeg_p else "未找到",
        "ffmpeg_path": ffmpeg_p or "无",
        "context_menu": "已开启" if is_context_menu_registered() else "未开启",
        "autostart": "已启用" if is_autostart_enabled() else "未启用"
    }
