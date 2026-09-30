"""
千绘莉多功能工具箱 (Chieri Toolbox) - 独立插件应用运行引导引擎 (Standalone Runner)
支持任一插件脱离主工具箱独立运行，具备专属设置接口、开机自启集成、独立托盘快捷栏及UI参数调节。
"""

import os
import sys
import argparse
from typing import Optional

# 确保项目根目录在 sys.path 中
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStatusBar, QMessageBox
)

from toolbox.core.config_manager import ConfigManager
from toolbox.core.plugin_manager import PluginManager
from toolbox.core.plugin_base import PluginBase
from toolbox.core.theme import ThemeManager
from toolbox.core.window_effects import apply_dual_opacity, apply_acrylic_effect
from toolbox.core.tray_manager import PluginTrayIcon
from toolbox.ui.icons import get_icon, get_pixmap, get_plugin_badge_pixmap
from toolbox.ui.standalone_settings_dialog import StandalonePluginSettingsDialog


class StandalonePluginMainWindow(QMainWindow):
    """
    独立插件运行态主窗口
    """
    def __init__(self, plugin: PluginBase, autostart: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.plugin = plugin
        self.autostart = autostart
        self.config_manager = ConfigManager()
        self.theme_manager = ThemeManager()
        self.tray_icon: Optional[PluginTrayIcon] = None
        self._force_exit = False

        self.init_window()
        self.init_ui()
        self.init_tray()
        self.apply_visual_settings()

    def init_window(self):
        self.setWindowTitle(f"{self.plugin.name} - 独立应用")
        self.setWindowIcon(self.plugin.get_icon(size=32))

        # 记忆并恢复独立窗口尺寸与位置
        geom_key = f"standalone_geom_{self.plugin.id}"
        geom = self.config_manager.get(geom_key)
        if isinstance(geom, dict) and "w" in geom and "h" in geom:
            self.resize(geom.get("w", 980), geom.get("h", 680))
            if "x" in geom and "y" in geom and geom["x"] >= 0 and geom["y"] >= 0:
                self.move(geom["x"], geom["y"])
        else:
            self.resize(980, 680)

        self.setMinimumSize(640, 480)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 顶部轻量级功能条 (图标、标题、独立设置按钮)
        top_bar = QWidget()
        top_bar.setObjectName("standaloneTopBar")
        top_bar.setFixedHeight(46)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 0, 16, 0)
        top_layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_plugin_badge_pixmap(self.plugin.id, size=22))
        top_layout.addWidget(icon_lbl)

        title_lbl = QLabel(f"{self.plugin.name} · 独立模式")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        top_layout.addWidget(title_lbl)

        top_layout.addStretch()

        btn_settings = QPushButton("独立设置")
        btn_settings.setIcon(get_icon("settings", size=14))
        btn_settings.clicked.connect(self.open_settings_dialog)
        top_layout.addWidget(btn_settings)

        main_layout.addWidget(top_bar)

        # 挂载插件 Widget
        widget = self.plugin.get_widget(central)
        main_layout.addWidget(widget, 1)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"「{self.plugin.name}」独立运行中 · 随开随用")

        # 激活插件
        try:
            self.plugin.on_activated()
        except Exception as e:
            print(f"[StandaloneRunner] 激活插件 [{self.plugin.id}] 异常: {e}")

    def init_tray(self):
        cfg_key = f"standalone_{self.plugin.id}"
        cfg = self.config_manager.get(cfg_key, {})
        enable_tray = cfg.get("enable_tray", True)
        if enable_tray:
            self.tray_icon = PluginTrayIcon(
                plugin=self.plugin,
                parent=self,
                on_open_callback=self.restore_and_activate,
                on_settings_callback=self.open_settings_dialog,
                on_exit_callback=self.exit_application,
                on_export_callback=None
            )
            self.tray_icon.show()

    def restore_and_activate(self):
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def open_settings_dialog(self):
        dialog = StandalonePluginSettingsDialog(self.plugin, self)
        dialog.settings_applied.connect(self.apply_visual_settings)
        dialog.exec()

    def apply_visual_settings(self):
        cfg_key = f"standalone_{self.plugin.id}"
        cfg = self.config_manager.get(cfg_key, {})

        theme_val = cfg.get("theme")
        if theme_val:
            self.theme_manager.set_mode(theme_val)

        bg_op = float(cfg.get("bg_opacity", self.config_manager.get_bg_opacity()))
        comp_op = float(cfg.get("component_opacity", self.config_manager.get_component_opacity()))
        apply_dual_opacity(self, bg_opacity=bg_op, component_opacity=comp_op)

        acrylic = bool(cfg.get("acrylic_enabled", self.config_manager.get_acrylic_enabled()))
        blur = int(cfg.get("blur_level", self.config_manager.get_blur_level()))
        apply_acrylic_effect(self, enabled=acrylic, blur_level=blur, is_dark=self.theme_manager.is_dark())

    def closeEvent(self, event):
        cfg_key = f"standalone_{self.plugin.id}"
        cfg = self.config_manager.get(cfg_key, {})
        close_to_tray = cfg.get("close_to_tray", False)

        if not self._force_exit and close_to_tray and self.tray_icon and self.tray_icon.isVisible():
            # 最小化至系统托盘常驻
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                self.plugin.name,
                "应用已最小化到系统托盘，右键可调出功能快捷栏或退出。",
                get_icon(self.plugin.icon, size=16),
                2000
            )
            return

        # 真正退出
        self.config_manager.set(f"standalone_geom_{self.plugin.id}", {
            "x": self.x(),
            "y": self.y(),
            "w": self.width(),
            "h": self.height()
        })

        try:
            self.plugin.on_deactivated()
            self.plugin.cleanup()
        except Exception:
            pass

        if self.tray_icon:
            self.tray_icon.hide()
            self.tray_icon.deleteLater()

        super().closeEvent(event)
        QApplication.quit()

    def exit_application(self):
        # 强制退出，无视 close_to_tray 且不篡改持久化配置
        self._force_exit = True
        self.close()
        QApplication.quit()


def launch_standalone(plugin_id: str, autostart: bool = False, initial_paths: Optional[list] = None) -> int:
    """启动独立插件应用主入口"""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(f"ChieriPlugin_{plugin_id}")
    app.setOrganizationName("Chieri")
    app.setQuitOnLastWindowClosed(False)

    theme_mgr = ThemeManager()
    theme_mgr.setup(app)

    cfg_key = f"standalone_{plugin_id}"
    cfg = ConfigManager().get(cfg_key, {})
    saved_theme = cfg.get("theme")
    if saved_theme:
        theme_mgr.set_mode(saved_theme)

    pm = PluginManager()
    plugin = pm.load_single_plugin(plugin_id) or pm.get_plugin(plugin_id)
    if not plugin:
        pm.discover_and_load()
        plugin = pm.get_plugin(plugin_id)

    if not plugin:
        QMessageBox.critical(None, "错误", f"未能找到插件 [{plugin_id}]，无法独立启动。")
        return 1

    win = StandalonePluginMainWindow(plugin, autostart=autostart)

    if initial_paths:
        plugin.handle_initial_paths(initial_paths)

    start_minimized = cfg.get("start_minimized", False) and autostart
    if not start_minimized:
        win.show()
    else:
        # 静默后台自启，托盘就绪
        if win.tray_icon:
            win.tray_icon.showMessage(
                plugin.name,
                "已随系统开机自启并在托盘就绪。",
                get_icon(plugin.icon, size=16),
                2000
            )

    return app.exec()


def main():
    parser = argparse.ArgumentParser(description="千绘莉工具箱 - 独立插件启动器")
    parser.add_argument("--plugin", "-p", type=str, default="screen_capture", help="要启动的插件唯一标识 ID")
    parser.add_argument("--autostart", action="store_true", help="标识为开机自启调度")
    parser.add_argument("paths", nargs="*", help="外部传入的文件路径或URL参数")
    args, unknown = parser.parse_known_args()

    sys.exit(launch_standalone(args.plugin, autostart=args.autostart, initial_paths=args.paths))


if __name__ == "__main__":
    main()
