"""
B站媒体下载器 - 插件定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class MediaDownloaderPlugin(PluginBase):
    id = "media_downloader"
    name = "B站媒体下载器"
    description = "一键解析 B站视频，多分P自由挑选、支持 1080P/720P 高清下载与 MP3/M4A 提取，内置 FFmpeg 自动混流。"
    category = "网络下载"
    icon = "video"
    version = "2.0.0"
    author = "Chieri"
    sort_order = 40

    def create_widget(self, parent: QWidget = None) -> QWidget:
        from .ui import MediaDownloaderWidget
        return MediaDownloaderWidget(parent)
