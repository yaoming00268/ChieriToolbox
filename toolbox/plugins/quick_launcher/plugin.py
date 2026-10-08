"""
千绘莉极速启动器 (Quick Launcher) - 插件声明
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class QuickLauncherPlugin(PluginBase):
    id = "quick_launcher"
    name = "极速启动器 (Spotlight)"
    description = "类 Raycast/Spotlight 全局极速召唤栏，拼音秒搜插件、安全算式计算、Base64编解码与屏幕拾色。"
    category = "效率工具"
    icon = "search"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 1
    supported_inputs = ["text/plain"]
    supported_outputs = ["text/plain"]

    def create_widget(self, parent: QWidget = None) -> QWidget:
        from .ui import QuickLauncherWidget
        return QuickLauncherWidget(parent)

    def get_quick_actions(self, window=None) -> list:
        def _summon():
            w = self.get_widget(window)
            if hasattr(w, "_summon_spotlight"):
                w._summon_spotlight()

        return [
            {
                "id": "summon_spotlight",
                "title": "唤起 Spotlight 搜索框",
                "icon": "search",
                "callback": _summon
            }
        ]
