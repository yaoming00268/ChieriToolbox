"""
全能文本翻译 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class TranslatorPlugin(PluginBase):
    id = "translator"
    name = "全能文本翻译"
    description = "多引擎文本即时翻译：支持免配置公开翻译引擎，以及自定义 OpenAI 兼容 API / 本地 Ollama 大模型。"
    category = "效率键入"
    icon = "languages"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 50

    def create_widget(self, parent: QWidget = None) -> QWidget:
        from .ui import TranslatorWidget
        return TranslatorWidget(parent)
