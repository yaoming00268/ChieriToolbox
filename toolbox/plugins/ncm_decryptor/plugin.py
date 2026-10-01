"""
网易云音乐 NCM 格式解密 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class NcmDecryptorPlugin(PluginBase):
    id = "ncm_decryptor"
    name = "网易云音乐格式解密"
    description = "纯算法秒级解密 .ncm 格式，自动转换为 MP3/FLAC 并完整恢复 ID3 标签、歌手、专辑与内嵌封面。"
    category = "音频工具"
    icon = "unlock"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 36

    def create_widget(self, parent: QWidget = None) -> QWidget:
        from .ui import NcmDecryptorWidget
        return NcmDecryptorWidget(parent)
