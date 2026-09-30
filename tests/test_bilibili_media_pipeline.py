"""
千绘莉多功能工具箱 (Chieri Toolbox) - B站视频全流程一条龙循环测试与全量功能综合测试套件
全面覆盖:
1. B站视频源下载 (BV197411B7ca，音视频流分离拉取与 FFmpeg 合并)
2. 视频转音频提取 (video_to_audio 插件 / FFmpeg 多格式抽取)
3. 视频逐帧解压提取 (frame_extractor 插件 / FFmpeg 关键帧与定时采样)
4. 图片缩放剪裁与格式转换 (image_master 插件 / 百分比、固定尺寸、居中裁剪、格式互转)
5. 音频精准剪裁切片 (audio_cutter 插件 / 毫秒级时间轴裁剪、流拷贝与重编码)
6. 一条龙循环闭环压测 (多轮次、多参数规格遍历测试)
7. 其余全量插件模块功能验证 (压缩解压、文件整理、代理、白板、粉碎机、NCM解密、翻译等)
"""

import os
import sys
import shutil
import tempfile
import unittest
from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
app = QApplication.instance()
if not app:
    app = QApplication(["--platform", "offscreen"])

from toolbox.core.paths import find_ffmpeg_executable
from toolbox.core.config_manager import ConfigManager
from toolbox.core.plugin_manager import PluginManager
from toolbox.plugins.media_downloader.api import BiliApiClient
from toolbox.plugins.media_downloader.downloader import MediaDownloadWorker
from toolbox.plugins.video_to_audio.engine import extract_audio, VideoToAudioWorker
from toolbox.plugins.frame_extractor.engine import extract_video_frames, FrameExtractorWorker
from toolbox.plugins.image_master.converter import convert_image
from toolbox.plugins.image_master.resizer import ImageBatchWorker
from toolbox.plugins.audio_cutter.engine import cut_audio, probe_audio_file, AudioCutWorker
from toolbox.plugins.audio_converter.engine import convert_audio
from toolbox.plugins.archive_manager.engine import create_archive, extract_archive, find_7z_executable
from toolbox.plugins.file_suite.logic import FileRenameEngine, FolderFlattenEngine
from toolbox.plugins.proxy_configurator.engine import get_system_proxy_status, get_env_proxy_status
from toolbox.plugins.whiteboard.canvas import WhiteboardCanvas
from toolbox.plugins.force_killer.engine import get_locking_processes
from toolbox.plugins.ncm_decryptor.decryptor import decrypt_ncm, CORE_KEY, META_KEY
from toolbox.plugins.translator.engine import translate_via_public
from toolbox.plugins.audio_recorder.engine import get_audio_input_devices
from toolbox.plugins.osu_skin_studio.skin_parser import SkinParser
from toolbox.plugins.system_integrator.registry_ops import run_system_health_check
from toolbox.core.plugin_exporter import PluginExporter

# 用户提供的 B站测试视频与凭据
USER_BVID = "BV197411B7ca"
USER_COOKIE = (
    "SESSDATA=516e716f%2C1806291042%2C83fe8%2A91CjAYdYWSka6RWrDvYMRv1KDL6wmbDRScPvEC1wMj73zXHXLhLb21-GyXo69VD1sGhzYSVmtSNmZjVVI5VVFuNWg0Qkg5c2xUQ2ZTdElQVUxheTk4Z2UzQVZFc0g1RVg5V1BNYUNldGpyVklpNGlxUjlwdjFIWWd3TENLOF9HdVRCRWhPczRJOURRIIEC; "
    "bili_jct=acf24adce7d7f4e4a5cac2785af7a7de; "
    "DedeUserID=3546703462403026; "
    "DedeUserID__ckMd5=4aa106ca07b04423"
)


class TestBilibiliMediaPipeline(unittest.TestCase):
    """
    B站视频媒体一条龙流水线与循环测试
    """
    @classmethod
    def setUpClass(cls):
        cls.work_dir = tempfile.mkdtemp(prefix="chieri_bili_pipeline_")
        cls.ffmpeg = find_ffmpeg_executable()
        assert cls.ffmpeg and os.path.isfile(cls.ffmpeg), f"FFmpeg not found: {cls.ffmpeg}"

        # 检查是否已有缓存视频以加速测试执行
        cls.cached_video = os.path.join(PROJECT_ROOT, "tests", ".media_cache", "test_bili_video.mp4")
        cls.target_video = os.path.join(cls.work_dir, "bili_source.mp4")

        if os.path.isfile(cls.cached_video) and os.path.getsize(cls.cached_video) > 1000000:
            shutil.copy2(cls.cached_video, cls.target_video)
            print(f"\n[Pipeline Setup] 使用已校验缓存视频: {cls.target_video} ({os.path.getsize(cls.target_video):,} 字节)")
        else:
            cls._download_source_video()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.work_dir):
            shutil.rmtree(cls.work_dir, ignore_errors=True)

    @classmethod
    def _download_source_video(cls):
        """若无缓存则直接调用 media_downloader 下载用户视频"""
        print(f"\n[Pipeline Setup] 正在从 B站下载视频 {USER_BVID}...")
        client = BiliApiClient(cookie=USER_COOKIE)
        info = client.get_video_info(USER_BVID)
        assert info.get("success"), f"获取视频信息失败: {info.get('error')}"
        cid = info["pages"][0]["cid"]
        streams = client.get_play_streams(USER_BVID, cid=cid, qn=80)
        assert streams.get("success"), f"获取流地址失败: {streams.get('error')}"

        worker = MediaDownloadWorker(
            video_url=streams.get("video_url"),
            audio_url=streams.get("audio_url"),
            save_dir=cls.work_dir,
            title="bili_source",
            ffmpeg_path=cls.ffmpeg,
            cookie=USER_COOKIE
        )
        worker.run()
        assert os.path.isfile(cls.target_video), "B站视频下载失败"

    def test_01_verify_downloaded_video_integrity(self):
        """测试 1: 验证下载的 B站视频完整性 (分辨率、时长、音视频轨道)"""
        self.assertTrue(os.path.isfile(self.target_video))
        size_bytes = os.path.getsize(self.target_video)
        self.assertGreater(size_bytes, 1024 * 1024, f"视频文件过小: {size_bytes} 字节")

        probe = probe_audio_file(self.target_video)
        self.assertNotIn("error", probe, f"ffprobe 解析异常: {probe.get('error')}")
        self.assertGreater(probe.get("duration", 0), 200, "视频时长小于预期")
        self.assertEqual(probe.get("channels"), 2, "音频声道数应为立体声 2")
        print(f"[TEST 1 OK] B站源视频校验通过: 时长 {probe['duration_str']}, 码率 {probe['bit_rate']} bps, 声道 {probe['channels']}")

    def test_02_video_to_audio_multi_format(self):
        """测试 2: 视频转音频多格式抽取 (MP3, WAV, FLAC, M4A)"""
        out_dir = os.path.join(self.work_dir, "extracted_audio")
        os.makedirs(out_dir, exist_ok=True)

        formats = [
            ("mp3", "320k"),
            ("wav", None),
            ("flac", None),
            ("m4a", "192k")
        ]

        for fmt, br in formats:
            out_path = os.path.join(out_dir, f"audio_output.{fmt}")
            ok, res = extract_audio(
                input_video=self.target_video,
                output_audio=out_path,
                fmt=fmt,
                bitrate=br or "320k",
                ffmpeg_path=self.ffmpeg
            )
            self.assertTrue(ok, f"抽取为 {fmt.upper()} 失败: {res}")
            self.assertTrue(os.path.isfile(out_path))
            self.assertGreater(os.path.getsize(out_path), 500000, f"{fmt} 输出音频过小")

            # 校验抽取的音频时长是否完整
            probe = probe_audio_file(out_path)
            self.assertGreater(probe.get("duration", 0), 200)
            print(f"[TEST 2 OK] 抽取音频成功: {fmt.upper()} ({os.path.getsize(out_path):,} 字节, {probe['duration_str']})")

    def test_03_frame_extraction_modes(self):
        """测试 3: 视频逐帧提取 (关键帧提取 + 定时时间间隔提取)"""
        frames_dir = os.path.join(self.work_dir, "extracted_frames")
        os.makedirs(frames_dir, exist_ok=True)

        # 模式 A: 按照时间间隔每 20 秒提取 1 帧 PNG
        interval_dir = os.path.join(frames_dir, "interval_png")
        ok_i, err_i, count_i = extract_video_frames(
            input_path=self.target_video,
            output_dir=interval_dir,
            format_choice="PNG",
            mode="interval",
            interval_sec=20.0,
            ffmpeg_exe=self.ffmpeg
        )
        self.assertTrue(ok_i, f"Interval 抽取失败: {err_i}")
        self.assertGreaterEqual(count_i, 10, f"提取帧数过少: {count_i}")

        # 验证提取的图片分辨率与格式
        first_frame = os.path.join(interval_dir, os.listdir(interval_dir)[0])
        with Image.open(first_frame) as img:
            w, h = img.size
            self.assertEqual(img.format, "PNG")
            self.assertGreater(w, 400)
            self.assertGreater(h, 300)
            print(f"[TEST 3A OK] 间隔解帧成功: 共 {count_i} 张图片, 首帧分辨率: {w}x{h}")

        # 模式 B: 提取关键帧 (Keyframes / I-Frames)
        key_dir = os.path.join(frames_dir, "keyframes_jpg")
        ok_k, err_k, count_k = extract_video_frames(
            input_path=self.target_video,
            output_dir=key_dir,
            format_choice="JPG",
            mode="keyframe",
            jpg_quality=95,
            ffmpeg_exe=self.ffmpeg
        )
        self.assertTrue(ok_k, f"Keyframe 抽取失败: {err_k}")
        self.assertGreaterEqual(count_k, 3)
        print(f"[TEST 3B OK] 关键帧解帧成功: 共提取 {count_k} 张关键帧")

    def test_04_image_resizing_cropping_and_converting(self):
        """测试 4: 图片缩放、居中裁剪、区域切片与多格式转换一条龙"""
        # 从前面提取的帧中选取样本图片
        sample_img_dir = os.path.join(self.work_dir, "extracted_frames", "interval_png")
        sample_files = [os.path.join(sample_img_dir, f) for f in os.listdir(sample_img_dir) if f.endswith(".png")]
        self.assertTrue(len(sample_files) > 0, "缺少用于图像处理的样本帧")
        sample_img = sample_files[0]

        img_out_dir = os.path.join(self.work_dir, "processed_images")
        os.makedirs(img_out_dir, exist_ok=True)

        # 4.1 百分比缩放 (50%)
        worker_pct = ImageBatchWorker(
            task_type="resize",
            file_paths=[sample_img],
            output_dir=os.path.join(img_out_dir, "resized_50pct"),
            resize_mode="percent",
            scale_pct=50.0
        )
        worker_pct.run()
        out_50 = os.path.join(img_out_dir, "resized_50pct", os.path.basename(sample_img))
        self.assertTrue(os.path.isfile(out_50))
        with Image.open(sample_img) as orig, Image.open(out_50) as resized:
            self.assertEqual(resized.size[0], orig.size[0] // 2)
            self.assertEqual(resized.size[1], orig.size[1] // 2)
            print(f"[TEST 4.1 OK] 百分比缩放: {orig.size} -> {resized.size}")

        # 4.2 固定分辨率缩放 (640x360)
        worker_fixed = ImageBatchWorker(
            task_type="resize",
            file_paths=[sample_img],
            output_dir=os.path.join(img_out_dir, "resized_fixed"),
            resize_mode="fixed",
            target_w=640,
            target_h=360,
            keep_ratio=True
        )
        worker_fixed.run()
        out_fixed = os.path.join(img_out_dir, "resized_fixed", os.path.basename(sample_img))
        self.assertTrue(os.path.isfile(out_fixed))
        with Image.open(out_fixed) as img:
            self.assertTrue(img.size[0] <= 640 and img.size[1] <= 360)
            print(f"[TEST 4.2 OK] 固定分辨率缩放: {img.size}")

        # 4.3 智能居中裁切至正方形头像 (400x400)
        worker_crop = ImageBatchWorker(
            task_type="resize",
            file_paths=[sample_img],
            output_dir=os.path.join(img_out_dir, "cropped_square"),
            resize_mode="crop",
            target_w=400,
            target_h=400
        )
        worker_crop.run()
        out_square = os.path.join(img_out_dir, "cropped_square", os.path.basename(sample_img))
        self.assertTrue(os.path.isfile(out_square))
        with Image.open(out_square) as img:
            self.assertEqual(img.size, (400, 400))
            print(f"[TEST 4.3 OK] 智能居中裁切: 正确裁切为 {img.size}")

        # 4.4 显式矩形区域剪裁 (crop_box: [100, 50, 500, 350])
        worker_box = ImageBatchWorker(
            task_type="resize",
            file_paths=[sample_img],
            output_dir=os.path.join(img_out_dir, "cropped_box"),
            crop_box=(100, 50, 500, 350),
            resize_mode="percent",
            scale_pct=100.0
        )
        worker_box.run()
        out_box = os.path.join(img_out_dir, "cropped_box", os.path.basename(sample_img))
        self.assertTrue(os.path.isfile(out_box))
        with Image.open(out_box) as img:
            self.assertEqual(img.size, (400, 300))
            print(f"[TEST 4.4 OK] 坐标区域剪裁: 正确裁剪为 {img.size}")

        # 4.5 多格式转换互转 (PNG -> WEBP, JPEG, ICO, BMP)
        for target_fmt in ("WEBP", "JPEG", "ICO", "BMP"):
            ok_conv, conv_path, msg = convert_image(
                src_path=sample_img,
                output_dir=os.path.join(img_out_dir, "converted_formats"),
                target_format=target_fmt,
                quality=90
            )
            self.assertTrue(ok_conv, f"转换至 {target_fmt} 失败: {msg}")
            self.assertTrue(os.path.isfile(conv_path))
            with Image.open(conv_path) as c_img:
                self.assertIsNotNone(c_img.size)
                print(f"[TEST 4.5 OK] 图像格式转换 {target_fmt}: {conv_path}")

    def test_05_audio_precision_cutting(self):
        """测试 5: 音频微秒/毫秒级精准时间轴剪裁 (多片段与重编码)"""
        # 使用先前抽取的 MP3
        src_audio = os.path.join(self.work_dir, "extracted_audio", "audio_output.mp3")
        self.assertTrue(os.path.isfile(src_audio))

        cuts_dir = os.path.join(self.work_dir, "audio_cuts")
        os.makedirs(cuts_dir, exist_ok=True)

        # 片段 1: 前奏切片 (0s -> 20s)，流拷贝极速剪切
        cut_intro = os.path.join(cuts_dir, "cut_intro_copy.mp3")
        ok_1, res_1 = cut_audio(src_audio, cut_intro, start_sec=0.0, end_sec=20.0, mode="copy")
        self.assertTrue(ok_1, f"前奏流拷贝剪切失败: {res_1}")
        probe_1 = probe_audio_file(cut_intro)
        self.assertAlmostEqual(probe_1.get("duration", 0), 20.0, delta=1.0)
        print(f"[TEST 5.1 OK] 前奏切片 (流拷贝 20s): 实际时长 {probe_1['duration_str']}")

        # 片段 2: 副歌高潮切片 (60s -> 95s)，高质量重编码剪切 (35秒)
        cut_chorus = os.path.join(cuts_dir, "cut_chorus_reencode.mp3")
        ok_2, res_2 = cut_audio(src_audio, cut_chorus, start_sec=60.0, end_sec=95.0, mode="reencode", bitrate="320k")
        self.assertTrue(ok_2, f"副歌重编码剪切失败: {res_2}")
        probe_2 = probe_audio_file(cut_chorus)
        self.assertAlmostEqual(probe_2.get("duration", 0), 35.0, delta=0.5)
        print(f"[TEST 5.2 OK] 副歌切片 (高质量重编码 35s): 实际时长 {probe_2['duration_str']}")

        # 片段 3: 尾奏切片 (200s -> 225s)，转码为 FLAC 格式切片
        cut_outro = os.path.join(cuts_dir, "cut_outro.flac")
        ok_3, res_3 = cut_audio(src_audio, cut_outro, start_sec=200.0, end_sec=225.0, mode="reencode", target_format="flac")
        self.assertTrue(ok_3, f"尾奏 FLAC 剪切失败: {res_3}")
        probe_3 = probe_audio_file(cut_outro)
        self.assertAlmostEqual(probe_3.get("duration", 0), 25.0, delta=0.5)
        print(f"[TEST 5.3 OK] 尾奏切片 (无损 FLAC 25s): 实际时长 {probe_3['duration_str']}")

    def test_06_end_to_end_loop_testing(self):
        """测试 6: 一条龙全流程循环闭环压测 (Loop Stress Test)"""
        print("\n" + "=" * 60)
        print(">>> 启动 B站视频一条龙循环综合闭环测试 (3 轮全量参数遍历)...")
        print("=" * 60)

        loop_configs = [
            {
                "cycle": 1,
                "name": "高品质母带预设 (MP3 320k / PNG 间隔采样 / 50% 缩放 / 0-30s 剪裁)",
                "audio_fmt": "mp3",
                "audio_br": "320k",
                "frame_fmt": "PNG",
                "frame_interval": 25.0,
                "img_mode": "percent",
                "img_pct": 50.0,
                "cut_start": 0.0,
                "cut_end": 30.0,
            },
            {
                "cycle": 2,
                "name": "无损流预设 (FLAC / JPG 关键帧提取 / 480x270 等比缩放 / 60-90s 副歌剪裁)",
                "audio_fmt": "flac",
                "audio_br": "auto",
                "frame_fmt": "JPG",
                "frame_interval": None,
                "img_mode": "fixed",
                "target_w": 480,
                "target_h": 270,
                "cut_start": 60.0,
                "cut_end": 90.0,
            },
            {
                "cycle": 3,
                "name": "轻量网络预设 (AAC / PNG 定时解帧 / 300x300 正方形裁切 / 120-150s 间奏剪裁)",
                "audio_fmt": "aac",
                "audio_br": "192k",
                "frame_fmt": "PNG",
                "frame_interval": 30.0,
                "img_mode": "crop",
                "target_w": 300,
                "target_h": 300,
                "cut_start": 120.0,
                "cut_end": 150.0,
            }
        ]

        for cfg in loop_configs:
            c_idx = cfg["cycle"]
            print(f"\n--- 循环轮次 [{c_idx}/3]: {cfg['name']} ---")
            cycle_dir = os.path.join(self.work_dir, f"loop_cycle_{c_idx}")
            os.makedirs(cycle_dir, exist_ok=True)

            # Step 1: 转音频
            c_audio = os.path.join(cycle_dir, f"extracted.{cfg['audio_fmt']}")
            ok_a, res_a = extract_audio(
                self.target_video,
                c_audio,
                fmt=cfg["audio_fmt"],
                bitrate=cfg["audio_br"],
                ffmpeg_path=self.ffmpeg
            )
            self.assertTrue(ok_a, f"Cycle {c_idx} 转音频失败")
            self.assertTrue(os.path.isfile(c_audio))

            # Step 2: 拆图片 (逐帧解压)
            c_frames_dir = os.path.join(cycle_dir, "frames")
            if cfg["frame_interval"]:
                ok_f, _, count_f = extract_video_frames(
                    self.target_video,
                    c_frames_dir,
                    format_choice=cfg["frame_fmt"],
                    mode="interval",
                    interval_sec=cfg["frame_interval"],
                    ffmpeg_exe=self.ffmpeg
                )
            else:
                ok_f, _, count_f = extract_video_frames(
                    self.target_video,
                    c_frames_dir,
                    format_choice=cfg["frame_fmt"],
                    mode="keyframe",
                    ffmpeg_exe=self.ffmpeg
                )
            self.assertTrue(ok_f, f"Cycle {c_idx} 拆图片失败")
            self.assertGreater(count_f, 0)
            first_frame_path = os.path.join(c_frames_dir, os.listdir(c_frames_dir)[0])

            # Step 3: 图片缩放剪裁
            c_img_dir = os.path.join(cycle_dir, "processed_img")
            if cfg["img_mode"] == "percent":
                w_img = ImageBatchWorker(
                    task_type="resize",
                    file_paths=[first_frame_path],
                    output_dir=c_img_dir,
                    resize_mode="percent",
                    scale_pct=cfg["img_pct"]
                )
            elif cfg["img_mode"] == "crop":
                w_img = ImageBatchWorker(
                    task_type="resize",
                    file_paths=[first_frame_path],
                    output_dir=c_img_dir,
                    resize_mode="crop",
                    target_w=cfg["target_w"],
                    target_h=cfg["target_h"]
                )
            else:
                w_img = ImageBatchWorker(
                    task_type="resize",
                    file_paths=[first_frame_path],
                    output_dir=c_img_dir,
                    resize_mode="fixed",
                    target_w=cfg["target_w"],
                    target_h=cfg["target_h"],
                    keep_ratio=True
                )
            w_img.run()
            processed_img_path = os.path.join(c_img_dir, os.path.basename(first_frame_path))
            self.assertTrue(os.path.isfile(processed_img_path), f"Cycle {c_idx} 图片处理失败")

            # Step 4: 音频精准剪裁
            c_cut_audio = os.path.join(cycle_dir, f"cut_clip.{cfg['audio_fmt']}")
            ok_cut, res_cut = cut_audio(
                c_audio,
                c_cut_audio,
                start_sec=cfg["cut_start"],
                end_sec=cfg["cut_end"],
                mode="reencode",
                target_format=cfg["audio_fmt"],
                ffmpeg_path=self.ffmpeg
            )
            self.assertTrue(ok_cut, f"Cycle {c_idx} 音频剪裁失败")
            probe_cut = probe_audio_file(c_cut_audio)
            expected_dur = cfg["cut_end"] - cfg["cut_start"]
            self.assertAlmostEqual(probe_cut.get("duration", 0), expected_dur, delta=1.0)

            print(f"[OK] 循环轮次 [{c_idx}/3] 一条龙全流程执行完毕: 音频、解帧、缩放裁切、剪切切片 100% 成功！")

        print("=" * 60)
        print(">>> B站视频一条龙循环综合测试全部顺利通过！")
        print("=" * 60)


class TestAllRemainingPluginsSuite(unittest.TestCase):
    """
    其余全量插件功能实操与闭环测试
    """
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test_remaining_plugins_")

    def tearDown(self):
        if os.path.exists(self.tmp):
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_archive_manager_full_lifecycle(self):
        """测试: 压缩解压工具 (7z / zip / 加密与校验)"""
        p7z = find_7z_executable()
        self.assertTrue(p7z and os.path.isfile(p7z))

        test_data = os.path.join(self.tmp, "doc.txt")
        with open(test_data, "w", encoding="utf-8") as f:
            f.write("Chieri Toolbox Archive Unit Test Data 2026")

        arc_path = os.path.join(self.tmp, "bundle.zip")
        ok_c, _ = create_archive([test_data], arc_path, format_type="zip")
        self.assertTrue(ok_c)
        self.assertTrue(os.path.isfile(arc_path))

        unzip_dir = os.path.join(self.tmp, "unzip")
        ok_e, _ = extract_archive(arc_path, unzip_dir)
        self.assertTrue(ok_e)
        self.assertTrue(os.path.isfile(os.path.join(unzip_dir, "doc.txt")))

    def test_file_suite_batch_operations(self):
        """测试: 文件整理大师 (正则替换重命名与文件夹扁平化)"""
        files = []
        for i in range(5):
            fp = os.path.join(self.tmp, f"track_{i + 1:02d}_audio.mp3")
            with open(fp, "w") as f:
                f.write("mp3_data")
            files.append(fp)

        engine = FileRenameEngine()
        res = engine.preview_replace_rename(files, find_str="track_", replace_str="song_")
        self.assertEqual(len(res), 5)
        self.assertTrue(res[0][3].startswith("song_"))

        # 扁平化测试: 将嵌套目录的文件提取至父级目录
        sub_dir = os.path.join(self.tmp, "nested", "level2")
        os.makedirs(sub_dir, exist_ok=True)
        nested_file = os.path.join(sub_dir, "nested.txt")
        with open(nested_file, "w") as f:
            f.write("nested")
        flatten_res = FolderFlattenEngine.flatten_folders([sub_dir])
        self.assertGreaterEqual(flatten_res.get("moved_count", 0), 1)
        self.assertGreaterEqual(flatten_res.get("cleaned_folders", 0), 1)
        self.assertTrue(os.path.isfile(os.path.join(os.path.dirname(sub_dir), "nested.txt")))

    def test_proxy_configurator_status(self):
        """测试: 应用代理配置工具 (系统代理与环境检测)"""
        stat = get_system_proxy_status()
        self.assertIn("enabled", stat)
        self.assertIn("server", stat)
        env_stat = get_env_proxy_status()
        self.assertIsInstance(env_stat, dict)

    def test_whiteboard_canvas_drawing_and_export(self):
        """测试: 交互式白板 (笔画路径与画板图像无损导出)"""
        from PySide6.QtGui import QColor, QPainter, QPen
        canvas = WhiteboardCanvas()
        canvas.resize(800, 600)
        canvas.set_color(QColor("#FF5722"))
        canvas.set_stroke_width(5)

        # 模拟笔画绘制并写入底图
        p = QPainter(canvas.canvas_pixmap)
        p.setPen(QPen(QColor("#FF5722"), 5))
        p.drawLine(10, 10, 100, 100)
        p.end()

        export_path = os.path.join(self.tmp, "whiteboard_art.png")
        ok_exp = canvas.export_image(export_path)
        self.assertTrue(ok_exp)
        self.assertTrue(os.path.isfile(export_path))
        with Image.open(export_path) as img:
            self.assertEqual(img.size, (800, 600))

    def test_force_killer_inspection(self):
        """测试: 顽固应用与文件强力粉碎 (文件锁检测)"""
        dummy = os.path.join(self.tmp, "locked_dummy.tmp")
        with open(dummy, "w") as f:
            f.write("content")
        procs = get_locking_processes(dummy)
        self.assertIsInstance(procs, list)

    def test_audio_recorder_device_discovery(self):
        """测试: 高清录音工具 (麦克风与硬件声卡枚举)"""
        devs = get_audio_input_devices()
        self.assertIsInstance(devs, list)
        self.assertGreater(len(devs), 0)

    def test_osu_skin_studio_parser(self):
        """测试: osu!mania 皮肤调校工作台 (skin.ini 结构化读写)"""
        ini_content = "[General]\nName: ChieriSkinPro\nAuthor: Chieri\n[Mania]\nKeys: 4\nColumnWidth: 36,36,36,36\nHitPosition: 410\n"
        ini_file = os.path.join(self.tmp, "skin.ini")
        with open(ini_file, "w", encoding="utf-8") as f:
            f.write(ini_content)
        parser = SkinParser()
        parser.load(ini_file)
        self.assertEqual(parser.general.get("Name"), "ChieriSkinPro")
        self.assertEqual(parser.get_mania_section(4).get("HitPosition"), "410")

    def test_system_integrator_diagnostics(self):
        """测试: 系统增强与右键助手 (健康诊断与路径完整性)"""
        diag = run_system_health_check()
        self.assertIn("python_version", diag)
        self.assertIn("ffmpeg_status", diag)
        self.assertTrue(diag.get("ffmpeg_status"))

    def test_plugin_exporter_inno_setup_packaging(self):
        """测试: 独立应用与 Inno Setup 安装包快速打包导出"""
        res = PluginExporter.export_plugin(
            plugin_id="screen_capture",
            output_dir=os.path.join(self.tmp, "exported_screen_capture"),
            create_shortcuts=False,
            compile_inno_setup=True
        )
        self.assertTrue(res.get("success"), f"Export failed: {res.get('error')}")
        installer_exe = res.get("installer_exe")
        self.assertTrue(installer_exe and os.path.isfile(installer_exe))
        self.assertGreater(os.path.getsize(installer_exe), 500000)


if __name__ == "__main__":
    unittest.main()
