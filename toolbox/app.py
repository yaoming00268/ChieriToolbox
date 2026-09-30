"""
工具箱 (Toolbox) - 应用程序主生命周期管理器
"""

import os
import sys
from typing import List, Optional
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from toolbox.core.theme import ThemeManager, apply_theme
from toolbox.core.config_manager import ConfigManager
from toolbox.ui.main_window import MainWindow


class ToolboxApp:
    def __init__(self, argv: List[str]):
        # 高分屏缩放适配
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        self.app = QApplication(argv)
        self.app.setApplicationName("ChieriToolbox")
        self.app.setOrganizationName("Chieri")
        self.app.setQuitOnLastWindowClosed(False)

        self.config_manager = ConfigManager()
        self.theme_manager = ThemeManager()
        self.theme_manager.setup(self.app)
        self.main_window: Optional[MainWindow] = None

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
            first_p = content_paths[0]
            if first_p.startswith("http") or "BV" in first_p or "b23.tv" in first_p:
                initial_plugin_id = "media_downloader"
            elif any(first_p.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico", ".tiff", ".gif")):
                initial_plugin_id = "image_master"
            elif os.path.exists(first_p):
                # 如果目录内有 skin.ini，直达 osu 皮肤工具
                if os.path.isdir(first_p) and os.path.exists(os.path.join(first_p, "skin.ini")):
                    initial_plugin_id = "osu_skin_studio"
                elif os.path.isfile(first_p) and os.path.basename(first_p).lower() == "skin.ini":
                    initial_plugin_id = "osu_skin_studio"
                else:
                    initial_plugin_id = "file_suite"

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
