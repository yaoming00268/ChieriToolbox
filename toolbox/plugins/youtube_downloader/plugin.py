"""
YouTube 视频下载器 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import YoutubeDownloaderWidget


class YoutubeDownloaderPlugin(PluginBase):
    id = "youtube_downloader"
    name = "油管视频爬取"
    description = "YouTube/流媒体视频解析与下载，画质码率自由挑选，支持音视频混流与代理配置。"
    category = "网络下载"
    icon = "youtube"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 42

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return YoutubeDownloaderWidget(parent)
