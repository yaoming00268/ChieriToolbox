"""
应用代理配置工具 - 插件接口定义
"""

from PySide6.QtWidgets import QWidget
from toolbox.core.plugin_base import PluginBase
from .ui import ProxyConfiguratorWidget


class ProxyConfiguratorPlugin(PluginBase):
    id = "proxy_configurator"
    name = "应用代理配置工具"
    description = "一键快速配置与切换 Windows 系统代理、环境变量 (HTTP/HTTPS)、Git 代理与 pip 镜像代理。"
    category = "系统增强"
    icon = "network"
    version = "1.0.0"
    author = "Chieri"
    sort_order = 64

    def create_widget(self, parent: QWidget = None) -> QWidget:
        return ProxyConfiguratorWidget(parent)

    def get_quick_actions(self, window=None) -> list:
        def _get_w():
            return self.get_widget(window)

        return [
            {
                "id": "enable_sys_proxy",
                "title": "启用系统代理",
                "icon": "network",
                "callback": lambda: _get_w()._enable_sys_proxy()
            },
            {
                "id": "disable_sys_proxy",
                "title": "停用系统代理",
                "icon": "clear",
                "callback": lambda: _get_w()._disable_sys_proxy()
            },
            {
                "id": "enable_all_proxies",
                "title": "一键开启所有代理通道",
                "icon": "check",
                "callback": lambda: _get_w()._enable_all_proxies()
            },
            {
                "id": "disable_all_proxies",
                "title": "一键关闭所有代理通道",
                "icon": "trash",
                "callback": lambda: _get_w()._disable_all_proxies()
            }
        ]

