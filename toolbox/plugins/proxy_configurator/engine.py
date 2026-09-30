"""
应用代理配置工具核心引擎
提供 Windows 系统代理、环境变量代理 (HTTP/HTTPS)、Git 全局代理与 pip 镜像/代理的读取、写入与网络延时检测。
"""

import ctypes
from ctypes import wintypes
import os
import shutil
import subprocess
import time
from typing import Dict, Optional, Tuple, List, Any
import winreg
import requests

INTERNET_OPTION_SETTINGS_CHANGED = 39
INTERNET_OPTION_REFRESH = 37

PIP_MIRRORS = {
    "清华大学源 (Tsinghua)": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "阿里云镜像 (Aliyun)": "https://mirrors.aliyun.com/pypi/simple/",
    "腾讯云镜像 (Tencent)": "https://mirrors.cloud.tencent.com/pypi/simple/",
    "中科大源 (USTC)": "https://pypi.mirrors.ustc.edu.cn/simple/",
    "Python 官方源 (PyPI)": "https://pypi.org/simple"
}


def refresh_system_internet_options():
    """通知 Windows 系统 Internet 设置已变更，使代理立即对 Edge、Chrome 及系统组件生效"""
    try:
        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
        wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
    except Exception:
        pass


def broadcast_environment_change():
    """广播 WM_SETTINGCHANGE 消息，通知所有进程环境变量已更新"""
    try:
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        result = wintypes.DWORD()
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            1000,
            ctypes.byref(result)
        )
    except Exception:
        pass


# -------------------------------------------------------------
# 1. Windows 系统代理 (System Proxy)
# -------------------------------------------------------------
def get_system_proxy_status() -> Dict:
    reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ) as key:
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            try:
                server, _ = winreg.QueryValueEx(key, "ProxyServer")
            except FileNotFoundError:
                server = ""
            try:
                override, _ = winreg.QueryValueEx(key, "ProxyOverride")
            except FileNotFoundError:
                override = ""

            return {
                "enabled": bool(enabled),
                "server": server,
                "override": override
            }
    except Exception as e:
        return {"enabled": False, "server": "", "override": "", "error": str(e)}


def set_system_proxy(
    enabled: bool,
    server: str = "",
    override: str = "<local>;localhost;127.*;192.168.*"
) -> Tuple[bool, str]:
    reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1 if enabled else 0)
            if server:
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, server)
            if override:
                winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, override)

        refresh_system_internet_options()
        status_text = f"系统代理已开启: {server}" if enabled else "系统代理已停用"
        return True, status_text
    except Exception as e:
        return False, f"修改系统代理注册表失败: {str(e)}"


# -------------------------------------------------------------
# 2. 用户环境变量代理 (HTTP_PROXY / HTTPS_PROXY)
# -------------------------------------------------------------
def get_env_proxy_status() -> Dict:
    env_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    reg_path = r"Environment"
    values = {}
    has_any = False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ) as key:
            for k in env_keys:
                try:
                    val, _ = winreg.QueryValueEx(key, k)
                    values[k] = val
                    if val:
                        has_any = True
                except FileNotFoundError:
                    values[k] = ""
    except Exception:
        for k in env_keys:
            values[k] = os.environ.get(k, "")
            if values[k]:
                has_any = True

    return {
        "enabled": has_any,
        "http": values.get("HTTP_PROXY", ""),
        "https": values.get("HTTPS_PROXY", ""),
        "all": values.get("ALL_PROXY", "")
    }


def set_env_proxy(enabled: bool, proxy_addr: str = "") -> Tuple[bool, str]:
    reg_path = r"Environment"
    env_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_ALL_ACCESS) as key:
            for k in env_keys:
                if enabled and proxy_addr:
                    # 补齐协议前缀
                    formatted = proxy_addr if proxy_addr.startswith("http") or proxy_addr.startswith("socks") else f"http://{proxy_addr}"
                    winreg.SetValueEx(key, k, 0, winreg.REG_SZ, formatted)
                    os.environ[k] = formatted
                else:
                    try:
                        winreg.DeleteValue(key, k)
                    except FileNotFoundError:
                        pass
                    if k in os.environ:
                        del os.environ[k]

        broadcast_environment_change()
        status_text = f"环境变量代理已配置: {proxy_addr}" if enabled else "环境变量代理已清除"
        return True, status_text
    except Exception as e:
        return False, f"配置用户环境变量失败: {str(e)}"


# -------------------------------------------------------------
# 3. Git 全局代理 (Git Proxy)
# -------------------------------------------------------------
def get_git_proxy_status() -> Dict:
    git_bin = shutil.which("git")
    if not git_bin:
        return {"installed": False, "enabled": False, "http": "", "https": ""}

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    http_proxy = ""
    try:
        p = subprocess.run(
            [git_bin, "config", "--global", "--get", "http.proxy"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            text=True
        )
        if p.returncode == 0:
            http_proxy = p.stdout.strip()
    except Exception:
        pass

    return {
        "installed": True,
        "enabled": bool(http_proxy),
        "http": http_proxy
    }


def set_git_proxy(enabled: bool, proxy_addr: str = "") -> Tuple[bool, str]:
    git_bin = shutil.which("git")
    if not git_bin:
        return False, "系统未找到 git 命令，可能未安装或未加入 PATH。"

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        if enabled and proxy_addr:
            formatted = proxy_addr if (proxy_addr.startswith("http") or proxy_addr.startswith("socks5")) else f"http://{proxy_addr}"
            subprocess.run([git_bin, "config", "--global", "http.proxy", formatted], check=True, creationflags=creationflags)
            subprocess.run([git_bin, "config", "--global", "https.proxy", formatted], check=True, creationflags=creationflags)
            return True, f"Git 全局代理已设为: {formatted}"
        else:
            subprocess.run([git_bin, "config", "--global", "--unset", "http.proxy"], creationflags=creationflags)
            subprocess.run([git_bin, "config", "--global", "--unset", "https.proxy"], creationflags=creationflags)
            return True, "Git 全局代理已清除。"
    except Exception as e:
        return False, f"配置 Git 代理失败: {str(e)}"


# -------------------------------------------------------------
# 4. Pip 代理与镜像源 (Pip Proxy & Mirrors)
# -------------------------------------------------------------
def _get_pip_executable() -> str:
    """自适应探测 Python / Pip 执行程序，兼顾源码开发态与便携打包态"""
    try:
        from toolbox.core.paths import get_app_root
        venv_py = os.path.join(get_app_root(), ".venv", "Scripts", "python.exe")
        if os.path.isfile(venv_py):
            return venv_py
    except Exception:
        pass
    py = shutil.which("python") or shutil.which("python3")
    return py if py else "python"


def get_pip_status() -> Dict:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    py_exe = _get_pip_executable()

    proxy_val = ""
    index_val = ""
    try:
        p = subprocess.run([py_exe, "-m", "pip", "config", "get", "global.proxy"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags, text=True)
        if p.returncode == 0:
            proxy_val = p.stdout.strip()

        p2 = subprocess.run([py_exe, "-m", "pip", "config", "get", "global.index-url"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags, text=True)
        if p2.returncode == 0:
            index_val = p2.stdout.strip()
    except Exception:
        pass

    return {
        "enabled": bool(proxy_val),
        "proxy": proxy_val,
        "index_url": index_val
    }


def set_pip_proxy(enabled: bool, proxy_addr: str = "") -> Tuple[bool, str]:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    py_exe = _get_pip_executable()

    try:
        if enabled and proxy_addr:
            formatted = proxy_addr if proxy_addr.startswith("http") or proxy_addr.startswith("socks5") else f"http://{proxy_addr}"
            subprocess.run([py_exe, "-m", "pip", "config", "set", "global.proxy", formatted], check=True, creationflags=creationflags)
            return True, f"Pip 代理已配置为: {formatted}"
        else:
            subprocess.run([py_exe, "-m", "pip", "config", "unset", "global.proxy"], creationflags=creationflags)
            return True, "Pip 代理已清除。"
    except Exception as e:
        return False, f"设置 Pip 代理失败: {str(e)}"


def set_pip_mirror(mirror_url: str) -> Tuple[bool, str]:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    py_exe = _get_pip_executable()

    try:
        subprocess.run([py_exe, "-m", "pip", "config", "set", "global.index-url", mirror_url], check=True, creationflags=creationflags)
        return True, f"Pip 镜像源已切换至: {mirror_url}"
    except Exception as e:
        return False, f"设置 Pip 镜像源失败: {str(e)}"


# -------------------------------------------------------------
# 5. 代理连通性与延时测速 (Latency Test)
# -------------------------------------------------------------
def test_proxy_latency(proxy_addr: str, test_url: str = "https://github.com") -> Tuple[bool, float, str]:
    """通过指定代理测试网络连通性与延时"""
    proxies = None
    if proxy_addr:
        formatted = proxy_addr if proxy_addr.startswith("http") or proxy_addr.startswith("socks") else f"http://{proxy_addr}"
        proxies = {
            "http": formatted,
            "https": formatted
        }

    start = time.time()
    try:
        resp = requests.get(test_url, proxies=proxies, timeout=5)
        elapsed_ms = (time.time() - start) * 1000
        if resp.status_code < 400:
            return True, elapsed_ms, f"连接成功 (HTTP {resp.status_code})"
        else:
            return False, elapsed_ms, f"响应状态码异常 (HTTP {resp.status_code})"
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        return False, elapsed_ms, f"连接超时或失败: {str(e)}"


# -------------------------------------------------------------
# 6. 单独网站/域名代理路由与根网址适配算法 (Per-Website Proxy)
# -------------------------------------------------------------
def extract_root_domain(url_or_domain: str) -> str:
    """
    从给定的完整 URL 或域名中提取根网址 (Root Domain)。
    无论填入完整 URL (https://api.github.com/v1) 还是子网址 (sub.domain.com)，
    均自适应解析提取根网址，使所有子网址与子路由适应填入的根网址代理。
    """
    from urllib.parse import urlparse
    raw = url_or_domain.strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "http://" + raw
    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").strip()
    except Exception:
        host = url_or_domain.strip().lower().split("/")[0]

    if ":" in host:
        host = host.split(":")[0]

    parts = host.split(".")
    # 若是 IP 地址，直接作为根目标
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return host

    common_second_level = {
        "com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "ac.cn", "mil.cn",
        "bj.cn", "sh.cn", "tj.cn", "cq.cn", "he.cn", "sx.cn", "nm.cn", "ln.cn",
        "jl.cn", "hl.cn", "js.cn", "zj.cn", "ah.cn", "fj.cn", "jx.cn", "sd.cn",
        "ha.cn", "hb.cn", "hn.cn", "gd.cn", "gx.cn", "hi.cn", "sc.cn", "gz.cn",
        "yn.cn", "xz.cn", "sn.cn", "gs.cn", "qh.cn", "nx.cn", "xj.cn", "tw.cn",
        "hk.cn", "mo.cn",
        "com.tw", "org.tw", "edu.tw", "net.tw", "gov.tw",
        "com.hk", "org.hk", "edu.hk", "net.hk", "gov.hk",
        "co.uk", "org.uk", "ac.uk", "gov.uk", "net.uk",
        "co.jp", "ne.jp", "ac.jp", "go.jp", "or.jp",
        "co.kr", "ne.kr", "ac.kr", "re.kr", "go.kr",
        "com.au", "net.au", "org.au", "edu.au", "gov.au",
        "co.nz", "net.nz", "org.nz", "govt.nz",
        "com.sg", "net.sg", "org.sg", "edu.sg", "gov.sg",
        "com.my", "net.my", "org.my", "edu.my", "gov.my"
    }
    if len(parts) >= 3:
        two_level = ".".join(parts[-2:])
        if two_level in common_second_level and len(parts) >= 3:
            return ".".join(parts[-3:])
        return ".".join(parts[-2:])
    return host


def matches_root_domain(target_url_or_host: str, root_domain: str) -> bool:
    """判断给定的 URL/域名 是否适应或归属于指定的根网址 (所有子网址适应根网址代理)"""
    tgt = extract_root_domain(target_url_or_host)
    clean_rd = extract_root_domain(root_domain) or root_domain.strip().lower()
    if not tgt or not clean_rd:
        return False
    if tgt == clean_rd or tgt.endswith("." + clean_rd):
        return True
    from urllib.parse import urlparse
    raw = target_url_or_host.strip().lower()
    if "://" not in raw:
        raw = "http://" + raw
    try:
        host = (urlparse(raw).hostname or "").strip()
    except Exception:
        host = ""
    if host and (host == clean_rd or host.endswith("." + clean_rd)):
        return True
    return False


def generate_pac_script(proxy_addr: str, root_domains: List[str]) -> str:
    """生成标准 PAC (Proxy Auto-Config) 脚本，使已配置的根网址及其所有子域名和子页面走代理，其余直连"""
    if not proxy_addr:
        proxy_stmt = "DIRECT"
    elif proxy_addr.startswith("PROXY") or proxy_addr.startswith("SOCKS"):
        proxy_stmt = f"{proxy_addr}; DIRECT"
    else:
        proxy_stmt = f"PROXY {proxy_addr}; DIRECT"

    clean_domains = []
    for d in root_domains:
        rd = extract_root_domain(d) or d.strip().lower()
        if rd and rd not in clean_domains:
            clean_domains.append(rd)
    clean_domains.sort()

    domains_js = ",\n        ".join(f'"{d}"' for d in clean_domains)
    return f"""// ChieriToolbox PAC Auto-Generated Routing Script
function FindProxyForURL(url, host) {{
    host = (host || "").toLowerCase();
    var rootDomains = [
        {domains_js}
    ];

    for (var i = 0; i < rootDomains.length; i++) {{
        var rd = rootDomains[i];
        if (!rd) continue;
        if (host === rd || dnsDomainIs(host, "." + rd)) {{
            return "{proxy_stmt}";
        }}
    }}
    return "DIRECT";
}}
"""


def export_pac_file(save_path: str, proxy_addr: str, root_domains: List[str]) -> Tuple[bool, str]:
    """生成并导出 PAC 脚本文件至指定磁盘路径"""
    try:
        content = generate_pac_script(proxy_addr, root_domains)
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True, f"PAC 脚本已成功导出至: {save_path}"
    except Exception as e:
        return False, f"导出 PAC 脚本失败: {e}"


def get_pac_proxy_status() -> Dict[str, Any]:
    """获取当前 Windows 系统 PAC 自动配置脚本状态"""
    reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ) as key:
            try:
                autoconfig_url, _ = winreg.QueryValueEx(key, "AutoConfigURL")
            except FileNotFoundError:
                autoconfig_url = ""
            return {"enabled": bool(autoconfig_url), "pac_url": autoconfig_url}
    except Exception as e:
        return {"enabled": False, "pac_url": "", "error": str(e)}


def set_pac_proxy(enabled: bool, pac_file_or_url: str = "") -> Tuple[bool, str]:
    """配置或清除 Windows 系统 Internet Settings 的 PAC 自动分流脚本 (AutoConfigURL)"""
    reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled and pac_file_or_url:
                if os.path.isabs(pac_file_or_url):
                    norm = pac_file_or_url.replace("\\", "/")
                    pac_uri = f"file:///{norm}"
                else:
                    pac_uri = pac_file_or_url
                winreg.SetValueEx(key, "AutoConfigURL", 0, winreg.REG_SZ, pac_uri)
                status_text = f"系统 PAC 智能分流已启用: {pac_uri}"
            else:
                try:
                    winreg.DeleteValue(key, "AutoConfigURL")
                except FileNotFoundError:
                    pass
                status_text = "系统 PAC 智能分流已停用"

        refresh_system_internet_options()
        return True, status_text
    except Exception as e:
        return False, f"配置系统 PAC 脚本失败: {e}"



# -------------------------------------------------------------
# 7. 注册表应用扫描与单独应用代理启动 (Per-App Proxy)
# -------------------------------------------------------------
def scan_registry_installed_apps() -> List[Dict[str, str]]:
    """扫描 Windows 注册表已安装软件列表 (HKLM & HKCU, 包含 32/64 位)"""
    apps = []
    seen = set()
    import re

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


def launch_app_with_proxy(exe_path: str, proxy_addr: str) -> Tuple[bool, str]:
    """以独立进程注入 HTTP/HTTPS 代理环境及 Chromium 代理参数启动应用程序"""
    if not os.path.isfile(exe_path):
        return False, f"未找到可执行文件: {exe_path}"

    env = os.environ.copy()
    formatted = ""
    if proxy_addr:
        formatted = proxy_addr if proxy_addr.startswith("http") or proxy_addr.startswith("socks") else f"http://{proxy_addr}"
        env["HTTP_PROXY"] = formatted
        env["HTTPS_PROXY"] = formatted
        env["ALL_PROXY"] = formatted

    cmd = [exe_path]
    if formatted:
        cmd.append(f"--proxy-server={formatted}")

    try:
        subprocess.Popen(cmd, env=env, cwd=os.path.dirname(exe_path))
        return True, f"已成功以代理环境启动: {os.path.basename(exe_path)}"
    except Exception as e:
        return False, f"启动应用异常: {str(e)}"

