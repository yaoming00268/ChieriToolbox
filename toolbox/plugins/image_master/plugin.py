"""
图像格式转换与缩放工坊 - 插件定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import ImageMasterWidget


class ImageMasterPlugin(PluginBase):
    id = "image_master"
    name = "图像格式转换与缩放工坊"
    description = "批量图片处理利器：支持常见格式互转 (PNG/JPG/WEBP/ICO等)、透明底色智能填充、高保真尺寸缩放。"
    category = "图像媒体"
    icon = "image"
    version = "1.3.0"
    author = "Chieri"
    sort_order = 20

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return ImageMasterWidget(parent)
