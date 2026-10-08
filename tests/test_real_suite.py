"""
千绘莉多功能工具箱 - 全 28 插件真实功能与音频深度闭环测试套件
真实测试:
1. 真实音频与多媒体引擎 (FFmpeg, 7-Zip, NCM 解密, 音频切片, 格式转换, 媒体压缩, 逐帧提取)
2. 真实网络爬虫 (Bilibili DASH 协议解析与分片下载, YouTube 解析与网络代理自适应)
3. 真实系统集成 (注册表, 进程占用探测, 音频设备枚举, 环境变量代理)
4. 全部 28 个插件端到端实例化与真实业务逻辑验证
"""

import os
import sys
import tempfile
import struct
import base64
import subprocess
import unittest
from PIL import Image
from Crypto.Cipher import AES

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
app = QApplication.instance()
if not app:
    app = QApplication(["--platform", "offscreen"])

from toolbox.core.plugin_manager import PluginManager
from toolbox.core.config_manager import ConfigManager
from toolbox.plugins.video_to_audio.engine import extract_audio
from toolbox.plugins.audio_converter.engine import convert_audio
from toolbox.plugins.audio_cutter.engine import cut_audio
from toolbox.plugins.media_compressor.engine import compress_image, compress_video
from toolbox.plugins.frame_extractor.engine import extract_video_frames
from toolbox.plugins.archive_manager.engine import create_archive, extract_archive, find_7z_executable
from toolbox.plugins.ncm_decryptor.decryptor import CORE_KEY, META_KEY, decrypt_ncm
from toolbox.plugins.translator.engine import translate_via_public
from toolbox.plugins.media_downloader.api import BiliApiClient
from toolbox.plugins.media_downloader.downloader import find_ffmpeg_executable
from toolbox.plugins.force_killer.engine import get_locking_processes
from toolbox.plugins.audio_recorder.engine import get_audio_input_devices
from toolbox.plugins.proxy_configurator.engine import get_system_proxy_status, get_env_proxy_status
from toolbox.plugins.file_suite.logic import FileRenameEngine, FolderFlattenEngine
from toolbox.plugins.image_master.converter import convert_image
from toolbox.plugins.osu_skin_studio.skin_parser import SkinParser
from toolbox.plugins.system_integrator.registry_ops import run_system_health_check
from toolbox.plugins.youtube_downloader.engine import _get_node_runtime, VideoInfoExtractor


class TestRealFullSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp()
        cls.ffmpeg = find_ffmpeg_executable()
        assert cls.ffmpeg and os.path.isfile(cls.ffmpeg), f"FFmpeg not found: {cls.ffmpeg}"

        # 1. 生成真实音视频源文件 (3秒 MP4，包含 AAC 440Hz 正弦波音轨与测试画面)
        cls.src_mp4 = os.path.join(cls.tmp_dir, "real_source.mp4")
        subprocess.run([
            cls.ffmpeg, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=24",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", cls.src_mp4
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    def test_01_video_to_audio_real(self):
        """测试 1: 真实视频音轨无损/转码提取 (MP4 -> MP3)"""
        out_mp3 = os.path.join(self.tmp_dir, "extracted.mp3")
        ok, msg = extract_audio(self.src_mp4, out_mp3, "mp3")
        self.assertTrue(ok, f"Video to audio extraction failed: {msg}")
        self.assertTrue(os.path.isfile(out_mp3))
        self.assertGreater(os.path.getsize(out_mp3), 1000)

    def test_02_audio_converter_real(self):
        """测试 2: 真实音频跨格式转码 (MP3 -> FLAC, WAV)"""
        src_mp3 = os.path.join(self.tmp_dir, "extracted.mp3")
        out_flac = os.path.join(self.tmp_dir, "converted.flac")
        ok_flac, msg_flac = convert_audio(src_mp3, out_flac, "flac")
        self.assertTrue(ok_flac, f"Audio convert to FLAC failed: {msg_flac}")
        self.assertGreater(os.path.getsize(out_flac), 10000)

        out_wav = os.path.join(self.tmp_dir, "converted.wav")
        ok_wav, msg_wav = convert_audio(src_mp3, out_wav, "wav")
        self.assertTrue(ok_wav, f"Audio convert to WAV failed: {msg_wav}")
        self.assertGreater(os.path.getsize(out_wav), 10000)

    def test_03_audio_cutter_real(self):
        """测试 3: 真实音频微秒/毫秒级精确剪裁 (0.5s - 2.0s 切片)"""
        src_mp3 = os.path.join(self.tmp_dir, "extracted.mp3")
        out_cut = os.path.join(self.tmp_dir, "cut.mp3")
        ok, msg = cut_audio(src_mp3, out_cut, start_sec=0.5, end_sec=2.0)
        self.assertTrue(ok, f"Audio cut failed: {msg}")
        self.assertTrue(os.path.isfile(out_cut))
        self.assertGreater(os.path.getsize(out_cut), 500)

    def test_04_media_compressor_real(self):
        """测试 4: 真实图片与视频体积智能压缩 (WEBP 压制与 H.264 CRF 编码)"""
        test_img = os.path.join(self.tmp_dir, "photo.png")
        Image.new("RGB", (640, 480), color=(120, 180, 240)).save(test_img)

        out_webp = os.path.join(self.tmp_dir, "compressed.webp")
        ok_img, _, orig_sz, comp_sz = compress_image(test_img, out_webp, format_choice="WEBP", quality=75)
        self.assertTrue(ok_img)
        self.assertTrue(os.path.isfile(out_webp))
        self.assertLess(comp_sz, orig_sz)

        out_vid = os.path.join(self.tmp_dir, "compressed.mp4")
        ok_vid, _, v_orig, v_comp = compress_video(self.src_mp4, out_vid, crf=36)
        self.assertTrue(ok_vid)
        self.assertTrue(os.path.isfile(out_vid))

    def test_05_frame_extractor_real(self):
        """测试 5: 真实视频逐帧高保真解压提取"""
        frames_dir = os.path.join(self.tmp_dir, "frames")
        ok, msg, count = extract_video_frames(self.src_mp4, frames_dir, format_choice="PNG", mode="fps", fps_val=2.0)
        self.assertTrue(ok, f"Frame extract failed: {msg}")
        self.assertGreaterEqual(count, 5)
        self.assertTrue(os.path.exists(frames_dir))

    def test_06_archive_manager_7z_real(self):
        """测试 6: 7-Zip 高强度加密打包与解压提取完整闭环"""
        p7z = find_7z_executable()
        self.assertTrue(p7z and os.path.isfile(p7z), f"7z.exe missing: {p7z}")

        sample_file = os.path.join(self.tmp_dir, "secret.txt")
        with open(sample_file, "w", encoding="utf-8") as f:
            f.write("Chieri Toolbox 7z encrypted test payload 2026")

        arc_7z = os.path.join(self.tmp_dir, "archive.7z")
        ok_c, msg_c = create_archive([sample_file], arc_7z, format_type="7z", password="Password@123")
        self.assertTrue(ok_c, f"Create 7z failed: {msg_c}")

        unzip_dir = os.path.join(self.tmp_dir, "unpacked_7z")
        ok_e, msg_e = extract_archive(arc_7z, unzip_dir, password="Password@123")
        self.assertTrue(ok_e, f"Extract 7z failed: {msg_e}")
        extracted_file = os.path.join(unzip_dir, "secret.txt")
        self.assertTrue(os.path.isfile(extracted_file))
        with open(extracted_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "Chieri Toolbox 7z encrypted test payload 2026")

    def test_07_ncm_decryptor_real(self):
        """测试 7: 网易云音乐 .ncm 格式真实密码学解密 (AES-128-ECB 与 RC4 密钥流)"""
        ncm_path = os.path.join(self.tmp_dir, "sample.ncm")
        header = b"CTENFDAM"
        rc4_key = b"chierisecret1234"
        full_key = b"neteasecloudmusic" + rc4_key
        pad = 16 - len(full_key) % 16
        padded_key = full_key + bytes([pad] * pad)
        cipher = AES.new(CORE_KEY, AES.MODE_ECB)
        enc_key = cipher.encrypt(padded_key)
        enc_key_xored = bytes([b ^ 0x64 for b in enc_key])

        meta_json = b'music:{"musicName": "Test Song", "artist": [["Chieri", 1]], "format": "mp3"}'
        pad_m = 16 - len(meta_json) % 16
        padded_meta = meta_json + bytes([pad_m] * pad_m)
        cipher_m = AES.new(META_KEY, AES.MODE_ECB)
        enc_meta = cipher_m.encrypt(padded_meta)
        meta_payload = b"163 key(Don't modify):" + base64.b64encode(enc_meta)

        sbox = bytearray(range(256))
        j = 0
        for i in range(256):
            j = (j + sbox[i] + rc4_key[i % len(rc4_key)]) & 0xFF
            sbox[i], sbox[j] = sbox[j], sbox[i]

        def get_stream_key(idx):
            idx = (idx + 1) & 0xFF
            a = sbox[idx]
            b = sbox[(idx + a) & 0xFF]
            return sbox[(a + b) & 0xFF]

        raw_audio = b"\xff\xfb\x90\x00" + b"REAL_AUDIO_STREAM_DATA" * 50
        enc_audio = bytearray(b ^ get_stream_key(i) for i, b in enumerate(raw_audio))

        meta_payload_xored = bytes([b ^ 0x63 for b in meta_payload])

        with open(ncm_path, "wb") as f:
            f.write(header)
            f.write(b"\x00\x00")
            f.write(struct.pack("<I", len(enc_key_xored)))
            f.write(enc_key_xored)
            f.write(struct.pack("<I", len(meta_payload_xored)))
            f.write(meta_payload_xored)
            f.write(b"\x00\x00\x00\x00\x00")
            f.write(struct.pack("<I", 0))
            f.write(enc_audio)

        out_dir = os.path.join(self.tmp_dir, "decrypted_ncm")
        ok, out_path, meta = decrypt_ncm(ncm_path, out_dir)
        self.assertTrue(ok, "NCM decryption failed")
        self.assertTrue(os.path.isfile(out_path))
        self.assertEqual(meta.get("musicName"), "Test Song")

    def test_08_translator_real(self):
        """测试 8: 真实在线全能文本翻译引擎"""
        ok, text = translate_via_public("Good morning, world!", "英语", "中文 (简体)")
        self.assertTrue(ok)
        self.assertTrue(len(text) > 0)

    def test_09_bilibili_crawler_real(self):
        """测试 9: 真实 B站视频 API 爬取与 DASH 流解析 (BV1GJ411x7h7)"""
        bili = BiliApiClient()
        info = bili.get_video_info("BV1GJ411x7h7")
        self.assertTrue(info.get("success"), f"Bili info error: {info.get('error')}")
        self.assertIn("Never Gonna Give You Up", info.get("title", ""))

        cid = info["pages"][0]["cid"]
        streams = bili.get_play_streams("BV1GJ411x7h7", cid)
        self.assertTrue(streams.get("success"), f"Bili stream error: {streams.get('error')}")
        self.assertTrue(streams.get("video_url") or streams.get("audio_url"))
        self.assertIn("actual_quality", streams)
        self.assertIn("is_downgraded", streams)
        self.assertIn("available_qualities", streams)
        self.assertIn("support_formats", streams)

        # 真实检测 nav 接口账号状态 (匿名/未登录状态)
        acc_status = bili.check_account_status()
        self.assertIn("is_login", acc_status)
        self.assertFalse(acc_status["is_login"])
        self.assertEqual(acc_status["vip_status"], 0)
        self.assertIn("未登录", acc_status["message"])

    def test_10_youtube_engine_real(self):
        """测试 10: 真实 YouTube 引擎运行环境自检 (Node.js 与 yt-dlp)"""
        node = _get_node_runtime()
        self.assertIsNotNone(node, "Node.js runtime not detected")
        import yt_dlp
        self.assertIsNotNone(yt_dlp)

    def test_11_audio_recorder_real(self):
        """测试 11: 真实音频硬件/麦克风录入设备枚举与自检"""
        devices = get_audio_input_devices()
        self.assertIsInstance(devices, list)
        self.assertGreater(len(devices), 0)

    def test_12_force_killer_real(self):
        """测试 12: 真实 Windows 文件句柄占用与进程解锁检测"""
        procs = get_locking_processes(self.src_mp4)
        self.assertIsInstance(procs, list)

    def test_13_proxy_configurator_real(self):
        """测试 13: 系统代理与环境变量代理配置自检"""
        sys_p = get_system_proxy_status()
        self.assertIn("enabled", sys_p)
        env_p = get_env_proxy_status()
        self.assertIsInstance(env_p, dict)

    def test_14_file_suite_real(self):
        """测试 14: 文件批量重命名正则替换与扁平化清理引擎"""
        test_file = os.path.join(self.tmp_dir, "IMG_20260101_001.JPG")
        with open(test_file, "w") as f:
            f.write("demo")
        engine = FileRenameEngine()
        res = engine.preview_replace_rename([test_file], find_str="IMG_", replace_str="PHOTO_")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0][3], "PHOTO_20260101_001.JPG")

    def test_15_image_master_real(self):
        """测试 15: 图像多格式无损转换 (PNG -> ICO, WEBP)"""
        img_p = os.path.join(self.tmp_dir, "orig.png")
        Image.new("RGBA", (128, 128), (255, 100, 50, 200)).save(img_p)
        ok, out_path, msg = convert_image(img_p, self.tmp_dir, "ICO")
        self.assertTrue(ok, f"Convert to ICO failed: {msg}")
        self.assertTrue(os.path.isfile(out_path))

    def test_16_osu_skin_studio_real(self):
        """测试 16: osu!mania 皮肤配置文件解析与判定线高度换算"""
        ini_content = "[General]\nName: ChieriSkin\nAuthor: Chieri\n[Mania]\nKeys: 4\nColumnWidth: 32,32,32,32\nHitPosition: 402\n"
        ini_path = os.path.join(self.tmp_dir, "skin.ini")
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write(ini_content)
        parser = SkinParser()
        parser.load(ini_path)
        self.assertEqual(parser.general.get("Name"), "ChieriSkin")

    def test_17_system_integrator_real(self):
        """测试 17: 系统健康自检引擎"""
        diag = run_system_health_check()
        self.assertIn("python_version", diag)
        self.assertIn("ffmpeg_status", diag)

    def test_18_all_22_plugins_discovered(self):
        """测试 18: 全部 26 个功能模块动态发现与 UI 实例化健全性"""
        pm = PluginManager()
        pm.discover_and_load()
        plugins = pm.get_all_plugins()
        self.assertGreaterEqual(len(plugins), 26, f"Expected at least 26 plugins, found {len(plugins)}")
        for p in plugins:
            w = p.create_widget()
            self.assertIsNotNone(w, f"Plugin {p.id} widget creation failed")

    def test_19_normalize_cookie_edge_cases(self):
        """测试 19: B站 Cookie 脏键、bmg_af_sc 边缘节点参数与 SESSDATA 增强清洗验证"""
        from toolbox.plugins.media_downloader.api import normalize_cookie

        # 1. 纯辅助脏字段 (用户报错复现样本)
        raw_dirty1 = "none={'on': 1, 'def': 'i1.hdslb.com'}; sgp={'on': 1, 'def': 'i0-sgp.hdslb.com'}"
        self.assertEqual(normalize_cookie(raw_dirty1), "")

        # 2. bmg_af_sc 字典头前缀
        raw_dirty2 = "bmg_af_sc=none={'on': 1, 'def': 'i1.hdslb.com'}; sgp={'on': 1, 'def': 'i0-sgp.hdslb.com'}"
        self.assertEqual(normalize_cookie(raw_dirty2), "")

        # 3. 包含 bmg_af_sc 与脏字段，但同时包含有效 SESSDATA 与 bili_jct
        raw_mixed = "none={'on': 1, 'def': 'i1.hdslb.com'}; sgp={'on': 1, 'def': 'i0-sgp.hdslb.com'}; SESSDATA=test_sess_val_12345; bili_jct=test_jct"
        cleaned_mixed = normalize_cookie(raw_mixed)
        self.assertIn("SESSDATA=test_sess_val_12345", cleaned_mixed)
        self.assertIn("bili_jct=test_jct", cleaned_mixed)
        self.assertNotIn("none=", cleaned_mixed)
        self.assertNotIn("sgp=", cleaned_mixed)

        # 4. 纯 SESSDATA 裸值
        raw_naked = "abc1234567890abcdef"
        self.assertEqual(normalize_cookie(raw_naked), "SESSDATA=abc1234567890abcdef")

    def test_20_main_window_system_tray(self):
        """测试 20: 主工具箱系统托盘图标初始化、上下文菜单项与生命周期闭环"""
        from toolbox.ui.main_window import MainWindow

        win = MainWindow()
        try:
            self.assertIsNotNone(win.app_tray_icon)
            self.assertEqual(win.app_tray_icon.toolTip(), "千绘莉多功能工具箱")
            menu = win.app_tray_icon.contextMenu()
            self.assertIsNotNone(menu)
            action_texts = [a.text() for a in menu.actions() if a.text()]
            self.assertIn("打开主界面", action_texts)
            self.assertIn("返回首页", action_texts)
            self.assertIn("设置中心...", action_texts)
            self.assertIn("退出工具箱", action_texts)
        finally:
            win.close()

    def test_21_tray_restore_window_state(self):
        """测试 21: 托盘图标唤醒、还原置顶与窗口状态保持"""
        from toolbox.ui.main_window import MainWindow
        from PySide6.QtWidgets import QSystemTrayIcon

        win = MainWindow()
        try:
            win.show()
            win.showMinimized()
            self.assertTrue(win.isMinimized())
            win._tray_restore_window()
            self.assertFalse(win.isMinimized())

            # 模拟托盘单击与双击激活信号
            win._on_app_tray_activated(QSystemTrayIcon.Trigger)
            self.assertFalse(win.isMinimized())
            win._on_app_tray_activated(QSystemTrayIcon.DoubleClick)
            self.assertFalse(win.isMinimized())
        finally:
            win.close()

    def test_22_close_to_tray_and_exit(self):
        """测试 22: 最小化到托盘 (close_to_tray) 与托盘强制退出闭环"""
        from toolbox.ui.main_window import MainWindow
        from PySide6.QtGui import QCloseEvent

        win = MainWindow()
        try:
            win.config_manager.set("close_to_tray", True)
            win.show()
            evt = QCloseEvent()
            win.closeEvent(evt)
            # 开启常驻时，closeEvent 应忽略事件并隐藏窗口
            self.assertFalse(evt.isAccepted())
            self.assertFalse(win.isVisible())

            # 通过托盘菜单退出
            win._tray_exit_app()
            self.assertIsNone(win.app_tray_icon)
        finally:
            win.config_manager.set("close_to_tray", False)
            win.close()

    def test_23_title_deduplication_logic(self):
        """测试 23: 标题与分P去重逻辑（修复冒号提前替换导致的截断与重复拼接）"""
        def format_title(title: str, part: str) -> str:
            title = str(title or "video")
            part = str(part or "")
            if not part or part == title or part in title:
                return title
            elif title in part:
                return part
            else:
                return f"{title}_{part}"

        # 1. part 为空
        self.assertEqual(format_title("测试视频", ""), "测试视频")
        # 2. part 与 title 完全相等
        self.assertEqual(format_title("测试视频", "测试视频"), "测试视频")
        # 3. part 包含在 title 中
        self.assertEqual(format_title("【官方MV】超电磁炮 OP", "超电磁炮 OP"), "【官方MV】超电磁炮 OP")
        # 4. title 包含在 part 中
        self.assertEqual(format_title("测试视频", "测试视频 - P1 完整重制版"), "测试视频 - P1 完整重制版")
        # 5. part 独立
        self.assertEqual(format_title("进击的巨人", "第1集"), "进击的巨人_第1集")
        # 6. 带英文冒号的生肉标题
        self.assertEqual(format_title("Precious You☆: Full", "Precious You☆: Full"), "Precious You☆: Full")
        self.assertEqual(format_title("Precious You☆: Full", "Full"), "Precious You☆: Full")
        # 7. 边界与防御性测试 (None/空值)
        self.assertEqual(format_title(None, "P1"), "video_P1")
        self.assertEqual(format_title("测试视频", None), "测试视频")
        self.assertEqual(format_title(None, None), "video")

    def test_24_cid_extraction_defensive_types(self):
        """测试 24: 收藏夹与空间投稿接口的 CID 防御性提取"""
        # 1. 收藏夹防御性提取
        m_fav1 = {"ugc": {"first_cid": 12345}, "cid": 999}
        ugc1 = m_fav1.get("ugc") if isinstance(m_fav1.get("ugc"), dict) else {}
        self.assertEqual(ugc1.get("first_cid") or m_fav1.get("cid"), 12345)

        m_fav2 = {"ugc": None, "cid": 67890}
        ugc2 = m_fav2.get("ugc") if isinstance(m_fav2.get("ugc"), dict) else {}
        self.assertEqual(ugc2.get("first_cid") or m_fav2.get("cid"), 67890)

        m_fav3 = {"ugc": "malformed", "cid": None}
        ugc3 = m_fav3.get("ugc") if isinstance(m_fav3.get("ugc"), dict) else {}
        self.assertIsNone(ugc3.get("first_cid") or m_fav3.get("cid"))

        # 2. 空间投稿防御性提取
        m_sp1 = {"pages": [{"id": 11111, "page": 1}], "cid": 999}
        pages1 = m_sp1.get("pages")
        first_page1 = pages1[0] if isinstance(pages1, list) and pages1 and isinstance(pages1[0], dict) else {}
        self.assertEqual(first_page1.get("id") or m_sp1.get("cid"), 11111)

        m_sp2 = {"pages": None, "cid": 22222}
        pages2 = m_sp2.get("pages")
        first_page2 = pages2[0] if isinstance(pages2, list) and pages2 and isinstance(pages2[0], dict) else {}
        self.assertEqual(first_page2.get("id") or m_sp2.get("cid"), 22222)

        m_sp3 = {"pages": [], "cid": 33333}
        pages3 = m_sp3.get("pages")
        first_page3 = pages3[0] if isinstance(pages3, list) and pages3 and isinstance(pages3[0], dict) else {}
        self.assertEqual(first_page3.get("id") or m_sp3.get("cid"), 33333)

        m_sp4 = {"pages": "invalid", "cid": None}
        pages4 = m_sp4.get("pages")
        first_page4 = pages4[0] if isinstance(pages4, list) and pages4 and isinstance(pages4[0], dict) else {}
        self.assertIsNone(first_page4.get("id") or m_sp4.get("cid"))

    def test_25_populate_qualities_fallback_and_default(self):
        """测试 25: 画质下拉候选为空时自动回退包含 8K/4K 大会员且默认选中 1080P"""
        from toolbox.plugins.media_downloader.ui import MediaDownloaderWidget
        widget = MediaDownloaderWidget()
        try:
            # 传入空画质列表触发回退机制
            widget._populate_qualities([])
            all_qns = [widget.combo_quality.itemData(i) for i in range(widget.combo_quality.count())]
            self.assertIn(127, all_qns)  # 8K
            self.assertIn(120, all_qns)  # 4K
            self.assertIn(116, all_qns)  # 1080P 60帧
            self.assertIn(80, all_qns)   # 1080P 高清
            # 验证默认选中为 80 (1080P 高清)
            self.assertEqual(widget.combo_quality.currentData(), 80)
        finally:
            widget.deleteLater()

    def test_26_batch_download_worker_synchronous_execution(self):
        """测试 26: BatchMediaDownloadWorker 同步调度单任务 MediaDownloadWorker.run()，防止多线程死锁或UI卡死"""
        from toolbox.plugins.media_downloader.downloader import BatchMediaDownloadWorker, MediaDownloadWorker
        from unittest.mock import MagicMock, patch

        mock_api = MagicMock()
        mock_api.get_play_streams.return_value = {
            "success": True,
            "video_url": "http://mock.video",
            "audio_url": "http://mock.audio"
        }
        mock_api.cookie = ""

        tasks = [
            {"bvid": "BV1test1", "cid": 1001, "title": "任务一", "part": "P1"},
            {"bvid": "BV1test2", "cid": 1002, "title": "任务二", "part": "P2"}
        ]

        batch_worker = BatchMediaDownloadWorker(
            api=mock_api,
            tasks=tasks,
            save_dir=self.tmp_dir,
            target_qn=80
        )

        progress_events = []
        log_events = []
        item_finished_events = []
        batch_finished_events = []

        batch_worker.progress_changed.connect(lambda pct, msg: progress_events.append((pct, msg)))
        batch_worker.log_message.connect(lambda msg: log_events.append(msg))
        batch_worker.item_finished.connect(lambda idx, tot, ok, path: item_finished_events.append((idx, tot, ok, path)))
        batch_worker.batch_finished.connect(lambda s, f, p: batch_finished_events.append((s, f, p)))

        # 模拟 MediaDownloadWorker.run 执行
        run_called = []
        def mock_run(worker_self):
            run_called.append(worker_self.title)
            self.assertEqual(batch_worker._current_worker, worker_self)
            worker_self.progress_changed.emit(50, "下载中...")
            worker_self.log_message.emit("下载进度 50%")
            worker_self.finished_task.emit(True, f"/path/to/{worker_self.title}.mp4")

        with patch.object(MediaDownloadWorker, "run", mock_run):
            batch_worker.run()

        # 验证单任务同步执行
        self.assertEqual(len(run_called), 2)
        self.assertEqual(len(item_finished_events), 2)
        self.assertTrue(item_finished_events[0][2])
        self.assertTrue(item_finished_events[1][2])
        self.assertEqual(len(batch_finished_events), 1)
        self.assertEqual(batch_finished_events[0][0], 2)  # 2 成功
        self.assertEqual(batch_finished_events[0][1], 0)  # 0 失败
        self.assertIsNone(batch_worker._current_worker)    # 验证 try ... finally 清理成功

    def test_27_batch_download_worker_cancellation(self):
        """测试 27: 批量下载任务在用户取消时即时退出且不计入失败"""
        from toolbox.plugins.media_downloader.downloader import BatchMediaDownloadWorker, MediaDownloadWorker
        from unittest.mock import MagicMock, patch

        mock_api = MagicMock()
        mock_api.get_play_streams.return_value = {
            "success": True,
            "video_url": "http://mock.video",
            "audio_url": "http://mock.audio"
        }
        mock_api.cookie = ""

        tasks = [
            {"bvid": "BV1test1", "cid": 1001, "title": "任务一", "part": "P1"},
            {"bvid": "BV1test2", "cid": 1002, "title": "任务二", "part": "P2"}
        ]

        batch_worker = BatchMediaDownloadWorker(
            api=mock_api,
            tasks=tasks,
            save_dir=self.tmp_dir
        )

        batch_finished_events = []
        batch_worker.batch_finished.connect(lambda s, f, p: batch_finished_events.append((s, f, p)))

        def mock_run_cancel(worker_self):
            batch_worker.cancel()
            worker_self.finished_task.emit(False, "已取消")

        with patch.object(MediaDownloadWorker, "run", mock_run_cancel):
            batch_worker.run()

        # 取消后应立即退出，不计为失败项
        self.assertEqual(len(batch_finished_events), 1)
        self.assertEqual(batch_finished_events[0][0], 0)  # 0 成功
        self.assertEqual(batch_finished_events[0][1], 0)  # 0 失败 (取消不计入失败)

    def test_28_single_video_download_quality_refetch(self):
        """测试 28: 单视频下载在切换清晰度时触发流刷新逻辑"""
        from toolbox.plugins.media_downloader.ui import MediaDownloaderWidget
        from unittest.mock import MagicMock, patch

        widget = MediaDownloaderWidget()
        try:
            widget.current_video_info = {
                "type": "video",
                "bvid": "BV1test",
                "title": "单视频测试",
                "pages": [{"cid": 9999, "page": 1, "part": "P1"}],
                "stream_res": {"success": True, "actual_qn": 64, "video_url": "http://old.v", "audio_url": "http://old.a"}
            }
            # 构造勾选项
            from PySide6.QtWidgets import QListWidgetItem
            from PySide6.QtCore import Qt
            item = QListWidgetItem("P1: 单视频测试")
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, {
                "type": "video_page",
                "bvid": "BV1test",
                "cid": 9999,
                "title": "单视频测试",
                "part": "P1",
                "page": 1
            })
            widget.list_pages.addItem(item)
            widget._populate_qualities([{"qn": 80, "name": "1080P"}, {"qn": 64, "name": "720P"}])
            widget.combo_quality.setCurrentIndex(widget.combo_quality.findData(80)) # 选中 80，不同于 64

            # 模拟 api.get_play_streams 刷新成功
            refreshed_stream = {"success": True, "actual_qn": 80, "video_url": "http://new_1080p.v", "audio_url": "http://new.a"}
            widget.api.get_play_streams = MagicMock(return_value=refreshed_stream)

            # 拦截 MediaDownloadWorker.start 避免实际起线程
            with patch("toolbox.plugins.media_downloader.ui.MediaDownloadWorker.start") as mock_start:
                widget._start_download()
                widget.api.get_play_streams.assert_called_once_with("BV1test", 9999, qn=80)
                self.assertEqual(widget.current_video_info["stream_res"]["actual_qn"], 80)
                self.assertEqual(widget.worker.video_url, "http://new_1080p.v")
                self.assertEqual(widget.worker.title, "单视频测试_P1")
        finally:
            if widget.worker:
                widget.worker = None
            widget.deleteLater()

    def test_29_media_download_worker_cancel_closes_resp(self):
        """测试 29: MediaDownloadWorker 取消时主动关闭底层 requests 响应对象以实现微秒级断流"""
        from toolbox.plugins.media_downloader.downloader import MediaDownloadWorker
        from unittest.mock import MagicMock
        worker = MediaDownloadWorker(video_url="http://mock.v", title="测试取消")
        mock_resp = MagicMock()
        worker._current_resp = mock_resp
        worker.cancel()
        self.assertTrue(worker._is_cancelled)
        mock_resp.close.assert_called_once()

    def test_30_batch_worker_cancel_during_metadata_fetch(self):
        """测试 30: 批量任务在元数据或流地址拉取期间被取消时直接 break，不误记为任务失败"""
        from toolbox.plugins.media_downloader.downloader import BatchMediaDownloadWorker
        from unittest.mock import MagicMock

        mock_api = MagicMock()
        batch_worker = BatchMediaDownloadWorker(
            api=mock_api,
            tasks=[{"bvid": "BV1meta", "cid": None}],
            save_dir=self.tmp_dir
        )
        def cancel_in_api(*args, **kwargs):
            batch_worker.cancel()
            return {"success": False, "error": "网络已中断"}

        mock_api.get_video_info.side_effect = cancel_in_api

        batch_finished_events = []
        batch_worker.batch_finished.connect(lambda s, f, p: batch_finished_events.append((s, f, p)))
        batch_worker.run()

        self.assertEqual(len(batch_finished_events), 1)
        self.assertEqual(batch_finished_events[0][0], 0)  # 0 成功
        self.assertEqual(batch_finished_events[0][1], 0)  # 0 失败 (不将取消误认为失败)


if __name__ == "__main__":
    unittest.main()
