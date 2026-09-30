"""
自动化回归测试套件：验证屏幕录像/区域选区、两阶段文件跨驱动器重命名、SkinParser 动态 Section 保存与打包供应链修复
"""

import os
import sys
import unittest
import tempfile
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
app = QApplication.instance()
if not app:
    app = QApplication(["--platform", "offscreen"])

from toolbox.plugins.screen_recorder.engine import (
    get_virtual_desktop_rect,
    get_available_screens,
    ScreenRecorderEngine
)
from toolbox.plugins.file_suite.logic import FileRenameEngine
from toolbox.plugins.osu_skin_studio.skin_parser import SkinParser
from toolbox.core.plugin_exporter import PluginExporter


class TestScreenAndEdgeFixes(unittest.TestCase):
    def test_01_virtual_desktop_rect_integrity(self):
        """测试 1: 物理虚拟桌面包围盒合法性 (偶数宽高且非空)"""
        vx, vy, vw, vh = get_virtual_desktop_rect()
        self.assertIsInstance(vx, int)
        self.assertIsInstance(vy, int)
        self.assertIsInstance(vw, int)
        self.assertIsInstance(vh, int)
        self.assertGreater(vw, 0)
        self.assertGreater(vh, 0)
        self.assertEqual(vw % 2, 0, "虚拟桌面宽度必须对齐偶数以规避 x264 崩溃")
        self.assertEqual(vh % 2, 0, "虚拟桌面高度必须对齐偶数以规避 x264 崩溃")

    def test_02_available_screens_metadata(self):
        """测试 2: 显示器屏幕枚举及物理坐标尺寸结构"""
        screens = get_available_screens()
        self.assertIsInstance(screens, list)
        self.assertGreater(len(screens), 0)
        for s in screens:
            self.assertIn("index", s)
            self.assertIn("title", s)
            self.assertIn("x", s)
            self.assertIn("y", s)
            self.assertIn("width", s)
            self.assertIn("height", s)
            self.assertIn("dpr", s)
            self.assertEqual(s["width"] % 2, 0)
            self.assertEqual(s["height"] % 2, 0)

    def test_03_screen_recorder_negative_coordinates_not_clamped(self):
        """测试 3: 严防负坐标被 max(0, x) 错误截断 (副屏置于左侧或上方场景)"""
        session = ScreenRecorderEngine()

        # 模拟负坐标选区与负坐标副屏
        captured_cmd = None
        def mock_popen(cmd, *args, **kwargs):
            nonlocal captured_cmd
            captured_cmd = cmd
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            return mock_proc

        with patch("subprocess.Popen", side_effect=mock_popen), \
             patch("toolbox.plugins.screen_recorder.engine.find_ffmpeg_executable", return_value="ffmpeg.exe"), \
             patch("os.path.isfile", return_value=True):

            # 1. 矩形区域选区包含负坐标 (如位于主屏左侧副屏 x=-1920)
            session.start_recording(
                output_path="test_out.mp4",
                mode="rect",
                rect=(-1920, 100, 800, 600)
            )
            self.assertIsNotNone(captured_cmd)
            self.assertIn("-offset_x", captured_cmd)
            idx_x = captured_cmd.index("-offset_x")
            self.assertEqual(captured_cmd[idx_x + 1], "-1920", "负坐标 offset_x 必须原样传递，绝不可被 max(0, rx) 截断为 0")

            # 2. 单独副屏包含负坐标
            session.stop_recording()
            captured_cmd = None
            session.start_recording(
                output_path="test_out.mp4",
                mode="screen",
                screen_rect=(-1920, -500, 1920, 1080)
            )
            self.assertIsNotNone(captured_cmd)
            idx_x = captured_cmd.index("-offset_x")
            idx_y = captured_cmd.index("-offset_y")
            self.assertEqual(captured_cmd[idx_x + 1], "-1920")
            self.assertEqual(captured_cmd[idx_y + 1], "-500")

    def test_04_file_rename_cross_volume_fallback(self):
        """测试 4: 两阶段重命名事务在跨磁盘驱动器时的安全回退机制"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_a = os.path.join(tmp_dir, "file_a.txt")
            file_b = os.path.join(tmp_dir, "file_b.txt")
            with open(file_a, "w", encoding="utf-8") as f:
                f.write("content a")

            plan = [(file_a, file_b, "file_a.txt", "file_b.txt")]

            # 模拟 os.replace 遭遇 Windows WinError 17 (跨磁盘驱动器错误)
            real_replace = os.replace
            def mock_replace(src, dst):
                if "_rn_stage_" in src:
                    raise OSError(17, "The system cannot move the file to a different disk drive")
                return real_replace(src, dst)

            with patch("os.replace", side_effect=mock_replace):
                res = FileRenameEngine.execute_rename(plan)
                self.assertEqual(res["success"], 1, f"应通过 shutil.move 成功回退完成重命名: {res['errors']}")
                self.assertTrue(os.path.isfile(file_b))
                with open(file_b, "r", encoding="utf-8") as f:
                    self.assertEqual(f.read(), "content a")

    def test_05_skin_parser_preserves_dynamically_added_sections(self):
        """测试 5: osu! skin.ini 解析器动态新增 Section (如 Taiko/Editor) 序列化无损保存"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            ini_path = os.path.join(tmp_dir, "skin.ini")
            initial_content = """[General]
Name: TestSkin
Author: Chieri

[Colours]
Combo1: 255,255,255
"""
            with open(ini_path, "w", encoding="utf-8") as f:
                f.write(initial_content)

            parser = SkinParser()
            parser.load(ini_path)

            # 动态加入新 Section
            parser.sections["Taiko"] = {"HitPos": "400", "BarLine": "1"}
            parser.sections["CatchTheBeat"] = {"Catcher": "fruit"}
            parser.save(ini_path)

            # 重新加载验证持久化
            parser2 = SkinParser()
            parser2.load(ini_path)

            taiko = parser2.get_section("Taiko")
            self.assertIsNotNone(taiko, "动态新增的 [Taiko] Section 必须被完整保存")
            self.assertEqual(taiko.get("HitPos"), "400")
            self.assertEqual(taiko.get("BarLine"), "1")

            ctb = parser2.get_section("CatchTheBeat")
            self.assertIsNotNone(ctb, "动态新增的 [CatchTheBeat] Section 必须被完整保存")
            self.assertEqual(ctb.get("Catcher"), "fruit")

            # 验证原 General 和 Colours 未受破坏
            self.assertEqual(parser2.general.get("Name"), "TestSkin")
            self.assertEqual(parser2.colours.get("Combo1"), "255,255,255")

    def test_06_plugin_exporter_hidden_imports(self):
        """测试 6: 独立导出规范 build_<plugin_id>.spec 必须包含 core.media_engine"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            res = PluginExporter.export_plugin(
                plugin_id="audio_cutter",
                output_dir=tmp_dir,
                create_shortcuts=False,
                create_archive=False,
                compile_inno_setup=False,
                generate_pyinstaller_spec=True
            )
            self.assertTrue(res.get("success"), f"Export failed: {res.get('error')}")
            spec_file = os.path.join(res.get("output_dir"), "build_audio_cutter.spec")
            self.assertTrue(os.path.isfile(spec_file))

            with open(spec_file, "r", encoding="utf-8") as f:
                spec_content = f.read()

            self.assertIn("'toolbox.core.media_engine'", spec_content,
                          "build spec 中的 hiddenimports 必须显式包含 'toolbox.core.media_engine'")


if __name__ == "__main__":
    unittest.main()
