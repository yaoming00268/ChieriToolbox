import json
import os
import sys
from typing import List, Optional
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from toolbox.core.theme import ThemeManager, apply_theme
from toolbox.core.config_manager import ConfigManager
from toolbox.ui.main_window import MainWindow

SINGLE_INSTANCE_SERVER_NAME = "ChieriToolbox_SingleInstance_App"


def check_and_forward_single_instance(initial_args: Optional[List[str]] = None) -> bool:
    """
    检查是否已有正在运行的工具箱主实例。
    若存在，则通过 QLocalSocket 将外部传入参数透传给已有实例并激活窗口，返回 True 表示当前进程可安全退出。
    """
    try:
        from PySide6.QtWidgets import QApplication
        _app = QApplication.instance()
        if not _app:
            _app = QApplication(sys.argv)
        socket = QLocalSocket()
        socket.connectToServer(SINGLE_INSTANCE_SERVER_NAME)
        if socket.waitForConnected(300):
            payload = json.dumps(initial_args or []).encode("utf-8")
            socket.write(payload)
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
            socket.waitForDisconnected(300)
            return True
    except Exception:
        pass
    return False


class ToolboxApp:
    def __init__(self, argv: List[str]):
        # 高分屏缩放适配
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        self.app = QApplication.instance()
        if not self.app:
            self.app = QApplication(argv)
        self.app.setApplicationName("ChieriToolbox")
        self.app.setOrganizationName("Chieri")
        self.app.setQuitOnLastWindowClosed(False)

        self.config_manager = ConfigManager()
        self.theme_manager = ThemeManager()
        self.theme_manager.setup(self.app)
        self.main_window: Optional[MainWindow] = None

        self.local_server: Optional[QLocalServer] = None
        self._init_single_instance_server()

    def _init_single_instance_server(self):
        try:
            self.local_server = QLocalServer(self.app)
            self.local_server.removeServer(SINGLE_INSTANCE_SERVER_NAME)
            if self.local_server.listen(SINGLE_INSTANCE_SERVER_NAME):
                self.local_server.newConnection.connect(self._on_client_connected)
        except Exception as e:
            print(f"[ToolboxApp] 初始化单实例管道服务异常: {e}")

    def _on_client_connected(self):
        if not self.local_server:
            return
        client = self.local_server.nextPendingConnection()
        if not client:
            return

        has_read = False

        def _read():
            nonlocal has_read
            if has_read:
                return
            try:
                data = client.readAll().data()
                if data:
                    has_read = True
                    args = json.loads(data.decode("utf-8"))
                    self.handle_external_arguments(args)
            except Exception as e:
                print(f"[ToolboxApp] 处理外部透传参数异常: {e}")
            finally:
                if has_read or client.state() == QLocalSocket.UnconnectedState:
                    client.deleteLater()

        client.readyRead.connect(_read)
        client.disconnected.connect(_read)
        if client.bytesAvailable() > 0:
            _read()

    @staticmethod
    def _detect_plugin_for_path(first_p: str) -> str:
        """根据路径特征智能探测对应的插件模块"""
        if first_p.startswith("http") or "BV" in first_p or "b23.tv" in first_p:
            return "media_downloader"
        elif any(first_p.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico", ".tiff", ".gif")):
            return "image_master"
        elif os.path.exists(first_p):
            if os.path.isdir(first_p) and os.path.exists(os.path.join(first_p, "skin.ini")):
                return "osu_skin_studio"
            elif os.path.isfile(first_p) and os.path.basename(first_p).lower() == "skin.ini":
                return "osu_skin_studio"
            else:
                return "file_suite"
        return "file_suite"

    def handle_external_arguments(self, raw_args: List[str]):
        """处理外部或已有实例转发来的命令行参数"""
        if not self.main_window:
            return

        self.main_window.showNormal()
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

        cleaned_paths = [p.strip().strip('"') for p in raw_args] if raw_args else []
        content_paths = [p for p in cleaned_paths if p and not p.startswith("--") and not p.startswith("/")]
        if content_paths:
            plugin_id = self._detect_plugin_for_path(content_paths[0])
            if plugin_id and self.main_window.plugin_manager.get_plugin(plugin_id):
                self.main_window.switch_to_plugin(plugin_id)
                plugin = self.main_window.plugin_manager.get_plugin(plugin_id)
                if plugin:
                    plugin.handle_initial_paths(content_paths)

    def run(self, initial_paths: Optional[List[str]] = None) -> int:
        initial_plugin_id = None
        cleaned_paths = [p.strip().strip('"') for p in initial_paths] if initial_paths else []
        cleaned_paths = [p for p in cleaned_paths if p]

        # 检查是否为开机自启静默模式
        is_autostart = any(arg in sys.argv or arg in cleaned_paths for arg in ("--autostart", "/autostart"))
        # 过滤掉命令行标志参数
        content_paths = [p for p in cleaned_paths if not p.startswith("--") and not p.startswith("/")]

        # 智能根据外部传入参数判断应直接打开的插件
        if content_paths:
            initial_plugin_id = self._detect_plugin_for_path(content_paths[0])

        print("[ToolboxApp] 创建 MainWindow 实例...")
        self.main_window = MainWindow(initial_plugin_id=initial_plugin_id, initial_paths=content_paths)
        print("[ToolboxApp] MainWindow 实例创建完成...")

        if is_autostart:
            print("[ToolboxApp] 检测到开机自启参数 (--autostart)，保持静默后台运行...")
        else:
            print("[ToolboxApp] 正在显示窗口...")
            self.main_window.show()
            print(f"[ToolboxApp] MainWindow.show() 已调用，窗口可见性: {self.main_window.isVisible()}")

        return self.app.exec()
