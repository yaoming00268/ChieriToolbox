"""
高清录音工具 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import AudioRecorderWidget


class AudioRecorderPlugin(PluginBase):
    id = "audio_recorder"
    name = "高清录音工具"
    description = "麦克风高清音频录制，支持动态波形电平显示、暂停/继续录制、导出 MP3/WAV 格式与历史回放。"
    category = "音频工具"
    icon = "mic"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 34

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return AudioRecorderWidget(parent)

    def get_quick_actions(self, window=None) -> list:
        def _get_w():
            return self.get_widget(window)

        return [
            {
                "id": "toggle_record",
                "title": "开始/暂停录音",
                "icon": "mic",
                "callback": lambda: _get_w()._toggle_record()
            },
            {
                "id": "stop_record",
                "title": "停止并保存录音",
                "icon": "stop",
                "callback": lambda: _get_w()._stop_record()
            }
        ]

