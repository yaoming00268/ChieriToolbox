"""
工具箱 (Toolbox) - 插件系统托盘与快捷菜单管理器 (TrayManager)
支持任一插件独立常驻系统托盘，右键调出专属快捷功能栏与退出菜单。
严格遵循无 Emoji 规范，全量使用矢量图标与无衬线排版。
"""

import os
from typing import Dict, Optional, Callable
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QWidget, QApplication
from PySide6.QtGui import QAction, QFont, QIcon

from toolbox.core.plugin_base import PluginBase
from toolbox.core.config_manager import ConfigManager


def _get_icon(name: str, **kwargs):
    from toolbox.ui.icons import get_icon
    return get_icon(name, **kwargs)


class PluginTrayIcon(QSystemTrayIcon):
    """
    单个插件专用的系统托盘图标控件
    """
    def __init__(
        self,
        plugin: PluginBase,
        parent: Optional[QObject] = None,
        on_open_callback: Optional[Callable[[], None]] = None,
        on_settings_callback: Optional[Callable[[], None]] = None,
        on_exit_callback: Optional[Callable[[], None]] = None,
        on_export_callback: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self.plugin = plugin
        self.on_open = on_open_callback
        self.on_settings = on_settings_callback
        self.on_exit = on_exit_callback
        self.on_export = on_export_callback

        tray_icon = None
        if hasattr(plugin, "get_ico_path"):
            ico_p = plugin.get_ico_path()
            if ico_p and os.path.isfile(ico_p):
                tray_icon = QIcon(ico_p)
        if not tray_icon or tray_icon.isNull():
            from toolbox.ui.icons import get_plugin_icon
            tray_icon = get_plugin_icon(plugin.id, size=24)
        if not tray_icon or tray_icon.isNull():
            tray_icon = _get_icon(plugin.icon, size=24)
        self.setIcon(tray_icon)
        self.setToolTip(f"{plugin.name} - 千绘莉工具箱")

        self.menu = QMenu()
        self.rebuild_menu()
        self.menu.aboutToShow.connect(self.rebuild_menu)
        self.setContextMenu(self.menu)

        self.activated.connect(self._on_tray_activated)

    def rebuild_menu(self):
        """动态构建右键快捷上下文菜单"""
        self.menu.clear()

        # 1. 顶部标题/打开主界面 (使用插件专属独立图标)
        act_open = QAction(self.icon(), f"打开 {self.plugin.name}", self.menu)
        font = act_open.font()
        font.setBold(True)
        act_open.setFont(font)
        if self.on_open:
            act_open.triggered.connect(self.on_open)
        self.menu.addAction(act_open)

        self.menu.addSeparator()

        # 2. 插件专属快捷功能栏
        parent_w = self.parent() if isinstance(self.parent(), QWidget) else None
        quick_actions = self.plugin.get_quick_actions(parent_w)
        if quick_actions:
            for item in quick_actions:
                title = item.get("title", "未命名动作")
                icon_name = item.get("icon", "tools")
                cb = item.get("callback")
                act = QAction(_get_icon(icon_name, size=16), title, self.menu)
                if cb:
                    act.triggered.connect(cb)
                self.menu.addAction(act)
            self.menu.addSeparator()

        # 3. 导出与设置操作
        if self.on_export:
            act_export = QAction(_get_icon("package", size=16), "导出为独立 Setup 安装包...", self.menu)
            act_export.triggered.connect(self.on_export)
            self.menu.addAction(act_export)

        if self.on_settings:
            act_settings = QAction(_get_icon("settings", size=16), "插件设置...", self.menu)
            act_settings.triggered.connect(self.on_settings)
            self.menu.addAction(act_settings)

        self.menu.addSeparator()

        # 4. 退出选项 (必须包含退出功能)
        act_exit = QAction(_get_icon("clear", size=16), "退出", self.menu)
        if self.on_exit:
            act_exit.triggered.connect(self.on_exit)
        else:
            act_exit.triggered.connect(self.hide)
        self.menu.addAction(act_exit)

    def _on_tray_activated(self, reason):
        # 双击或单击打开
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.on_open:
                self.on_open()


def _find_main_window():
    """查找全局已运行的 MainWindow 实例"""
    from toolbox.ui.main_window import MainWindow
    for top in QApplication.topLevelWidgets():
        if isinstance(top, MainWindow):
            return top
    return None


def _default_open_action(plugin_id: str):
    """默认激活并打开主窗口特定插件的动作"""
    mw = _find_main_window()
    if mw and hasattr(mw, "switch_to_plugin"):
        mw.showNormal()
        mw.raise_()
        mw.activateWindow()
        mw.switch_to_plugin(plugin_id)


def _default_settings_action(plugin_id: str):
    """默认呼出特定插件独立设置面板的动作"""
    mw = _find_main_window()
    if mw and hasattr(mw, "_open_plugin_settings_dialog"):
        mw._open_plugin_settings_dialog(plugin_id)


def _default_export_action(plugin_id: str):
    """默认呼出特定插件独立导出向导的动作"""
    mw = _find_main_window()
    if mw and hasattr(mw, "home_page"):
        mw.home_page._open_export_dialog(plugin_id)


class PluginTrayManager(QObject):
    """
    全局插件系统托盘管理器 (单例模式)
    """
    _instance = None
    tray_changed = Signal(str, bool)  # (plugin_id, is_active)

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        super().__init__()
        self._trays: Dict[str, PluginTrayIcon] = {}
        self.config_manager = ConfigManager()

    def add_tray_icon(
        self,
        plugin: PluginBase,
        on_open_callback: Optional[Callable[[], None]] = None,
        on_settings_callback: Optional[Callable[[], None]] = None,
        on_exit_callback: Optional[Callable[[], None]] = None,
        on_export_callback: Optional[Callable[[], None]] = None,
    ) -> PluginTrayIcon:
        """为特定插件建立独立托盘图标并注册"""
        pid = plugin.id
        effective_open = on_open_callback or (lambda target_id=pid: _default_open_action(target_id))
        effective_settings = on_settings_callback or (lambda target_id=pid: _default_settings_action(target_id))
        effective_exit = on_exit_callback or (lambda target_id=pid: self.remove_tray_icon(target_id))
        effective_export = on_export_callback or (lambda target_id=pid: _default_export_action(target_id))

        if pid in self._trays:
            tray = self._trays[pid]
            if on_open_callback:
                tray.on_open = effective_open
            if on_settings_callback:
                tray.on_settings = effective_settings
            if on_exit_callback:
                tray.on_exit = effective_exit
            if on_export_callback:
                tray.on_export = effective_export
            tray.rebuild_menu()
            tray.show()
            self.config_manager.set_tray_plugin(pid, True)
            self.tray_changed.emit(pid, True)
            return tray

        tray = PluginTrayIcon(
            plugin=plugin,
            on_open_callback=effective_open,
            on_settings_callback=effective_settings,
            on_exit_callback=effective_exit,
            on_export_callback=effective_export,
        )
        self._trays[pid] = tray
        tray.show()
        self.config_manager.set_tray_plugin(pid, True)
        self.tray_changed.emit(pid, True)
        return tray

    def remove_tray_icon(self, plugin_id: str, save_config: bool = True):
        """移除特定插件的独立托盘图标"""
        if plugin_id in self._trays:
            tray = self._trays[plugin_id]
            tray.hide()
            tray.deleteLater()
            del self._trays[plugin_id]
        if save_config:
            self.config_manager.set_tray_plugin(plugin_id, False)
        self.tray_changed.emit(plugin_id, False)

    def has_tray_icon(self, plugin_id: str) -> bool:
        """检查特定插件是否已显示在系统托盘"""
        return plugin_id in self._trays

    def get_tray_icon(self, plugin_id: str) -> Optional[PluginTrayIcon]:
        return self._trays.get(plugin_id)

    def clear_all(self):
        """清理所有托盘图标"""
        pids = list(self._trays.keys())
        for tray in list(self._trays.values()):
            tray.hide()
            tray.deleteLater()
        self._trays.clear()
        for pid in pids:
            self.tray_changed.emit(pid, False)

    def cleanup_all(self):
        """兼容性清理接口"""
        self.clear_all()

    def get_active_plugin_ids(self) -> list:
        """获取当前所有活跃托盘插件 ID 列表"""
        return list(self._trays.keys())

    add_plugin_tray_icon = add_tray_icon


TrayManager = PluginTrayManager

