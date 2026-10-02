"""
强力解锁与应用粉碎删除引擎
基于 Windows 官方 Restart Manager API 与系统底层底层接口，检测文件占用锁、强制结束顽固进程树与粉碎文件。
"""

import ctypes
from ctypes import wintypes
import os
import shutil
import subprocess
import sys
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


CRITICAL_SYSTEM_PROCESSES = {
    "csrss.exe", "lsass.exe", "services.exe", "wininit.exe",
    "smss.exe", "explorer.exe", "svchost.exe", "winlogon.exe",
    "system", "registry", "fontdrvhost.exe", "dwm.exe"
}


def is_process_critical(pid: int) -> bool:
    """检查进程是否为 Windows 系统关键临界进程 (强杀将引发 BSOD 蓝屏)"""
    if pid in (0, 4, os.getpid()):
        return True
    if sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            is_critical = ctypes.c_int(0)
            if hasattr(kernel32, "IsProcessCritical"):
                if kernel32.IsProcessCritical(handle, ctypes.byref(is_critical)):
                    return bool(is_critical.value)
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        pass
    return False


def kill_process(pid: int, force_tree: bool = True) -> Tuple[bool, str]:
    """强杀指定 PID 的进程及子进程树 (严格防护核心系统关键进程)"""
    if pid in (0, 4, os.getpid()) or is_process_critical(pid):
        return False, f"系统保护: PID {pid} 为系统关键核心进程或当前自身进程，禁止终止！"

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
    if image_name.lower() in CRITICAL_SYSTEM_PROCESSES:
        return False, f"系统保护: [{image_name}] 属于 Windows 核心系统进程，禁止终止！"

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

    # 路径安全防护：拦截根驱动器与系统核心目录（防止误粉碎全盘或破坏操作系统）
    target_norm = os.path.normcase(target)
    drive, rest = os.path.splitdrive(target)
    sys_root = os.path.normcase(os.environ.get("SystemRoot", "C:\\Windows"))
    prog_files = os.path.normcase(os.environ.get("ProgramFiles", "C:\\Program Files"))
    prog_files_x86 = os.path.normcase(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"))
    prog_data = os.path.normcase(os.environ.get("ProgramData", "C:\\ProgramData"))
    user_root = os.path.normcase(os.path.dirname(os.environ.get("USERPROFILE", "C:\\Users\\Default")))

    protected_exact_dirs = {
        sys_root,
        prog_files,
        prog_files_x86,
        prog_data,
        user_root,
        (os.environ.get("SystemDrive", "C:") + "\\").lower(),
    }
    if (
        not rest.strip("\\/")
        or target == os.path.dirname(target)
        or target_norm in protected_exact_dirs
        or target_norm == sys_root
        or target_norm.startswith(sys_root + os.sep)
    ):
        return False, "受系统保护的核心系统路径或根驱动器，禁止强制粉碎！"

    # 1. 检测并结束占用进程
    locking = get_locking_processes(target)
    killed_info = []
    if locking and auto_kill_locking_procs:
        for pid, name in locking:
            # 保护自身与核心系统关键进程 (防止 Windows 蓝屏死机 BSOD)
            if pid in (0, 4, os.getpid()) or name.lower() in CRITICAL_SYSTEM_PROCESSES or is_process_critical(pid):
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


from toolbox.core.paths import scan_registry_installed_apps

