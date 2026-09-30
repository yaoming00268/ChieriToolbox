"""
模拟键入与极速粘贴助手 - 插件定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import AutoInputWidget


class AutoInputPlugin(PluginBase):
    id = "auto_input"
    name = "模拟键入与极速粘贴助手"
    description = "突破防粘贴限制：全局快捷键一键触发、支持字符间隔毫秒级物理击键模拟、剪贴板快速输出与常用短语库。"
    category = "效率键入"
    icon = "keyboard"
    version = "1.2.0"
    author = "Chieri"
    sort_order = 30

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return AutoInputWidget(parent)

    def on_deactivated(self):
        super().on_deactivated()
        if self._widget and hasattr(self._widget, "on_deactivated"):
            self._widget.on_deactivated()

    def cleanup(self):
        if self._widget and hasattr(self._widget, "on_deactivated"):
            self._widget.on_deactivated()
        super().cleanup()
