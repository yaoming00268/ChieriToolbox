"""
文件批量整理大师 - 插件定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import FileSuiteWidget


class FileSuitePlugin(PluginBase):
    id = "file_suite"
    name = "文件批量整理大师"
    description = "强大的文件整理套件：支持文件名批量重命名、正则匹配、后缀名格式统一、子文件夹提取与扁平化清理。"
    category = "文件管理"
    icon = "folder"
    version = "1.2.0"
    author = "Chieri"
    sort_order = 10

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return FileSuiteWidget(parent)
