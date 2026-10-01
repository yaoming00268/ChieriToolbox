"""
压缩解压工具 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class ArchiveManagerPlugin(PluginBase):
    id = "archive_manager"
    name = "压缩解压工具"
    description = "全能归档管理：支持 7z, ZIP, RAR, TAR, GZ, LZ4 等格式解压与打包，支持密码与多引擎智能调度。"
    category = "文件管理"
    icon = "archive"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 15

    def create_widget(self, parent: QWidget = None) -> QWidget:
        from .ui import ArchiveManagerWidget
        return ArchiveManagerWidget(parent)
