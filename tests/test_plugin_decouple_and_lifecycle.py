"""
千绘莉工具箱 (Chieri Toolbox) - 底座解耦与随删随下生命周期全面自动化测试套件
验证目标:
1. 外部解耦目录识别 (%APPDATA%/ChieriToolbox/plugins 与 <exe_dir>/plugins_data) 及便携模式检测。
2. 插件 manifest.json 标准结构、元数据解析与磁盘大小计算。
3. 动态热加载 (Dynamic Load)：通过 spec_from_file_location 动态加载外部独立插件包。
4. 动态启停切换 (Enable / Disable)：配置持久化记录，禁用时不常驻内存。
5. 动态安全热卸载 (Hot Unload)：调用 teardown() 释放控件并清除 sys.modules 命名空间引用。
6. 物理卸载与空间回收 (Uninstall)：物理删除插件文件夹，彻底释放磁盘空间。
7. 离线包导入安装 (.cpk / .zip)：自动解压并热注册，带 ZipSlip 路径穿越防御。
8. 恶意包 ZipSlip 路径穿越攻击防御 (针对 ../、绝对路径、盘符注入强制拦截)。
9. 导出标准 .cpk 便携插件包。
10. 插件工坊 UI (PluginHubWidget / PluginHubDialog) 与主窗口联动集成。
"""

import gc
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from PySide6.QtWidgets import QApplication

# 确保无头测试环境
app = QApplication.instance()
if not app:
    app = QApplication(["--platform", "offscreen"])

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from toolbox.core.paths import (
    get_plugins_search_dirs, get_external_plugins_dir, is_portable_mode, get_app_root
)
from toolbox.core.config_manager import ConfigManager
from toolbox.core.plugin_base import PluginBase
from toolbox.core.plugin_manager import PluginManager
from toolbox.core.plugin_exporter import PluginExporter


class TestPluginDecoupleAndLifecycle(unittest.TestCase):
    def setUp(self):
        ConfigManager.reset_instance()
        PluginManager.reset_instance()
        self.pm = PluginManager()

    def tearDown(self):
        ConfigManager.reset_instance()
        PluginManager.reset_instance()

    def test_01_paths_decoupled_resolution(self):
        """验证解耦式插件存放目录与便携模式解析"""
        ext_dir = get_external_plugins_dir()
        self.assertTrue(bool(ext_dir))

        search_dirs = get_plugins_search_dirs()
        self.assertTrue(len(search_dirs) >= 1)
        # 内置目录必须在搜索路径中
        builtin_dir = os.path.normpath(os.path.join(PROJECT_ROOT, "toolbox", "plugins"))
        self.assertIn(builtin_dir, [os.path.normpath(d) for d in search_dirs])

        # 验证便携模式判定
        orig_argv = list(sys.argv)
        try:
            sys.argv.append("--portable")
            self.assertTrue(is_portable_mode())
            p_ext = get_external_plugins_dir()
            self.assertTrue(p_ext.endswith("plugins_data"))
        finally:
            sys.argv = orig_argv

    def test_02_all_builtin_plugins_have_valid_manifests_and_metadata(self):
        """验证全部 22 个内置插件均具备合规的 manifest 元数据与接口规范"""
        self.pm.discover_and_load()
        plugins = self.pm.get_all_plugins()
        self.assertEqual(len(plugins), 28, "内置插件总数应为 28 个")

        for p in plugins:
            self.assertTrue(p.is_builtin, f"插件 {p.id} 应为内置核心")
            p_dir = p.get_plugin_dir()
            self.assertTrue(os.path.isdir(p_dir), f"插件目录不存在: {p_dir}")

            manifest_p = os.path.join(p_dir, "manifest.json")
            self.assertTrue(os.path.isfile(manifest_p), f"缺少 manifest.json: {manifest_p}")

            manifest = p.get_manifest()
            self.assertEqual(manifest["id"], p.id)
            self.assertTrue(bool(manifest["name"]))
            self.assertTrue(bool(manifest["version"]))
            self.assertTrue(bool(manifest["category"]))
            self.assertGreaterEqual(p.get_file_size(), 0)

    def test_03_dynamic_load_external_plugin_package(self):
        """验证通过 spec_from_file_location 动态热加载外部独立扩展插件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            ext_plugin_dir = os.path.join(temp_dir, "calc_tool")
            os.makedirs(ext_plugin_dir)

            # 编写外部插件 manifest.json
            manifest_content = {
                "id": "calc_tool",
                "name": "极速计算工坊",
                "version": "1.0.0",
                "author": "ChieriExternal",
                "category": "开发辅助",
                "description": "外部独立扩展数学计算工坊",
                "icon": "tools",
                "entry_point": "plugin.py",
                "sort_order": 999
            }
            with open(os.path.join(ext_plugin_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest_content, f, ensure_ascii=False)

            # 编写外部插件 plugin.py
            plugin_py_content = """
from PySide6.QtWidgets import QLabel, QWidget
from toolbox.core.plugin_base import PluginBase

class CalcToolPlugin(PluginBase):
    id = "calc_tool"
    name = "极速计算工坊"
    category = "开发辅助"
    description = "外部独立扩展数学计算工坊"
    version = "1.0.0"
    author = "ChieriExternal"
    sort_order = 999

    def create_widget(self, parent=None):
        w = QLabel("Calc Tool Running", parent)
        return w
"""
            with open(os.path.join(ext_plugin_dir, "plugin.py"), "w", encoding="utf-8") as f:
                f.write(plugin_py_content)

            # 动态热加载
            plugin = self.pm.load_external_plugin(ext_plugin_dir)
            self.assertIsNotNone(plugin)
            self.assertEqual(plugin.id, "calc_tool")
            self.assertEqual(plugin.name, "极速计算工坊")
            self.assertFalse(plugin.is_builtin)
            self.assertEqual(plugin.get_plugin_dir(), ext_plugin_dir)

            # 验证命名空间已注入 sys.modules
            self.assertIn("chieri_plugin_calc_tool", sys.modules)

            # 验证创建 Widget
            widget = plugin.create_widget()
            self.assertIsNotNone(widget)

            # 验证可以通过 pm.get_plugin 获取
            self.assertEqual(self.pm.get_plugin("calc_tool"), plugin)

    def test_04_dynamic_enable_disable_toggle(self):
        """验证插件动态启停切换与内存注销"""
        self.pm.discover_and_load()
        target_id = "video_to_audio"
        self.assertIsNotNone(self.pm.get_plugin(target_id))

        # 1. 动态停用
        ok = self.pm.disable_plugin(target_id)
        self.assertTrue(ok)
        self.assertFalse(ConfigManager().is_plugin_enabled(target_id))
        self.assertIn(target_id, ConfigManager().get_disabled_plugins())
        self.assertIsNone(self.pm.get_plugin(target_id), "停用后内存实例应被卸载清空")

        # 2. 动态启用
        reloaded = self.pm.enable_plugin(target_id)
        self.assertIsNotNone(reloaded)
        self.assertTrue(ConfigManager().is_plugin_enabled(target_id))
        self.assertEqual(self.pm.get_plugin(target_id), reloaded)

    def test_05_dynamic_hot_unload_and_namespace_purging(self):
        """验证动态热卸载安全释放 UI 控件并清除 sys.modules 命名空间"""
        with tempfile.TemporaryDirectory() as temp_dir:
            p_dir = os.path.join(temp_dir, "hot_test")
            os.makedirs(p_dir)
            with open(os.path.join(p_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"id": "hot_test", "name": "HotTest", "entry_point": "plugin.py"}, f)

            with open(os.path.join(p_dir, "plugin.py"), "w", encoding="utf-8") as f:
                f.write("""
from PySide6.QtWidgets import QLabel
from toolbox.core.plugin_base import PluginBase

class HotTestPlugin(PluginBase):
    id = "hot_test"
    name = "HotTest"
    def create_widget(self, parent=None):
        return QLabel("HotWidget", parent)
""")

            plugin = self.pm.load_external_plugin(p_dir)
            self.assertIsNotNone(plugin)
            widget = plugin.get_widget()
            self.assertIsNotNone(widget)
            self.assertIn("chieri_plugin_hot_test", sys.modules)

            # 执行热卸载
            unloaded = self.pm.unload_plugin("hot_test")
            self.assertTrue(unloaded)
            self.assertIsNone(self.pm.get_plugin("hot_test"))
            self.assertIsNone(plugin._widget)
            self.assertNotIn("chieri_plugin_hot_test", sys.modules)

    def test_06_export_plugin_cpk_portable_package(self):
        """验证将插件导出为标准的 .cpk 便携分发包"""
        self.pm.discover_and_load()
        with tempfile.TemporaryDirectory() as temp_out:
            cpk_file = self.pm.export_plugin_cpk("ncm_decryptor", temp_out)
            self.assertTrue(os.path.isfile(cpk_file))
            self.assertTrue(cpk_file.endswith(".cpk"))

            # 验证归档内容合规性
            with zipfile.ZipFile(cpk_file, "r") as zf:
                names = zf.namelist()
                self.assertIn("manifest.json", names)
                self.assertIn("plugin.py", names)
                manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                self.assertEqual(manifest_data["id"], "ncm_decryptor")

    def test_07_install_plugin_package_import(self):
        """验证从本地 .cpk 插件包一键解压并动态安装注册"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cpk_path = os.path.join(temp_dir, "dummy_addon-1.0.0.cpk")
            target_install_dir = os.path.join(temp_dir, "installed_plugins")

            # 构造合法 .cpk 归档
            with zipfile.ZipFile(cpk_path, "w") as zf:
                manifest_json = json.dumps({
                    "id": "dummy_addon",
                    "name": "离线测试插件",
                    "version": "1.0.0",
                    "category": "系统效率",
                    "description": "离线包导入测试",
                    "entry_point": "plugin.py"
                })
                zf.writestr("manifest.json", manifest_json)
                code_content = """
from PySide6.QtWidgets import QLabel
from toolbox.core.plugin_base import PluginBase

class DummyAddonPlugin(PluginBase):
    id = "dummy_addon"
    name = "离线测试插件"
    category = "系统效率"
    description = "离线包导入测试"
    def create_widget(self, parent=None):
        return QLabel("Dummy Content", parent)
"""
                zf.writestr("plugin.py", code_content)

            # 安装测试
            installed_plugin = self.pm.install_plugin_package(cpk_path, target_dir=target_install_dir)
            self.assertIsNotNone(installed_plugin)
            self.assertEqual(installed_plugin.id, "dummy_addon")
            self.assertEqual(installed_plugin.name, "离线测试插件")
            self.assertTrue(os.path.isfile(os.path.join(target_install_dir, "dummy_addon", "plugin.py")))
            self.assertEqual(self.pm.get_plugin("dummy_addon"), installed_plugin)

    def test_08_zipslip_path_traversal_attack_defense(self):
        """验证严苛防御恶意包 ZipSlip 路径穿越漏洞 (.. 及绝对路径攻击)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = os.path.join(temp_dir, "safe_plugins")

            # 攻击用例 1: 使用 .. 路径穿越跳出目录
            evil_cpk1 = os.path.join(temp_dir, "evil_slip.cpk")
            with zipfile.ZipFile(evil_cpk1, "w") as zf:
                zf.writestr("../../evil_payload.txt", "MALICIOUS CONTENT")
                zf.writestr("manifest.json", json.dumps({"id": "evil_p1"}))

            with self.assertRaises(ValueError) as ctx1:
                self.pm.install_plugin_package(evil_cpk1, target_dir=install_dir)
            self.assertIn("ZipSlip", str(ctx1.exception))
            self.assertFalse(os.path.exists(os.path.join(temp_dir, "evil_payload.txt")))

            # 攻击用例 2: 使用根绝对路径攻击
            evil_cpk2 = os.path.join(temp_dir, "evil_abs.cpk")
            with zipfile.ZipFile(evil_cpk2, "w") as zf:
                zf.writestr("/root_evil.txt", "MALICIOUS ABSOLUTE")
                zf.writestr("manifest.json", json.dumps({"id": "evil_p2"}))

            with self.assertRaises(ValueError) as ctx2:
                self.pm.install_plugin_package(evil_cpk2, target_dir=install_dir)
            self.assertIn("ZipSlip", str(ctx2.exception))

            # 攻击用例 3: 盘符注入攻击
            evil_cpk3 = os.path.join(temp_dir, "evil_drive.cpk")
            with zipfile.ZipFile(evil_cpk3, "w") as zf:
                zf.writestr("C:evil.txt", "MALICIOUS DRIVE")
                zf.writestr("manifest.json", json.dumps({"id": "evil_p3"}))

            with self.assertRaises(ValueError) as ctx3:
                self.pm.install_plugin_package(evil_cpk3, target_dir=install_dir)
            self.assertIn("ZipSlip", str(ctx3.exception))

    def test_09_physical_uninstall_reclaims_disk_space(self):
        """验证物理删除卸载插件彻底回收磁盘空间"""
        with tempfile.TemporaryDirectory() as temp_dir:
            p_dir = os.path.join(temp_dir, "to_delete_plugin")
            os.makedirs(p_dir)
            with open(os.path.join(p_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"id": "to_delete_plugin", "name": "待删除插件", "entry_point": "plugin.py"}, f)

            with open(os.path.join(p_dir, "plugin.py"), "w", encoding="utf-8") as f:
                f.write("""
from PySide6.QtWidgets import QLabel
from toolbox.core.plugin_base import PluginBase
class ToDeletePlugin(PluginBase):
    id = "to_delete_plugin"
    name = "待删除插件"
    def create_widget(self, parent=None): return QLabel("test", parent)
""")

            plugin = self.pm.load_external_plugin(p_dir)
            self.assertIsNotNone(plugin)
            self.assertTrue(os.path.exists(p_dir))

            # 执行物理卸载
            ok = self.pm.uninstall_plugin("to_delete_plugin")
            self.assertTrue(ok)
            self.assertFalse(os.path.exists(p_dir), "插件文件夹应被彻底物理删除")
            self.assertIsNone(self.pm.get_plugin("to_delete_plugin"))

    def test_10_plugin_hub_ui_functionality(self):
        """验证插件工坊 UI (PluginHubWidget / PluginHubDialog) 检索与生命周期交互"""
        from toolbox.ui.plugin_hub_dialog import PluginHubWidget, PluginHubDialog

        self.pm.discover_and_load()
        dialog = PluginHubDialog()
        widget = dialog.hub_widget

        # 验证卡片数量与 22 个内置核心一致
        self.assertGreaterEqual(widget.cards_layout.count(), 22)

        # 验证搜索过滤
        widget._on_search_text_changed("b站")
        self.assertGreaterEqual(len(widget.pm.get_all_plugin_records()), 22)

        # 验证分类过滤
        widget._on_filter_chip_clicked("enabled")
        widget._on_filter_chip_clicked("builtin")
        widget._on_filter_chip_clicked("all")

        dialog.close()

    def test_11_main_window_plugin_hub_integration(self):
        """验证主窗口顶部导航栏插件工坊入口与动态生命周期联动"""
        from toolbox.ui.main_window import MainWindow

        win = MainWindow()
        self.assertTrue(hasattr(win, "btn_plugin_hub"))
        self.assertIsNotNone(win.btn_plugin_hub)

        # 验证初始已加载 28 个模块
        self.assertEqual(len(win.home_page.plugins), 28)

        # 模拟外部动态安装新插件，验证主窗口与 HomePage 实时响应
        with tempfile.TemporaryDirectory() as temp_dir:
            new_p_dir = os.path.join(temp_dir, "ext_flow")
            os.makedirs(new_p_dir)
            with open(os.path.join(new_p_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"id": "ext_flow", "name": "实时动态流插件", "entry_point": "plugin.py", "sort_order": 5}, f)
            with open(os.path.join(new_p_dir, "plugin.py"), "w", encoding="utf-8") as f:
                f.write("""
from PySide6.QtWidgets import QLabel
from toolbox.core.plugin_base import PluginBase
class ExtFlowPlugin(PluginBase):
    id = "ext_flow"
    name = "实时动态流插件"
    sort_order = 5
    def create_widget(self, parent=None): return QLabel("Flow", parent)
""")
            new_p = win.plugin_manager.load_external_plugin(new_p_dir)
            self.assertIsNotNone(new_p)

            # 验证 HomePage 已自动同步更新
            self.assertEqual(len(win.home_page.plugins), 29)
            self.assertIn("ext_flow", [p.id for p in win.home_page.plugins])

            # 卸载测试
            win.plugin_manager.uninstall_plugin("ext_flow")
            self.assertEqual(len(win.home_page.plugins), 28)

        win.close()

    def test_12_manifest_entry_point_path_traversal_defense(self):
        """验证 manifest.json 中的 entry_point 路径穿越攻击防御 (如 ../../malicious.py)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            outside_script = os.path.join(temp_dir, "outside_script.py")
            with open(outside_script, "w", encoding="utf-8") as f:
                f.write("""
from toolbox.core.plugin_base import PluginBase
class EscapedPlugin(PluginBase):
    id = "escaped"
    name = "Escaped"
    def create_widget(self, parent=None): return None
""")
            evil_plugin_dir = os.path.join(temp_dir, "plugin_sandbox")
            os.makedirs(evil_plugin_dir)
            with open(os.path.join(evil_plugin_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"id": "evil_escape", "name": "Evil", "entry_point": "../outside_script.py"}, f)

            # 动态热加载必须拦截越界 entry_point，拒绝逃逸并返回 None
            loaded = self.pm.load_external_plugin(evil_plugin_dir)
            self.assertIsNone(loaded, "必须拦截指向插件目录外部的恶意 entry_point")
            self.assertNotIn("chieri_plugin_evil_escape", sys.modules)

    def test_13_install_plugin_package_windows_backslash_compatibility(self):
        """验证离线包包含 Windows 反斜杠路径文件名时的自适应安装"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cpk_path = os.path.join(temp_dir, "win_backslash_addon.cpk")
            dest_dir = os.path.join(temp_dir, "dest_plugins")

            with zipfile.ZipFile(cpk_path, "w") as zf:
                zf.writestr("win_addon\\", "")
                zf.writestr("win_addon\\manifest.json", json.dumps({
                    "id": "win_addon",
                    "name": "Windows反斜杠插件",
                    "version": "1.0.0",
                    "entry_point": "plugin.py"
                }))
                zf.writestr("win_addon\\plugin.py", """
from PySide6.QtWidgets import QLabel
from toolbox.core.plugin_base import PluginBase
class WinAddonPlugin(PluginBase):
    id = "win_addon"
    name = "Windows反斜杠插件"
    def create_widget(self, parent=None): return QLabel("Win", parent)
""")
            installed = self.pm.install_plugin_package(cpk_path, target_dir=dest_dir)
            self.assertIsNotNone(installed)
            self.assertEqual(installed.id, "win_addon")
            self.assertTrue(os.path.isfile(os.path.join(dest_dir, "win_addon", "plugin.py")))

    def test_14_install_plugin_package_rollback_on_failure(self):
        """验证安装损坏包（如语法错误/加载崩溃）时自动回滚，不残留脏数据"""
        with tempfile.TemporaryDirectory() as temp_dir:
            broken_cpk = os.path.join(temp_dir, "broken_syntax.cpk")
            dest_dir = os.path.join(temp_dir, "dest_plugins")

            with zipfile.ZipFile(broken_cpk, "w") as zf:
                zf.writestr("manifest.json", json.dumps({"id": "broken_p", "name": "Broken"}))
                # 语法错误的代码
                zf.writestr("plugin.py", "def syntax_error_func(:")

            target_folder = os.path.join(dest_dir, "broken_p")
            with self.assertRaises(Exception):
                self.pm.install_plugin_package(broken_cpk, target_dir=dest_dir)

            # 验证损坏的解压目录已被自动回滚物理清理
            self.assertFalse(os.path.exists(target_folder), "安装失败后必须回滚删除残留目录")
            self.assertNotIn("broken_p", self.pm._plugins)

    def test_15_export_plugin_cpk_into_own_folder_self_containment(self):
        """验证将 .cpk 导出到插件自身目录时不会产生自我包含的递归嵌套错误"""
        with tempfile.TemporaryDirectory() as temp_dir:
            p_dir = os.path.join(temp_dir, "self_export_test")
            os.makedirs(p_dir)
            with open(os.path.join(p_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"id": "self_export_test", "name": "SelfExport", "entry_point": "plugin.py"}, f)
            with open(os.path.join(p_dir, "plugin.py"), "w", encoding="utf-8") as f:
                f.write("""
from toolbox.core.plugin_base import PluginBase
class P(PluginBase):
    id = "self_export_test"
    name = "SelfExport"
    def create_widget(self, p=None): return None
""")
            plugin = self.pm.load_external_plugin(p_dir)
            self.assertIsNotNone(plugin)

            # 导出目标直接选在插件自身目录
            out_cpk = self.pm.export_plugin_cpk("self_export_test", p_dir)
            self.assertTrue(os.path.isfile(out_cpk))

            # 校验 zip 内不包含导出的 out_cpk 本身
            with zipfile.ZipFile(out_cpk, "r") as zf:
                self.assertNotIn(os.path.basename(out_cpk), zf.namelist())

    def test_16_plugin_cleanup_terminates_running_qthread_safely(self):
        """验证插件若有后台 QThread 运行，cleanup() 时能安全终止而不触发 Qt abort 崩溃"""
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QWidget
        import time

        class WorkerThread(QThread):
            def run(self):
                while not self.isInterruptionRequested():
                    time.sleep(0.01)

        class ThreadedPlugin(PluginBase):
            id = "threaded_test"
            name = "ThreadedTest"
            def create_widget(self, parent=None):
                w = QWidget(parent)
                self.worker = WorkerThread(w)
                self.worker.start()
                return w

        p = ThreadedPlugin()
        w = p.get_widget()
        self.assertTrue(p.worker.isRunning())

        # 执行 cleanup，验证不会崩溃并且线程被安全终止
        p.cleanup()
        self.assertFalse(p.worker.isRunning())

    def test_17_uninstall_plugin_read_only_files_resilience(self):
        """验证卸载包含只读属性文件/文件夹的插件时能够顺利物理删除"""
        import stat
        with tempfile.TemporaryDirectory() as temp_dir:
            p_dir = os.path.join(temp_dir, "readonly_test")
            os.makedirs(p_dir)
            ro_file = os.path.join(p_dir, "locked.txt")
            with open(ro_file, "w", encoding="utf-8") as f:
                f.write("read only data")
            # 设为只读
            os.chmod(ro_file, stat.S_IREAD)

            with open(os.path.join(p_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"id": "readonly_test", "name": "RO"}, f)
            with open(os.path.join(p_dir, "plugin.py"), "w", encoding="utf-8") as f:
                f.write("""
from toolbox.core.plugin_base import PluginBase
class P(PluginBase):
    id = "readonly_test"
    name = "RO"
    def create_widget(self, p=None): return None
""")
            self.pm.load_external_plugin(p_dir)
            ok = self.pm.uninstall_plugin("readonly_test")
            self.assertTrue(ok)
            self.assertFalse(os.path.exists(p_dir), "包含只读文件的插件目录应被彻底删除")


if __name__ == "__main__":
    unittest.main()

