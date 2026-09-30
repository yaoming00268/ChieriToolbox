"""
osu!mania 皮肤调校工作台 - 插件定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import OsuSkinStudioWidget


class OsuSkinStudioPlugin(PluginBase):
    id = "osu_skin_studio"
    name = "osu!mania 皮肤调校工作台"
    description = "专为 osu!mania 皮肤打造：实时调节判定线高度、舞台起始偏移与列宽数组，内置高保真画布即时渲染。"
    category = "音游工具"
    icon = "sparkles"
    version = "1.5.0"
    author = "Chieri"
    sort_order = 50

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return OsuSkinStudioWidget(parent)
