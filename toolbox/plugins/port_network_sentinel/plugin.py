"""
端口网络哨兵 (Port Network Sentinel) - 插件声明
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase


class PortNetworkSentinelPlugin(PluginBase):
    id = "port_network_sentinel"
    name = "端口网络哨兵"
    description = "毫秒级探测本地处于 LISTENING 状态端口、定位并一键强杀占用进程、管理 Hosts 与刷新 DNS 缓存。"
    category = "系统增强"
    icon = "network"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 82
    supported_inputs = []
    supported_outputs = ["text/plain"]

    def create_widget(self, parent: QWidget = None) -> QWidget:
        from .ui import PortNetworkSentinelWidget
        return PortNetworkSentinelWidget(parent)

    def get_quick_actions(self, window=None) -> list:
        def _scan():
            w = self.get_widget(window)
            if hasattr(w, "_start_scan"):
                w._start_scan()

        return [
            {
                "id": "scan_ports",
                "title": "扫描本地侦听端口",
                "icon": "refresh",
                "callback": _scan
            }
        ]
