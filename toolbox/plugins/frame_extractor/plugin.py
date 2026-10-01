"""
视频与动图逐帧解压 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class FrameExtractorPlugin(PluginBase):
    id = "frame_extractor"
    name = "视频与动图逐帧解压"
    description = "将 MP4 / MKV / AVI 等视频或 GIF / WebP 动画解压为序列图片，支持选择 JPG / PNG / BMP 格式及指定输出目录。"
    category = "媒体处理"
    icon = "layers"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 24

    def create_widget(self, parent: QWidget = None) -> QWidget:
        from .ui import FrameExtractorWidget
        return FrameExtractorWidget(parent)
