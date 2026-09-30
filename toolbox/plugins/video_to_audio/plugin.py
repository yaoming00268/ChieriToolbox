"""
批量视频转音频 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import VideoToAudioWidget


class VideoToAudioPlugin(PluginBase):
    id = "video_to_audio"
    name = "批量视频转音频"
    description = "批量拖拽视频文件提取音频轨道，支持 MP3 / FLAC / WAV / AAC / M4A / OGG 格式与码率调节。"
    category = "音频工具"
    icon = "music"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 32

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return VideoToAudioWidget(parent)
