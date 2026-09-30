"""
音频精准剪裁 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import AudioCutterWidget


class AudioCutterPlugin(PluginBase):
    id = "audio_cutter"
    name = "音频精准剪裁"
    description = "微秒/毫秒级精准音频剪裁截取，时间码快速选取，无损/重编码极速导出。"
    category = "音频工具"
    icon = "scissors"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 38

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return AudioCutterWidget(parent)

    def get_quick_actions(self, window=None) -> list:
        def _get_w():
            return self.get_widget(window)

        return [
            {
                "id": "select_file",
                "title": "导入音频文件...",
                "icon": "folder",
                "callback": lambda: _get_w()._browse_audio_file()
            },
            {
                "id": "open_output",
                "title": "打开输出保存目录",
                "icon": "folder",
                "callback": lambda: _get_w()._open_output_dir()
            }
        ]

