"""
千绘莉多功能工具箱 - Inno Setup 原生 EXE 安装包导出集成测试
"""

import os
import sys
import shutil
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from toolbox.core.plugin_exporter import PluginExporter
from toolbox.core.plugin_manager import PluginManager


class TestInnoSetupExport(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="test_inno_export_")

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_find_iscc(self):
        iscc = PluginExporter.find_iscc_executable()
        self.assertIsNotNone(iscc, "ISCC.exe should be found on this system")
        self.assertTrue(os.path.isfile(iscc), f"ISCC executable path does not exist: {iscc}")
        print(f"[TEST] Found ISCC at: {iscc}")

    def test_export_screen_capture_inno_setup(self):
        res = PluginExporter.export_plugin(
            plugin_id="screen_capture",
            output_dir=self.tmp_dir,
            create_shortcuts=True,
            autostart_default=False,
            create_archive=True,
            compile_inno_setup=True,
        )

        print("[TEST] Export result keys:", list(res.keys()))
        self.assertTrue(res.get("success"), f"Export failed: {res.get('error')}")
        self.assertEqual(res.get("plugin_id"), "screen_capture")

        # 验证 .iss 脚本生成
        iss_p = res.get("iss_path")
        self.assertIsNotNone(iss_p)
        self.assertTrue(os.path.isfile(iss_p), f"ISS file not found: {iss_p}")

        # 验证 compile_setup.bat 生成
        bat_p = os.path.join(res.get("output_dir"), "compile_setup.bat")
        self.assertTrue(os.path.isfile(bat_p), f"compile_setup.bat not found: {bat_p}")

        # 验证 Inno Setup 原生 EXE 编译
        installer_exe = res.get("installer_exe")
        self.assertIsNotNone(installer_exe, f"Installer exe not generated. Error: {res.get('compile_error')}")
        self.assertTrue(os.path.isfile(installer_exe), f"Installer exe does not exist: {installer_exe}")
        exe_size = os.path.getsize(installer_exe)
        self.assertGreater(exe_size, 100000, f"Installer exe unexpectedly small: {exe_size} bytes")
        print(f"[TEST] Successfully built Inno Setup installer: {installer_exe} ({exe_size:,} bytes)")

        # 验证独立应用目录结构
        bundle_dir = res.get("output_dir")
        self.assertTrue(os.path.isfile(os.path.join(bundle_dir, "launch.bat")))
        self.assertTrue(os.path.isfile(os.path.join(bundle_dir, "launch.vbs")))
        self.assertTrue(os.path.isfile(os.path.join(bundle_dir, "standalone_entry.py")))
        self.assertTrue(os.path.isdir(os.path.join(bundle_dir, "toolbox", "plugins", "screen_capture")))

        # 验证 ZIP 便携包
        archive_p = res.get("archive_path")
        self.assertIsNotNone(archive_p)
        self.assertTrue(os.path.isfile(archive_p))

    def test_export_whiteboard_and_proxy_inno_setup(self):
        for pid in ("whiteboard", "proxy_configurator"):
            out_d = os.path.join(self.tmp_dir, f"out_{pid}")
            res = PluginExporter.export_plugin(
                plugin_id=pid,
                output_dir=out_d,
                create_shortcuts=True,
                autostart_default=True,
                create_archive=False,
                compile_inno_setup=True,
            )
            self.assertTrue(res.get("success"), f"Export {pid} failed: {res.get('error')}")
            installer_exe = res.get("installer_exe")
            self.assertIsNotNone(installer_exe, f"Installer exe not generated for {pid}")
            self.assertTrue(os.path.isfile(installer_exe))
    def test_plugin_quick_actions_integrity(self):
        pm = PluginManager()
        pm.discover_and_load()
        for pid in ("audio_cutter", "screen_capture", "screen_recorder", "proxy_configurator", "whiteboard", "audio_recorder"):
            p = pm.get_plugin(pid)
            self.assertIsNotNone(p, f"Plugin {pid} should exist")
            actions = p.get_quick_actions()
            self.assertIsInstance(actions, list)
            self.assertGreater(len(actions), 0, f"Plugin {pid} should have quick actions")
            for act in actions:
                self.assertIn("title", act)
                self.assertIn("callback", act)
                self.assertTrue(callable(act["callback"]), f"Action {act.get('title')} callback must be callable")


if __name__ == "__main__":
    unittest.main()
