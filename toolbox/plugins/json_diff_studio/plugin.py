"""
JSON 对比与分析工坊 (JSON Diff Studio) - 插件声明
"""

from typing import Any, List, Optional
from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class JsonDiffStudioPlugin(PluginBase):
    id = "json_diff_studio"
    name = "JSON对比分析工坊"
    description = "JSON/文本双栏高精对比、实时语法美化与紧凑压缩、层级折叠树视图、以及强大零依赖的 JSONPath 查询提取器。"
    category = "效率工具"
    icon = "git-compare"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 45
    supported_inputs = ["text/plain", "application/json"]
    supported_outputs = ["text/plain", "application/json"]

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        from .ui import JsonDiffStudioWidget
        return JsonDiffStudioWidget(parent)

    def get_quick_actions(self, window=None) -> list:
        def _beautify():
            w = self.get_widget(window)
            if hasattr(w, "_format_left"):
                w._format_left()

        def _diff():
            w = self.get_widget(window)
            if hasattr(w, "_run_diff"):
                w._run_diff()

        return [
            {
                "id": "format_json",
                "title": "格式化左侧 JSON",
                "icon": "sparkles",
                "callback": _beautify
            },
            {
                "id": "run_diff",
                "title": "执行双栏对比",
                "icon": "git-compare",
                "callback": _diff
            }
        ]

    def accept_pipeline_data(self, data_type: str, data: Any) -> bool:
        """接收跨插件管道数据流 (例如从其他工具送入的文本或 JSON)"""
        w = self.get_widget()
        if hasattr(w, "set_input_text"):
            text = str(data) if not isinstance(data, str) else data
            w.set_input_text(text)
            return True
        return False
