"""
系统增强与右键助手 - 插件定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import SystemIntegratorWidget


class SystemIntegratorPlugin(PluginBase):
    id = "system_integrator"
    name = "系统增强与右键助手"
    description = "为 Windows 资源管理器一键注册右键快捷菜单、开机自启管理以及工具箱运行环境健康体检。"
    category = "系统增强"
    icon = "system"
    version = "1.1.0"
    author = "Chieri"
    sort_order = 60

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return SystemIntegratorWidget(parent)
