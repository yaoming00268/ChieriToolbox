"""
网易云音乐 NCM 格式解密 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class NcmDecryptorPlugin(PluginBase):
    id = "ncm_decryptor"
    name = "全能音乐解密工坊"
    description = "纯算法秒级解密网易云 NCM、QQ音乐 QMC/MFLAC/MGG、酷狗 KGM/VPR、酷我 KWM 等主流加密音频格式，自动转换为 MP3/FLAC 并完整恢复 ID3 标签与内嵌封面。"
    category = "音频工具"
    icon = "unlock"
    version = "1.2.0"
    author = "Chieri"
    sort_order = 36
    supported_inputs = ["audio/*", "file/*"]
    supported_outputs = ["audio/*", "file/*"]

    def create_widget(self, parent: QWidget = None) -> QWidget:
        from .ui import NcmDecryptorWidget
        return NcmDecryptorWidget(parent)
