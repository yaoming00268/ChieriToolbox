"""
环境变量切换管家 (Environment Variable Switcher) - 插件声明
"""

from typing import Any, List, Optional
from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class EnvVarSwitcherPlugin(PluginBase):
    id = "env_var_switcher"
    name = "环境变量管家"
    description = "Windows 用户/系统环境变量与 PATH 可视化管理、失效与冗余路径体检、一键备份还原与开发环境预设方案快速切换。"
    category = "系统增强"
    icon = "sliders"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 83
    supported_inputs = []
    supported_outputs = ["text/plain"]

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        from .ui import EnvVarSwitcherWidget
        return EnvVarSwitcherWidget(parent)

    def get_quick_actions(self, window=None) -> list:
        def _refresh():
            w = self.get_widget(window)
            if hasattr(w, "_refresh_all"):
                w._refresh_all()

        def _backup():
            w = self.get_widget(window)
            if hasattr(w, "_do_backup"):
                w._do_backup()

        return [
            {
                "id": "refresh_env",
                "title": "刷新系统与用户环境变量",
                "icon": "refresh",
                "callback": _refresh
            },
            {
                "id": "backup_env",
                "title": "一键导出当前环境备份",
                "icon": "save",
                "callback": _backup
            }
        ]
