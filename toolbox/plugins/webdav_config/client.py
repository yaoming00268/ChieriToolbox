"""
WebDAV 核心协议驱动与客户端 (WebDAV Client)
兼容 OpenList / AList 内核、Nextcloud、坚果云及标准 RFC 4918 WebDAV 协议。
提供连通探测、目录元数据列取、文件流传输与 Windows 网络映射脚本生成。
"""

import os
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Dict, Tuple, Optional, Any
import requests
from requests.auth import HTTPBasicAuth


def _clean_tag(tag: str) -> str:
    """去除 XML 命名空间前缀，如 {DAV:}response -> response"""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def format_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class WebDAVClient:
    def __init__(self, base_url: str, username: str = "", password: str = "", timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        if self.username:
            self.session.auth = HTTPBasicAuth(self.username, self.password)

    def _get_full_url(self, path: str) -> str:
        clean_path = path.lstrip("/")
        if not clean_path:
            return self.base_url + "/"
        return f"{self.base_url}/{clean_path}"

    def test_connection(self) -> Tuple[bool, str, Dict[str, str]]:
        """探测 WebDAV 服务端连通性与返回头信息"""
        try:
            target_url = self._get_full_url("")
            # 优先使用 PROPFIND 深度 0
            headers = {"Depth": "0"}
            resp = self.session.request("PROPFIND", target_url, headers=headers, timeout=self.timeout)
            if resp.status_code in (200, 207):
                server_type = resp.headers.get("Server", "WebDAV Server")
                dav_headers = resp.headers.get("DAV", "1, 2")
                return True, f"连接成功！HTTP {resp.status_code} ({server_type})", dict(resp.headers)
            elif resp.status_code == 401:
                return False, "认证失败 (HTTP 401 Unauthorized)，请检查用户名或密码", {}
            elif resp.status_code == 404:
                return False, f"目标路径不存在 (HTTP 404 Not Found): {target_url}", {}
            else:
                # 尝试 OPTIONS 作为退避验证
                opt_resp = self.session.options(target_url, timeout=self.timeout)
                if opt_resp.status_code < 400:
                    return True, f"连通就绪！HTTP OPTIONS {opt_resp.status_code}", dict(opt_resp.headers)
                return False, f"服务端返回错误状态码: HTTP {resp.status_code}", {}
        except requests.exceptions.ConnectionError as e:
            return False, f"连接被拒绝或主机无法访问: {e}", {}
        except requests.exceptions.Timeout:
            return False, f"连接超时 (超过 {self.timeout} 秒未响应)", {}
        except Exception as e:
            return False, f"探测异常: {e}", {}

    def list_dir(self, remote_path: str = "/") -> Tuple[bool, str, List[Dict[str, Any]]]:
        """列取指定远端目录下的文件与子目录"""
        try:
            target_url = self._get_full_url(remote_path)
            headers = {"Depth": "1"}
            resp = self.session.request("PROPFIND", target_url, headers=headers, timeout=self.timeout)

            if resp.status_code not in (200, 207):
                return False, f"获取目录失败: HTTP {resp.status_code}", []

            root = ET.fromstring(resp.content)
            items = []
            target_parsed = urllib.parse.urlparse(target_url)
            norm_target_path = target_parsed.path.rstrip("/")

            for resp_node in root:
                if _clean_tag(resp_node.tag) != "response":
                    continue

                href = ""
                display_name = ""
                is_dir = False
                size = 0
                modified = ""

                for child in resp_node:
                    tag = _clean_tag(child.tag)
                    if tag == "href":
                        href = child.text or ""
                    elif tag == "propstat":
                        for prop_node in child:
                            if _clean_tag(prop_node.tag) == "prop":
                                for val_node in prop_node:
                                    v_tag = _clean_tag(val_node.tag)
                                    if v_tag == "displayname":
                                        display_name = val_node.text or ""
                                    elif v_tag == "resourcetype":
                                        for rt in val_node:
                                            if _clean_tag(rt.tag) == "collection":
                                                is_dir = True
                                    elif v_tag == "getcontentlength":
                                        try:
                                            size = int(val_node.text or 0)
                                        except ValueError:
                                            size = 0
                                    elif v_tag == "getlastmodified":
                                        modified = val_node.text or ""

                # 排除当前请求目录自身 (深度 1 会包含自身节点)
                parsed_href = urllib.parse.urlparse(href)
                norm_href = parsed_href.path.rstrip("/")
                if norm_href == norm_target_path or not norm_href:
                    continue

                if not display_name:
                    display_name = urllib.parse.unquote(norm_href.split("/")[-1])

                items.append({
                    "name": display_name,
                    "href": href,
                    "is_dir": is_dir,
                    "size": size,
                    "modified": modified
                })

            # 目录置顶，按名称升序排列
            items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            return True, "", items
        except Exception as e:
            return False, f"解析目录结构异常: {e}", []

    def download_file(self, remote_path: str, local_path: str) -> Tuple[bool, str]:
        """下载远端文件"""
        try:
            target_url = self._get_full_url(remote_path)
            os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
            with self.session.get(target_url, stream=True, timeout=self.timeout * 3) as r:
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
            return True, ""
        except Exception as e:
            return False, str(e)

    def upload_file(self, local_path: str, remote_path: str) -> Tuple[bool, str]:
        """上传本地文件至远端"""
        try:
            target_url = self._get_full_url(remote_path)
            with open(local_path, "rb") as f:
                resp = self.session.put(target_url, data=f, timeout=self.timeout * 3)
            if resp.status_code in (200, 201, 204):
                return True, ""
            return False, f"HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, str(e)

    def create_directory(self, remote_path: str) -> Tuple[bool, str]:
        """在远端创建文件夹 (MKCOL)"""
        try:
            target_url = self._get_full_url(remote_path)
            resp = self.session.request("MKCOL", target_url, timeout=self.timeout)
            if resp.status_code in (201, 200):
                return True, ""
            return False, f"创建目录失败: HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def delete_item(self, remote_path: str) -> Tuple[bool, str]:
        """删除远端文件或目录 (DELETE)"""
        try:
            target_url = self._get_full_url(remote_path)
            resp = self.session.delete(target_url, timeout=self.timeout)
            if resp.status_code in (200, 204):
                return True, ""
            return False, f"删除失败: HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)


# -------------------------------------------------------------
# Windows 资源管理器网络驱动器挂载助手
# -------------------------------------------------------------
def get_windows_mount_cmd(drive_letter: str, url: str, username: str, password: str) -> str:
    """生成 Windows net use 命令行指令"""
    dl = drive_letter.rstrip(":").upper()
    cmd = f'net use {dl}: "{url}"'
    if password:
        cmd += f' "{password}"'
    if username:
        cmd += f' /user:"{username}"'
    cmd += " /persistent:yes"
    return cmd


def mount_webdav_as_drive(drive_letter: str, url: str, username: str, password: str) -> Tuple[bool, str]:
    """调用系统 net use 执行挂载"""
    dl = drive_letter.rstrip(":").upper()
    cmd = ["net", "use", f"{dl}:", url]
    if password:
        cmd.append(password)
    if username:
        cmd.append(f"/user:{username}")
    cmd.append("/persistent:yes")

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            cmd,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            text=True,
            encoding="gbk",
            errors="replace",
            timeout=15
        )
        if proc.returncode == 0:
            return True, f"已成功将 WebDAV 映射为本地盘符 [{dl}:]"
        return False, f"挂载失败: {proc.stderr.strip() or proc.stdout.strip()}"
    except Exception as e:
        return False, f"执行命令异常: {e}"


def unmount_webdav_drive(drive_letter: str) -> Tuple[bool, str]:
    """卸载指定盘符"""
    dl = drive_letter.rstrip(":").upper()
    cmd = ["net", "use", f"{dl}:", "/delete", "/y"]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            cmd,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            text=True,
            timeout=15
        )
        if proc.returncode == 0:
            return True, f"已成功断开盘符 [{dl}:]"
        return False, f"断开失败: {proc.stderr.strip()}"
    except Exception as e:
        return False, f"卸载异常: {e}"
