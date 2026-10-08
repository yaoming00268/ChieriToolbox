"""
专业截图工具 (PixPin风) - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class ScreenCapturePlugin(PluginBase):
    id = "screen_capture"
    name = "专业截图工具 (PixPin风)"
    description = "全功能像素级屏幕截图工具，支持矩形选区、智能窗口嗅探、全屏快照、滚动长截图、桌面贴图置顶与快捷键绑定。"
    category = "图像工具"
    icon = "camera"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 21
    supported_outputs = ["image/*", "text/plain"]

    def create_widget(self, parent: QWidget = None) -> QWidget:
        from .ui import ScreenCaptureWidget
        return ScreenCaptureWidget(parent)

    def get_quick_actions(self, window=None) -> list:
        def _get_w():
            return self.get_widget(window)

        return [
            {
                "id": "rect_snip",
                "title": "矩形选区截图",
                "icon": "scissors",
                "callback": lambda: _get_w()._start_rectangular_snip()
            },
            {
                "id": "window_snip",
                "title": "窗口智能嗅探截图",
                "icon": "window",
                "callback": lambda: _get_w()._start_window_snip()
            },
            {
                "id": "full_snip",
                "title": "全屏快速截图",
                "icon": "monitor",
                "callback": lambda: _get_w()._start_fullscreen_snip()
            },
            {
                "id": "long_snip",
                "title": "滚动长截图分段",
                "icon": "file-plus",
                "callback": lambda: _get_w()._trigger_long_snip_shortcut()
            },
            {
                "id": "pin_snip",
                "title": "剪贴板快速贴图置顶",
                "icon": "copy",
                "callback": lambda: _get_w()._pin_clipboard_or_last()
            }
        ]

