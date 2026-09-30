"""
图片与视频体积压缩 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import MediaCompressorWidget


class MediaCompressorPlugin(PluginBase):
    id = "media_compressor"
    name = "图片与视频体积压缩"
    description = "批量压缩图片与视频体积，采用业界领先的 WebP/MozJPEG 及 FFmpeg H.264/HEVC/AV1 CRF 算法。"
    category = "媒体处理"
    icon = "zap"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 23

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return MediaCompressorWidget(parent)
