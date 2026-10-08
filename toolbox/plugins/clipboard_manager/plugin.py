"""
剪贴板管理器 (Clipboard Manager) - 插件声明
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class ClipboardManagerPlugin(PluginBase):
    id = "clipboard_manager"
    name = "无限剪贴板历史"
    description = "无限记录剪贴历史、常用短语看板，自动检测手机号、身份证与API密钥并打码防泄露。"
    category = "效率工具"
    icon = "clipboard"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 12
    supported_inputs = ["text/plain", "image/*"]
    supported_outputs = ["text/plain", "image/*"]

    def create_widget(self, parent: QWidget = None) -> QWidget:
        from .ui import ClipboardManagerWidget
        return ClipboardManagerWidget(parent)

    def accept_pipeline_data(self, data_type: str, data: any) -> bool:
        import os
        from PySide6.QtGui import QPixmap
        w = self.get_widget()
        if isinstance(data, QPixmap) and not data.isNull():
            w.mgr.add_image(data)
            w._refresh_history_list()
            return True
        elif isinstance(data, str) and data:
            if os.path.isfile(data) and data.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico")):
                pix = QPixmap(data)
                if not pix.isNull():
                    w.mgr.add_image(pix)
                    w._refresh_history_list()
                    return True
            w.mgr.add_text(data)
            w._refresh_history_list()
            return True
        elif isinstance(data, (list, tuple)):
            handled = False
            for item in data:
                if self.accept_pipeline_data(data_type, item):
                    handled = True
            return handled
        return False
