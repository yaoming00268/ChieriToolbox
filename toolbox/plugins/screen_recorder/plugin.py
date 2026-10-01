"""
高清屏幕录像机 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class ScreenRecorderPlugin(PluginBase):
    id = "screen_recorder"
    name = "高清屏幕录像机"
    description = "全功能屏幕录制工具，支持全屏录制、指定窗口录制与自定义矩形区域录像，集成音频捕获与高质量压制。"
    category = "媒体处理"
    icon = "monitor"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 27

    def create_widget(self, parent: QWidget = None) -> QWidget:
        from .ui import ScreenRecorderWidget
        return ScreenRecorderWidget(parent)

    def get_quick_actions(self, window=None) -> list:
        def _get_w():
            return self.get_widget(window)

        return [
            {
                "id": "toggle_record",
                "title": "开始/停止录像",
                "icon": "video",
                "callback": lambda: _get_w()._toggle_recording_action()
            },
            {
                "id": "toggle_pause",
                "title": "暂停/继续录像",
                "icon": "clock",
                "callback": lambda: _get_w()._toggle_pause_action()
            }
        ]
