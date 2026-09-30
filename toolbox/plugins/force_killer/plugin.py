"""
应用强制删除与文件粉碎 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import ForceKillerWidget


class ForceKillerPlugin(PluginBase):
    id = "force_killer"
    name = "顽固应用与文件强力粉碎"
    description = "解除顽固文件占用锁并彻底粉碎删除，强制终止卡死顽固进程树与后台服务。"
    category = "系统增强"
    icon = "shield"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 62

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return ForceKillerWidget(parent)
