"""
插件惰性加载与防弹窗闪烁自动化验证套件
验证目标:
1. PluginManager.discover_and_load() 执行时仅加载轻量插件元数据，禁止预先导入任何插件的 ui.py 界面模块。
2. MainWindow 启动与首页展示阶段，不预先实例化任何插件 Widget。
3. SettingsDialog (功能模块管理) 打开阶段，不触发任何插件 Widget 构造。
4. 启动与管理期间无任何异常顶层弹窗 (visible top-level windows)。
5. 全量 22 个插件按需点击进入时均能正常惰性加载并成功创建 Widget。
6. ScreenCaptureWidget 启动与 settings 加载时不主动弹出 Xbox 悬浮胶囊窗。
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication, QWidget

# 确保在无头或桌面环境下运行
app = QApplication.instance()
if not app:
    app = QApplication(["--platform", "offscreen"])


class TestLazyPluginLoading(unittest.TestCase):
    def test_01_discovery_does_not_import_plugin_ui_modules(self):
        """验证全量插件动态发现时不预先导入任何插件的 ui.py"""
        import subprocess

        # 1. 干净子进程隔离验证（不受任何同进程内其他测试文件污染）
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "from toolbox.core.plugin_manager import PluginManager; "
                    "pm = PluginManager(); "
                    "pm.discover_and_load(); "
                    "assert len(pm.get_all_plugins()) == 22, 'Plugins count mismatch'; "
                    "ui_mods = [m for m in sys.modules if m.startswith('toolbox.plugins.') and m.endswith('.ui')]; "
                    "assert len(ui_mods) == 0, f'UI modules loaded during discovery: {ui_mods}'; "
                    "print('CLEAN_DISCOVERY_OK')"
                ),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"子进程隔离发现失败:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )
        self.assertIn("CLEAN_DISCOVERY_OK", proc.stdout)

        # 2. 当前进程增量验证
        before_ui_modules = {
            m for m in sys.modules
            if m.startswith("toolbox.plugins.") and m.endswith(".ui")
        }

        from toolbox.core.plugin_manager import PluginManager
        pm = PluginManager()
        pm.discover_and_load()

        plugins = pm.get_all_plugins()
        self.assertEqual(len(plugins), 22, "应发现并加载全量 22 个插件")

        after_ui_modules = {
            m for m in sys.modules
            if m.startswith("toolbox.plugins.") and m.endswith(".ui")
        }
        newly_imported = after_ui_modules - before_ui_modules
        self.assertEqual(
            list(newly_imported),
            [],
            f"插件发现时不应提前导入任何 ui.py 模块，但检测到新导入了: {newly_imported}"
        )

    def test_02_main_window_init_no_unwanted_popups_or_eager_widgets(self):
        """验证主窗口初始化时不预先创建插件 Widget，且不产生可见顶层弹窗"""
        from toolbox.ui.main_window import MainWindow

        win = MainWindow()
        pm = win.plugin_manager

        # 验证所有插件的 _widget 均为 None (未被惰性触发前)
        for p in pm.get_all_plugins():
            self.assertIsNone(
                p._widget,
                f"插件 [{p.id}] 在首页阶段被提前实例化了 Widget！"
            )

        # 验证没有可见的异常弹出窗口 (除 win 自身外，如果有)
        visible_top_levels = [w for w in QApplication.topLevelWidgets() if w.isVisible() and w is not win]
        self.assertEqual(
            visible_top_levels,
            [],
            f"检测到异常可见顶层弹窗: {visible_top_levels}"
        )
        win.close()

    def test_03_settings_dialog_does_not_instantiate_widgets(self):
        """验证打开设置中心（功能模块管理）时不触发任何插件 Widget 构造"""
        from toolbox.ui.main_window import MainWindow
        from toolbox.ui.settings_dialog import SettingsDialog

        win = MainWindow()
        pm = win.plugin_manager

        dlg = SettingsDialog(parent=win)

        for p in pm.get_all_plugins():
            self.assertIsNone(
                p._widget,
                f"插件 [{p.id}] 在打开设置中心时被错误实例化了 Widget！"
            )

        dlg.close()
        win.close()

    def test_04_screen_capture_overlay_never_shows_on_init(self):
        """验证截图工具在开启 xbox_overlay 配置时，初始化也不会直接弹出浮动置顶窗口"""
        from toolbox.core.config_manager import ConfigManager
        cfg = ConfigManager()
        orig_sc_cfg = cfg.get_plugin_config("screen_capture", {})
        
        try:
            # 模拟用户开启了 xbox_overlay
            fake_cfg = dict(orig_sc_cfg)
            fake_cfg["xbox_overlay"] = True
            cfg.set_plugin_config("screen_capture", fake_cfg)

            from toolbox.plugins.screen_capture.plugin import ScreenCapturePlugin
            sc_plugin = ScreenCapturePlugin()
            sc_widget = sc_plugin.create_widget()

            # 验证即使配置中 xbox_overlay 为 True，在 widget 未处于可见状态时也不会弹出
            if sc_widget.xbox_overlay:
                self.assertFalse(
                    sc_widget.xbox_overlay.isVisible(),
                    "XboxCaptureOverlayWidget 不应在隐藏初始化状态下显示！"
                )
            sc_widget.cleanup()
        finally:
            cfg.set_plugin_config("screen_capture", orig_sc_cfg)

    def test_05_all_22_plugins_can_be_lazily_loaded_and_navigated(self):
        """验证全量 22 个插件按需导航时能够正常完成惰性加载并返回有效 Widget"""
        from toolbox.ui.main_window import MainWindow

        win = MainWindow()
        pm = win.plugin_manager

        for p in pm.get_all_plugins():
            self.assertIsNone(p._widget, f"插件 [{p.id}] 初始态应未加载 Widget")
            win.switch_to_plugin(p.id)
            self.assertIsNotNone(p._widget, f"插件 [{p.id}] 导航后未能惰性创建 Widget")
            self.assertIsInstance(p._widget, QWidget)

        win.go_to_home()
        win.close()

    def test_06_deleted_underlying_cpp_widget_recovers_gracefully(self):
        """验证当底层 C++ 部件被外部或父窗体销毁时，PluginBase 不会崩溃且自动完成恢复"""
        from toolbox.plugins.whiteboard.plugin import WhiteboardPlugin

        p = WhiteboardPlugin()
        parent_w = QWidget()
        w = p.get_widget(parent_w)
        self.assertIsNotNone(w)
        self.assertIsNotNone(p._widget)

        # 模拟外部父窗体被销毁导致底层 C++ QWidget 被析构
        parent_w.deleteLater()
        QApplication.processEvents()

        # 此时调用 on_activated / on_deactivated 应安全不抛出 RuntimeError
        try:
            p.on_activated()
            p.on_deactivated()
        except RuntimeError as e:
            self.fail(f"在底层部件被销毁后触发生命周期钩子抛出了 RuntimeError: {e}")

        # 重新获取部件应成功重新构造，而不是崩溃
        new_w = p.get_widget()
        self.assertIsNotNone(new_w)
        self.assertIsInstance(new_w, QWidget)

    def test_07_standalone_window_close_does_not_leave_dangling_visible_widgets(self):
        """验证在多开独立窗口中打开插件并关闭时，部件被安全隐藏且不残留悬浮孤儿窗口"""
        from toolbox.ui.main_window import MainWindow

        win = MainWindow()
        pm = win.plugin_manager
        plugin = pm.get_plugin("file_suite")
        self.assertIsNotNone(plugin)

        # 开启独立子窗口
        win._open_plugin_standalone(plugin)
        self.assertIn("file_suite", win._plugin_windows)
        swin = win._plugin_windows["file_suite"]

        # 关闭独立子窗口
        swin.close()
        QApplication.processEvents()

        # 验证插件部件当前处于隐藏状态且 parent 为 None 或已被安全重置
        if plugin._widget:
            self.assertFalse(plugin._widget.isVisible(), "独立窗口关闭后部件必须已被隐藏！")

        # 验证没有残留的可见顶层孤儿窗口
        visible_tops = [w for w in QApplication.topLevelWidgets() if w.isVisible() and w is not win]
        self.assertEqual(visible_tops, [], f"检测到残留可见窗口: {visible_tops}")

        win.close()

    def test_08_screen_capture_background_snip_never_pops_hidden_mainwindow(self):
        """验证截图工具在主窗口隐藏或最小化时执行截图操作，绝不错误弹回 MainWindow 或悬浮坞"""
        from toolbox.plugins.screen_capture.plugin import ScreenCapturePlugin
        from toolbox.ui.main_window import MainWindow

        win = MainWindow()
        win.hide()
        QApplication.processEvents()
        self.assertFalse(win.isVisible(), "主窗口初始应为隐藏状态")

        sc_plugin = win.plugin_manager.get_plugin("screen_capture")
        sc_widget = sc_plugin.get_widget(win.stack)

        # 模拟在后台静默触发全屏/窗口截图
        sc_widget._window_was_visible = False
        sc_widget._do_fullscreen_snip()
        sc_widget._do_window_snip()
        QApplication.processEvents()

        self.assertFalse(win.isVisible(), "执行截图后不应强制弹出隐藏中的主窗口！")
        if sc_widget.xbox_overlay:
            self.assertFalse(sc_widget.xbox_overlay.isVisible(), "执行截图后悬浮坞不应在部件隐藏时弹出！")

        win.close()

    def test_09_homepage_cards_never_trigger_top_level_windows_during_render(self):
        """验证首页卡片、最近使用栏与分类导航按钮在渲染与刷新时，绝不因缺少 parent 而弹出为独立顶层窗口"""
        from toolbox.ui.home_page import HomePage
        from toolbox.core.plugin_manager import PluginManager
        from toolbox.ui.components.card_widget import PluginCardWidget

        # 监控所有 QWidget 的 setVisible(True) 操作，一旦发现卡片在没有 parent 的情况下被设置为可见立即记录
        rogue_top_level_widgets = []
        orig_set_visible = QWidget.setVisible

        def intercepted_set_visible(widget, visible):
            if visible and widget.parent() is None and isinstance(widget, (PluginCardWidget, QFrame)):
                rogue_top_level_widgets.append((widget.__class__.__name__, widget.objectName()))
            return orig_set_visible(widget, visible)

        QWidget.setVisible = intercepted_set_visible
        try:
            pm = PluginManager()
            plugins = pm.get_all_plugins()
            if not plugins:
                pm.discover_and_load()
                plugins = pm.get_all_plugins()

            home = HomePage()
            home.set_plugins(plugins)
            QApplication.processEvents()

            # 再次强制切换分类并搜索，模拟用户频繁交互刷新
            home.current_category = "全部"
            home._filter_and_render_cards()
            QApplication.processEvents()

            home.current_category = "最近使用"
            home._filter_and_render_cards()
            QApplication.processEvents()

            home.close()
        finally:
            QWidget.setVisible = orig_set_visible

        self.assertEqual(
            rogue_top_level_widgets,
            [],
            f"严禁在未挂载父容器时将卡片设置为可见引发桌面幽灵弹窗: {rogue_top_level_widgets}"
        )


if __name__ == "__main__":
    unittest.main()

