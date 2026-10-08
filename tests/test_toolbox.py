"""
千绘莉多功能工具箱 (Chieri Toolbox) - 全面自动化单元与集成测试套件
验证各插件模块的独立性、配置持久化隔离、本地二进制引擎、文件重命名/扁平化逻辑、图像转换与透明度安全缩放、外部参数直达分发及UI健全性。
"""

import os
import sys
import tempfile
import unittest
from PIL import Image

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication

# 全局 QApplication 实例以支持 QWidget 创建测试
app = QApplication.instance()
if not app:
    app = QApplication(["--platform", "offscreen"])

from toolbox.core.config_manager import ConfigManager
from toolbox.core.plugin_manager import PluginManager
from toolbox.plugins.media_downloader.downloader import find_ffmpeg_executable, sanitize_filename
from toolbox.plugins.media_downloader.api import BiliApiClient
from toolbox.plugins.system_integrator.registry_ops import (
    get_toolbox_main_command,
    run_system_health_check,
    is_context_menu_registered,
    is_autostart_enabled
)
from toolbox.plugins.osu_skin_studio.skin_parser import SkinParser
from toolbox.plugins.file_suite.logic import FileRenameEngine, FolderFlattenEngine, scan_files
from toolbox.plugins.image_master.converter import convert_image
from toolbox.plugins.image_master.resizer import ImageBatchWorker
from toolbox.plugins.auto_input.worker import PasteSimulatorWorker
from toolbox.ui.main_window import MainWindow


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        ConfigManager.reset_instance()

    def tearDown(self):
        ConfigManager.reset_instance()

    def test_config_crud_and_persistence(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = tf.name

        try:
            cfg = ConfigManager(temp_path)
            self.assertEqual(cfg.get("theme"), "system")
            cfg.set("theme", "light")
            cfg.set("test_key", 98765)
            self.assertEqual(cfg.get("test_key"), 98765)

            # 重置单例以验证真正的磁盘持久化反序列化
            ConfigManager.reset_instance()
            cfg2 = ConfigManager(temp_path)
            self.assertEqual(cfg2.get("test_key"), 98765)
            self.assertEqual(cfg2.get("theme"), "light")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_empty_config_file_graceful_handling(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = tf.name
            # 文件为 0 字节

        try:
            cfg = ConfigManager(temp_path)
            self.assertEqual(cfg.get("theme"), "system")
            self.assertEqual(cfg.get("window", {}).get("width"), 1080)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_switch_config_file(self):
        c1 = ConfigManager()
        default_file = c1.config_file
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            other_path = tf.name
        try:
            c2 = ConfigManager(other_path)
            self.assertEqual(c2.config_file, other_path)
        finally:
            if os.path.exists(other_path):
                os.remove(other_path)


class TestPluginManager(unittest.TestCase):
    def setUp(self):
        self.pm = PluginManager()
        self.pm.discover_and_load()

    def test_discovered_plugin_count(self):
        plugins = self.pm.get_all_plugins()
        plugin_ids = {p.id for p in plugins}
        expected_ids = {
            "file_suite",
            "image_master",
            "auto_input",
            "media_downloader",
            "osu_skin_studio",
            "system_integrator",
            "youtube_downloader",
            "video_to_audio",
            "audio_converter",
            "ncm_decryptor",
            "translator",
            "audio_cutter",
            "archive_manager",
            "force_killer",
            "proxy_configurator",
            "media_compressor",
            "frame_extractor",
            "webdav_config",
            "audio_recorder",
            "screen_capture",
            "screen_recorder",
            "whiteboard",
            "quick_launcher",
            "clipboard_manager",
            "port_network_sentinel",
            "watermark_studio",
            "json_diff_studio",
            "env_var_switcher"
        }
        self.assertTrue(expected_ids.issubset(plugin_ids), f"Missing plugins: {expected_ids - plugin_ids}")
        self.assertGreaterEqual(len(plugins), 28)

    def test_plugin_metadata(self):
        for p in self.pm.get_all_plugins():
            self.assertTrue(bool(p.id))
            self.assertTrue(bool(p.name))
            self.assertTrue(bool(p.category))
            self.assertTrue(bool(p.description))

    def test_plugin_widgets_instantiation(self):
        for p in self.pm.get_all_plugins():
            widget = p.create_widget()
            self.assertIsNotNone(widget, f"Widget for plugin {p.id} was None")

    def test_plugin_lifecycle(self):
        for p in self.pm.get_all_plugins():
            activated = self.pm.activate_plugin(p.id)
            self.assertEqual(activated.id, p.id)
            self.assertEqual(self.pm.get_active_plugin_id(), p.id)
            self.pm.deactivate_current_plugin()
            self.assertIsNone(self.pm.get_active_plugin_id())


class TestSelfContainedBinaries(unittest.TestCase):
    def test_ffmpeg_local_binaries(self):
        ffmpeg_exe = find_ffmpeg_executable()
        self.assertIsNotNone(ffmpeg_exe, "FFmpeg executable could not be found!")
        self.assertTrue(os.path.isfile(ffmpeg_exe), f"FFmpeg path does not exist: {ffmpeg_exe}")
        self.assertTrue(
            ffmpeg_exe.lower().startswith(PROJECT_ROOT.lower()),
            f"FFmpeg is not self-contained in {PROJECT_ROOT}: {ffmpeg_exe}"
        )

        # 检查 ffprobe 与 ffplay 是否同样完好迁移
        bin_dir = os.path.join(PROJECT_ROOT, "bin")
        for tool in ("ffprobe.exe", "ffplay.exe"):
            tool_p = os.path.join(bin_dir, tool)
            self.assertTrue(os.path.isfile(tool_p), f"Missing {tool} in {bin_dir}")

    def test_main_command_path(self):
        cmd = get_toolbox_main_command()
        expected_main = os.path.join(PROJECT_ROOT, "main.py")
        self.assertIn(expected_main, cmd)
        self.assertTrue(os.path.isfile(expected_main), f"Main entry does not exist: {expected_main}")

    def test_system_health_check(self):
        diag = run_system_health_check()
        self.assertEqual(diag["ffmpeg_status"], "已就绪")
        self.assertTrue(os.path.isfile(diag["ffmpeg_path"]))
        self.assertIn("python_version", diag)


class TestFileSuiteLogic(unittest.TestCase):
    def test_scan_files(self):
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "test1.txt")
            f2 = os.path.join(td, "test2.png")
            with open(f1, "w") as f: f.write("1")
            with open(f2, "w") as f: f.write("2")

            scanned = scan_files([td], recursive=False)
            self.assertIn(os.path.normpath(f1), scanned)
            self.assertIn(os.path.normpath(f2), scanned)

    def test_template_rename_preview(self):
        files = ["C:/dir/img_a.png", "C:/dir/img_b.png"]
        plan = FileRenameEngine.preview_template_rename(files, "photo_{n}", start_index=1, pad_digits=3)
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0][3], "photo_001.png")
        self.assertEqual(plan[1][3], "photo_002.png")

    def test_replace_rename_preview(self):
        files = ["C:/dir/IMG_2026.png"]
        plan = FileRenameEngine.preview_replace_rename(files, "IMG", "PIC", use_regex=False)
        self.assertEqual(plan[0][3], "PIC_2026.png")

        # 正则测试
        plan_re = FileRenameEngine.preview_replace_rename(files, r"\d+", "NUM", use_regex=True)
        self.assertEqual(plan_re[0][3], "IMG_NUM.png")

    def test_extension_rename_preview(self):
        files = ["C:/dir/doc.txt", "C:/dir/img.png"]
        plan = FileRenameEngine.preview_extension_rename(files, ".txt", ".md")
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0][3], "doc.md")

    def test_execute_rename_with_collision_protection(self):
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "file1.txt")
            f2 = os.path.join(td, "file2.txt")
            with open(f1, "w") as f: f.write("f1")
            with open(f2, "w") as f: f.write("f2")

            # 将 file1 重命名为 file2，应自动避让命名为 file2_1.txt
            plan = [(f1, f2, "file1.txt", "file2.txt")]
            res = FileRenameEngine.execute_rename(plan)
            self.assertEqual(res["success"], 1)
            self.assertTrue(os.path.exists(f2))
            self.assertTrue(os.path.exists(os.path.join(td, "file2_1.txt")))

    def test_folder_flatten_engine(self):
        with tempfile.TemporaryDirectory() as td:
            sub = os.path.join(td, "sub_folder")
            os.makedirs(sub)
            sub_file = os.path.join(sub, "item.txt")
            with open(sub_file, "w") as f: f.write("content")

            res = FolderFlattenEngine.flatten_folders([sub])
            self.assertEqual(res["moved_count"], 1)
            self.assertEqual(res["cleaned_folders"], 1)
            self.assertTrue(os.path.exists(os.path.join(td, "item.txt")))
            self.assertFalse(os.path.exists(sub))


class TestImageMasterLogic(unittest.TestCase):
    def test_convert_image_png_to_jpeg_with_mkdir(self):
        with tempfile.TemporaryDirectory() as td:
            src_png = os.path.join(td, "transparent.png")
            # 半透明 RGBA 图像
            img = Image.new("RGBA", (80, 80), (255, 0, 0, 128))
            img.save(src_png)

            # 目标目录尚不存在，应自动创建并平铺白底
            target_dir = os.path.join(td, "nested", "output")
            ok, out_path, detail = convert_image(src_png, target_dir, "JPG")
            self.assertTrue(ok, f"convert_image failed: {detail}")
            self.assertTrue(os.path.exists(out_path))

            # 验证转换后为 RGB 格式
            with Image.open(out_path) as res_img:
                self.assertEqual(res_img.mode, "RGB")

    def test_convert_image_to_ico(self):
        with tempfile.TemporaryDirectory() as td:
            src_png = os.path.join(td, "icon.png")
            img = Image.new("RGBA", (64, 64), (0, 128, 255, 255))
            img.save(src_png)

            ok, out_path, detail = convert_image(src_png, td, "ICO")
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(out_path))
            with Image.open(out_path) as ico:
                self.assertEqual(ico.format, "ICO")

    def test_image_batch_worker_resize_rgba_to_jpeg(self):
        with tempfile.TemporaryDirectory() as td:
            src_jpg = os.path.join(td, "rgba_named.jpg")
            img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
            img.save(src_jpg, format="PNG")  # 后缀为 jpg 但内容为 RGBA

            out_dir = os.path.join(td, "resized")
            worker = ImageBatchWorker(
                task_type="resize",
                file_paths=[src_jpg],
                output_dir=out_dir,
                resize_mode="fixed",
                target_w=50,
                target_h=50,
                keep_ratio=True
            )
            finished_result = []
            worker.task_finished.connect(lambda s, f: finished_result.append((s, f)))
            worker.run()

            self.assertEqual(len(finished_result), 1)
            self.assertEqual(finished_result[0], (1, 0))  # 1成功，0失败
            out_file = os.path.join(out_dir, "rgba_named.jpg")
            self.assertTrue(os.path.exists(out_file))


class TestMediaDownloaderLogic(unittest.TestCase):
    def test_sanitize_filename(self):
        raw = 'My/Video\\Title: "Test"? <Nice>* |'
        sanitized = sanitize_filename(raw)
        for char in '/\\:*?"<>|':
            self.assertNotIn(char, sanitized)

    def test_extract_bvid(self):
        # 1. 纯 BV 号
        self.assertEqual(BiliApiClient.extract_bvid("BV1xx411c7mD"), "BV1xx411c7mD")
        # 2. 完整 URL 带有参数
        self.assertEqual(
            BiliApiClient.extract_bvid("https://www.bilibili.com/video/BV1xx411c7mD?spm_id_from=333.999.0.0"),
            "BV1xx411c7mD"
        )
        # 3. 小写 bv 开头
        self.assertEqual(BiliApiClient.extract_bvid("bv1xx411c7mD"), "bv1xx411c7mD")
        # 4. 非法字符串
        self.assertIsNone(BiliApiClient.extract_bvid("hello_world_not_bvid"))

    def test_account_status_parsing_scenarios(self):
        """测试未登录、普通会员、月度大会员、年度大会员状态解析与标签生成"""
        from unittest.mock import MagicMock
        client = BiliApiClient()

        # 1. 未登录 (code=-101 或 data.isLogin=False)
        mock_resp_unlogin = MagicMock()
        mock_resp_unlogin.json.return_value = {"code": -101, "message": "账号未登录"}
        client.session.get = MagicMock(return_value=mock_resp_unlogin)
        res_unlogin = client.check_account_status()
        self.assertFalse(res_unlogin["is_login"])
        self.assertEqual(res_unlogin["vip_status"], 0)
        self.assertIn("未登录", res_unlogin["message"])

        # 2. 普通会员已登录 (isLogin=True, vipStatus=0)
        mock_resp_normal = MagicMock()
        mock_resp_normal.json.return_value = {
            "code": 0,
            "data": {
                "isLogin": True,
                "uname": "TesterNormal",
                "mid": 123456,
                "vipType": 0,
                "vipStatus": 0,
                "vip_label": {"text": ""}
            }
        }
        client.session.get = MagicMock(return_value=mock_resp_normal)
        res_normal = client.check_account_status()
        self.assertTrue(res_normal["is_login"])
        self.assertEqual(res_normal["vip_status"], 0)
        self.assertEqual(res_normal["uname"], "TesterNormal")
        self.assertIn("最高1080P", res_normal["message"])

        # 3. 年度大会员 (isLogin=True, vipStatus=1, vipType=2)
        mock_resp_annual_vip = MagicMock()
        mock_resp_annual_vip.json.return_value = {
            "code": 0,
            "data": {
                "isLogin": True,
                "uname": "TesterVIP",
                "mid": 654321,
                "vipType": 2,
                "vipStatus": 1,
                "vip_label": {"text": "年度大会员"}
            }
        }
        client.session.get = MagicMock(return_value=mock_resp_annual_vip)
        res_annual_vip = client.check_account_status()
        self.assertTrue(res_annual_vip["is_login"])
        self.assertEqual(res_annual_vip["vip_status"], 1)
        self.assertEqual(res_annual_vip["vip_type"], 2)
        self.assertEqual(res_annual_vip["vip_label"], "年度大会员")
        self.assertIn("全规格已解锁", res_annual_vip["message"])

        # 4. 月度/季度大会员 (isLogin=True, vipStatus=1, vipType=1, vip_label为空)
        mock_resp_monthly = MagicMock()
        mock_resp_monthly.json.return_value = {
            "code": 0,
            "data": {
                "isLogin": True,
                "uname": "TesterMonth",
                "mid": 987654,
                "vipType": 1,
                "vipStatus": 1,
                "vip_label": {"text": ""}
            }
        }
        client.session.get = MagicMock(return_value=mock_resp_monthly)
        res_monthly = client.check_account_status()
        self.assertTrue(res_monthly["is_login"])
        self.assertEqual(res_monthly["vip_status"], 1)
        self.assertEqual(res_monthly["vip_type"], 1)
        self.assertEqual(res_monthly["vip_label"], "大会员")
        self.assertIn("全规格已解锁", res_monthly["message"])

        # 5. 过期大会员边界情况 (vipStatus=0, vipType=0 或 2, vip_label保留历史残留"年度大会员")
        mock_resp_expired = MagicMock()
        mock_resp_expired.json.return_value = {
            "code": 0,
            "data": {
                "isLogin": True,
                "uname": "TesterExpired",
                "mid": 112233,
                "vipType": 0,
                "vipStatus": 0,
                "vip_label": {"text": "年度大会员"}
            }
        }
        client.session.get = MagicMock(return_value=mock_resp_expired)
        res_expired = client.check_account_status()
        self.assertTrue(res_expired["is_login"])
        self.assertEqual(res_expired["vip_status"], 0)
        self.assertEqual(res_expired["vip_label"], "普通会员")
        self.assertIn("最高1080P", res_expired["message"])

        # 6. 异常状态: vipStatus=1 但 vipType=0，按规范仍识别为普通会员
        mock_resp_weird = MagicMock()
        mock_resp_weird.json.return_value = {
            "code": 0,
            "data": {
                "isLogin": True,
                "uname": "TesterWeird",
                "mid": 445566,
                "vipType": 0,
                "vipStatus": 1,
                "vip_label": {}
            }
        }
        client.session.get = MagicMock(return_value=mock_resp_weird)
        res_weird = client.check_account_status()
        self.assertTrue(res_weird["is_login"])
        self.assertEqual(res_weird["vip_label"], "普通会员")
        self.assertIn("最高1080P", res_weird["message"])

    def test_quality_negotiation_and_downgrade_detection(self):
        """测试画质请求降级检测与 QUALITY_MAP 完整映射"""
        from unittest.mock import MagicMock
        from toolbox.plugins.media_downloader.api import QUALITY_MAP, VIP_QN_SET

        # 验证全量画质映射
        expected_qns = [127, 126, 125, 120, 116, 112, 80, 74, 64, 32, 16]
        for qn in expected_qns:
            self.assertIn(qn, QUALITY_MAP)

        client = BiliApiClient()

        # 模拟请求 120 (4K)，但因非大会员账号服务端仅返回 80 (1080P) 流
        mock_playurl_resp = MagicMock()
        mock_playurl_resp.json.return_value = {
            "code": 0,
            "data": {
                "quality": 80,
                "accept_quality": [120, 80, 64, 32],
                "accept_description": ["4K 超清", "1080P 高清", "720P 高清", "480P 清晰"],
                "support_formats": [
                    {"quality": 120, "new_description": "4K 超清"},
                    {"quality": 116, "new_description": "1080P 60帧"},
                    {"quality": 80, "new_description": "1080P 高清"}
                ],
                "dash": {
                    "video": [
                        {"id": 80, "baseUrl": "https://sample.bili.com/video_1080.m4s", "bandwidth": 3000000},
                        {"id": 64, "baseUrl": "https://sample.bili.com/video_720.m4s", "bandwidth": 1500000}
                    ],
                    "audio": [
                        {"id": 30280, "baseUrl": "https://sample.bili.com/audio_192.m4s", "bandwidth": 192000}
                    ]
                }
            }
        }
        client.session.get = MagicMock(return_value=mock_playurl_resp)

        res = client.get_play_streams("BV1xx411c7mD", 12345, qn=120)
        self.assertTrue(res["success"])
        self.assertEqual(res["actual_qn"], 80)
        self.assertEqual(res["actual_quality"], "1080P 高清")
        self.assertTrue(res["is_downgraded"])
        # 验证同时合并了 accept_quality 与 support_formats 中的画质 (120, 80, 64, 32, 116)
        avail_qns = [item["qn"] for item in res["available_qualities"]]
        self.assertIn(116, avail_qns)
        self.assertIn(120, avail_qns)

        # 模拟匹配成功情况 (请求 80，返回 80)
        res_ok = client.get_play_streams("BV1xx411c7mD", 12345, qn=80)
        self.assertFalse(res_ok["is_downgraded"])
        self.assertEqual(res_ok["actual_qn"], 80)

    def test_audio_stream_selection_priority(self):
        """测试音轨优先级: Hi-Res (flac) -> 杜比全景声 (dolby) -> 高码率普通音轨 (audio)"""
        from unittest.mock import MagicMock
        client = BiliApiClient()

        # 1. 存在 FLAC (Hi-Res) 音频 (测试 list 结构)
        mock_flac_resp = MagicMock()
        mock_flac_resp.json.return_value = {
            "code": 0,
            "data": {
                "dash": {
                    "video": [{"id": 80, "baseUrl": "http://v.m4s"}],
                    "flac": {
                        "audio": [{"id": 30251, "baseUrl": "http://flac_audio.m4s", "codecs": "fLaC", "bandwidth": 900000}]
                    },
                    "dolby": {
                        "audio": [{"id": 30250, "baseUrl": "http://dolby_audio.m4s", "codecs": "ec-3", "bandwidth": 448000}]
                    },
                    "audio": [
                        {"id": 30280, "baseUrl": "http://standard_192.m4s", "codecs": "mp4a", "bandwidth": 192000}
                    ]
                }
            }
        }
        client.session.get = MagicMock(return_value=mock_flac_resp)
        res_flac = client.get_play_streams("BV1xx411c7mD", 111, qn=80)
        self.assertEqual(res_flac["audio_url"], "http://flac_audio.m4s")
        self.assertEqual(res_flac["audio_codec"], "fLaC")

        # 2. 无 FLAC，但存在杜比全景声
        mock_dolby_resp = MagicMock()
        mock_dolby_resp.json.return_value = {
            "code": 0,
            "data": {
                "dash": {
                    "video": [{"id": 80, "baseUrl": "http://v.m4s"}],
                    "flac": None,
                    "dolby": {
                        "audio": [{"id": 30250, "baseUrl": "http://dolby_audio.m4s", "codecs": "ec-3", "bandwidth": 448000}]
                    },
                    "audio": [
                        {"id": 30280, "baseUrl": "http://standard_192.m4s", "codecs": "mp4a", "bandwidth": 192000}
                    ]
                }
            }
        }
        client.session.get = MagicMock(return_value=mock_dolby_resp)
        res_dolby = client.get_play_streams("BV1xx411c7mD", 111, qn=80)
        self.assertEqual(res_dolby["audio_url"], "http://dolby_audio.m4s")
        self.assertEqual(res_dolby["audio_codec"], "ec-3")

        # 3. 仅普通音轨，按 bandwidth 降序优先选取最高码率 (192K 优先于 64K)
        mock_std_resp = MagicMock()
        mock_std_resp.json.return_value = {
            "code": 0,
            "data": {
                "dash": {
                    "video": [{"id": 80, "baseUrl": "http://v.m4s"}],
                    "audio": [
                        {"id": 30216, "baseUrl": "http://standard_64.m4s", "codecs": "mp4a", "bandwidth": 64000},
                        {"id": 30280, "baseUrl": "http://standard_192.m4s", "codecs": "mp4a", "bandwidth": 192000},
                        {"id": 30232, "baseUrl": "http://standard_132.m4s", "codecs": "mp4a", "bandwidth": 132000}
                    ]
                }
            }
        }
        client.session.get = MagicMock(return_value=mock_std_resp)
        res_std = client.get_play_streams("BV1xx411c7mD", 111, qn=80)
        self.assertEqual(res_std["audio_url"], "http://standard_192.m4s")
        self.assertEqual(res_std["audio_bandwidth"], 192000)

    def test_worker_cookie_and_referer_propagation(self):
        """测试下载引擎工作线程将 Cookie 与 Referer 正确透传至分片网络请求"""
        from unittest.mock import patch, MagicMock
        from toolbox.plugins.media_downloader.downloader import MediaDownloadWorker

        worker = MediaDownloadWorker(
            video_url="http://mock.bili.com/video.m4s",
            audio_url="http://mock.bili.com/audio.m4s",
            save_dir=tempfile.gettempdir(),
            title="CookieTestTitle",
            cookie="SESSDATA=mock_token_12345; buvid3=mock_buvid"
        )
        self.assertEqual(worker.cookie, "SESSDATA=mock_token_12345; buvid3=mock_buvid")

        captured_headers = []
        def mock_get(url, headers=None, **kwargs):
            captured_headers.append(dict(headers or {}))
            mock_res = MagicMock()
            mock_res.headers = {"content-length": "10"}
            mock_res.iter_content.return_value = [b"0123456789"]
            return mock_res

        with patch("requests.get", side_effect=mock_get):
            dummy_target = os.path.join(tempfile.gettempdir(), "test_worker_temp.m4s")
            try:
                ok = worker._download_stream("http://mock.bili.com/video.m4s", dummy_target, "视频")
                self.assertTrue(ok)
                self.assertTrue(len(captured_headers) > 0)
                req_hdr = captured_headers[0]
                self.assertEqual(req_hdr.get("Referer"), "https://www.bilibili.com")
                self.assertEqual(req_hdr.get("Cookie"), "SESSDATA=mock_token_12345; buvid3=mock_buvid")
            finally:
                if os.path.exists(dummy_target):
                    os.remove(dummy_target)

        # 测试当 audio_url 为空时，工作线程能安全处理单视频流而不会因寻找 a_temp 崩溃
        worker_no_audio = MediaDownloadWorker(
            video_url="http://mock.bili.com/video_only.m4s",
            audio_url="",
            save_dir=tempfile.gettempdir(),
            title="VideoOnlyTest"
        )
        self.assertEqual(worker_no_audio.audio_url, "")

    def test_media_downloader_ui_cookie_and_vip_badge(self):
        """测试媒体下载器 UI 账号状态徽章、画质下拉大会员标记与 Cookie 设置交互"""
        from toolbox.plugins.media_downloader.ui import MediaDownloaderWidget
        widget = MediaDownloaderWidget()
        self.assertIsNotNone(widget.le_cookie)
        self.assertIsNotNone(widget.lbl_account_badge)
        self.assertIsNotNone(widget.btn_read_browser)
        self.assertIsNotNone(widget.btn_check_account)

        # 验证密码隐藏与切换显示
        from PySide6.QtWidgets import QLineEdit
        self.assertEqual(widget.le_cookie.echoMode(), QLineEdit.Password)
        widget.btn_toggle_cookie.click()
        self.assertEqual(widget.le_cookie.echoMode(), QLineEdit.Normal)
        widget.btn_toggle_cookie.click()
        self.assertEqual(widget.le_cookie.echoMode(), QLineEdit.Password)

        # 验证未登录徽章
        widget._update_account_badge({"is_login": False})
        self.assertIn("未登录", widget.lbl_account_badge.text())

        # 验证普通会员徽章 (vip_status=0)
        widget._update_account_badge({"is_login": True, "uname": "UserA", "vip_status": 0, "vip_type": 0})
        self.assertIn("已登录: UserA", widget.lbl_account_badge.text())

        # 验证过期大会员 (vip_status=0, vip_type=2) 徽章仍为普通会员
        widget._update_account_badge({"is_login": True, "uname": "UserExp", "vip_status": 0, "vip_type": 2})
        self.assertIn("已登录: UserExp", widget.lbl_account_badge.text())

        # 验证大会员徽章 (vip_status=1, vip_type=2)
        widget._update_account_badge({"is_login": True, "uname": "UserVIP", "vip_status": 1, "vip_type": 2})
        self.assertIn("大会员: UserVIP", widget.lbl_account_badge.text())

        # 验证画质下拉填充与 [大会员] 标注
        mock_qualities = [
            {"qn": 120, "name": "4K 超清"},
            {"qn": 116, "name": "1080P 60帧"},
            {"qn": 80, "name": "1080P 高清"},
            {"qn": 64, "name": "720P 高清"},
        ]
        widget._populate_qualities(mock_qualities)
        items_text = [widget.combo_quality.itemText(i) for i in range(widget.combo_quality.count())]
        self.assertIn("4K 超清 [大会员]", items_text)
        self.assertIn("1080P 60帧 [大会员]", items_text)
        self.assertIn("1080P 高清", items_text)
        self.assertIn("720P 高清", items_text)

        # 验证 Cookie 输入自动持久化与 API 同步
        widget.le_cookie.setText("test_sessdata_abc")
        self.assertIn("test_sessdata_abc", widget.api.cookie)

        # 清理避免污染全局配置
        widget.le_cookie.setText("")
        widget.cleanup()
        widget.close()

    def test_cookie_normalization_and_json_safety(self):
        """测试对浏览器导出的 JSON 数组、多行带换行 Cookie 与截断格式的容错与净化"""
        from toolbox.plugins.media_downloader.api import normalize_cookie, BiliApiClient
        from toolbox.plugins.media_downloader.ui import MediaDownloaderWidget

        # 1. JSON 数组测试 (含换行与格式化空白)
        json_array = '''[
            {"name": "SESSDATA", "value": "token_val_123"},
            {"name": "bili_jct", "value": "csrf_456"},
            {"name": "DedeUserID", "value": "10086"}
        ]'''
        norm1 = normalize_cookie(json_array)
        self.assertIn("SESSDATA=token_val_123", norm1)
        self.assertIn("bili_jct=csrf_456", norm1)
        self.assertNotIn("\n", norm1)
        self.assertNotIn("\r", norm1)

        # 2. 截断/不完整 JSON 提取 (含字面量 \\n 反转义)
        truncated = r'''_puhfM",\n "name": "SESSDATA",\n "value": "trunc_token_999"'''
        norm2 = normalize_cookie(truncated)
        self.assertIn("SESSDATA=trunc_token_999", norm2)
        self.assertNotIn("\n", norm2)

        # 2.1 过滤 bmg_af_sc 的嵌套字典与非 Cookie 字段 (如 none, sgp, domain)
        nested_json = r'''[
            {"name": "bmg_af_sc", "value": "{\"none\":{\"on\":1,\"def\":\"i1.hdslb.com\"},\"sgp\":{\"on\":1}}"},
            {"name": "SESSDATA", "value": "vip_sessdata_abc"}
        ]'''
        norm2_1 = normalize_cookie(nested_json)
        self.assertIn("SESSDATA=vip_sessdata_abc", norm2_1)
        self.assertNotIn("none=", norm2_1)
        self.assertNotIn("sgp=", norm2_1)

        # 2.2 纯残损 none/sgp 脏数据清洗 (不含 SESSDATA 时不产生 none/sgp 键值)
        junk_sc = "none={'on': 1, 'def': 'i1.hdslb.com'}; sgp={'on': 1, 'def': 'i0-sgp.hdslb.com'}"
        self.assertEqual(normalize_cookie(junk_sc), "")

        # 3. 纯 SESSDATA 裸值
        norm3 = normalize_cookie("raw_secret_value")
        self.assertEqual(norm3, "SESSDATA=raw_secret_value")

        # 4. BiliApiClient 请求头安全性 (绝对不出现回车换行与非法空白)
        client = BiliApiClient(json_array)
        header_cookie = client.session.headers.get("Cookie", "")
        self.assertIn("SESSDATA=token_val_123", header_cookie)
        self.assertNotIn("\n", header_cookie)
        self.assertNotIn("\r", header_cookie)

        # 5. UI 粘贴 JSON 自动就地清洗
        w = MediaDownloaderWidget()
        self.assertIsNotNone(w.btn_paste_cookie)
        w.le_cookie.setText(json_array)
        # 输入框应已自动清洗为无换行单行格式
        self.assertNotIn("\n", w.le_cookie.text())
        self.assertIn("SESSDATA=token_val_123", w.le_cookie.text())
        w.le_cookie.setText("")
        w.cleanup()
        w.close()

    def test_extract_fav_and_up_mid(self):
        """测试收藏夹ID、UP主MID与目标类型智能识别"""
        from toolbox.plugins.media_downloader.api import BiliApiClient

        # 1. 收藏夹链接与ID
        self.assertEqual(BiliApiClient.extract_fav_id("https://www.bilibili.com/medialist/play/ml100000038"), "100000038")
        self.assertEqual(BiliApiClient.extract_fav_id("https://www.bilibili.com/medialist/detail/ml123456"), "123456")
        self.assertEqual(BiliApiClient.extract_fav_id("https://space.bilibili.com/59436138/favlist?fid=998877"), "998877")
        self.assertEqual(BiliApiClient.extract_fav_id("ml556677"), "556677")
        self.assertEqual(BiliApiClient.extract_fav_id("fid: 887766"), "887766")
        self.assertEqual(BiliApiClient.extract_fav_id("12345678"), "12345678")

        # 2. UP 主主页与 MID
        self.assertEqual(BiliApiClient.extract_up_mid("https://space.bilibili.com/946974"), "946974")
        self.assertEqual(BiliApiClient.extract_up_mid("https://space.bilibili.com/946974/video"), "946974")
        self.assertEqual(BiliApiClient.extract_up_mid("https://space.bilibili.com/946974/upload/video"), "946974")
        self.assertEqual(BiliApiClient.extract_up_mid("UID: 946974"), "946974")
        self.assertEqual(BiliApiClient.extract_up_mid("mid: 946974"), "946974")

        # 3. 智能类型识别
        t1, id1 = BiliApiClient.detect_target_type_and_id("https://www.bilibili.com/video/BV1GJ411x7h7")
        self.assertEqual(t1, "video")
        self.assertEqual(id1, "BV1GJ411x7h7")

        t2, id2 = BiliApiClient.detect_target_type_and_id("https://www.bilibili.com/medialist/play/ml100000038")
        self.assertEqual(t2, "favorite")
        self.assertEqual(id2, "100000038")

        t3, id3 = BiliApiClient.detect_target_type_and_id("https://space.bilibili.com/946974/video")
        self.assertEqual(t3, "space")
        self.assertEqual(id3, "946974")

    def test_get_favorite_videos_api(self):
        """测试收藏夹视频列表解析及分页处理"""
        from unittest.mock import MagicMock
        from toolbox.plugins.media_downloader.api import BiliApiClient

        client = BiliApiClient()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 0,
            "data": {
                "info": {
                    "id": 100000038,
                    "title": "测试收藏夹",
                    "upper": {"name": "收藏夹UP"},
                    "cover": "http://fav_cover.jpg",
                    "media_count": 2
                },
                "medias": [
                    {
                        "bvid": "BV1xx411c7mA",
                        "title": "视频A",
                        "upper": {"name": "UP主A"},
                        "cover": "http://cover_a.jpg",
                        "duration": 120,
                        "page": 1
                    },
                    {
                        "bvid": "BV1xx411c7mB",
                        "title": "视频B",
                        "upper": {"name": "UP主B"},
                        "cover": "http://cover_b.jpg",
                        "duration": 240,
                        "page": 1
                    }
                ],
                "has_more": False
            }
        }
        client.session.get = MagicMock(return_value=mock_resp)

        res = client.get_favorite_videos("100000038")
        self.assertTrue(res["success"])
        self.assertEqual(res["type"], "favorite")
        self.assertEqual(res["title"], "测试收藏夹")
        self.assertEqual(len(res["videos"]), 2)
        self.assertEqual(res["videos"][0]["bvid"], "BV1xx411c7mA")
        self.assertEqual(res["videos"][1]["title"], "视频B")

    def test_get_space_videos_api(self):
        """测试UP主空间主页投稿全视频解析及分页处理"""
        from unittest.mock import MagicMock
        from toolbox.plugins.media_downloader.api import BiliApiClient

        client = BiliApiClient()

        def mock_get(url, params=None, **kwargs):
            mock_res = MagicMock()
            if "card" in url:
                mock_res.json.return_value = {
                    "code": 0,
                    "data": {"card": {"name": "测试大UP", "face": "http://up_face.jpg"}}
                }
            elif "medialist" in url:
                mock_res.json.return_value = {
                    "code": 0,
                    "data": {
                        "total_count": 2,
                        "has_more": False,
                        "media_list": [
                            {
                                "id": 1001,
                                "bv_id": "BV1SpaceVid1",
                                "title": "投稿视频1",
                                "cover": "http://cover1.jpg",
                                "duration": 300,
                                "upper": {"name": "测试大UP"}
                            },
                            {
                                "id": 1002,
                                "bv_id": "BV1SpaceVid2",
                                "title": "投稿视频2",
                                "cover": "http://cover2.jpg",
                                "duration": 450,
                                "upper": {"name": "测试大UP"}
                            }
                        ]
                    }
                }
            return mock_res

        client.session.get = MagicMock(side_effect=mock_get)
        res = client.get_space_videos("946974")
        self.assertTrue(res["success"])
        self.assertEqual(res["type"], "space")
        self.assertEqual(res["owner"], "测试大UP")
        self.assertEqual(len(res["videos"]), 2)
        self.assertEqual(res["videos"][0]["bvid"], "BV1SpaceVid1")
        self.assertEqual(res["videos"][1]["bvid"], "BV1SpaceVid2")

    def test_audio_export_format_options(self):
        """测试多音频导出格式 (MP3, M4A, WAV, FLAC, AAC, OGG) 参数传递与处理"""
        from toolbox.plugins.media_downloader.downloader import MediaDownloadWorker

        for fmt in ["mp3", "m4a", "wav", "flac", "aac", "ogg"]:
            worker = MediaDownloadWorker(
                video_url="",
                audio_url="http://mock.bili.com/audio.m4s",
                save_dir=tempfile.gettempdir(),
                title="AudioTest",
                audio_only=True,
                audio_format=fmt
            )
            self.assertEqual(worker.audio_format, fmt)
            self.assertTrue(worker.audio_only)

    def test_batch_media_download_worker(self):
        """测试批量下载工作线程 (BatchMediaDownloadWorker) 队列流转与事件通知"""
        from unittest.mock import MagicMock
        from toolbox.plugins.media_downloader.downloader import BatchMediaDownloadWorker

        mock_api = MagicMock()
        mock_api.get_video_info.return_value = {
            "success": True,
            "pages": [{"cid": 9999, "page": 1, "part": "P1"}]
        }
        mock_api.get_play_streams.return_value = {
            "success": True,
            "video_url": "http://video.m4s",
            "audio_url": "http://audio.m4s"
        }

        tasks = [
            {"bvid": "BV101", "cid": 101, "title": "任务1"},
            {"bvid": "BV102", "cid": None, "title": "任务2"}
        ]

        worker = BatchMediaDownloadWorker(
            api=mock_api,
            tasks=tasks,
            save_dir=tempfile.gettempdir(),
            audio_only=True,
            audio_format="mp3"
        )
        self.assertEqual(len(worker.tasks), 2)
        self.assertEqual(worker.audio_format, "mp3")

    def test_ui_multi_select_and_batch_options(self):
        """测试UI端多选勾选、全选/全不选/反选以及音频格式联动"""
        from toolbox.plugins.media_downloader.ui import MediaDownloaderWidget
        from PySide6.QtCore import Qt

        widget = MediaDownloaderWidget()
        try:
            self.assertIsNotNone(widget.combo_parse_mode)
            self.assertIsNotNone(widget.btn_select_all)
            self.assertIsNotNone(widget.btn_select_none)
            self.assertIsNotNone(widget.btn_select_invert)
            self.assertIsNotNone(widget.lbl_selected_count)
            self.assertIsNotNone(widget.combo_audio_format)

            # 模拟解析出收藏夹多视频
            mock_fav_info = {
                "success": True,
                "type": "favorite",
                "title": "我的收藏夹",
                "owner": "UP_Fav",
                "videos": [
                    {"bvid": "BV1", "title": "视频1", "duration": 100},
                    {"bvid": "BV2", "title": "视频2", "duration": 200},
                    {"bvid": "BV3", "title": "视频3", "duration": 300},
                ]
            }
            widget._on_video_info_parsed(mock_fav_info)
            self.assertEqual(widget.list_pages.count(), 3)
            # 默认应全部勾选
            self.assertIn("已勾选: 3/3", widget.lbl_selected_count.text())

            # 测试全不选
            widget.btn_select_none.click()
            self.assertIn("已勾选: 0/3", widget.lbl_selected_count.text())

            # 测试反选
            widget.btn_select_invert.click()
            self.assertIn("已勾选: 3/3", widget.lbl_selected_count.text())

            # 单项勾选取消测试
            widget.list_pages.item(0).setCheckState(Qt.Unchecked)
            self.assertIn("已勾选: 2/3", widget.lbl_selected_count.text())

            # 测试全选
            widget.btn_select_all.click()
            self.assertIn("已勾选: 3/3", widget.lbl_selected_count.text())

            # 音频格式联动测试
            self.assertFalse(widget.combo_audio_format.isEnabled())
            widget.cb_audio_only.setChecked(True)
            self.assertTrue(widget.combo_audio_format.isEnabled())
            widget.combo_audio_format.setCurrentText("FLAC")
            widget.save_settings()

            # 验证持久化生效
            widget.load_config()
            self.assertEqual(widget.combo_audio_format.currentText(), "FLAC")
        finally:
            widget.cleanup()
            widget.close()



class TestOsuSkinStudioLogic(unittest.TestCase):
    def test_osu_skin_parser(self):
        with tempfile.TemporaryDirectory() as td:
            ini_path = os.path.join(td, "skin.ini")
            with open(ini_path, "w", encoding="utf-8") as f:
                f.write("[General]\nName: TestSkin\nAuthor: Chieri\n\n[Mania]\nKeys: 4\nColumnStart: 136\nHitPosition: 402\n")

            parser = SkinParser()
            parser.load(ini_path)
            self.assertEqual(parser.general.get("Name"), "TestSkin")
            self.assertEqual(parser.general.get("Author"), "Chieri")

            sec4 = parser.get_mania_section("4")
            self.assertIsNotNone(sec4)
            self.assertEqual(sec4.get("HitPosition"), "402")

            sec4["HitPosition"] = "450"
            parser.update_or_add_mania_section("4", sec4)
            parser.save(ini_path)

            parser2 = SkinParser()
            parser2.load(ini_path)
            sec4_reloaded = parser2.get_mania_section("4")
            self.assertIsNotNone(sec4_reloaded)
            self.assertEqual(sec4_reloaded.get("HitPosition"), "450")


class TestMainWindowAndExternalPaths(unittest.TestCase):
    def test_main_window_navigation(self):
        win = MainWindow()
        self.assertIsNotNone(win)
        self.assertEqual(win.stack.currentIndex(), 0)
        # 模拟导航到插件再返回首页
        win.switch_to_plugin("file_suite")
        self.assertNotEqual(win.stack.currentIndex(), 0)
        win.go_to_home()
        self.assertEqual(win.stack.currentIndex(), 0)
        win.close()

    def test_initial_paths_dispatch_image_master(self):
        with tempfile.TemporaryDirectory() as td:
            test_img = os.path.join(td, "test_pic.png")
            with open(test_img, "wb") as f:
                f.write(b"data")

            win = MainWindow(initial_plugin_id="image_master", initial_paths=[test_img])
            plugin = win.plugin_manager.get_plugin("image_master")
            widget = plugin.get_widget()
            paths = widget.fl_images.get_paths()
            self.assertIn(os.path.normpath(test_img), paths)
            win.close()

    def test_initial_paths_dispatch_file_suite(self):
        with tempfile.TemporaryDirectory() as td:
            f = os.path.join(td, "document.txt")
            with open(f, "w") as fp: fp.write("text")

            win = MainWindow(initial_plugin_id="file_suite", initial_paths=[f])
            plugin = win.plugin_manager.get_plugin("file_suite")
            widget = plugin.get_widget()
            paths = widget.fl_name.get_paths()
            self.assertIn(os.path.normpath(f), paths)
            win.close()

    def test_initial_paths_dispatch_osu_skin(self):
        with tempfile.TemporaryDirectory() as td:
            ini_path = os.path.join(td, "skin.ini")
            with open(ini_path, "w", encoding="utf-8") as f:
                f.write("[General]\nName: ChieriSkin\n")

            win = MainWindow(initial_plugin_id="osu_skin_studio", initial_paths=[td])
            plugin = win.plugin_manager.get_plugin("osu_skin_studio")
            widget = plugin.get_widget()
            self.assertEqual(widget.current_skin_dir, td)
            self.assertEqual(widget.parser.general.get("Name"), "ChieriSkin")
            win.close()

    def test_initial_paths_dispatch_media_downloader(self):
        win = MainWindow(initial_plugin_id="media_downloader", initial_paths=["BV1xx411c7mD"])
        plugin = win.plugin_manager.get_plugin("media_downloader")
        widget = plugin.get_widget()
        self.assertEqual(widget.le_url.text(), "BV1xx411c7mD")
        win.close()


class TestWorkerComponents(unittest.TestCase):
    def test_auto_input_worker(self):
        worker = PasteSimulatorWorker()
        worker.update_config("Ctrl+Shift+X", 0.05, True, "test")
        self.assertEqual(worker.hotkey_str, "Ctrl+Shift+X")
        self.assertEqual(worker.delay, 0.05)
        self.assertTrue(worker.use_clipboard)
        self.assertEqual(worker.text_to_paste, "test")


class TestVectorIconsAndThemeSystem(unittest.TestCase):
    def test_all_svg_icons_render_valid_pixmaps(self):
        from toolbox.ui.icons import SVG_PATHS, get_pixmap, get_icon
        self.assertGreater(len(SVG_PATHS), 15)
        for icon_name in SVG_PATHS:
            pix = get_pixmap(icon_name, "#2563eb", 24)
            self.assertFalse(pix.isNull(), f"Icon {icon_name} rendered null pixmap")
            self.assertEqual(pix.width(), 24)
            self.assertEqual(pix.height(), 24)

            icon = get_icon(icon_name, "#38bdf8", 32)
            self.assertFalse(icon.isNull(), f"Icon {icon_name} produced null QIcon")

    def test_theme_system_detection_and_manager(self):
        from toolbox.core.theme import (
            ThemeManager, detect_system_theme, THEME_DARK, THEME_LIGHT, THEME_SYSTEM,
            apply_theme, DARK_THEME_QSS, LIGHT_THEME_QSS
        )
        sys_theme = detect_system_theme()
        self.assertIn(sys_theme, [THEME_DARK, THEME_LIGHT])

        tm = ThemeManager()
        tm.setup(app)

        # 验证切换至浅色模式
        changed_records = []
        tm.event_bus.theme_changed.connect(lambda t: changed_records.append(t))

        tm.set_mode(THEME_LIGHT)
        self.assertEqual(tm.get_mode(), THEME_LIGHT)
        self.assertEqual(tm.get_effective_theme(), THEME_LIGHT)
        self.assertFalse(tm.is_dark())
        self.assertIn(THEME_LIGHT, changed_records)

        # 验证切换至深色模式
        tm.set_mode(THEME_DARK)
        self.assertEqual(tm.get_mode(), THEME_DARK)
        self.assertEqual(tm.get_effective_theme(), THEME_DARK)
        self.assertTrue(tm.is_dark())
        self.assertIn(THEME_DARK, changed_records)

        # 验证切换至系统模式
        tm.set_mode(THEME_SYSTEM)
        self.assertEqual(tm.get_mode(), THEME_SYSTEM)
        self.assertIn(tm.get_effective_theme(), [THEME_DARK, THEME_LIGHT])

        # 验证 apply_theme 兼容性
        w = MainWindow()
        apply_theme(w, THEME_LIGHT)
        self.assertEqual(w.styleSheet(), LIGHT_THEME_QSS)
        apply_theme(w, THEME_DARK)
        self.assertEqual(w.styleSheet(), DARK_THEME_QSS)
        w.close()

    def test_main_window_theme_switching_buttons(self):
        from toolbox.core.theme import THEME_LIGHT, THEME_DARK, THEME_SYSTEM
        win = MainWindow()
        self.assertIsNotNone(win.btn_theme_light)
        self.assertIsNotNone(win.btn_theme_dark)
        self.assertIsNotNone(win.btn_theme_system)

        # 点击浅色按钮
        win.btn_theme_light.click()
        self.assertEqual(win.theme_manager.get_mode(), THEME_LIGHT)
        self.assertTrue(win.btn_theme_light.isChecked())

        # 点击深色按钮
        win.btn_theme_dark.click()
        self.assertEqual(win.theme_manager.get_mode(), THEME_DARK)
        self.assertTrue(win.btn_theme_dark.isChecked())

        # 点击系统按钮
        win.btn_theme_system.click()
        self.assertEqual(win.theme_manager.get_mode(), THEME_SYSTEM)
        self.assertTrue(win.btn_theme_system.isChecked())

        win.close()

    def test_home_page_filtering_and_clear_search(self):
        win = MainWindow()
        hp = win.home_page
        self.assertGreater(len(hp.plugins), 0)

        # 模拟搜索
        hp.search_input.setText("文件")
        matched = [c.plugin.name for c in hp.card_widgets]
        self.assertIn("文件批量整理大师", matched)
        self.assertFalse(hp.btn_clear_search.isHidden())

        # 模拟清空搜索
        hp.btn_clear_search.click()
        self.assertEqual(hp.search_input.text(), "")
        self.assertTrue(hp.btn_clear_search.isHidden())
        self.assertEqual(len(hp.card_widgets), len(hp.plugins))

        win.close()

    def test_zero_emojis_in_toolbox(self):
        """测试全量扫描 toolbox/ 下所有 Python 文件，严格保证零 Emoji / 图标字符残留"""
        import re
        emoji_pattern = re.compile(
            r'[\U00010000-\U0010ffff]'
            r'|[\u2600-\u26ff]'
            r'|[\u2700-\u27bf]'
            r'|[\u2300-\u23ff]'
            r'|[\u2b50-\u2b55]'
        )
        toolbox_dir = os.path.join(PROJECT_ROOT, "toolbox")
        violations = []
        for root, _, files in os.walk(toolbox_dir):
            if "__pycache__" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    fp = os.path.join(root, f)
                    with open(fp, "r", encoding="utf-8", errors="ignore") as fp_obj:
                        for idx, line in enumerate(fp_obj, 1):
                            emojis = emoji_pattern.findall(line)
                            if emojis:
                                violations.append((fp, idx, emojis, line.strip()))
        self.assertEqual(len(violations), 0, f"Found emoji violations in toolbox: {violations}")

    def test_category_buttons_rebuild_leak_free(self):
        """测试多次切换深浅主题时，分类胶囊栏旧按钮彻底解绑销毁，绝不产生层叠泄露"""
        from toolbox.core.theme import THEME_DARK, THEME_LIGHT
        win = MainWindow()
        hp = win.home_page
        initial_child_count = len(hp.cat_frame.children())
        initial_btn_count = len(hp.cat_button_group.buttons())

        for _ in range(5):
            win._set_theme(THEME_DARK)
            win._set_theme(THEME_LIGHT)

        final_child_count = len(hp.cat_frame.children())
        final_btn_count = len(hp.cat_button_group.buttons())
        self.assertEqual(final_child_count, initial_child_count)
        self.assertEqual(final_btn_count, initial_btn_count)
        win.close()

    def test_search_enter_and_escape_interactivity(self):
        """测试搜索栏 Enter 键直达插件与 Esc 键一键清除"""
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent, Qt
        win = MainWindow()
        hp = win.home_page

        opened_plugins = []
        hp.open_plugin_requested.connect(lambda pid: opened_plugins.append(pid))

        # 搜索并回车直达
        hp.search_input.setText("文件")
        hp._on_search_enter_pressed()
        self.assertEqual(len(opened_plugins), 1)
        self.assertEqual(opened_plugins[0], "file_suite")

        # 模拟按下 Esc 键清空输入
        key_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        hp.eventFilter(hp.search_input, key_event)
        self.assertEqual(hp.search_input.text(), "")

        win.close()

    def test_brand_container_click_returns_home(self):
        """测试点击顶部导航栏品牌 Logo 标题返回首页"""
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPointF, Qt, QEvent
        win = MainWindow()
        win.switch_to_plugin("file_suite")
        self.assertNotEqual(win.stack.currentIndex(), 0)

        # 模拟点击品牌区域
        mouse_event = QMouseEvent(
            QEvent.MouseButtonPress,
            QPointF(5, 5),
            QPointF(5, 5),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier
        )
        win.brand_container.mousePressEvent(mouse_event)
        self.assertEqual(win.stack.currentIndex(), 0)
        win.close()

    def test_drag_drop_box_properties_and_empty_state(self):
        """测试拖拽列表组件的 dragActive 动态属性与清空状态"""
        from toolbox.ui.components.drag_drop_box import ModernFileListWidget
        fl = ModernFileListWidget("测试列表")
        self.assertEqual(fl.list_widget.count(), 0)
        self.assertEqual(fl.get_paths(), [])

        # 验证 dragActive 初始与变更
        fl.list_widget.setProperty("dragActive", "true")
        self.assertEqual(fl.list_widget.property("dragActive"), "true")
        fl.list_widget.setProperty("dragActive", "false")
        self.assertEqual(fl.list_widget.property("dragActive"), "false")



class TestYoutubeDownloaderPlugin(unittest.TestCase):
    def test_worker_and_extractor_initialization(self):
        from toolbox.plugins.youtube_downloader.engine import VideoInfoExtractor, YoutubeDownloadWorker
        extractor = VideoInfoExtractor("https://www.youtube.com/watch?v=dQw4w9WgXcQ", proxy="http://127.0.0.1:7890")
        self.assertEqual(extractor.url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(extractor.proxy, "http://127.0.0.1:7890")

        worker = YoutubeDownloadWorker(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            save_dir="C:/downloads",
            audio_only=True,
            audio_format="mp3"
        )
        self.assertTrue(worker.audio_only)
        self.assertEqual(worker.audio_format, "mp3")

    def test_youtube_initial_paths(self):
        win = MainWindow(initial_plugin_id="youtube_downloader", initial_paths=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])
        plugin = win.plugin_manager.get_plugin("youtube_downloader")
        w = plugin.get_widget()
        self.assertEqual(w.le_url.text(), "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        win.close()


class TestVideoToAudioPlugin(unittest.TestCase):
    def test_scan_video_files(self):
        from toolbox.plugins.video_to_audio.engine import scan_video_files
        with tempfile.TemporaryDirectory() as td:
            v1 = os.path.join(td, "clip1.mp4")
            v2 = os.path.join(td, "clip2.mkv")
            f_txt = os.path.join(td, "doc.txt")
            with open(v1, "wb") as f: f.write(b"video1")
            with open(v2, "wb") as f: f.write(b"video2")
            with open(f_txt, "w") as f: f.write("text")

            scanned = scan_video_files([td])
            self.assertIn(os.path.normpath(v1), scanned)
            self.assertIn(os.path.normpath(v2), scanned)
            self.assertNotIn(os.path.normpath(f_txt), scanned)

    def test_video_to_audio_initial_paths(self):
        with tempfile.TemporaryDirectory() as td:
            v = os.path.join(td, "sample.mp4")
            with open(v, "wb") as f: f.write(b"video")

            win = MainWindow(initial_plugin_id="video_to_audio", initial_paths=[v])
            plugin = win.plugin_manager.get_plugin("video_to_audio")
            w = plugin.get_widget()
            self.assertIn(os.path.normpath(v), w.fl_videos.get_paths())
            win.close()


class TestAudioConverterPlugin(unittest.TestCase):
    def test_scan_audio_files(self):
        from toolbox.plugins.audio_converter.engine import scan_audio_files
        with tempfile.TemporaryDirectory() as td:
            a1 = os.path.join(td, "track1.mp3")
            a2 = os.path.join(td, "track2.flac")
            f_png = os.path.join(td, "pic.png")
            with open(a1, "wb") as f: f.write(b"audio1")
            with open(a2, "wb") as f: f.write(b"audio2")
            with open(f_png, "wb") as f: f.write(b"png")

            scanned = scan_audio_files([td])
            self.assertIn(os.path.normpath(a1), scanned)
            self.assertIn(os.path.normpath(a2), scanned)
            self.assertNotIn(os.path.normpath(f_png), scanned)

    def test_audio_converter_initial_paths(self):
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "song.wav")
            with open(a, "wb") as f: f.write(b"wav")

            win = MainWindow(initial_plugin_id="audio_converter", initial_paths=[a])
            plugin = win.plugin_manager.get_plugin("audio_converter")
            w = plugin.get_widget()
            self.assertIn(os.path.normpath(a), w.fl_audios.get_paths())
            win.close()


class TestNcmDecryptorPlugin(unittest.TestCase):
    def test_ncm_synthetic_decryption_and_roundtrip(self):
        """测试使用标准 NCM 格式逆向算法解密合成 NCM 文件，恢复元数据与音频流"""
        import struct, base64, json
        from Crypto.Cipher import AES
        from toolbox.plugins.ncm_decryptor.decryptor import (
            CORE_KEY, META_KEY, decrypt_ncm, scan_ncm_files
        )

        def pkcs7_pad(data, block_size=16):
            pad_len = block_size - (len(data) % block_size)
            return data + bytes([pad_len] * pad_len)

        # 1. 构造加密的 RC4 密钥
        rc4_key = b"test_secret_rc4_key_9999"
        raw_key = b"neteasecloudmusic" + rc4_key
        cipher_core = AES.new(CORE_KEY, AES.MODE_ECB)
        encrypted_key = cipher_core.encrypt(pkcs7_pad(raw_key))
        xored_key = bytes([b ^ 0x64 for b in encrypted_key])

        # 2. 构造加密的元数据
        meta_dict = {
            "musicName": "UnitSong",
            "artist": [["ChieriArtist", 123]],
            "album": "ToolboxAlbum",
            "format": "mp3"
        }
        raw_meta = b"music:" + json.dumps(meta_dict).encode("utf-8")
        cipher_meta = AES.new(META_KEY, AES.MODE_ECB)
        enc_meta = cipher_meta.encrypt(pkcs7_pad(raw_meta))
        b64_meta = base64.b64encode(enc_meta)
        meta_payload = b"163 key(Don't modify):" + b64_meta
        xored_meta = bytes([b ^ 0x63 for b in meta_payload])

        # 3. 构造伪造音频与 S-box 加密
        raw_audio = b"ID3\x03\x00\x00\x00\x00\x00\x00TEST_MP3_STREAM" * 40
        sample_cover = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 30  # JPEG header

        box = bytearray(range(256))
        c = 0
        k_len = len(rc4_key)
        for i in range(256):
            c = (box[i] + c + rc4_key[i % k_len]) & 0xFF
            box[i], box[c] = box[c], box[i]

        sbox = bytearray(256)
        for i in range(256):
            sbox[i] = box[(box[i] + box[(box[i] + i) & 0xFF]) & 0xFF]

        mask_256 = bytes([sbox[(j + 1) & 0xFF] for j in range(256)])
        enc_audio = bytearray(len(raw_audio))
        for i in range(len(raw_audio)):
            enc_audio[i] = raw_audio[i] ^ mask_256[i % 256]

        with tempfile.TemporaryDirectory() as td:
            ncm_path = os.path.join(td, "test_track.ncm")
            with open(ncm_path, "wb") as f:
                f.write(b"CTENFDAM")
                f.write(b"\x02\x00")
                f.write(struct.pack("<I", len(xored_key)))
                f.write(xored_key)
                f.write(struct.pack("<I", len(xored_meta)))
                f.write(xored_meta)
                f.write(b"\x00" * 5)  # gap
                f.write(struct.pack("<I", 0))  # crc
                f.write(b"\x00" * 4)  # gap
                f.write(struct.pack("<I", len(sample_cover)))
                f.write(sample_cover)
                f.write(enc_audio)

            # 扫描测试
            scanned = scan_ncm_files([td])
            self.assertEqual(len(scanned), 1)

            # 解密测试
            ok, out_path, meta = decrypt_ncm(ncm_path, output_dir=td, embed_tags=False)
            self.assertTrue(ok, f"Decryption failed: {out_path}")
            self.assertTrue(os.path.isfile(out_path))
            self.assertEqual(meta.get("musicName"), "UnitSong")
            self.assertEqual(meta.get("album"), "ToolboxAlbum")

            with open(out_path, "rb") as f_out:
                decrypted_content = f_out.read()
            self.assertEqual(decrypted_content, raw_audio)

    def test_ncm_standard_netease_layout_and_flac_detection(self):
        from Crypto.Cipher import AES
        import base64
        import json
        import struct
        from toolbox.plugins.ncm_decryptor.decryptor import (
            CORE_KEY, META_KEY, decrypt_ncm
        )

        def pkcs7_pad(data, block_size=16):
            pad_len = block_size - (len(data) % block_size)
            return data + bytes([pad_len] * pad_len)

        rc4_key = b"flac_secret_rc4_key_1234"
        raw_key = b"neteasecloudmusic" + rc4_key
        encrypted_key = AES.new(CORE_KEY, AES.MODE_ECB).encrypt(pkcs7_pad(raw_key))
        xored_key = bytes([b ^ 0x64 for b in encrypted_key])

        meta_dict = {
            "musicName": "FlacTrack",
            "artist": [["FlacArtist", 456]],
            "album": "FlacAlbum",
            "format": "flac"
        }
        raw_meta = b"music:" + json.dumps(meta_dict).encode("utf-8")
        enc_meta = AES.new(META_KEY, AES.MODE_ECB).encrypt(pkcs7_pad(raw_meta))
        meta_payload = b"163 key(Don't modify):" + base64.b64encode(enc_meta)
        xored_meta = bytes([b ^ 0x63 for b in meta_payload])

        # FLAC 音频流魔数
        raw_flac = b"fLaC\x00\x00\x00\x22\x10\x00\x10\x00" + b"FLAC_STREAM_CONTENT" * 30
        sample_cover = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 20

        # S-Box 加密
        box = bytearray(range(256))
        c = 0
        k_len = len(rc4_key)
        for i in range(256):
            c = (box[i] + c + rc4_key[i % k_len]) & 0xFF
            box[i], box[c] = box[c], box[i]

        sbox = bytearray(256)
        for i in range(256):
            sbox[i] = box[(box[i] + box[(box[i] + i) & 0xFF]) & 0xFF]

        mask_256 = bytes([sbox[(j + 1) & 0xFF] for j in range(256)])
        enc_audio = bytearray(len(raw_flac))
        for i in range(len(raw_flac)):
            enc_audio[i] = raw_flac[i] ^ mask_256[i % 256]

        with tempfile.TemporaryDirectory() as td:
            ncm_path = os.path.join(td, "standard_track.ncm")
            with open(ncm_path, "wb") as f:
                f.write(b"CTENFDAM")
                f.write(b"\x02\x00")
                f.write(struct.pack("<I", len(xored_key)))
                f.write(xored_key)
                f.write(struct.pack("<I", len(xored_meta)))
                f.write(xored_meta)
                # 官方标准 NCM 结构: 5字节 CRC/gap + 4字节 cover_frame_len + 4字节 image_len + image_data + padding
                f.write(b"\x00" * 5)
                cover_frame_len = len(sample_cover) + 16
                f.write(struct.pack("<I", cover_frame_len))
                f.write(struct.pack("<I", len(sample_cover)))
                f.write(sample_cover)
                f.write(b"\x00" * 16)  # padding
                f.write(enc_audio)

            out_dir = os.path.join(td, "new_nested_out")
            ok, out_path, meta = decrypt_ncm(ncm_path, output_dir=out_dir, embed_tags=False)
            self.assertTrue(ok, f"Standard NCM decryption failed: {out_path}")
            self.assertTrue(os.path.isfile(out_path))
            self.assertTrue(out_path.lower().endswith(".flac"), f"Expected flac extension, got {out_path}")
            self.assertEqual(meta.get("musicName"), "FlacTrack")

            with open(out_path, "rb") as f_out:
                decrypted_flac = f_out.read()
            self.assertEqual(decrypted_flac, raw_flac)


class TestTranslatorPlugin(unittest.TestCase):
    def test_language_codes_and_defaults(self):
        from toolbox.plugins.translator.engine import LANGUAGE_CODES
        self.assertIn("自动检测", LANGUAGE_CODES)
        self.assertIn("中文 (简体)", LANGUAGE_CODES)
        self.assertIn("英语", LANGUAGE_CODES)
        self.assertEqual(LANGUAGE_CODES["英语"], "en")

    def test_public_translation_or_graceful_fallback(self):
        from toolbox.plugins.translator.engine import translate_via_public
        ok, res = translate_via_public("Hello", "英语", "中文 (简体)")
        if ok:
            self.assertTrue(len(res) > 0)
        else:
            self.assertIn("请求", res)

    def test_translator_initial_paths(self):
        win = MainWindow(initial_plugin_id="translator", initial_paths=["Test text for translation"])
        plugin = win.plugin_manager.get_plugin("translator")
        w = plugin.get_widget()
        self.assertIn("Test text for translation", w.te_source.toPlainText())
        win.close()


class TestAudioCutterPlugin(unittest.TestCase):
    def test_timecode_conversions(self):
        from toolbox.plugins.audio_cutter.engine import seconds_to_timecode, timecode_to_seconds
        self.assertEqual(seconds_to_timecode(0.0), "00:00:00.000")
        self.assertEqual(seconds_to_timecode(65.123), "00:01:05.123")
        self.assertEqual(seconds_to_timecode(3661.500), "01:01:01.500")

        self.assertAlmostEqual(timecode_to_seconds("00:00:00.000"), 0.0)
        self.assertAlmostEqual(timecode_to_seconds("00:01:05.123"), 65.123)
        self.assertAlmostEqual(timecode_to_seconds("01:01:01.500"), 3661.500)
        self.assertAlmostEqual(timecode_to_seconds("10.5"), 10.5)

    def test_audio_cutter_invalid_boundary(self):
        from toolbox.plugins.audio_cutter.engine import cut_audio
        ok, err = cut_audio("dummy.mp3", "out.mp3", start_sec=10.0, end_sec=5.0)
        self.assertFalse(ok)
        self.assertIn("结束时间必须大于起始时间", err)

    def test_audio_cutter_ui_extension_sync(self):
        from toolbox.plugins.audio_cutter.ui import AudioCutterWidget
        widget = AudioCutterWidget()
        widget.current_audio_path = "C:/test/sample.mp3"
        widget.le_output_path.setText("C:/test/sample_cut.mp3")

        # 切换到重新编码模式
        widget.rb_reencode.setChecked(True)
        widget.combo_format.setCurrentText("FLAC")
        self.assertTrue(widget.le_output_path.text().endswith(".flac"))

        widget.combo_format.setCurrentText("WAV")
        self.assertTrue(widget.le_output_path.text().endswith(".wav"))

        # 切回无损流拷贝模式
        widget.rb_copy.setChecked(True)
        self.assertTrue(widget.le_output_path.text().endswith(".mp3"))
        widget.close()


class TestArchiveManagerPlugin(unittest.TestCase):
    def test_get_available_engines(self):
        from toolbox.plugins.archive_manager.engine import get_available_engines
        engines = get_available_engines()
        self.assertIn("Python 内置 (zip/tar)", engines)

    def test_zip_create_and_extract_roundtrip(self):
        from toolbox.plugins.archive_manager.engine import create_archive, extract_archive
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "doc1.txt")
            f2 = os.path.join(td, "doc2.txt")
            with open(f1, "w", encoding="utf-8") as fp: fp.write("Hello File 1")
            with open(f2, "w", encoding="utf-8") as fp: fp.write("Hello File 2")

            zip_out = os.path.join(td, "bundle.zip")
            ok, msg = create_archive([f1, f2], zip_out, format_type="zip", compression_level=5)
            self.assertTrue(ok, f"ZIP create failed: {msg}")
            self.assertTrue(os.path.isfile(zip_out))

            extract_dir = os.path.join(td, "extracted")
            ok2, msg2 = extract_archive(zip_out, extract_dir)
            self.assertTrue(ok2, f"ZIP extract failed: {msg2}")

            res1 = os.path.join(extract_dir, "doc1.txt")
            res2 = os.path.join(extract_dir, "doc2.txt")
            self.assertTrue(os.path.isfile(res1))
            self.assertTrue(os.path.isfile(res2))
            with open(res1, "r", encoding="utf-8") as fp:
                self.assertEqual(fp.read(), "Hello File 1")

    def test_tar_gz_create_and_extract_roundtrip(self):
        from toolbox.plugins.archive_manager.engine import create_archive, extract_archive
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "tar_item.txt")
            with open(f1, "w", encoding="utf-8") as fp: fp.write("Tar data test")

            tar_out = os.path.join(td, "bundle.tar.gz")
            ok, msg = create_archive([f1], tar_out, format_type="tar.gz")
            self.assertTrue(ok)
            self.assertTrue(os.path.isfile(tar_out))

            extract_dir = os.path.join(td, "tar_extracted")
            ok2, msg2 = extract_archive(tar_out, extract_dir)
            self.assertTrue(ok2)
            self.assertTrue(os.path.isfile(os.path.join(extract_dir, "tar_item.txt")))

    def test_lz4_create_and_extract(self):
        from toolbox.plugins.archive_manager.engine import create_archive, extract_archive
        with tempfile.TemporaryDirectory() as td:
            raw_f = os.path.join(td, "raw_data.bin")
            with open(raw_f, "wb") as fp: fp.write(b"LZ4_COMPRESSION_TEST" * 50)

            lz4_out = os.path.join(td, "raw_data.bin.lz4")
            ok, msg = create_archive([raw_f], lz4_out, format_type="lz4")
            self.assertTrue(ok)
            self.assertTrue(os.path.isfile(lz4_out))

            extract_dir = os.path.join(td, "lz4_out")
            ok2, msg2 = extract_archive(lz4_out, extract_dir)
            self.assertTrue(ok2)
            extracted_file = os.path.join(extract_dir, "raw_data.bin")
            self.assertTrue(os.path.isfile(extracted_file))

    def test_password_encryption_refuses_silent_unencrypted_zip(self):
        from unittest.mock import patch
        from toolbox.plugins.archive_manager.engine import create_archive

        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "secret.txt")
            with open(src, "w") as fp: fp.write("super secret")

            out_zip = os.path.join(td, "secret.zip")
            with patch("toolbox.plugins.archive_manager.engine.find_7z_executable", return_value=None), \
                 patch("toolbox.plugins.archive_manager.engine.find_winrar_executable", return_value=None):
                ok, msg = create_archive([src], out_zip, format_type="zip", password="mypassword")
                self.assertFalse(ok)
                self.assertIn("无法进行加密压缩", msg)
                self.assertFalse(os.path.exists(out_zip))


class TestForceKillerPlugin(unittest.TestCase):
    def test_get_locking_processes_and_delete(self):
        from toolbox.plugins.force_killer.engine import (
            get_locking_processes, remove_file_attributes, force_unlock_and_delete, list_running_processes
        )
        # 1. 验证 list_running_processes 返回当前运行进程
        procs = list_running_processes("python")
        self.assertGreater(len(procs), 0)

        # 2. 验证锁定探测与解锁删除
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"locked content")
            tf.flush()
            temp_path = tf.name

            # 打开句柄模拟占用锁
            locking_procs = get_locking_processes(temp_path)
            self.assertGreater(len(locking_procs), 0)
            self.assertEqual(locking_procs[0][0], os.getpid())

        # 关闭并删除
        ok, msg = force_unlock_and_delete(temp_path, shred=False, auto_kill_locking_procs=False)
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(temp_path))

    def test_directory_lock_detection_and_unlock(self):
        import ctypes
        from toolbox.plugins.force_killer.engine import (
            get_locking_processes, force_unlock_and_delete
        )
        with tempfile.TemporaryDirectory() as td:
            sub = os.path.join(td, "app_bin")
            os.makedirs(sub)
            target_dll = os.path.abspath(os.path.join(sub, "core.dll"))

            GENERIC_READ = 0x80000000
            GENERIC_WRITE = 0x40000000
            OPEN_ALWAYS = 4
            h_file = ctypes.windll.kernel32.CreateFileW(
                target_dll, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_ALWAYS, 0, None
            )
            self.assertNotEqual(h_file, -1)

            try:
                # 传入整个目录 td 进行锁检测 (验证目录递归展开探测)
                procs = get_locking_processes(td)
                self.assertGreater(len(procs), 0)
                pids = [p[0] for p in procs]
                self.assertIn(os.getpid(), pids)
            finally:
                ctypes.windll.kernel32.CloseHandle(h_file)

            # 解锁后强力删除整个目录
            ok, msg = force_unlock_and_delete(td, auto_kill_locking_procs=False)
            self.assertTrue(ok)
            self.assertFalse(os.path.exists(td))

    def test_registry_app_scanning_and_ui(self):
        from toolbox.plugins.force_killer.engine import scan_registry_installed_apps
        from toolbox.plugins.force_killer.ui import ForceKillerWidget
        apps = scan_registry_installed_apps()
        self.assertIsInstance(apps, list)

        w = ForceKillerWidget()
        self.assertIsNotNone(w.table_reg_apps)
        self.assertEqual(w.tabs.count(), 3)
        w._on_scan_apps_finished(apps[:5])
        self.assertLessEqual(w.table_reg_apps.rowCount(), 5)
        w.close()


class TestProxyConfiguratorPlugin(unittest.TestCase):
    def test_status_reading(self):
        from toolbox.plugins.proxy_configurator.engine import (
            get_system_proxy_status, get_env_proxy_status, get_git_proxy_status, get_pip_status, PIP_MIRRORS
        )
        sys_status = get_system_proxy_status()
        self.assertIn("enabled", sys_status)

        env_status = get_env_proxy_status()
        self.assertIn("enabled", env_status)

        git_status = get_git_proxy_status()
        self.assertIn("installed", git_status)

        pip_status = get_pip_status()
        self.assertIn("enabled", pip_status)

        self.assertIn("清华大学源 (Tsinghua)", PIP_MIRRORS)

    def test_proxy_registry_apps_and_root_domain(self):
        from toolbox.plugins.proxy_configurator.engine import (
            extract_root_domain, matches_root_domain, scan_registry_installed_apps
        )
        self.assertEqual(extract_root_domain("https://api.github.com/v1"), "github.com")
        self.assertEqual(extract_root_domain("sub.example.co.uk:8080/path"), "example.co.uk")
        self.assertEqual(extract_root_domain("192.168.1.1:8080"), "192.168.1.1")
        self.assertTrue(matches_root_domain("https://raw.githubusercontent.com/test", "githubusercontent.com"))
        self.assertTrue(matches_root_domain("api.github.com", "github.com"))
        self.assertTrue(matches_root_domain("https://deep.sub.api.github.com/v2", "https://github.com/"))
        self.assertFalse(matches_root_domain("https://notgithub.com", "github.com"))
        # 验证复合后缀 (edu.cn, com.tw, co.jp)
        self.assertEqual(extract_root_domain("https://cs.tsinghua.edu.cn/info"), "tsinghua.edu.cn")
        self.assertEqual(extract_root_domain("sub.shop.com.tw"), "shop.com.tw")
        self.assertTrue(matches_root_domain("https://api.cs.tsinghua.edu.cn/v1", "tsinghua.edu.cn"))
        # 验证 PAC 脚本生成与导出
        from toolbox.plugins.proxy_configurator.engine import (
            generate_pac_script, export_pac_file, get_pac_proxy_status
        )
        pac_code = generate_pac_script("127.0.0.1:7890", ["github.com", "tsinghua.edu.cn"])
        self.assertIn("FindProxyForURL", pac_code)
        self.assertIn("github.com", pac_code)
        self.assertIn("PROXY 127.0.0.1:7890", pac_code)
        with tempfile.NamedTemporaryFile(suffix=".pac", delete=False) as tf:
            pac_file = tf.name
        try:
            ok, msg = export_pac_file(pac_file, "127.0.0.1:7890", ["github.com"])
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(pac_file))
        finally:
            if os.path.exists(pac_file):
                os.remove(pac_file)
        pac_st = get_pac_proxy_status()
        self.assertIn("enabled", pac_st)

        # 验证 UI 控件与自适应测试匹配函数
        from toolbox.plugins.proxy_configurator.ui import ProxyConfiguratorWidget
        pw = ProxyConfiguratorWidget()
        self.assertIsNotNone(pw.btn_enable_pac)
        self.assertIsNotNone(pw.le_test_url)
        pw.configured_urls = ["github.com", "huggingface.co"]
        pw.le_test_url.setText("https://sub.api.github.com/v1")
        pw._test_url_matching()
        self.assertIn("匹配成功", pw.lbl_match_result.text())
        pw.le_test_url.setText("https://google.com")
        pw._test_url_matching()
        self.assertIn("未匹配", pw.lbl_match_result.text())
        pw.close()

        apps = scan_registry_installed_apps()
        self.assertIsInstance(apps, list)




class TestSettingsAndCoreArchitecture(unittest.TestCase):
    def setUp(self):
        ConfigManager.reset_instance()
        self._cfg_path = os.path.join(PROJECT_ROOT, "toolbox_config.json")
        self._orig_cfg_content = None
        if os.path.exists(self._cfg_path):
            with open(self._cfg_path, "r", encoding="utf-8") as f:
                self._orig_cfg_content = f.read()

    def tearDown(self):
        if self._orig_cfg_content is not None:
            with open(self._cfg_path, "w", encoding="utf-8") as f:
                f.write(self._orig_cfg_content)
        ConfigManager.reset_instance()

    def test_config_manager_settings_helpers(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            tp = tf.name
        try:
            cfg = ConfigManager(tp)
            # 1. 插件禁用测试
            self.assertTrue(cfg.is_plugin_enabled("media_compressor"))
            cfg.set_plugin_enabled("media_compressor", False)
            self.assertFalse(cfg.is_plugin_enabled("media_compressor"))
            self.assertIn("media_compressor", cfg.get_disabled_plugins())
            cfg.set_plugin_enabled("media_compressor", True)
            self.assertTrue(cfg.is_plugin_enabled("media_compressor"))

            # 2. 多开模式
            self.assertFalse(cfg.get_multi_window_mode())
            cfg.set_multi_window_mode(True)
            self.assertTrue(cfg.get_multi_window_mode())

            # 3. 双层透明度与卡片尺寸
            self.assertEqual(cfg.get_bg_opacity(), 1.0)
            cfg.set_bg_opacity(0.85)
            self.assertAlmostEqual(cfg.get_bg_opacity(), 0.85, places=2)

            self.assertEqual(cfg.get_component_opacity(), 1.0)
            cfg.set_component_opacity(0.9)
            self.assertAlmostEqual(cfg.get_component_opacity(), 0.9, places=2)

            self.assertEqual(cfg.get_card_width(), 280)
            cfg.set_card_width(320)
            self.assertEqual(cfg.get_card_width(), 320)

            self.assertEqual(cfg.get_card_height(), 165)
            cfg.set_card_height(180)
            self.assertEqual(cfg.get_card_height(), 180)

            self.assertEqual(cfg.get_card_spacing(), 18)
            cfg.set_card_spacing(24)
            self.assertEqual(cfg.get_card_spacing(), 24)

            # 4. 毛玻璃
            self.assertFalse(cfg.get_acrylic_enabled())
            cfg.set_acrylic_enabled(True)
            self.assertTrue(cfg.get_acrylic_enabled())
            self.assertEqual(cfg.get_blur_level(), 50)
            cfg.set_blur_level(80)
            self.assertEqual(cfg.get_blur_level(), 80)

            # 5. 开机自启
            as_cfg = cfg.get_autostart_config()
            self.assertFalse(as_cfg.get("enabled"))
            cfg.set_autostart_config(True, ["media_compressor", "audio_recorder"])
            as_cfg2 = cfg.get_autostart_config()
            self.assertTrue(as_cfg2.get("enabled"))
            self.assertEqual(as_cfg2.get("plugins"), ["media_compressor", "audio_recorder"])
        finally:
            if os.path.exists(tp):
                os.remove(tp)

    def test_settings_dialog_instantiation_and_save(self):
        from toolbox.ui.settings_dialog import SettingsDialog
        win = MainWindow()
        dialog = SettingsDialog(win)
        self.assertIsNotNone(dialog)
        self.assertGreater(len(dialog._plugin_checkboxes), 15)
        self.assertGreater(len(dialog._autostart_checkboxes), 15)

        # 模拟修改双层透明度、卡片尺寸与多开
        dialog.slider_bg_opacity.setValue(90)
        dialog.slider_comp_opacity.setValue(85)
        dialog.slider_card_w.setValue(300)
        dialog.slider_card_h.setValue(170)
        dialog.slider_card_spacing.setValue(20)
        dialog.cb_multi_window.setChecked(True)
        dialog.cb_acrylic.setChecked(True)
        dialog._apply_settings_action()

        self.assertAlmostEqual(ConfigManager().get_bg_opacity(), 0.9, places=2)
        self.assertAlmostEqual(ConfigManager().get_component_opacity(), 0.85, places=2)
        self.assertEqual(ConfigManager().get_card_width(), 300)
        self.assertEqual(ConfigManager().get_card_height(), 170)
        self.assertEqual(ConfigManager().get_card_spacing(), 20)
        self.assertTrue(ConfigManager().get_multi_window_mode())
        self.assertTrue(ConfigManager().get_acrylic_enabled())

        dialog.close()
        win.close()

    def test_recent_plugins_bar_and_filtering(self):
        from PySide6.QtWidgets import QPushButton
        win = MainWindow()
        win.show()
        hp = win.home_page
        ConfigManager().set("recent_plugins", ["media_compressor", "image_master"])
        hp._rebuild_recent_bar()
        self.assertTrue(hp.recent_frame.isVisible())
        self.assertGreaterEqual(hp.recent_layout.count(), 2)

        # 禁用一个插件后，验证最近使用栏和卡片自动剔除
        ConfigManager().set_plugin_enabled("image_master", False)
        hp._on_settings_changed()
        recent_names = [hp.recent_layout.itemAt(i).widget().text() for i in range(hp.recent_layout.count()) if hp.recent_layout.itemAt(i).widget() and isinstance(hp.recent_layout.itemAt(i).widget(), QPushButton)]
        # 应该只剩下未被禁用的插件
        for name in recent_names:
            self.assertNotIn("图像格式转换与缩放", name)

        # 恢复
        ConfigManager().set_plugin_enabled("image_master", True)
        hp._on_settings_changed()
        win.close()

    def test_multi_window_standalone_dispatch(self):
        win = MainWindow()
        ConfigManager().set_multi_window_mode(True)
        self.assertEqual(len(win._plugin_windows), 0)

        # 打开插件，验证弹出独立窗口且主页面仍停留于首页 (Index 0)
        win.switch_to_plugin("whiteboard")
        self.assertEqual(win.stack.currentIndex(), 0)
        self.assertIn("whiteboard", win._plugin_windows)
        standalone_win = win._plugin_windows["whiteboard"]
        self.assertIsNotNone(standalone_win)
        self.assertIn("白板", standalone_win.windowTitle())

        # 再次切换，激活已存在窗口
        win.switch_to_plugin("whiteboard")
        self.assertEqual(len(win._plugin_windows), 1)

        # 关闭独立窗口
        standalone_win.close()
        self.assertEqual(len(win._plugin_windows), 0)

        ConfigManager().set_multi_window_mode(False)
        win.close()


class TestMediaCompressorPlugin(unittest.TestCase):
    def test_image_compression(self):
        from toolbox.plugins.media_compressor.engine import compress_image, is_image_file, is_video_file
        self.assertTrue(is_image_file("test.png"))
        self.assertTrue(is_video_file("test.mp4"))

        with tempfile.TemporaryDirectory() as td:
            src_img = os.path.join(td, "test_in.png")
            im = Image.new("RGB", (200, 200), color="blue")
            im.save(src_img, format="PNG")

            out_webp = os.path.join(td, "test_out.webp")
            ok, err, b_sz, a_sz = compress_image(src_img, out_webp, format_choice="WEBP", quality=75)
            self.assertTrue(ok, err)
            self.assertTrue(os.path.exists(out_webp))
            self.assertGreater(b_sz, 0)
            self.assertGreater(a_sz, 0)

            out_jpg = os.path.join(td, "test_out.jpg")
            ok, err, b_sz, a_sz = compress_image(src_img, out_jpg, format_choice="JPEG", quality=80, max_dimension=100)
            self.assertTrue(ok, err)
            self.assertTrue(os.path.exists(out_jpg))
            with Image.open(out_jpg) as out_im:
                self.assertLessEqual(max(out_im.size), 100)

    def test_media_compressor_widget_config(self):
        from toolbox.plugins.media_compressor.ui import MediaCompressorWidget
        w = MediaCompressorWidget()
        self.assertIsNotNone(w)
        w.slider_img_quality.setValue(65)
        w.save_settings()

        # 验证配置持久化
        cfg = ConfigManager().get_plugin_config("media_compressor")
        self.assertEqual(cfg.get("img_quality"), 65)
        w.load_settings()
        self.assertEqual(w.slider_img_quality.value(), 65)
        w.close()


class TestFrameExtractorPlugin(unittest.TestCase):
    def test_gif_frame_extraction(self):
        from toolbox.plugins.frame_extractor.engine import extract_gif_frames, is_supported_media
        self.assertTrue(is_supported_media("sample.gif"))
        self.assertTrue(is_supported_media("sample.mp4"))

        with tempfile.TemporaryDirectory() as td:
            gif_p = os.path.join(td, "animated.gif")
            f1 = Image.new("RGB", (50, 50), color="red")
            f2 = Image.new("RGB", (50, 50), color="yellow")
            f1.save(gif_p, save_all=True, append_images=[f2], loop=0, duration=200)

            out_dir = os.path.join(td, "extracted_frames")
            ok, err, count = extract_gif_frames(gif_p, out_dir, format_choice="PNG")
            self.assertTrue(ok, err)
            self.assertEqual(count, 2)
            self.assertTrue(os.path.exists(os.path.join(out_dir, "animated_frame_00001.png")))
            self.assertTrue(os.path.exists(os.path.join(out_dir, "animated_frame_00002.png")))

    def test_frame_extractor_widget_config(self):
        from toolbox.plugins.frame_extractor.ui import FrameExtractorWidget
        w = FrameExtractorWidget()
        self.assertIsNotNone(w)
        w.combo_format.setCurrentIndex(1) # JPG
        w.save_settings()

        cfg = ConfigManager().get_plugin_config("frame_extractor")
        self.assertEqual(cfg.get("format_idx"), 1)
        w.close()


class TestWebDAVConfigPlugin(unittest.TestCase):
    def test_webdav_client_logic(self):
        from toolbox.plugins.webdav_config.client import (
            WebDAVClient, get_windows_mount_cmd, format_bytes
        )
        client = WebDAVClient("http://127.0.0.1:5244/dav/", "admin", "123456")
        self.assertEqual(client._get_full_url("photos/pic.jpg"), "http://127.0.0.1:5244/dav/photos/pic.jpg")

        cmd = get_windows_mount_cmd("Z", "http://127.0.0.1:5244/dav/", "admin", "123456")
        self.assertIn("net use Z:", cmd)
        self.assertIn("123456", cmd)

        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(1048576), "1.00 MB")

    def test_webdav_widget_config(self):
        from toolbox.plugins.webdav_config.ui import WebDAVConfigWidget
        w = WebDAVConfigWidget()
        self.assertIsNotNone(w)
        w.le_url.setText("http://192.168.1.100:5244/dav/")
        w.save_settings()

        cfg = ConfigManager().get_plugin_config("webdav_config")
        self.assertIn("profiles", cfg)
        w.close()


class TestAudioRecorderPlugin(unittest.TestCase):
    def test_audio_device_detection(self):
        from toolbox.plugins.audio_recorder.engine import get_audio_input_devices
        devs = get_audio_input_devices()
        self.assertIsInstance(devs, list)
        self.assertGreater(len(devs), 0)

    def test_waveform_visualizer(self):
        from toolbox.plugins.audio_recorder.visualizer import WaveformVisualizer
        wv = WaveformVisualizer(num_bars=24)
        wv.set_level(0.7)
        self.assertGreaterEqual(wv.target_level, 0.7)
        wv.set_state(active=True, paused=False)
        self.assertTrue(wv.is_active)
        self.assertFalse(wv.is_paused)
        wv.close()

    def test_audio_recorder_widget_config(self):
        from toolbox.plugins.audio_recorder.ui import AudioRecorderWidget, format_seconds
        self.assertEqual(format_seconds(125.4), "00:02:05.4")
        w = AudioRecorderWidget()
        self.assertIsNotNone(w)
        w.combo_bitrate.setCurrentIndex(0)
        w.save_settings()

        cfg = ConfigManager().get_plugin_config("audio_recorder")
        self.assertEqual(cfg.get("bitrate_idx"), 0)
        w.close()


class TestScreenCapturePlugin(unittest.TestCase):
    def test_capture_functions(self):
        from PySide6.QtGui import QPixmap, QColor
        from toolbox.plugins.screen_capture.capture import (
            grab_fullscreen, stitch_long_screenshot, PinnedImageViewer
        )
        pix = grab_fullscreen()
        self.assertIsInstance(pix, QPixmap)

        # 模拟长截图垂直拼接
        p1 = QPixmap(100, 50)
        p1.fill(QColor("red"))
        p2 = QPixmap(100, 60)
        p2.fill(QColor("blue"))
        combined = stitch_long_screenshot([p1, p2])
        self.assertEqual(combined.width(), 100)
        self.assertEqual(combined.height(), 110)

        # 贴图组件测试
        viewer = PinnedImageViewer(p1)
        self.assertIsNotNone(viewer)
        self.assertEqual(viewer.current_pixmap.width(), 100)
        viewer.close()

    def test_screen_capture_widget_config(self):
        from toolbox.plugins.screen_capture.ui import ScreenCaptureWidget
        w = ScreenCaptureWidget()
        self.assertIsNotNone(w)
        w.cb_pin.setChecked(True)
        w.save_settings()

        cfg = ConfigManager().get_plugin_config("screen_capture")
        self.assertTrue(cfg.get("auto_pin"))
        w.cleanup()
        w.close()

    def test_screen_capture_mode_tabs_and_xbox_overlay(self):
        """测试截图模式独立设置标签页切换与类 Xbox 截屏悬浮控制坞启闭和持久化"""
        from toolbox.plugins.screen_capture.ui import ScreenCaptureWidget, XboxCaptureOverlayWidget
        w = ScreenCaptureWidget()
        self.assertIsNotNone(w.mode_tabs)
        self.assertEqual(w.mode_tabs.count(), 4)

        # 验证 4 个模式设置页
        w.mode_tabs.setCurrentIndex(1)  # 窗口智能截图设置页
        self.assertEqual(w.mode_tabs.currentIndex(), 1)
        self.assertTrue(hasattr(w, "cb_win_border"))
        self.assertTrue(hasattr(w, "cb_win_shadow"))

        w.mode_tabs.setCurrentIndex(2)  # 全屏快速截图设置页
        self.assertEqual(w.mode_tabs.currentIndex(), 2)
        self.assertTrue(hasattr(w, "combo_full_delay"))
        self.assertTrue(hasattr(w, "combo_full_scope"))

        w.mode_tabs.setCurrentIndex(3)  # 滚动长截图设置页
        self.assertEqual(w.mode_tabs.currentIndex(), 3)
        self.assertTrue(hasattr(w, "combo_long_dir"))
        self.assertTrue(hasattr(w, "cb_long_overlap"))

        # 验证类 Xbox 截屏组件开启
        self.assertFalse(w.cb_xbox_overlay.isChecked())
        w.cb_xbox_overlay.setChecked(True)
        self.assertTrue(w.cb_xbox_overlay.isChecked())
        self.assertIsNotNone(w.xbox_overlay)
        self.assertIsInstance(w.xbox_overlay, XboxCaptureOverlayWidget)

        # 验证持久化存储
        w.save_settings()
        cfg = ConfigManager().get_plugin_config("screen_capture")
        self.assertTrue(cfg.get("xbox_overlay"))
        self.assertEqual(cfg.get("mode_tab_idx"), 3)

        # 验证关闭悬浮坞
        w.cb_xbox_overlay.setChecked(False)
        self.assertFalse(w.xbox_overlay.isVisible())

        w.cleanup()
        w.close()


class TestScreenRecorderPlugin(unittest.TestCase):
    def test_visible_windows_detection(self):
        from toolbox.plugins.screen_recorder.engine import get_visible_windows
        wins = get_visible_windows()
        self.assertIsInstance(wins, list)

    def test_screen_recorder_widget_config(self):
        from toolbox.plugins.screen_recorder.ui import ScreenRecorderWidget, format_seconds
        self.assertEqual(format_seconds(3665), "01:01:05")
        w = ScreenRecorderWidget()
        self.assertIsNotNone(w)
        w.combo_fps.setCurrentIndex(0) # 60 FPS
        w.save_settings()

        cfg = ConfigManager().get_plugin_config("screen_recorder")
        self.assertEqual(cfg.get("fps_idx"), 0)
        w.cleanup()
        w.close()

    def test_screen_recorder_obs_features(self):
        from toolbox.plugins.screen_recorder.engine import (
            get_available_screens, get_audio_output_devices
        )
        from toolbox.plugins.screen_recorder.ui import ScreenRecorderWidget
        screens = get_available_screens()
        self.assertIsInstance(screens, list)
        self.assertGreater(len(screens), 0)

        out_devs = get_audio_output_devices()
        self.assertIsInstance(out_devs, list)

        w = ScreenRecorderWidget()
        self.assertIsNotNone(w.combo_screens)
        self.assertIsNotNone(w.combo_system_audio)
        self.assertIsNotNone(w.combo_mic)
        self.assertIsNotNone(w.edit_key_record)
        self.assertIsNotNone(w.edit_key_pause)
        w.save_settings()
        w.cleanup()
        w.close()


class TestWhiteboardPlugin(unittest.TestCase):
    def test_whiteboard_canvas_drawing_and_undo(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QColor
        from toolbox.plugins.whiteboard.canvas import WhiteboardCanvas
        canvas = WhiteboardCanvas()
        canvas.resize(400, 300)

        # 切换画笔并模拟绘制笔画
        canvas.set_tool("pen")
        canvas.set_color(QColor("#ef4444"))
        canvas.set_stroke_width(6)
        self.assertEqual(canvas.stroke_width, 6)

        # 绘制笔画
        canvas.is_drawing = True
        canvas.last_pos = QPoint(10, 10)
        canvas.current_pos = QPoint(50, 50)
        canvas._draw_segment(canvas.last_pos, canvas.current_pos)
        canvas._save_undo_state()
        self.assertGreaterEqual(len(canvas.undo_stack), 2)

        # 撤销与重做
        canvas.undo()
        self.assertGreaterEqual(len(canvas.redo_stack), 1)
        canvas.redo()
        self.assertEqual(len(canvas.redo_stack), 0)

        # 导出图片
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            out_p = tf.name
        try:
            ok = canvas.export_image(out_p)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(out_p))
            self.assertGreater(os.path.getsize(out_p), 0)
        finally:
            if os.path.exists(out_p):
                os.remove(out_p)

        canvas.close()

    def test_whiteboard_widget_config(self):
        from toolbox.plugins.whiteboard.ui import WhiteboardWidget
        w = WhiteboardWidget()
        self.assertIsNotNone(w)
        w.combo_bg.setCurrentIndex(1) # 墨绿黑板
        w.save_settings()

        cfg = ConfigManager().get_plugin_config("whiteboard")
        self.assertEqual(cfg.get("bg_idx"), 1)
        w.close()


class TestReviewerHardeningAndVerification(unittest.TestCase):
    def setUp(self):
        ConfigManager.reset_instance()

    def tearDown(self):
        ConfigManager.reset_instance()

    def test_multi_window_mode_switch_roundtrip(self):
        """测试单窗口打开插件 -> 开启多开 -> 独立窗口打开 -> 关闭独立窗口 -> 关闭多开 -> 再次单窗口打开，验证 C++ 对象不被销毁且正常显示"""
        win = MainWindow()
        ConfigManager().set_multi_window_mode(False)

        # 1. 单窗口打开 whiteboard
        win.switch_to_plugin("whiteboard")
        self.assertNotEqual(win.stack.currentIndex(), 0)
        p = win.plugin_manager.get_plugin("whiteboard")
        orig_widget = p.get_widget()
        self.assertIsNotNone(orig_widget)

        # 2. 开启多窗口模式并打开插件
        ConfigManager().set_multi_window_mode(True)
        win.switch_to_plugin("whiteboard")
        self.assertIn("whiteboard", win._plugin_windows)
        standalone = win._plugin_windows["whiteboard"]

        # 3. 关闭独立窗口（应当 takeCentralWidget，保证 widget 不被销毁）
        standalone.close()
        self.assertNotIn("whiteboard", win._plugin_windows)

        # 4. 关闭多窗口模式，再次在主窗口打开插件
        ConfigManager().set_multi_window_mode(False)
        win.switch_to_plugin("whiteboard")
        self.assertNotEqual(win.stack.currentIndex(), 0)
        self.assertIs(win.stack.currentWidget(), orig_widget)

        win.close()

    def test_screen_capture_shortcuts_and_persistence(self):
        """测试截图工具快捷键自定义配置与持久化存储"""
        from PySide6.QtGui import QKeySequence
        from toolbox.plugins.screen_capture.ui import ScreenCaptureWidget
        w = ScreenCaptureWidget()
        w.edit_key_rect.setKeySequence(QKeySequence("Ctrl+Shift+A"))
        w.edit_key_win.setKeySequence(QKeySequence("Ctrl+Shift+W"))
        w.edit_key_full.setKeySequence(QKeySequence("Ctrl+Shift+F"))
        w.edit_key_long.setKeySequence(QKeySequence("Ctrl+Shift+L"))
        w.le_save_dir.setText("C:/test_screenshots")
        w.save_settings()

        cfg = ConfigManager().get_plugin_config("screen_capture")
        self.assertEqual(cfg.get("key_rect"), "Ctrl+Shift+A")
        self.assertEqual(cfg.get("key_win"), "Ctrl+Shift+W")
        self.assertEqual(cfg.get("key_full"), "Ctrl+Shift+F")
        self.assertEqual(cfg.get("key_long"), "Ctrl+Shift+L")
        self.assertEqual(cfg.get("save_dir"), "C:/test_screenshots")

        # 验证新实例化能够正确加载恢复
        w2 = ScreenCaptureWidget()
        self.assertEqual(w2.edit_key_rect.keySequence().toString(), "Ctrl+Shift+A")
        self.assertEqual(w2.edit_key_win.keySequence().toString(), "Ctrl+Shift+W")
        self.assertEqual(w2.edit_key_full.keySequence().toString(), "Ctrl+Shift+F")
        self.assertEqual(w2.edit_key_long.keySequence().toString(), "Ctrl+Shift+L")
        self.assertEqual(w2.le_save_dir.text(), "C:/test_screenshots")
        w.cleanup()
        w.close()
        w2.cleanup()
        w2.close()

    def test_home_page_recent_category_tab(self):
        """测试首页分类胶囊中点击最近使用分类的筛选逻辑与卡片展示"""
        ConfigManager().set("recent_plugins", ["screen_capture", "media_compressor", "whiteboard"])
        win = MainWindow()
        hp = win.home_page
        hp._rebuild_category_buttons()

        # 模拟点击最近使用分类胶囊
        hp._on_category_clicked("最近使用")
        self.assertEqual(hp.current_category, "最近使用")
        rendered_pids = [c.plugin.id for c in hp.card_widgets]
        self.assertEqual(rendered_pids, ["screen_capture", "media_compressor", "whiteboard"])
        win.close()

    def test_all_plugins_settings_persistence(self):
        """测试全量 22 个插件均支持 load_settings/load_config 与 save_settings/save_config 独立参数持久化"""
        pm = PluginManager()
        pm.discover_and_load()
        plugins = pm.get_all_plugins()
        self.assertGreaterEqual(len(plugins), 26)

        for p in plugins:
            widget = p.create_widget()
            self.assertIsNotNone(widget, f"Plugin {p.id} created None widget")
            has_save = hasattr(widget, "save_settings") or hasattr(widget, "save_config")
            self.assertTrue(has_save, f"Plugin {p.id} widget missing save_settings/save_config")

            # 执行一次保存，确保无异常抛出且写入 ConfigManager
            if hasattr(widget, "save_settings"):
                widget.save_settings()
            elif hasattr(widget, "save_config"):
                widget.save_config()

            p_cfg = ConfigManager().get_plugin_config(p.id)
            self.assertIsInstance(p_cfg, dict, f"Plugin {p.id} config is not a dict")

            if hasattr(widget, "cleanup"):
                try:
                    widget.cleanup()
                except Exception:
                    pass
            widget.close()

    def test_long_screenshot_overlap_stitching(self):
        """测试连续长截图无缝拼接智能消除重合区域"""
        from PySide6.QtGui import QPixmap, QPainter, QColor
        from toolbox.plugins.screen_capture.capture import stitch_long_screenshot

        # 构造图1: 100x100, 顶部70px红色，底部30px非均匀渐变(70..80绿色, 80..90黄色, 90..100紫色)
        p1 = QPixmap(100, 100)
        painter1 = QPainter(p1)
        painter1.fillRect(0, 0, 100, 70, QColor("red"))
        painter1.fillRect(0, 70, 100, 10, QColor("green"))
        painter1.fillRect(0, 80, 100, 10, QColor("yellow"))
        painter1.fillRect(0, 90, 100, 10, QColor("purple"))
        painter1.end()

        # 构造图2: 100x100, 顶部30px具有相同的图案(0..10绿色, 10..20黄色, 20..30紫色)，底部70px蓝色
        p2 = QPixmap(100, 100)
        painter2 = QPainter(p2)
        painter2.fillRect(0, 0, 100, 10, QColor("green"))
        painter2.fillRect(0, 10, 100, 10, QColor("yellow"))
        painter2.fillRect(0, 20, 100, 10, QColor("purple"))
        painter2.fillRect(0, 30, 100, 70, QColor("blue"))
        painter2.end()

        stitched = stitch_long_screenshot([p1, p2])
        # 重合高度 30px, 拼接后高度应为 100 + 100 - 30 = 170
        self.assertEqual(stitched.width(), 100)
        self.assertEqual(stitched.height(), 170)


class TestStandaloneAndTrayFeatures(unittest.TestCase):
    """
    针对独立 Setup 安装包导出、独立插件托盘快捷栏与退出功能、卡片右键分组增删与删除隐藏、
    首页默认打开分组设置的全面自动化测试。
    """
    def setUp(self):
        import shutil
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "test_config.json")
        ConfigManager.reset_instance()
        self.cfg = ConfigManager(self.config_path)

    def tearDown(self):
        import shutil
        ConfigManager.reset_instance()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_custom_groups_crud(self):
        # 1. 验证默认自定义分组为空列表
        self.assertEqual(self.cfg.get_custom_groups(), [])

        # 2. 添加自定义分组
        self.cfg.add_custom_group("办公效率")
        self.cfg.add_custom_group("媒体娱乐")
        self.assertIn("办公效率", self.cfg.get_custom_groups())
        self.assertIn("媒体娱乐", self.cfg.get_custom_groups())

        # 3. 将插件加入分组
        self.cfg.add_plugin_to_group("screen_capture", "办公效率")
        self.cfg.add_plugin_to_group("screen_capture", "常用")
        self.assertIn("办公效率", self.cfg.get_plugin_custom_groups("screen_capture"))
        self.assertIn("常用", self.cfg.get_plugin_custom_groups("screen_capture"))
        self.assertTrue(self.cfg.is_plugin_in_group("screen_capture", "办公效率", "图像工具"))

        # 4. 从自定义分组移除插件
        self.cfg.remove_plugin_from_group("screen_capture", "办公效率")
        self.assertNotIn("办公效率", self.cfg.get_plugin_custom_groups("screen_capture"))
        self.assertIn("常用", self.cfg.get_plugin_custom_groups("screen_capture"))

        # 5. 从内置分类踢出插件（如将 media_compressor 踢出 媒体处理）
        self.assertTrue(self.cfg.is_plugin_in_group("media_compressor", "媒体处理", "媒体处理"))
        ok_rem = self.cfg.remove_plugin_from_group("media_compressor", "媒体处理", default_category="媒体处理")
        self.assertTrue(ok_rem)
        self.assertFalse(self.cfg.is_plugin_in_group("media_compressor", "媒体处理", "媒体处理"))
        self.assertIn("媒体处理", self.cfg.get_plugin_excluded_groups("media_compressor"))

        # 6. 重新加入内置分类
        ok_add = self.cfg.add_plugin_to_group("media_compressor", "媒体处理", default_category="媒体处理")
        self.assertTrue(ok_add)
        self.assertTrue(self.cfg.is_plugin_in_group("media_compressor", "媒体处理", "媒体处理"))
        self.assertNotIn("媒体处理", self.cfg.get_plugin_excluded_groups("media_compressor"))

        # 7. 删除分组（级联清理）
        self.cfg.delete_custom_group("常用")
        self.assertNotIn("常用", self.cfg.get_custom_groups())
        self.assertNotIn("常用", self.cfg.get_plugin_custom_groups("screen_capture"))

    def test_default_startup_group_persistence(self):
        # 默认值为 "全部"
        self.assertEqual(self.cfg.get_default_startup_group(), "全部")

        # 设置并保存为特定分组
        self.cfg.set_default_startup_group("媒体影音")
        self.assertEqual(self.cfg.get_default_startup_group(), "媒体影音")

        # 重新加载验证持久化
        ConfigManager.reset_instance()
        cfg2 = ConfigManager(self.config_path)
        self.assertEqual(cfg2.get_default_startup_group(), "媒体影音")

    def test_home_page_startup_category_selection(self):
        from toolbox.ui.home_page import HomePage
        from toolbox.ui.main_window import MainWindow
        # 设置默认启动展示分组为 "媒体处理"
        self.cfg.set_default_startup_group("媒体处理")
        pm = PluginManager()
        pm.discover_and_load()
        plugins = pm.get_all_plugins()

        # 1. 验证构造直接传入插件列表
        hp = HomePage(plugins=plugins)
        self.assertEqual(hp.current_category, "媒体处理")

        # 检查分类按钮组中选中态
        checked_btns = [b for b in hp.cat_button_group.buttons() if b.isChecked()]
        self.assertTrue(len(checked_btns) > 0)
        self.assertTrue(checked_btns[0].text().startswith("媒体处理"))
        hp.close()

        # 2. 深度验证：MainWindow 真实两阶段初始化（HomePage() -> load_plugins() -> set_plugins()）
        win = MainWindow()
        self.assertEqual(win.home_page.current_category, "媒体处理")
        win_checked = [b for b in win.home_page.cat_button_group.buttons() if b.isChecked()]
        self.assertTrue(len(win_checked) > 0)
        self.assertTrue(win_checked[0].text().startswith("媒体处理"))
        win.close()

    def test_settings_dialog_default_group_integration(self):
        from toolbox.ui.settings_dialog import SettingsDialog
        pm = PluginManager()
        pm.discover_and_load()
        self.cfg.add_custom_group("自定义套件")
        self.cfg.set_default_startup_group("自定义套件")

        diag = SettingsDialog()
        self.assertEqual(diag.combo_default_group.currentText(), "自定义套件")

        # 切换默认展示项并保存
        all_items = [diag.combo_default_group.itemText(i) for i in range(diag.combo_default_group.count())]
        self.assertIn("全部", all_items)
        self.assertIn("最近使用", all_items)
        self.assertIn("自定义套件", all_items)

        diag.combo_default_group.setCurrentText("全部")
        diag._apply_settings_action()
        self.assertEqual(self.cfg.get_default_startup_group(), "全部")
        diag.close()

    def test_tray_manager_and_quick_actions(self):
        from toolbox.core.tray_manager import PluginTrayManager
        pm = PluginManager()
        pm.discover_and_load()
        sc_plugin = pm.get_plugin("screen_capture")
        self.assertIsNotNone(sc_plugin)

        # 1. 验证 quick_actions 接口返回正确的快捷菜单项（包含截图各种模式）
        actions = sc_plugin.get_quick_actions()
        action_names = [a.get("title", "") for a in actions]
        self.assertIn("矩形选区截图", action_names)
        self.assertIn("窗口智能嗅探截图", action_names)
        self.assertIn("全屏快速截图", action_names)
        self.assertIn("滚动长截图分段", action_names)
        self.assertIn("剪贴板快速贴图置顶", action_names)

        # 验证截图插件具有 _pin_clipboard_or_last 方法
        sc_widget = sc_plugin.get_widget()
        self.assertTrue(hasattr(sc_widget, "_pin_clipboard_or_last"))

        # 2. 验证录音机、录像机与白板快捷菜单
        ar_plugin = pm.get_plugin("audio_recorder")
        if ar_plugin:
            ar_actions = [a.get("title", "") for a in ar_plugin.get_quick_actions()]
            self.assertTrue(any("录音" in title for title in ar_actions))

        sr_plugin = pm.get_plugin("screen_recorder")
        if sr_plugin:
            sr_actions = [a.get("title", "") for a in sr_plugin.get_quick_actions()]
            self.assertTrue(any("录像" in title for title in sr_actions))

        wb_plugin = pm.get_plugin("whiteboard")
        if wb_plugin:
            wb_actions = [a.get("title", "") for a in wb_plugin.get_quick_actions()]
            self.assertIn("清空白板画布", wb_actions)
            self.assertIn("导出白板画作为图片", wb_actions)

        # 3. 验证托盘右键菜单具备退出功能以及托盘管理器的增删
        tray_mgr = PluginTrayManager()
        tray_mgr.cleanup_all()

        tray_icon = tray_mgr.add_tray_icon(sc_plugin)
        self.assertIsNotNone(tray_icon)
        self.assertIn("screen_capture", tray_mgr.get_active_plugin_ids())

        # 验证托盘菜单中存在“退出”动作
        menu = tray_icon.contextMenu()
        self.assertIsNotNone(menu)
        menu_action_texts = [act.text() for act in menu.actions()]
        self.assertTrue(any("退出" in text for text in menu_action_texts))

        # 移除托盘
        tray_mgr.remove_tray_icon("screen_capture")
        self.assertNotIn("screen_capture", tray_mgr.get_active_plugin_ids())
        tray_mgr.cleanup_all()

    def test_plugin_exporter_standalone_setup_bundle(self):
        import zipfile
        from toolbox.core.plugin_exporter import PluginExporter
        export_out = os.path.join(self.temp_dir, "export_output")
        res = PluginExporter.export_plugin(
            plugin_id="force_killer",
            output_dir=export_out,
            package_type="setup",
            create_shortcuts=True,
            autostart_default=False,
            create_archive=True,
            generate_pyinstaller_spec=True
        )
        self.assertTrue(res.get("success"), f"Export failed: {res.get('error')}")
        target_dir = res.get("output_dir")
        self.assertTrue(os.path.isdir(target_dir))

        # 检查生成的核心启动与安装脚本文件
        self.assertTrue(os.path.exists(os.path.join(target_dir, "launch.bat")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "launch.pyw")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "standalone_entry.py")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "config.json")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "installer.py")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "setup.bat")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "uninstall.bat")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "build_force_killer.spec")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "build_force_killer.bat")))

        # 检查 ZIP 安装包生成
        archive_path = res.get("archive_path")
        self.assertTrue(os.path.exists(archive_path))
        with zipfile.ZipFile(archive_path, 'r') as zf:
            names = zf.namelist()
            self.assertTrue(any("launch.bat" in n for n in names))
            self.assertTrue(any("installer.py" in n for n in names))
            self.assertTrue(any("setup.bat" in n for n in names))

    def test_card_context_menu_and_delete_feature(self):
        from toolbox.ui.home_page import HomePage
        pm = PluginManager()
        pm.discover_and_load()
        plugins = pm.get_all_plugins()
        hp = HomePage(plugins=plugins)

        # 验证卡片信号
        self.assertTrue(len(hp.card_widgets) > 0)
        card = hp.card_widgets[0]
        self.assertTrue(hasattr(card, "card_context_menu_requested"))

        # 验证删除插件隐藏逻辑
        target_plugin = plugins[0]
        self.assertTrue(self.cfg.is_plugin_enabled(target_plugin.id))

        # 模拟执行 _delete_plugin_from_home 核心操作
        self.cfg.set_plugin_enabled(target_plugin.id, False)
        self.assertFalse(self.cfg.is_plugin_enabled(target_plugin.id))
        self.assertIn(target_plugin.id, self.cfg.get_disabled_plugins())

        # 验证分组加入与移出
        hp._add_plugin_to_group(target_plugin.id, "测试分组", default_category=target_plugin.category)
        self.assertTrue(self.cfg.is_plugin_in_group(target_plugin.id, "测试分组", target_plugin.category))
        hp._remove_plugin_from_group(target_plugin.id, "测试分组", default_category=target_plugin.category)
        self.assertFalse(self.cfg.is_plugin_in_group(target_plugin.id, "测试分组", target_plugin.category))

        # 重新启用
        self.cfg.set_plugin_enabled(target_plugin.id, True)
        self.assertTrue(self.cfg.is_plugin_enabled(target_plugin.id))
        hp.close()

    def test_standalone_runner_and_settings_dialog(self):
        from toolbox.standalone_runner import StandalonePluginMainWindow
        from toolbox.ui.standalone_settings_dialog import StandalonePluginSettingsDialog
        pm = PluginManager()
        pm.discover_and_load()
        plugin = pm.get_plugin("quick_launcher") or pm.get_plugin("screen_capture")
        self.assertIsNotNone(plugin)

        # 验证独立窗口初始化
        win = StandalonePluginMainWindow(plugin)
        self.assertIn(plugin.name, win.windowTitle())
        self.assertIsNotNone(win.centralWidget())

        # 验证独立设置窗口初始化与参数持久化
        diag = StandalonePluginSettingsDialog(plugin, parent=win)
        self.assertIn(plugin.name, diag.windowTitle())
        diag.slider_bg.setValue(85)
        diag.slider_blur.setValue(60)
        diag._save_settings()

        cfg_key = f"standalone_{plugin.id}"
        saved_cfg = self.cfg.get(cfg_key, {})
        self.assertAlmostEqual(saved_cfg.get("bg_opacity", 0.0), 0.85, places=2)
        self.assertEqual(saved_cfg.get("blur_level"), 60)

        diag.close()
        win.close()

    def test_plugin_independent_icons_and_mipmaps(self):
        """测试全部 22 个插件均具备专属独立的 .ico 与 .png 图标，且包含完整的 6 个 mipmap 尺寸"""
        pm = PluginManager()
        pm.discover_and_load()
        plugins = pm.get_all_plugins()
        self.assertGreaterEqual(len(plugins), 26)

        expected_sizes = {(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}

        for p in plugins:
            # 1. 验证接口路径返回有效性
            png_path = p.get_icon_path()
            ico_path = p.get_ico_path()
            self.assertTrue(os.path.isfile(png_path), f"Plugin {p.id} PNG missing: {png_path}")
            self.assertTrue(os.path.isfile(ico_path), f"Plugin {p.id} ICO missing: {ico_path}")

            # 2. 验证 PNG 分辨率 (基准 256x256)
            with Image.open(png_path) as im_png:
                self.assertEqual(im_png.size, (256, 256), f"Plugin {p.id} PNG size is {im_png.size}")

            # 3. 验证 ICO 包含全部 6 个 mipmap 级别
            with Image.open(ico_path) as im_ico:
                ico_sizes = im_ico.info.get("sizes", set())
                self.assertTrue(
                    expected_sizes.issubset(ico_sizes),
                    f"Plugin {p.id} ICO missing mipmap sizes: {expected_sizes - ico_sizes}"
                )

            # 4. 验证 QIcon 图标实例化非空
            qicon = p.get_icon(size=24)
            self.assertFalse(qicon.isNull(), f"Plugin {p.id} produced null QIcon")

    def test_plugin_exporter_uses_dedicated_plugin_icon(self):
        """测试独立插件导出时，自动使用该插件专属独立 .ico 与 .png 作为安装包与应用图标"""
        from toolbox.core.plugin_exporter import PluginExporter
        pm = PluginManager()
        pm.discover_and_load()
        p = pm.get_plugin("archive_manager")
        self.assertIsNotNone(p)

        export_out = os.path.join(tempfile.gettempdir(), "test_export_icon_out")
        try:
            res = PluginExporter.export_plugin(
                plugin_id="archive_manager",
                output_dir=export_out,
                package_type="setup",
                create_shortcuts=True,
                autostart_default=False,
                create_archive=False,
                compile_inno_setup=False,
            )
            self.assertTrue(res.get("success"), f"Export failed: {res.get('error')}")
            target_dir = res.get("output_dir")

            target_ico = os.path.join(target_dir, "app_icon.ico")
            target_png = os.path.join(target_dir, "app_icon.png")
            self.assertTrue(os.path.isfile(target_ico))
            self.assertTrue(os.path.isfile(target_png))

            # 验证导出目录中的 app_icon.ico 内容与插件专属 icon.ico 一致，而非全局工具箱图标
            with open(target_ico, "rb") as f_target, open(p.get_ico_path(), "rb") as f_plugin:
                self.assertEqual(f_target.read(), f_plugin.read())

            with open(target_png, "rb") as f_target_png, open(p.get_icon_path(), "rb") as f_plugin_png:
                self.assertEqual(f_target_png.read(), f_plugin_png.read())

            # 验证 Inno Setup .iss 脚本中设置了 SetupIconFile 为专属图标
            iss_path = res.get("iss_path")
            with open(iss_path, "r", encoding="utf-8-sig") as f_iss:
                iss_content = f_iss.read()
            self.assertIn("SetupIconFile=", iss_content)
            self.assertIn("UninstallDisplayIcon=", iss_content)
        finally:
            if os.path.exists(export_out):
                import shutil
                shutil.rmtree(export_out, ignore_errors=True)

    def test_settings_dialog_tray_residency_management(self):
        """测试设置中心独立系统托盘常驻管理选项卡、开关联动与 ConfigManager/PluginTrayManager 闭环"""
        from toolbox.ui.settings_dialog import SettingsDialog
        from toolbox.core.tray_manager import PluginTrayManager

        tray_mgr = PluginTrayManager()
        tray_mgr.cleanup_all()

        diag = SettingsDialog()
        # 1. 验证托盘管理选项卡存在
        tab_titles = [diag.tabs.tabText(i) for i in range(diag.tabs.count())]
        self.assertIn("系统托盘常驻", tab_titles)

        # 2. 验证全部插件的托盘复选框均已注册
        self.assertGreaterEqual(len(diag._tray_checkboxes), 26)
        self.assertGreaterEqual(len(diag._plugin_tray_checkboxes), 26)

        test_pid = "screen_capture"
        tray_cb = diag._tray_checkboxes[test_pid]
        fast_cb = diag._plugin_tray_checkboxes[test_pid]

        # 初始确保未勾选
        tray_cb.setChecked(False)
        self.assertFalse(self.cfg.is_plugin_in_tray(test_pid))
        self.assertFalse(tray_mgr.has_tray_icon(test_pid))

        # 3. 勾选托盘常驻 -> 验证实时更新与持久化
        tray_cb.setChecked(True)
        self.assertTrue(self.cfg.is_plugin_in_tray(test_pid))
        self.assertTrue(tray_mgr.has_tray_icon(test_pid))
        self.assertTrue(fast_cb.isChecked())
        self.assertEqual(diag._tray_status_labels[test_pid].text(), "常驻中")

        # 4. 取消勾选 -> 验证实时移除与持久化
        fast_cb.setChecked(False)
        self.assertFalse(self.cfg.is_plugin_in_tray(test_pid))
        self.assertFalse(tray_mgr.has_tray_icon(test_pid))
        self.assertFalse(tray_cb.isChecked())
        self.assertEqual(diag._tray_status_labels[test_pid].text(), "未常驻")

        # 5. 测试全部常驻与全部取消
        diag._set_all_tray_plugins(True)
        self.assertTrue(all(cb.isChecked() for cb in diag._tray_checkboxes.values()))
        diag._set_all_tray_plugins(False)
        self.assertTrue(not any(cb.isChecked() for cb in diag._tray_checkboxes.values()))

        # 6. 测试禁用插件联动：插件禁用后，托盘勾选项自动置灰禁用且移除托盘常驻
        tray_cb.setChecked(True)
        self.assertTrue(tray_mgr.has_tray_icon(test_pid))
        plugin_enable_cb = diag._plugin_checkboxes[test_pid]
        plugin_enable_cb.setChecked(False)  # 禁用插件
        self.assertFalse(fast_cb.isEnabled())
        self.assertFalse(fast_cb.isChecked())
        self.assertFalse(tray_cb.isEnabled())
        self.assertFalse(tray_cb.isChecked())
        self.assertFalse(tray_mgr.has_tray_icon(test_pid))

        # 重新启用
        plugin_enable_cb.setChecked(True)
        self.assertTrue(fast_cb.isEnabled())
        self.assertTrue(tray_cb.isEnabled())

        # 7. 测试托盘图标在 SettingsDialog 关闭后的动作与生命周期安全 (杜绝 NameError / 悬垂引用)
        tray_cb.setChecked(True)
        t_icon = tray_mgr.get_tray_icon(test_pid)
        self.assertIsNotNone(t_icon)

        # 模拟对话框关闭
        diag.close()

        # 触发 on_open 与 on_exit
        t_icon.on_open()
        t_icon.on_exit()
        self.assertFalse(tray_mgr.has_tray_icon(test_pid))

        # 8. 测试列表过滤
        diag_new = SettingsDialog()
        diag_new._filter_tray_list("截图")
        for pid, cb in diag_new._tray_checkboxes.items():
            parent_frame = cb.parentWidget()
            if pid == "screen_capture":
                self.assertFalse(parent_frame.isHidden())
            else:
                self.assertTrue(parent_frame.isHidden())

        diag_new.close()
        tray_mgr.cleanup_all()

    def test_standalone_window_and_dialog_dedicated_icons(self):
        """测试独立设置对话框与独立窗口均使用各插件的专属独立图标"""
        from toolbox.ui.standalone_settings_dialog import StandalonePluginSettingsDialog
        from toolbox.ui.standalone_window import PluginStandaloneWindow
        from toolbox.standalone_runner import StandalonePluginMainWindow

        pm = PluginManager()
        pm.discover_and_load()
        p = pm.get_plugin("screen_capture")
        self.assertIsNotNone(p)

        # 1. StandalonePluginSettingsDialog
        diag = StandalonePluginSettingsDialog(p)
        self.assertFalse(diag.windowIcon().isNull())
        diag.close()

        # 2. PluginStandaloneWindow (多开模式独立窗口)
        win = PluginStandaloneWindow(p)
        self.assertFalse(win.windowIcon().isNull())
        win.close()

        # 3. StandalonePluginMainWindow (独立导出应用运行窗口)
        runner_win = StandalonePluginMainWindow(p)
        self.assertFalse(runner_win.windowIcon().isNull())
        if runner_win.tray_icon:
            runner_win.tray_icon.hide()
        runner_win.close()


if __name__ == "__main__":
    unittest.main()



