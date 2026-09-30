"""
WebDAV 配置管理器 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import WebDAVConfigWidget


class WebDAVConfigPlugin(PluginBase):
    id = "webdav_config"
    name = "WebDAV 配置管理器"
    description = "集成 OpenList/AList 内核标准的 WebDAV 客户端与存储配置，支持多配置管理、连通性探测、远程文件浏览与网络驱动器一键映射挂载。"
    category = "网络工具"
    icon = "globe"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 40

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return WebDAVConfigWidget(parent)
