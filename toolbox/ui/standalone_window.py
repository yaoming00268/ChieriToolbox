"""
工具箱 (Toolbox) - 独立多开子窗口 (Plugin Standalone Window)
支持多开模式下将插件承载于独立无依赖的顶级 QMainWindow 中，
并保留主窗口首页随时启动其它工具，各子窗口支持独立记忆位置尺寸与配置。
"""

from typing import Optional, Callable
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QStatusBar
from toolbox.core.plugin_base import PluginBase
from toolbox.core.config_manager import ConfigManager
from toolbox.core.theme import ThemeManager
from toolbox.core.window_effects import apply_window_opacity, apply_dual_opacity, apply_acrylic_effect
from toolbox.ui.icons import get_icon


class PluginStandaloneWindow(QMainWindow):
    window_closed = Signal(str)  # 信号: plugin_id

    def __init__(self, plugin: PluginBase, parent: Optional[QWidget] = None, on_close_callback: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self.plugin = plugin
        self.config_manager = ConfigManager()
        self.theme_manager = ThemeManager()
        self.on_close_callback = on_close_callback

        self.init_ui()
        self.apply_visual_settings()

    def init_ui(self):
        self.setWindowTitle(f"{self.plugin.name} - 千绘莉工具箱")
        self.setWindowIcon(self.plugin.get_icon(size=32))

        # 尝试恢复该插件的历史窗口尺寸与位置
        geom_key = f"window_geom_{self.plugin.id}"
        geom = self.config_manager.get(geom_key)
        if isinstance(geom, dict) and "w" in geom and "h" in geom:
            self.resize(geom.get("w", 980), geom.get("h", 680))
            if "x" in geom and "y" in geom and geom["x"] >= 0 and geom["y"] >= 0:
                self.move(geom["x"], geom["y"])
        else:
            self.resize(980, 680)

        self.setMinimumSize(640, 480)

        # 挂载插件 Widget
        widget = self.plugin.get_widget(self)
        self.setCentralWidget(widget)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"独立窗口模式 · {self.plugin.name} 运行中")

        # 激活插件
        try:
            self.plugin.on_activated()
        except Exception as e:
            print(f"[PluginStandaloneWindow] 激活插件 [{self.plugin.id}] 异常: {e}")

    def apply_visual_settings(self):
        """同步全局背景透明度、组件透明度与毛玻璃效果"""
        bg_opacity = self.config_manager.get_bg_opacity()
        comp_opacity = self.config_manager.get_component_opacity()
        apply_dual_opacity(self, bg_opacity=bg_opacity, component_opacity=comp_opacity)

        acrylic_enabled = self.config_manager.get_acrylic_enabled()
        blur_level = self.config_manager.get_blur_level()
        apply_acrylic_effect(self, enabled=acrylic_enabled, blur_level=blur_level, is_dark=self.theme_manager.is_dark())

    def closeEvent(self, event):
        # 保存独立窗口位置与尺寸
        geom_key = f"window_geom_{self.plugin.id}"
        self.config_manager.set(geom_key, {
            "x": self.x(),
            "y": self.y(),
            "w": self.width(),
            "h": self.height()
        })

        # 若部件拥有专属持久化方法，自动调用
        central = self.takeCentralWidget()
        if central:
            if hasattr(central, "save_settings"):
                try:
                    central.save_settings()
                except Exception as e:
                    print(f"[PluginStandaloneWindow] 部件保存配置异常: {e}")
            elif hasattr(central, "save_config"):
                try:
                    central.save_config()
                except Exception as e:
                    print(f"[PluginStandaloneWindow] 部件保存配置异常: {e}")

        # 停用插件生命周期
        try:
            self.plugin.on_deactivated()
        except Exception as e:
            print(f"[PluginStandaloneWindow] 停用插件 [{self.plugin.id}] 异常: {e}")

        self.window_closed.emit(self.plugin.id)
        if self.on_close_callback:
            try:
                self.on_close_callback(self.plugin.id)
            except Exception:
                pass

        super().closeEvent(event)
