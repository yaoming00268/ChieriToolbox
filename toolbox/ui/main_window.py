"""
工具箱 (Toolbox) - 统一主窗口 (MainWindow)
提供现代化顶部全局导航栏 (矢量品牌、交互式面包屑、深浅/跟随系统三态切换器、快捷返回)、
QStackedWidget 视图切换与插件生命周期流转。
"""

import sys
from typing import Dict, Optional, List
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QStatusBar, QMessageBox,
    QButtonGroup, QFrame, QSystemTrayIcon, QMenu
)
from toolbox.core.plugin_manager import PluginManager
from toolbox.core.config_manager import ConfigManager
from toolbox.core.event_bus import EventBus
from toolbox.core.theme import ThemeManager, THEME_SYSTEM, THEME_DARK, THEME_LIGHT
from toolbox.core.window_effects import apply_window_opacity, apply_dual_opacity, apply_acrylic_effect
from toolbox.ui.home_page import HomePage
from toolbox.ui.icons import get_icon, get_pixmap
from toolbox.ui.standalone_window import PluginStandaloneWindow
from toolbox.ui.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self, initial_plugin_id: Optional[str] = None, initial_paths: Optional[List[str]] = None):
        super().__init__()
        self.plugin_manager = PluginManager()
        self.config_manager = ConfigManager()
        self.theme_manager = ThemeManager()
        self.event_bus = EventBus()
        self.initial_plugin_id = initial_plugin_id
        self.initial_paths = initial_paths or []
        self.app_tray_icon: Optional[QSystemTrayIcon] = None
        self._force_exit: bool = False

        # 缓存已实例化的插件视图控件: plugin_id -> widget_index
        self._plugin_page_indices: Dict[str, int] = {}
        # 多开模式下独立窗口容器: plugin_id -> PluginStandaloneWindow
        self._plugin_windows: Dict[str, PluginStandaloneWindow] = {}

        self.init_window()
        self.init_ui()
        self.init_shortcuts()
        self.init_connections()
        self.load_plugins()

    def init_window(self):
        self.setWindowTitle("千绘莉的多功能工具箱 (Chieri Toolbox)")
        import os
        from PySide6.QtGui import QIcon
        from toolbox.core.paths import get_bundle_dir, get_app_root
        ico_candidates = [
            os.path.join(get_bundle_dir(), "app_icon.ico"),
            os.path.join(get_app_root(), "app_icon.ico"),
            os.path.join(get_bundle_dir(), "app_icon.png"),
            os.path.join(get_app_root(), "app_icon.png"),
        ]
        chosen_icon = None
        for ic in ico_candidates:
            if os.path.isfile(ic):
                chosen_icon = QIcon(ic)
                break
        self.setWindowIcon(chosen_icon if chosen_icon else get_icon("app_logo", size=32))
        w_cfg = self.config_manager.get("window", {})
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        target_w = w_cfg.get("width", 1120)
        target_h = w_cfg.get("height", 750)
        if avail:
            target_w = min(target_w, max(880, avail.width() - 40))
            target_h = min(target_h, max(600, avail.height() - 60))
        self.resize(target_w, target_h)
        self.setMinimumSize(880, 600)
        if w_cfg.get("is_maximized", False):
            self.showMaximized()
        self.apply_visual_settings()

    def apply_visual_settings(self):
        """应用背景透明度、组件透明度与毛玻璃效果"""
        bg_opacity = self.config_manager.get_bg_opacity()
        comp_opacity = self.config_manager.get_component_opacity()
        apply_dual_opacity(self, bg_opacity=bg_opacity, component_opacity=comp_opacity)
        acrylic = self.config_manager.get_acrylic_enabled()
        blur = self.config_manager.get_blur_level()
        apply_acrylic_effect(self, enabled=acrylic, blur_level=blur, is_dark=self.theme_manager.is_dark())

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. 顶部全局导航栏
        self.nav_bar = QWidget()
        self.nav_bar.setObjectName("topNavBar")
        self.nav_bar.setFixedHeight(54)
        nav_layout = QHBoxLayout(self.nav_bar)
        nav_layout.setContentsMargins(18, 0, 18, 0)
        nav_layout.setSpacing(14)

        # 品牌 Logo 与标题 (点击可直接返回首页)
        self.brand_container = QWidget()
        self.brand_container.setCursor(Qt.PointingHandCursor)
        self.brand_container.setToolTip("千绘莉多功能工具箱 · 点击返回首页")
        self.brand_container.mousePressEvent = lambda e: self.go_to_home() if e.button() == Qt.LeftButton else None
        brand_layout = QHBoxLayout(self.brand_container)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(8)

        self.lbl_logo = QLabel()
        self.lbl_logo.setFixedSize(22, 22)
        brand_layout.addWidget(self.lbl_logo)

        self.lbl_brand_title = QLabel("千绘莉工具箱")
        self.lbl_brand_title.setObjectName("appBrandTitle")
        brand_layout.addWidget(self.lbl_brand_title)
        nav_layout.addWidget(self.brand_container)

        # 导航分隔线
        sep = QLabel("|")
        sep.setStyleSheet("color: #475569; font-size: 13px; margin: 0 4px;")
        nav_layout.addWidget(sep)

        # 交互式面包屑容器
        self.breadcrumb_container = QWidget()
        bc_layout = QHBoxLayout(self.breadcrumb_container)
        bc_layout.setContentsMargins(0, 0, 0, 0)
        bc_layout.setSpacing(6)

        self.btn_bc_home = QPushButton("首页")
        self.btn_bc_home.setObjectName("flatIconBtn")
        self.btn_bc_home.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.btn_bc_home.clicked.connect(self.go_to_home)
        bc_layout.addWidget(self.btn_bc_home)

        self.lbl_bc_sep = QLabel()
        self.lbl_bc_sep.setPixmap(get_pixmap("chevron-right", color="#64748b", size=14))
        self.lbl_bc_sep.setVisible(False)
        bc_layout.addWidget(self.lbl_bc_sep)

        self.lbl_bc_plugin = QLabel()
        self.lbl_bc_plugin.setObjectName("breadcrumbActive")
        self.lbl_bc_plugin.setVisible(False)
        bc_layout.addWidget(self.lbl_bc_plugin)

        nav_layout.addWidget(self.breadcrumb_container)
        nav_layout.addStretch()

        # 核心：深浅主题三态模式切换胶囊 (Light / Dark / Follow System)
        self.theme_switch_box = QFrame()
        self.theme_switch_box.setObjectName("themeSwitchBox")
        theme_box_layout = QHBoxLayout(self.theme_switch_box)
        theme_box_layout.setContentsMargins(2, 2, 2, 2)
        theme_box_layout.setSpacing(2)

        self.theme_btn_group = QButtonGroup(self)
        self.theme_btn_group.setExclusive(True)

        self.btn_theme_light = QPushButton()
        self.btn_theme_light.setObjectName("themeSegmentBtn")
        self.btn_theme_light.setCheckable(True)
        self.btn_theme_light.setIcon(get_icon("sun", size=15))
        self.btn_theme_light.setToolTip("浅色模式 (Light)")
        self.btn_theme_light.clicked.connect(lambda: self._set_theme(THEME_LIGHT))
        self.theme_btn_group.addButton(self.btn_theme_light)
        theme_box_layout.addWidget(self.btn_theme_light)

        self.btn_theme_dark = QPushButton()
        self.btn_theme_dark.setObjectName("themeSegmentBtn")
        self.btn_theme_dark.setCheckable(True)
        self.btn_theme_dark.setIcon(get_icon("moon", size=15))
        self.btn_theme_dark.setToolTip("深色模式 (Dark)")
        self.btn_theme_dark.clicked.connect(lambda: self._set_theme(THEME_DARK))
        self.theme_btn_group.addButton(self.btn_theme_dark)
        theme_box_layout.addWidget(self.btn_theme_dark)

        self.btn_theme_system = QPushButton()
        self.btn_theme_system.setObjectName("themeSegmentBtn")
        self.btn_theme_system.setCheckable(True)
        self.btn_theme_system.setIcon(get_icon("monitor", size=15))
        self.btn_theme_system.setToolTip("跟随 Windows 系统外观设置 (Auto/System)")
        self.btn_theme_system.clicked.connect(lambda: self._set_theme(THEME_SYSTEM))
        self.theme_btn_group.addButton(self.btn_theme_system)
        theme_box_layout.addWidget(self.btn_theme_system)

        nav_layout.addWidget(self.theme_switch_box)
        self._sync_theme_buttons()

        # 核心：设置中心按钮
        self.btn_settings = QPushButton()
        self.btn_settings.setObjectName("flatIconBtn")
        self.btn_settings.setIcon(get_icon("settings", size=16))
        self.btn_settings.setToolTip("工具箱设置中心 (Alt+S)")
        self.btn_settings.setFixedSize(32, 32)
        self.btn_settings.clicked.connect(self.open_settings_dialog)
        nav_layout.addWidget(self.btn_settings)

        # 核心：快捷返回首页按钮
        self.btn_back_home = QPushButton("返回首页 [Esc]")
        self.btn_back_home.setObjectName("btnBackHome")
        self.btn_back_home.setIcon(get_icon("arrow-left", color="#ffffff", size=15))
        self.btn_back_home.setToolTip("随时点击或按 Esc 键立即返回工具箱首页")
        self.btn_back_home.setVisible(False)
        self.btn_back_home.clicked.connect(self.go_to_home)
        nav_layout.addWidget(self.btn_back_home)

        main_layout.addWidget(self.nav_bar)

        # 2. 主页面堆叠容器
        self.stack = QStackedWidget()
        self.stack.setObjectName("mainStack")
        main_layout.addWidget(self.stack, 1)

        # 首页位于 Index 0
        self.home_page = HomePage()
        self.home_page.open_plugin_requested.connect(self.switch_to_plugin)
        self.home_page.open_standalone_requested.connect(self._open_plugin_standalone_by_id)
        self.stack.addWidget(self.home_page)

        # 3. 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 · 随开随用")

        self._update_nav_icons()

    def _sync_theme_buttons(self):
        mode = self.theme_manager.get_mode()
        if mode == THEME_LIGHT:
            self.btn_theme_light.setChecked(True)
        elif mode == THEME_DARK:
            self.btn_theme_dark.setChecked(True)
        else:
            self.btn_theme_system.setChecked(True)

    def _set_theme(self, mode: str):
        self.theme_manager.set_mode(mode)
        self._sync_theme_buttons()
        self._update_nav_icons()

    def _update_nav_icons(self):
        is_dark = self.theme_manager.is_dark()
        mode = self.theme_manager.get_mode()

        logo_color = "#38bdf8" if is_dark else "#0284c7"
        self.lbl_logo.setPixmap(get_pixmap("app_logo", color=logo_color, size=22))
        self.lbl_bc_sep.setPixmap(get_pixmap("chevron-right", color="#64748b", size=14))
        self.btn_back_home.setIcon(get_icon("arrow-left", color="#ffffff" if is_dark else "#1e293b", size=15))

        # 动态着色主题切换按钮图标：选中态高对比度醒目，未选中态低饱和度弱化
        active_color = "#ffffff" if is_dark else "#2563eb"
        inactive_color = "#64748b" if is_dark else "#94a3b8"

        self.btn_theme_light.setIcon(get_icon("sun", color=active_color if mode == THEME_LIGHT else inactive_color, size=15))
        self.btn_theme_dark.setIcon(get_icon("moon", color=active_color if mode == THEME_DARK else inactive_color, size=15))
        self.btn_theme_system.setIcon(get_icon("monitor", color=active_color if mode == THEME_SYSTEM else inactive_color, size=15))
        self.btn_settings.setIcon(get_icon("settings", color=active_color if is_dark else "#475569", size=16))

    def init_shortcuts(self):
        """注册全局快捷键返回首页与设置"""
        shortcut_esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        shortcut_esc.activated.connect(self.go_to_home)

        shortcut_alt_left = QShortcut(QKeySequence("Alt+Left"), self)
        shortcut_alt_left.activated.connect(self.go_to_home)

        shortcut_alt_home = QShortcut(QKeySequence("Alt+Home"), self)
        shortcut_alt_home.activated.connect(self.go_to_home)

        shortcut_settings = QShortcut(QKeySequence("Alt+S"), self)
        shortcut_settings.activated.connect(self.open_settings_dialog)

    def init_connections(self):
        self.event_bus.navigate_home.connect(self.go_to_home)
        self.event_bus.navigate_to_plugin.connect(self.switch_to_plugin)
        self.event_bus.status_message.connect(self.status_bar.showMessage)
        self.event_bus.theme_changed.connect(lambda t: (self._sync_theme_buttons(), self._update_nav_icons()))
        self.event_bus.settings_changed.connect(self._on_settings_changed)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    _open_settings_dialog = open_settings_dialog

    def _on_settings_changed(self):
        """响应设置变更，实时刷新视觉效果与窗口状态"""
        self.apply_visual_settings()
        for win in list(self._plugin_windows.values()):
            if win.isVisible():
                win.apply_visual_settings()

    def load_plugins(self):
        """扫描并加载所有插件"""
        self.plugin_manager.discover_and_load()
        plugins = self.plugin_manager.get_all_plugins()
        self.home_page.set_plugins(plugins)
        self.status_bar.showMessage(f"已加载 {len(plugins)} 个功能模块，随开随用")

        # 检查是否为开机自启动直接调度
        if "--autostart" in sys.argv:
            as_cfg = self.config_manager.get_autostart_config()
            if as_cfg.get("enabled", False):
                pids = [pid for pid in as_cfg.get("plugins", [])
                        if self.plugin_manager.get_plugin(pid) and self.config_manager.is_plugin_enabled(pid)]
                if len(pids) > 1 and not self.config_manager.get_multi_window_mode():
                    for pid in pids:
                        p = self.plugin_manager.get_plugin(pid)
                        self._open_plugin_standalone(p)
                else:
                    for pid in pids:
                        self.switch_to_plugin(pid)

        if self.initial_plugin_id and self.plugin_manager.get_plugin(self.initial_plugin_id):
            self.switch_to_plugin(self.initial_plugin_id)
            if self.initial_paths:
                p = self.plugin_manager.get_plugin(self.initial_plugin_id)
                if p:
                    p.handle_initial_paths(self.initial_paths)

        # 恢复常驻系统托盘的插件快捷图标
        try:
            from toolbox.core.tray_manager import PluginTrayManager
            tray_mgr = PluginTrayManager()
            for pid in self.config_manager.get_tray_plugins():
                p = self.plugin_manager.get_plugin(pid)
                if p and self.config_manager.is_plugin_enabled(pid):
                    tray_mgr.add_tray_icon(
                        p,
                        on_open_callback=lambda target_id=pid: self.switch_to_plugin(target_id),
                        on_settings_callback=lambda target_id=pid: self._open_plugin_settings_dialog(target_id),
                        on_exit_callback=lambda target_id=pid: tray_mgr.remove_tray_icon(target_id),
                        on_export_callback=lambda target_id=pid: self.home_page._open_export_dialog(target_id)
                    )
        except Exception as e:
            print(f"[MainWindow] 恢复托盘图标异常: {e}")

        # 初始化主应用系统托盘图标
        try:
            self.init_app_tray()
        except Exception as e:
            print(f"[MainWindow] 初始化应用托盘图标异常: {e}")

    def _open_plugin_settings_dialog(self, plugin_id: str):
        """打开特定插件的独立设置对话框"""
        plugin = self.plugin_manager.get_plugin(plugin_id)
        if plugin:
            from toolbox.ui.standalone_settings_dialog import StandalonePluginSettingsDialog
            diag = StandalonePluginSettingsDialog(plugin, parent=self)
            diag.exec()

    def _open_plugin_standalone_by_id(self, plugin_id: str):
        plugin = self.plugin_manager.get_plugin(plugin_id)
        if plugin:
            w = plugin._widget
            if w and self.stack.indexOf(w) != -1:
                self.stack.removeWidget(w)
            self._open_plugin_standalone(plugin)

    def switch_to_plugin(self, plugin_id: str):
        """
        进入插件专属操作界面：
        1. 检查多开模式：若开启则弹出独立窗口并保留首页常驻
        2. 若单窗口模式：在主界面 Stack 中切换并更新面包屑
        """
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

        plugin = self.plugin_manager.get_plugin(plugin_id)
        if not plugin:
            QMessageBox.warning(self, "未找到插件", f"未找到标识为 [{plugin_id}] 的功能模块。")
            return

        # 核心：检查是否开启多开模式 (在新独立窗口打开)
        if self.config_manager.get_multi_window_mode():
            w = plugin._widget
            if w and self.stack.indexOf(w) != -1:
                self.stack.removeWidget(w)
            self._open_plugin_standalone(plugin)
            return

        # 常规单窗口模式
        try:
            widget = plugin.get_widget(self.stack)
            idx = self.stack.indexOf(widget)
            if idx == -1:
                idx = self.stack.addWidget(widget)
                self._plugin_page_indices[plugin_id] = idx
        except Exception as e:
            QMessageBox.critical(self, "加载插件界面异常", f"创建插件 [{plugin.name}] 界面失败: {e}")
            return

        self.stack.setCurrentIndex(idx)

        # 激活插件
        self.plugin_manager.activate_plugin(plugin_id)
        self.config_manager.record_recent_plugin(plugin_id)
        self.home_page._rebuild_recent_bar()

        # 面包屑状态更新
        self.lbl_bc_sep.setVisible(True)
        self.lbl_bc_plugin.setText(plugin.name)
        self.lbl_bc_plugin.setVisible(True)
        self.btn_back_home.setVisible(True)
        self.status_bar.showMessage(f"当前功能: {plugin.name} · 按 [Esc] 或点击右上角返回首页")

    def _open_plugin_standalone(self, plugin):
        """以独立窗口形式打开插件并保留首页常驻"""
        pid = plugin.id
        if pid in self._plugin_windows and self._plugin_windows[pid].isVisible():
            win = self._plugin_windows[pid]
            win.raise_()
            win.activateWindow()
        else:
            win = PluginStandaloneWindow(plugin, on_close_callback=self._on_standalone_closed)
            self._plugin_windows[pid] = win
            win.show()
            win.raise_()
            win.activateWindow()

        self.config_manager.record_recent_plugin(pid)
        self.home_page._rebuild_recent_bar()
        self.status_bar.showMessage(f"已在独立新窗口打开: {plugin.name} (首页常驻可继续开启其它工具)")

    def _on_standalone_closed(self, plugin_id: str):
        if plugin_id in self._plugin_windows:
            del self._plugin_windows[plugin_id]

    def showEvent(self, event):
        super().showEvent(event)

    def nativeEvent(self, eventType, message):
        """实时拦截 Windows 系统外观与主题设置变动事件 (WM_SETTINGCHANGE)"""
        if eventType in (b"windows_generic_MSG", "windows_generic_MSG"):
            try:
                import ctypes
                from ctypes import wintypes
                msg = ctypes.wintypes.MSG.from_address(message.__int__())
                if msg.message == 0x001A:  # WM_SETTINGCHANGE
                    if self.theme_manager.get_mode() == THEME_SYSTEM:
                        self.theme_manager.check_system_theme_update()
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def go_to_home(self):
        """快捷返回首页"""
        if self.stack.currentIndex() == 0:
            return

        self.plugin_manager.deactivate_current_plugin()
        self.stack.setCurrentIndex(0)
        self.lbl_bc_sep.setVisible(False)
        self.lbl_bc_plugin.setVisible(False)
        self.btn_back_home.setVisible(False)
        self.status_bar.showMessage("已返回首页 · 随选随用")

    def init_app_tray(self):
        """初始化主工具箱系统托盘图标"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.app_tray_icon = None
            return

        icon = self.windowIcon()
        if not icon or icon.isNull():
            icon = get_icon("app_logo", size=32)

        self.app_tray_icon = QSystemTrayIcon(icon, self)
        self.app_tray_icon.setToolTip("千绘莉多功能工具箱")

        menu = QMenu(self)

        act_open = QAction(icon, "打开主界面", menu)
        font = act_open.font()
        font.setBold(True)
        act_open.setFont(font)
        act_open.triggered.connect(self._tray_restore_window)
        menu.addAction(act_open)

        act_home = QAction(get_icon("home", size=16), "返回首页", menu)
        act_home.triggered.connect(self._tray_go_home)
        menu.addAction(act_home)

        menu.addSeparator()

        recent_menu = menu.addMenu(get_icon("star", size=16), "常用插件")
        plugins = self.plugin_manager.get_all_plugins()
        for p in plugins[:8]:
            act_p = QAction(p.name, recent_menu)
            act_p.triggered.connect(lambda checked=False, pid=p.id: self._tray_open_plugin(pid))
            recent_menu.addAction(act_p)

        menu.addSeparator()

        act_settings = QAction(get_icon("settings", size=16), "设置中心...", menu)
        act_settings.triggered.connect(self.open_settings_dialog)
        menu.addAction(act_settings)

        menu.addSeparator()

        act_exit = QAction(get_icon("clear", size=16), "退出工具箱", menu)
        act_exit.triggered.connect(self._tray_exit_app)
        menu.addAction(act_exit)

        self.app_tray_icon.setContextMenu(menu)
        self.app_tray_icon.activated.connect(self._on_app_tray_activated)
        self.app_tray_icon.show()

    def _tray_restore_window(self):
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def _tray_go_home(self):
        self.go_to_home()
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def _tray_open_plugin(self, plugin_id: str):
        self.switch_to_plugin(plugin_id)
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def _tray_exit_app(self):
        self._force_exit = True
        if hasattr(self, "app_tray_icon") and self.app_tray_icon:
            self.app_tray_icon.hide()
            self.app_tray_icon.deleteLater()
            self.app_tray_icon = None
        self.close()
        QApplication.quit()

    def _on_app_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.activateWindow()
            else:
                if self.isMinimized():
                    self.showNormal()
                else:
                    self.show()
                self.raise_()
                self.activateWindow()

    def closeEvent(self, event):
        """窗口关闭时清理所有插件资源"""
        close_to_tray = self.config_manager.get("close_to_tray", False)
        if not getattr(self, "_force_exit", False) and close_to_tray and getattr(self, "app_tray_icon", None) and self.app_tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.app_tray_icon.showMessage(
                "千绘莉多功能工具箱",
                "工具箱已在后台托盘常驻，双击或右键托盘图标可重新打开。",
                QSystemTrayIcon.Information,
                2000
            )
            return

        for win in list(self._plugin_windows.values()):
            try:
                win.close()
            except Exception:
                pass
        self._plugin_windows.clear()

        self.plugin_manager.cleanup_all()
        try:
            from toolbox.core.tray_manager import PluginTrayManager
            PluginTrayManager().clear_all()
        except Exception:
            pass

        if hasattr(self, "app_tray_icon") and self.app_tray_icon:
            self.app_tray_icon.hide()
            self.app_tray_icon.deleteLater()
            self.app_tray_icon = None

        w_cfg = self.config_manager.get("window", {})
        if not self.isMaximized():
            self.config_manager.set("window", {
                "width": self.width(),
                "height": self.height(),
                "is_maximized": False
            })
        else:
            self.config_manager.set("window", {
                "width": w_cfg.get("width", 1120),
                "height": w_cfg.get("height", 750),
                "is_maximized": True
            })
        super().closeEvent(event)
        QApplication.quit()

