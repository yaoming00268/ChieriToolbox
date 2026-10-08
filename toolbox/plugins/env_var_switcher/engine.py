"""
环境变量切换管家 (Environment Variable Switcher) - 核心引擎
负责 Windows 注册表用户/系统环境变量的安全读取与写入、PATH 条目有效性诊断与清理、
一键快照备份还原、方案切换、以及广播 WM_SETTINGCHANGE 消息使配置即时生效。
"""

import os
import sys
import json
import time
import ctypes
from typing import Dict, List, Tuple, Optional, Any

if sys.platform == "win32":
    import winreg
else:
    winreg = None


USER_ENV_KEY = r"Environment"
SYSTEM_ENV_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


def is_admin() -> bool:
    """检查当前进程是否具备 Windows 管理员提升权限"""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def broadcast_environment_change() -> bool:
    """
    向 Windows 所有顶层窗口广播 WM_SETTINGCHANGE 消息。
    使得资源管理器与新启动的命令行终端无需注销重启即可立即加载最新环境变量。
    """
    if sys.platform != "win32":
        return False
    try:
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002

        # 针对 64 位 Windows，SendMessageTimeoutW 的 lpdwResult 是 PDWORD_PTR (8 字节)
        # 必须使用 ctypes.c_size_t() 避免 4 字节缓冲区溢出与内存破坏
        res = ctypes.c_size_t()
        # 传递 "Environment" 作为 lParam
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            4000,
            ctypes.byref(res)
        )
        return True
    except Exception as e:
        print(f"[EnvVarSwitcher] 广播 WM_SETTINGCHANGE 异常: {e}")
        return False


def get_user_variables() -> Dict[str, Tuple[str, int]]:
    """读取 Windows 用户级环境变量，返回 {var_name: (value, reg_type)}"""
    vars_dict: Dict[str, Tuple[str, int]] = {}
    if not winreg:
        return vars_dict
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, USER_ENV_KEY, 0, winreg.KEY_READ) as key:
            count = winreg.QueryInfoKey(key)[1]
            for i in range(count):
                name, val, reg_type = winreg.EnumValue(key, i)
                vars_dict[name] = (str(val), reg_type)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[EnvVarSwitcher] 读取用户环境变量异常: {e}")
    return vars_dict


def get_system_variables() -> Dict[str, Tuple[str, int]]:
    """读取 Windows 系统级环境变量，返回 {var_name: (value, reg_type)}"""
    vars_dict: Dict[str, Tuple[str, int]] = {}
    if not winreg:
        return vars_dict
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, SYSTEM_ENV_KEY, 0, winreg.KEY_READ) as key:
            count = winreg.QueryInfoKey(key)[1]
            for i in range(count):
                name, val, reg_type = winreg.EnumValue(key, i)
                vars_dict[name] = (str(val), reg_type)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[EnvVarSwitcher] 读取系统环境变量异常: {e}")
    return vars_dict


def _get_var_case_insensitive(vars_dict: Dict[str, Tuple[str, int]], name: str) -> Tuple[str, int]:
    """大小写无关查找环境变量名，防御 Windows 注册表 Path / PATH / path 差异"""
    name_upper = name.upper()
    for k, v in vars_dict.items():
        if k.upper() == name_upper:
            return v
    return ("", 0)


def set_variable(
    name: str,
    value: str,
    scope: str = "user",
    reg_type: Optional[int] = None,
    broadcast: bool = True
) -> Tuple[bool, str]:
    """
    持久化设置用户或系统环境变量并更新内存环境。
    :param scope: 'user' 或 'system'
    """
    if not winreg:
        return False, "当前平台不支持 Windows 注册表"

    name = name.strip()
    if not name:
        return False, "变量名不能为空"

    # 若含有 %...% 或为 PATH 变量，则默认使用 REG_EXPAND_SZ，否则 REG_SZ
    if reg_type is None:
        if name.upper() == "PATH" or "%" in value:
            reg_type = winreg.REG_EXPAND_SZ
        else:
            reg_type = winreg.REG_SZ

    try:
        if scope.lower() == "system":
            if not is_admin():
                return False, "修改系统级环境变量需要以管理员身份运行工具箱"
            root = winreg.HKEY_LOCAL_MACHINE
            sub_key = SYSTEM_ENV_KEY
        else:
            root = winreg.HKEY_CURRENT_USER
            sub_key = USER_ENV_KEY

        with winreg.OpenKey(root, sub_key, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, reg_type, value)

        # 同步更新当前进程内存中的 os.environ
        if name.upper() == "PATH":
            # Windows 中当前进程 os.environ['PATH'] 必须是系统 PATH 与用户 PATH 的融合
            # 防止写入用户 PATH 时意外抹除 C:\Windows\System32 导致子进程与命令查找全面崩溃
            user_p = value if scope.lower() == "user" else _get_var_case_insensitive(get_user_variables(), "Path")[0]
            sys_p = value if scope.lower() == "system" else _get_var_case_insensitive(get_system_variables(), "Path")[0]
            parts = []
            if sys_p:
                parts.append(os.path.expandvars(sys_p))
            if user_p:
                parts.append(os.path.expandvars(user_p))
            os.environ["PATH"] = ";".join(parts)
        else:
            os.environ[name] = os.path.expandvars(value)

        if broadcast:
            broadcast_environment_change()

        return True, f"成功设置 [{scope.upper()}] 环境变量: {name}"
    except PermissionError:
        return False, f"权限不足，无法写入 [{scope.upper()}] 环境变量"
    except Exception as e:
        return False, f"写入环境变量异常: {e}"


def delete_variable(name: str, scope: str = "user", broadcast: bool = True) -> Tuple[bool, str]:
    """删除指定作用域下的环境变量"""
    if not winreg:
        return False, "当前平台不支持 Windows 注册表"

    name = name.strip()
    try:
        if scope.lower() == "system":
            if not is_admin():
                return False, "删除系统级环境变量需要以管理员身份运行工具箱"
            root = winreg.HKEY_LOCAL_MACHINE
            sub_key = SYSTEM_ENV_KEY
        else:
            root = winreg.HKEY_CURRENT_USER
            sub_key = USER_ENV_KEY

        with winreg.OpenKey(root, sub_key, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)

        if name.upper() == "PATH":
            # 若删除单侧 PATH，保留另一侧环境
            other_p = _get_var_case_insensitive(get_system_variables(), "Path")[0] if scope.lower() == "user" else _get_var_case_insensitive(get_user_variables(), "Path")[0]
            if other_p:
                os.environ["PATH"] = os.path.expandvars(other_p)
            else:
                os.environ.pop(name, None)
        else:
            os.environ.pop(name, None)

        if broadcast:
            broadcast_environment_change()

        return True, f"成功删除 [{scope.upper()}] 环境变量: {name}"
    except FileNotFoundError:
        return True, f"变量 {name} 不存在或已被删除"
    except PermissionError:
        return False, f"权限不足，无法删除 [{scope.upper()}] 环境变量"
    except Exception as e:
        return False, f"删除环境变量异常: {e}"


# =========================================================================
# PATH 变量诊断、解析与一键体检
# =========================================================================

def parse_path_entries(path_str: str) -> List[Dict[str, Any]]:
    """
    解析 PATH 字符串中的各个目录条目，检查有效性、重复性并识别常见开发工具。
    """
    entries = [p.strip() for p in path_str.split(";") if p.strip()]
    seen_canonical = set()
    results: List[Dict[str, Any]] = []

    for idx, raw_path in enumerate(entries):
        # 去除外层引号 (Windows PATH 中包含空格的路径常包裹双引号)
        clean_raw = raw_path.strip().strip('"').strip("'")
        expanded = os.path.expandvars(clean_raw)
        is_valid = os.path.isdir(expanded) if expanded else False
        canonical_p = os.path.normpath(expanded).lower() if expanded else ""
        is_duplicate = canonical_p in seen_canonical if canonical_p else False
        if canonical_p:
            seen_canonical.add(canonical_p)

        # 智能探测工具特征
        tool_tag = ""
        p_lower = clean_raw.lower()
        if "python" in p_lower:
            tool_tag = "Python"
        elif "git" in p_lower:
            tool_tag = "Git"
        elif "nodejs" in p_lower or "node" in p_lower or "npm" in p_lower:
            tool_tag = "Node.js"
        elif "java" in p_lower or "jdk" in p_lower or "jre" in p_lower:
            tool_tag = "Java/JDK"
        elif "rust" in p_lower or "cargo" in p_lower:
            tool_tag = "Rust/Cargo"
        elif "go" in p_lower and ("bin" in p_lower or "pkg" in p_lower):
            tool_tag = "Golang"
        elif "system32" in p_lower or "windows" in p_lower:
            tool_tag = "Windows核心"
        elif "powershell" in p_lower:
            tool_tag = "PowerShell"
        elif "vs" in p_lower or "visual studio" in p_lower or "msbuild" in p_lower:
            tool_tag = "Visual Studio"

        status_text = "正常"
        if not is_valid:
            status_text = "失效目录 (不存在)"
        elif is_duplicate:
            status_text = "冗余重复项"

        results.append({
            "index": idx + 1,
            "raw": clean_raw,
            "expanded": expanded,
            "is_valid": is_valid,
            "is_duplicate": is_duplicate,
            "tool_tag": tool_tag,
            "status": status_text
        })

    return results


def clean_path_entries(
    entries: List[str],
    remove_dead: bool = True,
    remove_duplicates: bool = True
) -> Tuple[List[str], Dict[str, int]]:
    """清理 PATH 列表中的幽灵路径与重复路径"""
    cleaned: List[str] = []
    seen = set()
    stats = {"removed_dead": 0, "removed_duplicates": 0}

    for p in entries:
        clean_p = p.strip().strip('"').strip("'")
        if not clean_p:
            continue
        exp = os.path.expandvars(clean_p)
        if remove_dead and not os.path.isdir(exp):
            stats["removed_dead"] += 1
            continue
        canonical_exp = os.path.normpath(exp).lower()
        if remove_duplicates and canonical_exp in seen:
            stats["removed_duplicates"] += 1
            continue
        seen.add(canonical_exp)
        cleaned.append(clean_p)

    return cleaned, stats


# =========================================================================
# 一键快照备份与还原
# =========================================================================

def create_env_backup(backup_dir: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
    """创建当前系统与用户环境变量的完整 JSON 备份快照"""
    if backup_dir is None:
        backup_dir = os.path.join(os.path.expanduser("~"), ".chieri_toolbox", "env_backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"env_backup_{timestamp}.json"
    file_path = os.path.join(backup_dir, filename)

    user_vars = get_user_variables()
    sys_vars = get_system_variables()

    backup_payload = {
        "timestamp": timestamp,
        "created_at": time.asctime(),
        "platform": sys.platform,
        "user_variables": {k: {"value": v[0], "type": v[1]} for k, v in user_vars.items()},
        "system_variables": {k: {"value": v[0], "type": v[1]} for k, v in sys_vars.items()}
    }

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(backup_payload, f, indent=2, ensure_ascii=False)
        return True, file_path, backup_payload
    except Exception as e:
        return False, str(e), {}


def restore_env_backup(
    backup_file_or_data: Any,
    restore_user: bool = True,
    restore_system: bool = False
) -> Tuple[bool, str]:
    """从备份快照中恢复环境变量"""
    if isinstance(backup_file_or_data, str) and os.path.isfile(backup_file_or_data):
        try:
            with open(backup_file_or_data, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return False, f"读取备份文件失败: {e}"
    elif isinstance(backup_file_or_data, dict):
        data = backup_file_or_data
    else:
        return False, "无效的备份数据格式"

    restored_count = 0
    errors = []

    # 1. 恢复用户级变量
    if restore_user and "user_variables" in data:
        for name, item in data["user_variables"].items():
            val = item.get("value", "")
            rtype = item.get("type", 1)
            ok, msg = set_variable(name, val, scope="user", reg_type=rtype, broadcast=False)
            if ok:
                restored_count += 1
            else:
                errors.append(msg)

    # 2. 恢复系统级变量
    if restore_system and "system_variables" in data:
        if not is_admin():
            errors.append("未具备管理员权限，跳过系统变量恢复")
        else:
            for name, item in data["system_variables"].items():
                val = item.get("value", "")
                rtype = item.get("type", 1)
                ok, msg = set_variable(name, val, scope="system", reg_type=rtype, broadcast=False)
                if ok:
                    restored_count += 1
                else:
                    errors.append(msg)

    broadcast_environment_change()

    if errors:
        return True, f"已恢复 {restored_count} 项变量，存在以下提示: {'; '.join(errors)}"
    return True, f"成功恢复 {restored_count} 项环境变量！"
