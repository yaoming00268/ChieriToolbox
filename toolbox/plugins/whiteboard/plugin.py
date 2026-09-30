"""
交互式白板 (希沃风) - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import WhiteboardWidget


class WhiteboardPlugin(PluginBase):
    id = "whiteboard"
    name = "交互式白板 (希沃风)"
    description = "全功能教学与演示交互白板，支持平滑手写笔、荧光记号笔、图形绘制、橡皮擦除、网格背景切换与历史撤销重做。"
    category = "办公辅助"
    icon = "pencil"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 50

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return WhiteboardWidget(parent)

    def get_quick_actions(self, window=None) -> list:
        def _get_w():
            return self.get_widget(window)

        return [
            {
                "id": "clear_canvas",
                "title": "清空白板画布",
                "icon": "trash",
                "callback": lambda: _get_w()._clear_canvas()
            },
            {
                "id": "export_image",
                "title": "导出白板画作为图片",
                "icon": "save",
                "callback": lambda: _get_w()._export_image()
            }
        ]

