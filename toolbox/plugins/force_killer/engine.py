"""
强力解锁与应用粉碎删除引擎
基于 Windows 官方 Restart Manager API 与系统底层底层接口，检测文件占用锁、强制结束顽固进程树与粉碎文件。
"""

import ctypes
from ctypes import wintypes
import os
import shutil
import subprocess
import winreg
import re
from typing import Dict, List, Optional, Tuple

RM_SESSION_KEY_LEN = 32
CCH_RM_SESSION_KEY = RM_SESSION_KEY_LEN * 2

FILE_ATTRIBUTE_NORMAL = 0x80
MOVEFILE_DELAY_UNTIL_REBOOT = 0x00000004


class RM_UNIQUE_PROCESS(ctypes.Structure):
    _fields_ = [
        ("dwProcessId", wintypes.DWORD),
        ("ProcessStartTime", wintypes.FILETIME)
    ]


class RM_PROCESS_INFO(ctypes.Structure):
    _fields_ = [
        ("Process", RM_UNIQUE_PROCESS),
        ("strAppName", wintypes.WCHAR * 256),
        ("strServiceShortName", wintypes.WCHAR * 64),
        ("ApplicationType", wintypes.DWORD),
        ("AppStatus", wintypes.ULONG),
        ("TSSessionId", wintypes.DWORD),
        ("bRestartable", wintypes.BOOL)
    ]


def get_locking_processes(file_or_dir_path: str) -> List[Tuple[int, str]]:
    """使用 Windows Restart Manager 探测锁定给定文件或文件夹的进程列表 (PID, 进程名)"""
    if not os.path.exists(file_or_dir_path):
        return []

    target_files = []
    if os.path.isdir(file_or_dir_path):
        # Restart Manager 仅支持文件句柄注册。若为目录，则收集目录下的文件进行注册探测
        for root, _, files in os.walk(file_or_dir_path):
            for f in files:
                target_files.append(os.path.abspath(os.path.join(root, f)))
                if len(target_files) >= 128:
                    break
            if len(target_files) >= 128:
                break
    elif os.path.isfile(file_or_dir_path):
        target_files = [os.path.abspath(file_or_dir_path)]

    if not target_files:
        return []

    rm = ctypes.windll.rstrtmgr
    session_handle = wintypes.DWORD()
    session_key = (wintypes.WCHAR * (CCH_RM_SESSION_KEY + 1))()
    res = rm.RmStartSession(ctypes.byref(session_handle), 0, session_key)
    if res != 0:
        return []

    try:
        path_arr = (wintypes.LPCWSTR * len(target_files))(*target_files)
        res = rm.RmRegisterResources(session_handle, len(target_files), path_arr, 0, None, 0, None)
        if res != 0:
            return []

        n_proc_info_needed = wintypes.UINT(0)
        n_proc_info = wintypes.UINT(0)
        reboot_reasons = wintypes.DWORD(0)

        res = rm.RmGetList(
            session_handle,
            ctypes.byref(n_proc_info_needed),
            ctypes.byref(n_proc_info),
            None,
            ctypes.byref(reboot_reasons)
        )
        if res not in (0, 234):  # 234: ERROR_MORE_DATA
            return []

        if n_proc_info_needed.value == 0:
            return []

        n_proc_info = wintypes.UINT(n_proc_info_needed.value)
        proc_infos = (RM_PROCESS_INFO * n_proc_info.value)()
        res = rm.RmGetList(
            session_handle,
            ctypes.byref(n_proc_info_needed),
            ctypes.byref(n_proc_info),
            proc_infos,
            ctypes.byref(reboot_reasons)
        )
        if res != 0:
            return []

        results = []
        seen = set()
        for i in range(n_proc_info.value):
            pid = proc_infos[i].Process.dwProcessId
            app_name = proc_infos[i].strAppName
            if pid not in seen:
                seen.add(pid)
                results.append((pid, app_name))
        return results
    except Exception:
        return []
    finally:
        rm.RmEndSession(session_handle)


def kill_process(pid: int, force_tree: bool = True) -> Tuple[bool, str]:
    """强杀指定 PID 的进程及子进程树"""
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    cmd = ["taskkill", "/F"]
    if force_tree:
        cmd.append("/T")
    cmd.extend(["/PID", str(pid)])

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10
        )
        if proc.returncode == 0:
            return True, f"成功终止进程 PID: {pid}"
        else:
            return False, proc.stderr.strip() or f"退出码: {proc.returncode}"
    except Exception as e:
        return False, str(e)


def kill_processes_by_name(image_name: str) -> Tuple[bool, str]:
    """强杀指定映像名的所有进程"""
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    cmd = ["taskkill", "/F", "/T", "/IM", image_name]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10
        )
        if proc.returncode == 0:
            return True, f"已强杀所有 [{image_name}] 进程"
        else:
            return False, proc.stderr.strip()
    except Exception as e:
        return False, str(e)


def remove_file_attributes(target_path: str):
    """去除只读、隐藏、系统属性以允许删除"""
    try:
        ctypes.windll.kernel32.SetFileAttributesW(target_path, FILE_ATTRIBUTE_NORMAL)
    except Exception:
        pass


def shred_file(file_path: str, wipe_passes: int = 1):
    """文件覆写粉碎 (采用 64KB 块缓冲覆写杜绝大文件内存 OOM)"""
    try:
        size = os.path.getsize(file_path)
        if size > 0 and size < 500 * 1024 * 1024:  # 500MB 以下快速覆写
            chunk_size = 65536
            zero_chunk = b"\x00" * chunk_size
            with open(file_path, "ba+", buffering=0) as f:
                for _ in range(wipe_passes):
                    f.seek(0)
                    remaining = size
                    while remaining > 0:
                        w_len = min(remaining, chunk_size)
                        f.write(zero_chunk[:w_len])
                        remaining -= w_len
                    f.flush()
    except Exception:
        pass


def force_unlock_and_delete(
    target_path: str,
    shred: bool = False,
    auto_kill_locking_procs: bool = True
) -> Tuple[bool, str]:
    """强力解除占用并彻底删除文件或文件夹"""
    target = os.path.normpath(os.path.abspath(target_path))
    if not os.path.exists(target):
        return True, "目标路径已不存在。"

    # 1. 检测并结束占用进程
    locking = get_locking_processes(target)
    killed_info = []
    if locking and auto_kill_locking_procs:
        for pid, name in locking:
            # 保护自身与核心系统关键进程
            if pid in (0, 4, os.getpid()):
                continue
            ok, msg = kill_process(pid, force_tree=True)
            if ok:
                killed_info.append(f"{name} (PID:{pid})")

    # 2. 递归去除只读属性
    if os.path.isdir(target):
        for root, dirs, files in os.walk(target):
            for d in dirs:
                remove_file_attributes(os.path.join(root, d))
            for f in files:
                remove_file_attributes(os.path.join(root, f))
    remove_file_attributes(target)

    # 3. 如果需要粉碎覆写
    if shred and os.path.isfile(target):
        shred_file(target)

    # 4. 执行删除
    try:
        if os.path.isdir(target):
            def _remove_readonly(func, p, exc_info):
                try:
                    remove_file_attributes(p)
                    func(p)
                except Exception:
                    pass
            shutil.rmtree(target, onerror=_remove_readonly)
        else:
            os.remove(target)

        if not os.path.exists(target):
            detail = f"文件已彻底删除。"
            if killed_info:
                detail += f" 已终止占用进程: {', '.join(killed_info)}"
            return True, detail
    except Exception as e:
        # 如果依然被系统驱动占用，注册重启时静默移除
        try:
            res = ctypes.windll.kernel32.MoveFileExW(target, None, MOVEFILE_DELAY_UNTIL_REBOOT)
            if res != 0:
                return True, "目标当前被系统底层驱动锁定，已成功注册为[下次开机/重启系统时自动彻底粉碎删除]。"
            else:
                err = ctypes.windll.kernel32.GetLastError()
                return False, f"强制删除失败 ({e})，且注册下次开机自删失败 (Win32 错误码: {err}，请尝试以管理员身份运行工具箱)。"
        except Exception as e2:
            return False, f"删除失败: {str(e)} (注册开机自删失败: {str(e2)})"

    return False, "未能成功删除目标。"


def list_running_processes(filter_kw: str = "") -> List[Dict]:
    """获取系统正在运行的进程列表 (PID, 映像名, 会话名, 内存占用)"""
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    cmd = ["tasklist", "/FO", "CSV", "/NH"]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=15
        )
        if proc.returncode != 0:
            return []

        import csv
        results = []
        filter_lower = filter_kw.lower().strip()
        reader = csv.reader(proc.stdout.splitlines())
        for row in reader:
            if len(row) >= 5:
                name = row[0]
                pid_str = row[1]
                session_name = row[2]
                session_num = row[3]
                mem_str = row[4]

                if filter_lower:
                    if filter_lower not in name.lower() and filter_lower not in pid_str:
                        continue

                results.append({
                    "name": name,
                    "pid": int(pid_str) if pid_str.isdigit() else 0,
                    "session": session_name,
                    "memory": mem_str
                })
        return results
    except Exception:
        return []


def scan_registry_installed_apps() -> List[Dict[str, str]]:
    """
    扫描 Windows 注册表已安装软件 (HKLM & HKCU, 包含 32/64 位)。
    提取应用名称、版本、安装目录、主执行程序与卸载命令，便于强制解除占用与顽固卸载粉碎。
    """
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

