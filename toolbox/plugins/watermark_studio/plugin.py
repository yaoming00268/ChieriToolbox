"""
水印工坊 (Watermark Studio) - 插件声明
"""

import os
from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class WatermarkStudioPlugin(PluginBase):
    id = "watermark_studio"
    name = "水印防盗工坊"
    description = "批量全图平铺防盗水印、身份证/营业执照防滥用专用隐私水印与肉眼不可见的隐形频域盲水印。"
    category = "图像工具"
    icon = "image"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 28
    supported_inputs = ["image/*", "file/*"]
    supported_outputs = ["image/*", "file/*"]

    def create_widget(self, parent: QWidget = None) -> QWidget:
        from .ui import WatermarkStudioWidget
        return WatermarkStudioWidget(parent)

    def accept_pipeline_data(self, data_type: str, data: any) -> bool:
        w = self.get_widget()
        if isinstance(data, (list, tuple)):
            w.handle_initial_paths(list(data))
            return True
        elif isinstance(data, str) and os.path.exists(data):
            w.handle_initial_paths([data])
            return True
        return False
