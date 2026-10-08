"""
千绘莉工具箱 (Chieri Toolbox) - 双端局域网互联与算力云服务宿主 (Chieri Local Cloud & Chieri Drop)
实现双端无感握手与跨端协作：
1. UDP 局域网服务发现与广播回应 (端口 23333)
2. 轻量高性能 HTTP REST API (端口 8765)
3. 移动端云超分图片处理代理 (/api/upscale)
4. Chieri Drop 局域网无感文件极速互传与全局剪贴板流转 (/api/drop, /api/clipboard)
"""

import os
import sys
import json
import time
import socket
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Dict, Any

from PySide6.QtCore import QObject, Signal

from toolbox.core.paths import get_app_root
from toolbox.core.model_manager import ModelManager
from toolbox.plugins.image_master.upscale_engine import upscale_image_file

DEFAULT_HTTP_PORT = 8765
UDP_DISCOVERY_PORT = 23333


def get_local_ip_addresses() -> list:
    """获取本机所有活跃的局域网 IP 地址"""
    ip_list = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and ":" not in ip:
                ip_list.append(ip)
    except Exception:
        pass
    if not ip_list:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and ip not in ip_list:
                ip_list.append(ip)
        except Exception:
            pass
    return ip_list or ["127.0.0.1"]


class LocalCloudHttpHandler(BaseHTTPRequestHandler):
    server_version = "ChieriLocalCloud/2.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # 静默底层 HTTP 控制台冗余输出
        pass

    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/api/ping", "/ping"):
            self._send_json(200, {
                "ok": True,
                "status": "ok",
                "service": "Chieri Local Cloud",
                "version": "2.1.0",
                "hostname": socket.gethostname(),
                "port": self.server.server_port,
                "timestamp": int(time.time())
            })
        elif path == "/api/models":
            mm = ModelManager()
            models = mm.list_models()
            self._send_json(200, {
                "ok": True,
                "models": models
            })
        elif path == "/api/clipboard":
            # 获取桌面剪贴板内容
            text = ""
            try:
                import pyperclip
                text = pyperclip.paste()
            except Exception:
                pass
            self._send_json(200, {"ok": True, "text": text})
        elif path == "/api/drop/list":
            drop_dir = os.path.join(get_app_root(), "Downloads", "ChieriDrop")
            files = []
            if os.path.isdir(drop_dir):
                for f in os.listdir(drop_dir):
                    fp = os.path.join(drop_dir, f)
                    if os.path.isfile(fp):
                        files.append({
                            "name": f,
                            "size": os.path.getsize(fp),
                            "mtime": int(os.path.getmtime(fp))
                        })
            self._send_json(200, {"ok": True, "files": files})
        else:
            self._send_json(404, {"ok": False, "error": "Endpoint not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get("Content-Length", 0))

        if path == "/api/upscale":
            # 移动端提交的云超分请求
            # Header 可携带元数据: X-Scale, X-Model, X-Block-Size, X-Denoise
            scale = int(self.headers.get("X-Scale", 2))
            model_id = self.headers.get("X-Model", "realesr-animevideov3")
            block_size = int(self.headers.get("X-Block-Size", 1000))
            denoise = self.headers.get("X-Denoise", "conservative")

            if content_length <= 0:
                self._send_json(400, {"ok": False, "error": "Empty image payload"})
                return

            img_bytes = self.rfile.read(content_length)

            # 暂存待超分图像
            tmp_in = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_out_path = tmp_in.name + "_upscaled.png"
            try:
                tmp_in.write(img_bytes)
                tmp_in.close()

                t0 = time.time()
                ok, msg = upscale_image_file(
                    tmp_in.name, tmp_out_path,
                    scale=scale,
                    model_id=model_id,
                    block_size=block_size,
                    denoise_level=denoise
                )

                if not ok or not os.path.isfile(tmp_out_path):
                    self._send_json(500, {"ok": False, "error": f"Upscale failed: {msg}"})
                    return

                cost_time = time.time() - t0
                with open(tmp_out_path, "rb") as out_f:
                    out_bytes = out_f.read()

                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(out_bytes)))
                self.send_header("X-Process-Time", f"{cost_time:.2f}s")
                self.send_header("X-Scale", str(scale))
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(out_bytes)

            finally:
                if os.path.exists(tmp_in.name):
                    try:
                        os.remove(tmp_in.name)
                    except Exception:
                        pass
                if os.path.exists(tmp_out_path):
                    try:
                        os.remove(tmp_out_path)
                    except Exception:
                        pass

        elif path == "/api/drop/send":
            # Chieri Drop 手机投送文件至电脑
            filename = urllib.parse.unquote(self.headers.get("X-Filename", f"mobile_drop_{int(time.time())}.bin"))
            drop_dir = os.path.join(get_app_root(), "Downloads", "ChieriDrop")
            os.makedirs(drop_dir, exist_ok=True)
            dst_path = os.path.join(drop_dir, os.path.basename(filename))

            with open(dst_path, "wb") as f:
                remaining = content_length
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)

            self._send_json(200, {
                "ok": True,
                "message": "文件已成功保存至电脑 Downloads/ChieriDrop",
                "filename": os.path.basename(dst_path),
                "path": dst_path
            })

        elif path == "/api/clipboard":
            # 手机投送剪贴板文本至电脑
            raw_body = self.rfile.read(content_length).decode("utf-8", errors="replace")
            try:
                data = json.loads(raw_body)
                text = data.get("text", "")
            except Exception:
                text = raw_body

            try:
                from PySide6.QtGui import QGuiApplication
                app = QGuiApplication.instance()
                if app:
                    app.clipboard().setText(text)
                else:
                    import pyperclip
                    pyperclip.copy(text)
            except Exception:
                try:
                    import pyperclip
                    pyperclip.copy(text)
                except Exception:
                    pass

            self._send_json(200, {"ok": True, "status": "ok", "message": "剪贴板已同步至电脑"})
        else:
            self._send_json(404, {"ok": False, "error": "Endpoint not found"})


class ChieriLocalCloudService(QObject):
    """
    千绘莉双端局域网服务管理中心 (后台单例)
    """
    _instance = None
    _lock = threading.Lock()

    server_status_changed = Signal(bool, str, int)  # (running, primary_ip, port)
    task_executed = Signal(str, str)               # (task_type, details)

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self, http_port: int = DEFAULT_HTTP_PORT, udp_port: int = UDP_DISCOVERY_PORT):
        if not getattr(self, "_initialized", False):
            self._initialized = True
            super().__init__()
            self._http_server: Optional[ThreadingHTTPServer] = None
            self._http_thread: Optional[threading.Thread] = None
            self._udp_thread: Optional[threading.Thread] = None
            self._is_running = False
        self._port = http_port
        self._udp_port = udp_port

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def port(self) -> int:
        return self._port

    def get_service_urls(self) -> list:
        ips = get_local_ip_addresses()
        return [f"http://{ip}:{self._port}" for ip in ips]

    def start(self, port: Optional[int] = None) -> bool:
        """启动局域网服务快捷入口"""
        return self.start_service(port or self._port)

    def stop(self):
        """停止局域网服务快捷入口"""
        self.stop_service()

    def start_service(self, port: Optional[int] = None) -> bool:
        if self._is_running:
            return True

        target_port = port if port is not None else self._port
        self._port = target_port
        # 尝试绑定 HTTP 端口 (若被占用递增尝试)
        for p in range(target_port, target_port + 10):
            try:
                self._http_server = ThreadingHTTPServer(("0.0.0.0", p), LocalCloudHttpHandler)
                self._port = p
                break
            except OSError:
                continue

        if not self._http_server:
            print("[ChieriLocalCloud] 无法绑定 HTTP 端口")
            return False

        self._is_running = True

        # 启动 HTTP 服务线程
        def _run_http():
            print(f"[ChieriLocalCloud] HTTP 局域网服务已启动，监听端口: {self._port}")
            try:
                self._http_server.serve_forever()
            except Exception:
                pass
            finally:
                self._is_running = False

        self._http_thread = threading.Thread(target=_run_http, daemon=True)
        self._http_thread.start()

        # 启动 UDP 自动发现应答线程
        def _run_udp():
            try:
                udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                udp_sock.bind(("0.0.0.0", self._udp_port))
                udp_sock.settimeout(2.0)
                print(f"[ChieriLocalCloud] UDP 局域网无感发现已监听在端口 {self._udp_port}")

                hostname = socket.gethostname()
                while self._is_running:
                    try:
                        data, addr = udp_sock.recvfrom(1024)
                        msg = data.decode("utf-8", errors="ignore").strip()
                        if "CHIERI_DISCOVER_REQ" in msg:
                            resp = f"CHIERI_DISCOVER_RESP:{self._port}:{hostname}"
                            udp_sock.sendto(resp.encode("utf-8"), addr)
                    except socket.timeout:
                        continue
                    except Exception:
                        pass
                udp_sock.close()
            except Exception as e:
                print(f"[ChieriLocalCloud] UDP 发现模块启动受限: {e}")

        self._udp_thread = threading.Thread(target=_run_udp, daemon=True)
        self._udp_thread.start()

        primary_ip = get_local_ip_addresses()[0]
        self.server_status_changed.emit(True, primary_ip, self._port)
        return True

    def stop_service(self):
        if not self._is_running:
            return

        self._is_running = False
        if self._http_server:
            try:
                self._http_server.shutdown()
                self._http_server.server_close()
            except Exception:
                pass
            self._http_server = None

        primary_ip = get_local_ip_addresses()[0]
        self.server_status_changed.emit(False, primary_ip, self._port)
        print("[ChieriLocalCloud] 局域网服务已停止")
