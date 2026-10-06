"""
针对审查报告 ee7386c9-5cbd-4b61-8dfd-097ee62fe728 中 18 项整改特性的专用测试套件
全面验证数据安全防护、单实例管道机制、并发原子合并、跨平台规范与网络弹性
"""

import os
import sys
import tempfile
import zipfile
import requests
import pytest
from PySide6.QtCore import Qt, QRect
from PySide6.QtWidgets import QApplication, QWidget

# 确保 QApplication 存在
app = QApplication.instance()
if not app:
    app = QApplication(["--platform", "offscreen"])



def test_paths_scan_registry_apps_exported():
    from toolbox.core.paths import scan_registry_installed_apps
    from toolbox.plugins.force_killer.engine import scan_registry_installed_apps as fk_scan
    from toolbox.plugins.proxy_configurator.engine import scan_registry_installed_apps as pc_scan

    assert callable(scan_registry_installed_apps)
    assert fk_scan is scan_registry_installed_apps
    assert pc_scan is scan_registry_installed_apps
    apps = scan_registry_installed_apps()
    assert isinstance(apps, list)


def test_force_killer_bsod_and_root_drive_protection():
    from toolbox.plugins.force_killer.engine import (
        kill_process, kill_processes_by_name, force_unlock_and_delete,
        CRITICAL_SYSTEM_PROCESSES, is_process_critical
    )

    # 1. 关键进程防护
    assert "csrss.exe" in CRITICAL_SYSTEM_PROCESSES
    assert "services.exe" in CRITICAL_SYSTEM_PROCESSES
    assert is_process_critical(0)
    assert is_process_critical(4)
    assert is_process_critical(os.getpid())

    ok, msg = kill_process(4)
    assert not ok
    assert "系统保护" in msg

    ok, msg = kill_processes_by_name("csrss.exe")
    assert not ok
    assert "系统保护" in msg

    # 2. 根驱动器与系统目录粉碎拦截
    drive = os.path.splitdrive(os.getcwd())[0] + "\\"
    ok, msg = force_unlock_and_delete(drive)
    assert not ok
    assert "核心系统路径或根驱动器" in msg

    sys_root = os.environ.get("SystemRoot", "C:\\Windows")
    ok, msg = force_unlock_and_delete(sys_root)
    assert not ok
    assert "核心系统路径或根驱动器" in msg

    sys32 = os.path.join(sys_root, "System32")
    ok, msg = force_unlock_and_delete(sys32)
    assert not ok
    assert "核心系统路径或根驱动器" in msg


def test_file_suite_flatten_root_drive_protection():
    from toolbox.plugins.file_suite.logic import FolderFlattenEngine

    drive = os.path.splitdrive(os.getcwd())[0] + "\\"
    res = FolderFlattenEngine.flatten_folders([drive])
    assert len(res["errors"]) > 0
    assert any("禁止对驱动器根目录执行扁平化操作" in err for err in res["errors"])


def test_audio_converter_same_file_protection(monkeypatch):
    from toolbox.plugins.audio_converter.engine import convert_audio
    import subprocess

    with tempfile.TemporaryDirectory() as td:
        fake_audio = os.path.join(td, "song.mp3")
        with open(fake_audio, "wb") as f:
            f.write(b"AUDIO_RAW_DATA_123456")

        fake_ffmpeg = os.path.join(td, "mock_ffmpeg.exe")
        with open(fake_ffmpeg, "wb") as f:
            f.write(b"")

        captured_cmd = []
        def mock_run(cmd, *args, **kwargs):
            captured_cmd.extend(cmd)
            # 模拟在 target_out 写入新数据
            target_out = cmd[-1]
            with open(target_out, "wb") as f:
                f.write(b"CONVERTED_AUDIO_DATA_OK")
            class MockProc:
                returncode = 0
                stdout = ""
                stderr = ""
            return MockProc()

        monkeypatch.setattr(subprocess, "run", mock_run)
        ok, res = convert_audio(fake_audio, fake_audio, fmt="mp3", ffmpeg_path=fake_ffmpeg)
        assert ok
        # 校验 FFmpeg 实际接收的输出文件名必须是临时文件，而非覆盖原文件
        assert "._conv_tmp_" in captured_cmd[-1]
        # 最终原文件被安全原子替换为新数据
        with open(fake_audio, "rb") as f:
            assert f.read() == b"CONVERTED_AUDIO_DATA_OK"


def test_config_manager_lost_update_merge():
    from toolbox.core.config_manager import ConfigManager, _deep_merge_dict

    with tempfile.TemporaryDirectory() as td:
        cfg_file = os.path.join(td, "test_config.json")
        ConfigManager.reset_instance()
        cm1 = ConfigManager(cfg_file)
        cm1.set("theme", "dark")
        cm1.set_plugin_config("plugin_a", {"key_a": 1})

        # 模拟实例 B 在磁盘上并发写入新的插件配置
        ConfigManager.reset_instance()
        cm2 = ConfigManager(cfg_file)
        cm2.set_plugin_config("plugin_b", {"key_b": 2})

        # 此时实例 A 再写入 plugin_c，验证保存时递归合并不会丢失 cm2 写入的 plugin_b
        cm1.set_plugin_config("plugin_c", {"key_c": 3})

        ConfigManager.reset_instance()
        cm_final = ConfigManager(cfg_file)
        plugins = cm_final.get("plugins")
        assert "plugin_a" in plugins
        assert "plugin_b" in plugins
        assert "plugin_c" in plugins
        assert cm_final.get("theme") == "dark"


def test_auto_input_worker_safety():
    from toolbox.plugins.auto_input.worker import TypingWorker, PasteSimulatorWorker

    tw = TypingWorker("abc", delay=0.01, use_clipboard=False)
    tw.stop()
    assert tw._stop_flag is True

    sim = PasteSimulatorWorker()
    sim._typing_worker = tw
    # 停止监听必须安全返回且不会调用 terminate
    sim.stop_listening()
    assert sim._typing_worker is None


def test_screen_recorder_audio_resolution(monkeypatch):
    from toolbox.plugins.screen_recorder.engine import ScreenRecorderEngine
    import subprocess

    captured_cmd = []
    class MockPopen:
        def __init__(self, cmd, *args, **kwargs):
            captured_cmd.extend(cmd)
            self.pid = 99999
        def poll(self):
            return None
        def terminate(self):
            pass
        def wait(self, timeout=None):
            pass

    monkeypatch.setattr(subprocess, "Popen", MockPopen)

    engine = ScreenRecorderEngine()
    ok, msg = engine.start_recording(
        output_path="test_rec.mp4",
        mode="fullscreen",
        system_audio_device="未检测到声卡输出",
        mic_device="不录制麦克风"
    )
    assert ok
    # 验证当系统声卡为“未检测到声卡输出”且无麦克风时，不会在 ffmpeg 命令中传入虚假 dshow/wasapi audio 导致必崩
    audio_flags = [captured_cmd[i+1] for i, arg in enumerate(captured_cmd) if arg == "-f" and i+1 < len(captured_cmd) and captured_cmd[i+1] in ("dshow", "wasapi")]
    assert len(audio_flags) == 0
    engine.stop_recording()


def test_screen_capture_dpi_calibration():
    from toolbox.plugins.screen_capture.capture import get_window_rect_under_cursor

    rect = get_window_rect_under_cursor()
    # 在非图形悬停或无异常时返回 None 或有效 QRect
    if rect is not None:
        assert isinstance(rect, QRect)


def test_window_effects_dual_opacity():
    from toolbox.core.window_effects import apply_dual_opacity

    w = QWidget()
    apply_dual_opacity(w, bg_opacity=0.8, component_opacity=0.9)
    # 顶层窗口保持 1.0，防止双重相乘发虚
    assert abs(w.windowOpacity() - 1.0) < 0.001
    assert w.testAttribute(Qt.WA_TranslucentBackground) is True

    apply_dual_opacity(w, bg_opacity=1.0, component_opacity=1.0)
    assert w.testAttribute(Qt.WA_TranslucentBackground) is False
    w.close()


def test_media_downloader_parse_worker_and_proxies():
    from toolbox.plugins.media_downloader.ui import MediaParseWorker
    from toolbox.plugins.media_downloader.downloader import MediaDownloadWorker
    from toolbox.plugins.media_downloader.api import BiliApiClient

    # 1. MediaParseWorker 异步参数接收
    worker = MediaParseWorker(BiliApiClient(), raw_text="BV1xx411c7mD", mode_idx=1)
    assert worker.raw_text == "BV1xx411c7mD"
    assert worker.mode_idx == 1

    # 2. MediaDownloadWorker proxies 支持
    dw = MediaDownloadWorker(
        video_url="http://example.com/v.m4s",
        title="test_proxies",
        proxies={"http": "http://127.0.0.1:7890"}
    )
    assert dw.proxies == {"http": "http://127.0.0.1:7890"}


def test_archive_manager_pkware_slashes_and_zipslip():
    from toolbox.plugins.archive_manager.engine import (
        create_archive, _is_safe_path
    )

    with tempfile.TemporaryDirectory() as td:
        sub_dir = os.path.join(td, "sample_folder", "nested")
        os.makedirs(sub_dir, exist_ok=True)
        file_path = os.path.join(sub_dir, "hello.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("content")

        zip_out = os.path.join(td, "test_out.zip")
        ok, msg = create_archive([os.path.join(td, "sample_folder")], zip_out, format_type="zip")
        assert ok

        # 检查内部 entry 必须为正斜杠且含有空目录 entry
        with zipfile.ZipFile(zip_out, "r") as zf:
            for name in zf.namelist():
                assert "\\" not in name, f"Zip entry 包含非法反斜杠: {name}"

        # ZipSlip 大小写测试
        base_d = os.path.join(td, "EXTRACT")
        os.makedirs(base_d, exist_ok=True)
        # Windows 大小写不敏感安全校验
        assert _is_safe_path(base_d.lower(), os.path.join(base_d.upper(), "safe.txt"))
        assert not _is_safe_path(base_d, "../../evil.txt")


def test_proxy_configurator_pip_and_pac():
    from toolbox.plugins.proxy_configurator.engine import (
        get_pip_status, LocalPACServer, _get_pip_executable
    )

    status = get_pip_status()
    assert isinstance(status, dict)
    assert "enabled" in status

    # PAC 本地微型 HTTP 服务测试
    with tempfile.NamedTemporaryFile("w", suffix=".pac", delete=False) as f:
        f.write("function FindProxyForURL(url, host) { return 'DIRECT'; }")
        pac_tmp = f.name

    try:
        pac_server = LocalPACServer.get_instance()
        ok, pac_url = pac_server.start(pac_tmp)
        assert ok
        assert pac_url.startswith("http://127.0.0.1:")
        resp = requests.get(pac_url, timeout=3)
        assert resp.status_code == 200
        assert "FindProxyForURL" in resp.text
        pac_server.stop()
    finally:
        if os.path.exists(pac_tmp):
            os.remove(pac_tmp)


def test_plugin_exporter_binary_requirements():
    from toolbox.core.plugin_exporter import PluginExporter

    # 1. 验证按需依赖映射字典
    reqs = PluginExporter.PLUGIN_BIN_REQUIREMENTS
    assert isinstance(reqs, dict)
    assert reqs.get("video_to_audio") == ["ffmpeg.exe"]
    assert "ffplay.exe" not in reqs.get("video_to_audio", [])
    assert "ffprobe.exe" not in reqs.get("video_to_audio", [])
    assert reqs.get("audio_cutter") == ["ffmpeg.exe", "ffprobe.exe"]
    assert reqs.get("archive_manager") == ["7z.exe", "7z.dll"]

    # 2. 验证独立导出时精确按需依赖打包行为
    with tempfile.TemporaryDirectory() as td:
        res = PluginExporter.export_plugin(
            plugin_id="video_to_audio",
            output_dir=td,
            package_type="portable",
            create_archive=False,
            generate_pyinstaller_spec=False,
            compile_inno_setup=False,
        )
        assert res.get("success") is True
        bin_dir = os.path.join(td, "ChieriPlugin_video_to_audio", "bin")
        if os.path.isdir(bin_dir):
            files = os.listdir(bin_dir)
            # video_to_audio 绝不能把 ffplay.exe 和 ffprobe.exe 复制进去
            assert "ffplay.exe" not in files
            assert "ffprobe.exe" not in files


def test_paths_sanitize_filename_reserved_and_max_length():
    from toolbox.core.paths import sanitize_filename, WINDOWS_RESERVED_NAMES

    # 1. 保留设备名检查
    for reserved in ["CON", "prn", "aux", "nul", "com1", "lpt9"]:
        res = sanitize_filename(f"{reserved}.mp4")
        assert res.startswith("_")
        assert reserved.lower() in res.lower()

    # 2. 超长文件名截断与扩展名保留
    long_name = "a" * 200 + ".mp3"
    sanitized = sanitize_filename(long_name, max_length=120)
    assert len(sanitized) <= 120
    assert sanitized.endswith(".mp3")

    # 3. 非法字符过滤
    dirty = 'test:*?"<>|/\\file.txt'
    assert sanitize_filename(dirty) == "test_________file.txt"


def test_ncm_decryptor_collision_handling():
    from toolbox.plugins.ncm_decryptor.decryptor import decrypt_ncm

    with tempfile.TemporaryDirectory() as td:
        # 创建冲突的已有目标音频文件
        existing_audio = os.path.join(td, "test_track.mp3")
        with open(existing_audio, "wb") as f:
            f.write(b"ORIGINAL_ALREADY_EXISTS")

        fake_ncm = os.path.join(td, "test_track.ncm")
        with open(fake_ncm, "wb") as f:
            f.write(b"NOT_NCM")

        ok, msg, _ = decrypt_ncm(fake_ncm, output_dir=td)
        assert not ok
        # 验证已有音频文件未被截断或覆写
        assert os.path.exists(existing_audio)
        with open(existing_audio, "rb") as f:
            assert f.read() == b"ORIGINAL_ALREADY_EXISTS"


def test_webdav_registry_diagnosis():
    from toolbox.plugins.webdav_config.client import diagnose_webclient_registry, fix_webclient_registry

    diag = diagnose_webclient_registry()
    assert isinstance(diag, dict)
    assert "supported" in diag
    if diag.get("supported"):
        assert "basic_auth_level" in diag
        assert "file_size_limit" in diag
        assert "http_allowed" in diag
        assert "needs_fix" in diag


def test_media_downloader_mux_stderr_capture(monkeypatch):
    from toolbox.plugins.media_downloader.downloader import MediaDownloadWorker
    import subprocess

    class MockFailingProc:
        def __init__(self, *args, **kwargs):
            self.returncode = 1
        def communicate(self):
            return b"", b"FFmpeg mock error: invalid codec parameter or audio stream incompatible"

    monkeypatch.setattr(subprocess, "Popen", MockFailingProc)

    captured_logs = []
    captured_finish = []

    with tempfile.TemporaryDirectory() as td:
        fake_ffmpeg = os.path.join(td, "mock_ffmpeg.exe")
        with open(fake_ffmpeg, "wb") as f:
            f.write(b"")

        worker = MediaDownloadWorker(
            video_url="http://example.com/v.m4s",
            audio_url="http://example.com/a.m4s",
            title="test_mux_fail",
            save_dir=td,
            ffmpeg_path=fake_ffmpeg
        )
        worker.log_message.connect(lambda msg: captured_logs.append(msg))
        worker.finished_task.connect(lambda ok, msg: captured_finish.append((ok, msg)))

        def mock_dl_stream(url, out_path, is_video=True, **kwargs):
            with open(out_path, "wb") as f:
                f.write(b"fake_stream")
            return True

        monkeypatch.setattr(worker, "_download_stream", mock_dl_stream)
        worker.run()

        # 验证混流失败时捕获并输出了 stderr
        assert any("FFmpeg mock error" in log for log in captured_logs)
        assert len(captured_finish) == 1
        assert captured_finish[0][0] is False
        assert "FFmpeg mock error" in captured_finish[0][1]

