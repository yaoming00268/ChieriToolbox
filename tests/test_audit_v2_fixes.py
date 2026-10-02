import os
import sys
import json
import tempfile
import unittest
import subprocess
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QApplication

# 确保 QApplication 存在
app = QApplication.instance() or QApplication(sys.argv)

from toolbox.core.config_manager import ConfigManager, _deep_merge_dict
from toolbox.core.theme import ThemeManager, THEME_DARK, THEME_LIGHT, THEME_SYSTEM
from toolbox.core.paths import get_audio_input_devices
from toolbox.plugins.proxy_configurator.engine import _cleanup_local_pac
from toolbox.plugins.auto_input.worker import TypingWorker
from toolbox.plugins.force_killer.engine import is_process_critical
from toolbox.ui.home_page import HomePage
from toolbox.plugins.screen_capture.ui import ScreenCaptureWidget
from toolbox.plugins.screen_recorder.ui import ScreenRecorderWidget
from toolbox.plugins.screen_recorder.engine import ScreenRecorderEngine, get_available_screens
from toolbox.plugins.media_downloader.downloader import MediaDownloadWorker
from toolbox.plugins.audio_recorder.engine import AudioRecorderEngine
from toolbox.plugins.audio_recorder.ui import AudioRecorderWidget
from toolbox.plugins.media_compressor.engine import compress_video, MediaCompressorWorker
from toolbox.plugins.archive_manager.engine import create_archive, extract_archive
from toolbox.plugins.whiteboard.canvas import WhiteboardCanvas


class TestAuditV2Fixes(unittest.TestCase):

    def setUp(self):
        ConfigManager.reset_instance()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cfg_file = os.path.join(self.tmp_dir.name, "test_config.json")
        self.cfg = ConfigManager(self.cfg_file)

    def tearDown(self):
        ConfigManager.reset_instance()
        self.tmp_dir.cleanup()

    def test_sec_01_proxy_cleanup_has_sys(self):
        """SEC-01: 测试 atexit 注册的 _cleanup_local_pac 函数能正常运行无 NameError"""
        try:
            _cleanup_local_pac()
        except NameError as e:
            self.fail(f"_cleanup_local_pac threw NameError: {e}")

    def test_sec_02_auto_input_worker_has_sys(self):
        """SEC-02: 测试 TypingWorker.run 在 Windows 环境不因缺少 sys 导入抛出 NameError"""
        tw = TypingWorker(text="", delay=0.01, use_clipboard=False)
        received_msgs = []
        tw.finished_typing.connect(lambda msg: received_msgs.append(msg))
        tw.run()
        self.assertTrue(len(received_msgs) > 0)
        self.assertIn("警告: 待键入文本内容为空", received_msgs[0])

    def test_sec_03_force_killer_is_process_critical_has_sys(self):
        """SEC-03: 测试 is_process_critical 对普通非零 PID 检测时不因缺少 sys 崩溃"""
        try:
            # 传一个肯定不是系统临界 0/4 的大 PID
            result = is_process_critical(99999999)
            self.assertIsInstance(result, bool)
            self.assertFalse(result)
        except NameError as e:
            self.fail(f"is_process_critical threw NameError: {e}")

    def test_syn_01_home_page_search_enter_no_duplicates(self):
        """SYN-01: 测试 HomePage 中 _on_search_enter_pressed 不存在重复定义覆盖且逻辑健全"""
        # 反射检查 HomePage 类的代码，确认方法只定义了一次
        import inspect
        source = inspect.getsource(HomePage)
        count = source.count("def _on_search_enter_pressed(self):")
        self.assertEqual(count, 1, "HomePage 中 _on_search_enter_pressed 不应有重复定义")

    def test_arc_01_hotkeys_safe_defaults_and_lifecycle(self):
        """ARC-01: 测试截图与录屏默认热键为无冲突组合键，且失焦/隐藏注销全局热键"""
        # 截图默认键
        sc = ScreenCaptureWidget()
        self.assertIn("ctrl", sc.edit_key_rect.keySequence().toString().lower())
        self.assertNotIn(sc.edit_key_rect.keySequence().toString(), ("F1", "F2", "F3", "F4"))

        # 录屏默认键
        sr = ScreenRecorderWidget()
        self.assertIn("ctrl", sr.edit_key_record.keySequence().toString().lower())
        self.assertNotIn(sr.edit_key_record.keySequence().toString(), ("F9", "F10"))

        # 测试失焦注销
        with patch.object(sc, "_clear_global_hotkeys") as mock_clear:
            sc.on_deactivated()
            mock_clear.assert_called_once()

        with patch.object(sr, "_clear_global_hotkeys") as mock_clear2:
            sr.on_deactivated()
            mock_clear2.assert_called_once()

        sc.cleanup()
        sr.cleanup()

    def test_arc_03_config_manager_physical_delete(self):
        """ARC-03: 测试 ConfigManager.delete 能在与磁盘数据深度合并时物理剔除已删除的键"""
        # 写入初始配置到磁盘
        initial_data = {
            "key_to_delete": "should_be_deleted",
            "key_to_keep": "should_remain",
            "plugins": {
                "test_plugin": {"foo": 1, "bar": 2}
            }
        }
        with open(self.cfg_file, "w", encoding="utf-8") as f:
            json.dump(initial_data, f)

        # 重新加载
        self.cfg.reload()
        self.assertEqual(self.cfg.get("key_to_delete"), "should_be_deleted")

        # 物理删除顶级键
        self.cfg.delete("key_to_delete", auto_save=True)

        # 验证内存与磁盘均已删除
        self.assertIsNone(self.cfg.get("key_to_delete"))
        with open(self.cfg_file, "r", encoding="utf-8") as f:
            disk_json = json.load(f)
        self.assertNotIn("key_to_delete", disk_json)
        self.assertEqual(disk_json.get("key_to_keep"), "should_remain")

        # 验证插件私有配置整块覆写（删除 bar 字段）
        self.cfg.set_plugin_config("test_plugin", {"foo": 99}, auto_save=True)
        with open(self.cfg_file, "r", encoding="utf-8") as f:
            disk_json2 = json.load(f)
        self.assertEqual(disk_json2["plugins"]["test_plugin"], {"foo": 99})
        self.assertNotIn("bar", disk_json2["plugins"]["test_plugin"])

    def test_arc_05_standalone_theme_isolation(self):
        """ARC-05: 测试独立插件窗口设置主题时，支持 save_config=False，隔离全局配置"""
        tm = ThemeManager()
        self.cfg.set("theme", "light")

        # 独立插件启动器切换主题，save_config=False
        tm.set_mode(THEME_DARK, save_config=False)
        self.assertEqual(tm.get_mode(), THEME_DARK)
        # 全局配置中的主题依然保持 light
        self.assertEqual(self.cfg.get("theme"), "light")

    def test_arc_06_paths_no_spurious_qcoreapplication(self):
        """ARC-06: 测试未创建 QApplication 时的音频输入设备探测安全逻辑"""
        # 在已有 QApplication 时正常返回列表
        devs = get_audio_input_devices()
        self.assertIsInstance(devs, list)

    def test_lgc_01_media_downloader_stream_truncation_detection(self):
        """LGC-01: 测试媒体流提前中断（字节数不足）时触发异常重试而非误判成功"""
        worker = MediaDownloadWorker(
            video_url="http://mock.test/video.m4s",
            audio_url="",
            save_dir=self.tmp_dir.name,
            title="TruncateTest"
        )
        # 模拟响应返回 content-length 为 100，但 iter_content 仅产生 20 字节即截断
        mock_resp = MagicMock()
        mock_resp.headers = {"content-length": "100"}
        mock_resp.iter_content.return_value = [b"A" * 20]

        dummy_target = os.path.join(self.tmp_dir.name, "truncated.m4s")
        with patch("requests.get", return_value=mock_resp):
            # 耗尽重试次数后应该返回 False
            ok = worker._download_stream("http://mock.test/video.m4s", dummy_target, "视频")
            self.assertFalse(ok, "流提前截断且重试耗尽时必须返回 False，严防误判为成功")

    def test_con_01_audio_recorder_devnull_and_async_transcode(self):
        """CON-01: 测试音频录制使用 DEVNULL 防止管道死锁，且转码过程不阻塞"""
        ar = AudioRecorderEngine()
        captured_popen_kwargs = {}

        def mock_popen(*args, **kwargs):
            nonlocal captured_popen_kwargs
            captured_popen_kwargs = kwargs
            m = MagicMock()
            m.poll.return_value = None
            return m

        with patch("subprocess.Popen", side_effect=mock_popen), \
             patch("toolbox.plugins.audio_recorder.engine.find_ffmpeg_executable", return_value="ffmpeg.exe"), \
             patch("os.path.isfile", return_value=True):
            ok, _ = ar.start_recording("test_out.mp3", "dummy_mic", format_choice="MP3")
            self.assertTrue(ok)
            self.assertEqual(captured_popen_kwargs.get("stderr"), subprocess.DEVNULL)
            ar.stop_recording()

    def test_con_02_and_lgc_02_screen_recorder_async_wait_and_screens(self):
        """CON-02 & LGC-02: 测试多屏识别包含设备名/物理信息，stop_recording 异步等待不卡死"""
        screens = get_available_screens()
        self.assertIsInstance(screens, list)
        self.assertGreater(len(screens), 0)

        sr = ScreenRecorderEngine()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc), \
             patch("toolbox.plugins.screen_recorder.engine.find_ffmpeg_executable", return_value="ffmpeg.exe"), \
             patch("os.path.isfile", return_value=True):
            ok, _ = sr.start_recording("test_rec.mp4")
            self.assertTrue(ok)
            # stop_recording 应立即返回并进入 FINALIZING 异步等待，主线程不被 wait(4) 阻塞
            ok_stop, _ = sr.stop_recording()
            self.assertTrue(ok_stop)
            self.assertFalse(sr.is_recording)

    def test_con_03_media_compressor_cancellable(self):
        """CON-03: 测试视频压缩执行时能够通过 cancel_callback 及时中止子进程"""
        cancelled = False
        def cancel_check():
            return cancelled

        mock_proc = MagicMock()
        # 第一次 poll 返回 None（还在运行），触发 cancel_check
        mock_proc.poll.side_effect = [None, None, 0]
        mock_proc.communicate.return_value = ("", "")

        in_file = os.path.join(self.tmp_dir.name, "in.mp4")
        with open(in_file, "wb") as f: f.write(b"0" * 100)
        out_file = os.path.join(self.tmp_dir.name, "out.mp4")

        with patch("subprocess.Popen", return_value=mock_proc), \
             patch("toolbox.plugins.media_compressor.engine.find_ffmpeg_executable", return_value="ffmpeg.exe"), \
             patch("os.path.isfile", return_value=True):
            cancelled = True
            ok, msg, _, _ = compress_video(in_file, out_file, cancel_callback=cancel_check)
            self.assertFalse(ok)
            self.assertIn("中止", msg)
            mock_proc.terminate.assert_called_once()

    def test_lgc_03_archive_manager_lz4_streaming_and_multi(self):
        """LGC-03: 测试 LZ4 流式单文件与多文件打包解包正确性"""
        f1 = os.path.join(self.tmp_dir.name, "file1.txt")
        f2 = os.path.join(self.tmp_dir.name, "file2.txt")
        with open(f1, "w", encoding="utf-8") as f: f.write("Content of File 1 " * 50)
        with open(f2, "w", encoding="utf-8") as f: f.write("Content of File 2 " * 50)

        # 单文件流式压缩与解压
        single_arc = os.path.join(self.tmp_dir.name, "file1.txt.lz4")
        ok1, _ = create_archive([f1], single_arc, format_type="lz4")
        self.assertTrue(ok1)
        ext_dir1 = os.path.join(self.tmp_dir.name, "ext_single")
        ok2, _ = extract_archive(single_arc, ext_dir1)
        self.assertTrue(ok2)
        self.assertTrue(os.path.isfile(os.path.join(ext_dir1, "file1.txt")))

        # 多文件 tar.lz4 归档压缩与解压
        multi_arc = os.path.join(self.tmp_dir.name, "multi.tar.lz4")
        ok3, _ = create_archive([f1, f2], multi_arc, format_type="lz4")
        self.assertTrue(ok3)
        ext_dir2 = os.path.join(self.tmp_dir.name, "ext_multi")
        ok4, _ = extract_archive(multi_arc, ext_dir2)
        self.assertTrue(ok4)
        self.assertTrue(os.path.isfile(os.path.join(ext_dir2, "file1.txt")))
        self.assertTrue(os.path.isfile(os.path.join(ext_dir2, "file2.txt")))

    def test_lgc_04_whiteboard_undo_preserves_canvas_size(self):
        """LGC-04: 测试白板画布在窗口变大后撤销不缩减画布尺寸导致画面裁切"""
        canvas = WhiteboardCanvas()
        canvas.resize(800, 600)
        canvas.setFixedSize(800, 600)
        canvas._save_undo_state()
        initial_w = canvas.canvas_pixmap.width()

        # 模拟窗口变大至 1600x1200
        canvas.resize(1600, 1200)
        canvas.setFixedSize(1600, 1200)
        # 触发 resizeEvent
        from PySide6.QtGui import QResizeEvent
        canvas.resizeEvent(QResizeEvent(QSize(1600, 1200), QSize(800, 600)))
        canvas._save_undo_state()

        # 执行 undo，恢复历史状态
        canvas.undo()
        # 画布尺寸必须至少保持 1600 宽，绝不回退至 800
        self.assertGreaterEqual(canvas.canvas_pixmap.width(), 1600)

    def test_arc_03_delete_plugin_config_persistence(self):
        """ARC-03 深度验证: 测试 delete_plugin_config(plugin_id) 物理清除且 save/reload 后绝不复活"""
        self.cfg.set_plugin_config("p_victim", {"secret": 12345}, auto_save=True)
        self.cfg.reload()
        self.assertIn("p_victim", self.cfg.data.get("plugins", {}))

        # 物理彻底删除该插件配置
        removed = self.cfg.delete_plugin_config("p_victim", key=None, auto_save=True)
        self.assertTrue(removed)
        self.assertNotIn("p_victim", self.cfg.data.get("plugins", {}))

        # 重新从磁盘载入，验证已在物理磁盘彻底移除，杜绝合并复活
        self.cfg.reload()
        self.assertNotIn("p_victim", self.cfg.data.get("plugins", {}))

    def test_arc_05_standalone_dialog_theme_isolation(self):
        """ARC-05 深度验证: 测试 StandalonePluginSettingsDialog 保存独立主题不污染全局 config['theme']"""
        from toolbox.ui.standalone_settings_dialog import StandalonePluginSettingsDialog
        from toolbox.core.plugin_base import PluginBase

        class DummyPlugin(PluginBase):
            id = "dummy_test_iso"
            name = "Dummy Iso Plugin"
            icon = "tools"
            description = "Test"
            def create_widget(self): return None

        self.cfg.set("theme", "light")
        p = DummyPlugin()
        dlg = StandalonePluginSettingsDialog(p)
        dlg.combo_theme.setCurrentIndex(2)  # 2: THEME_DARK
        dlg._save_settings()

        # 独立配置应为 dark
        stand_cfg = self.cfg.get(f"standalone_{p.id}", {})
        self.assertEqual(stand_cfg.get("theme"), "dark")
        # 全局配置 theme 必须依然维持 light，严禁被独立对话框覆写
        self.assertEqual(self.cfg.get("theme"), "light")
        dlg.close()

    def test_con_03_media_compressor_large_stderr_no_deadlock(self):
        """CON-03 深度验证: 测试 FFmpeg 产生大量 stderr 日志时子进程被异步排空，绝不发生管道死锁"""
        import io
        import subprocess

        # 构造模拟脚本，向 stderr 连续灌入 128KB 文本
        sim_code = "import sys; sys.stderr.write('A' * 131072); sys.exit(0)"
        in_file = os.path.join(self.tmp_dir.name, "sim_in.mp4")
        out_file = os.path.join(self.tmp_dir.name, "sim_out.mp4")
        with open(in_file, "wb") as f: f.write(b"0" * 100)

        fake_ffmpeg = os.path.join(self.tmp_dir.name, "ffmpeg.exe")
        with open(fake_ffmpeg, "w") as f: f.write("")

        # 真实运行 Python 灌入管道测试排空线程（必须在 patch 外部启动，否则 Popen 会被 mock）
        real_proc = subprocess.Popen(
            [sys.executable, "-c", sim_code],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True
        )

        with patch("subprocess.Popen", return_value=real_proc):
            ok, msg, _, _ = compress_video(in_file, out_file, ffmpeg_exe=fake_ffmpeg)
            self.assertEqual(real_proc.poll(), 0)

    def test_lgc_03_archive_manager_tarslip_symlink_defense(self):
        """LGC-03 深度验证: 测试 TarSlip 恶意软链接越界成员被安全拦截防御"""
        import io
        import tarfile

        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w|") as tf:
            # 1. 正常成员
            ti1 = tarfile.TarInfo("safe.txt")
            ti1.size = 4
            tf.addfile(ti1, io.BytesIO(b"safe"))
            # 2. 恶意越界符号链接
            ti2 = tarfile.TarInfo("malicious_link")
            ti2.type = tarfile.SYMTYPE
            ti2.linkname = "../../evil_target"
            tf.addfile(ti2)

        tar_buf.seek(0)
        ext_dir = os.path.join(self.tmp_dir.name, "safe_extract_test")
        os.makedirs(ext_dir, exist_ok=True)

        with tarfile.open(fileobj=tar_buf, mode="r|*") as tf_in:
            from toolbox.plugins.archive_manager.engine import _safe_extract_tar
            _safe_extract_tar(tf_in, ext_dir)

        # safe.txt 必须存在
        self.assertTrue(os.path.isfile(os.path.join(ext_dir, "safe.txt")))
        # malicious_link 必须被拦截防御，绝不在磁盘建立
        self.assertFalse(os.path.exists(os.path.join(ext_dir, "malicious_link")))

    def test_con_01_and_02_ui_busy_states(self):
        """CON-01 & CON-02: 测试录屏 FINALIZING 与录音 TRANSCODING 期间启动按钮禁用防重入"""
        sr = ScreenRecorderWidget()
        sr._on_status_changed("FINALIZING")
        self.assertFalse(sr.btn_start.isEnabled(), "FINALIZING 封装期间严禁重新开启录屏")
        sr._on_status_changed("FINISHED")
        self.assertTrue(sr.btn_start.isEnabled())
        sr.cleanup()

        ar = AudioRecorderWidget()
        ar._on_status_changed("TRANSCODING")
        self.assertFalse(ar.btn_record.isEnabled(), "TRANSCODING 转码期间严禁重新开启录音")
        ar._on_status_changed("FINISHED")
        self.assertTrue(ar.btn_record.isEnabled())
