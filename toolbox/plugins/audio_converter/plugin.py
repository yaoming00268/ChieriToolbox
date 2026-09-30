"""
音频格式批量转换 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import AudioConverterWidget


class AudioConverterPlugin(PluginBase):
    id = "audio_converter"
    name = "音频格式批量转换"
    description = "多格式音频批量互转，支持采样率 (44.1k/48k/96k)、声道 (立体声/单声道) 及比特率灵活配置。"
    category = "音频工具"
    icon = "refresh"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 34

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return AudioConverterWidget(parent)
