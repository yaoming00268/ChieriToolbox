"""
端口网络哨兵 (Port Network Sentinel) - 核心引擎
提供本地端口侦测、占用进程定位、一键强杀、Hosts 多方案管理与 DNS 缓存刷新。
"""

import os
import re
import sys
import subprocess
from typing import List, Dict, Tuple, Optional, Any


def get_process_map() -> Dict[int, str]:
    """获取本机所有正在运行的 PID -> 进程名 映射表"""
    pid_map = {}
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
            creationflags=creationflags
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = [p.strip(' "') for p in line.split('","')]
                if len(parts) >= 2:
                    name = parts[0]
                    try:
                        pid = int(parts[1])
                        pid_map[pid] = name
                    except ValueError:
                        pass
    except Exception:
        pass
    return pid_map


def scan_listening_ports() -> List[Dict[str, Any]]:
    """
    扫描本机所有处于侦听状态的端口 (TCP LISTENING 及 UDP)
    返回字典列表: [{proto, ip, port, state, pid, process_name}]
    """
    results = []
    pid_names = get_process_map()
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    try:
        proc = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
            creationflags=creationflags
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                line = line.strip()
                if not line or line.startswith("活动连接") or line.startswith("Active Connections") or line.startswith("协议"):
                    continue

                parts = line.split()
                if len(parts) < 4:
                    continue

                proto = parts[0].upper()
                if proto not in ("TCP", "UDP"):
                    continue

                local_addr = parts[1]
                state = ""
                pid = 0

                if proto == "TCP":
                    if len(parts) >= 5:
                        state = parts[3]
                        try:
                            pid = int(parts[4])
                        except ValueError:
                            pid = 0
                    if state.upper() != "LISTENING":
                        continue
                else:  # UDP
                    state = "LISTENING"
                    try:
                        pid = int(parts[-1])
                    except ValueError:
                        pid = 0

                # 提取 IP 与端口
                if ":" in local_addr:
                    ip, port_str = local_addr.rsplit(":", 1)
                    try:
                        port = int(port_str)
                    except ValueError:
                        continue
                else:
                    continue

                proc_name = pid_names.get(pid, "未知系统进程" if pid <= 4 else f"PID-{pid}")

                results.append({
                    "proto": proto,
                    "ip": ip,
                    "port": port,
                    "state": state,
                    "pid": pid,
                    "process_name": proc_name
                })
    except Exception as e:
        print(f"[PortSentinel] 扫描端口失败: {e}")

    # 按端口号升序排序
    results.sort(key=lambda x: (x["port"], x["proto"]))
    return results


def kill_process_by_pid(pid: int) -> Tuple[bool, str]:
    """强行终止指定 PID 进程"""
    if pid <= 4:
        return False, "受保护的 Windows 系统核心进程，禁止终止"
    if pid == os.getpid():
        return False, "受保护的千绘莉工具箱自身进程，禁止终止"

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
            creationflags=creationflags
        )
        if proc.returncode == 0:
            return True, f"成功强行结束进程 PID {pid}"
        else:
            return False, f"终止失败: {proc.stderr.strip() or proc.stdout.strip()}"
    except Exception as e:
        return False, f"执行异常: {e}"


def get_hosts_path() -> str:
    """获取 Windows 系统 hosts 文件绝对路径"""
    windir = os.environ.get("WINDIR", r"C:\Windows")
    return os.path.join(windir, "System32", "drivers", "etc", "hosts")


def read_hosts_file() -> str:
    """读取 hosts 文件内容"""
    hp = get_hosts_path()
    if not os.path.isfile(hp):
        return "# hosts 文件不存在"
    try:
        with open(hp, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"# 读取 hosts 失败: {e}"


def save_hosts_file(content: str) -> Tuple[bool, str]:
    """保存 hosts 文件并自动生成备份"""
    hp = get_hosts_path()
    try:
        # 生成备份
        bak_path = hp + ".ctbak"
        if os.path.isfile(hp):
            import shutil
            shutil.copy2(hp, bak_path)

        with open(hp, "w", encoding="utf-8") as f:
            f.write(content)
        return True, "Hosts 文件已成功保存"
    except PermissionError:
        return False, "权限不足！修改系统 Hosts 需要以管理员身份运行千绘莉工具箱。"
    except Exception as e:
        return False, f"写入 Hosts 异常: {e}"


def flush_dns_cache() -> Tuple[bool, str]:
    """刷新本地 DNS 解析缓存"""
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            ["ipconfig", "/flushdns"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
            creationflags=creationflags
        )
        if proc.returncode == 0:
            return True, "DNS 解析缓存已成功刷新！"
        else:
            return False, f"刷新失败: {proc.stderr}"
    except Exception as e:
        return False, f"刷新异常: {e}"
