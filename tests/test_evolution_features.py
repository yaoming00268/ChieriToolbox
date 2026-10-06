"""
千绘莉工具箱 (Chieri Toolbox) - 进化特性全面自动化验证测试套件
涵盖：
1. ModelManager 动态模型下载与镜像调度
2. SuperResolution 图像超分辨率重构与 Alpha 通道保护
3. LocalCloud 局域网服务 (HTTP / UDP 发现 / 剪贴板 / Chieri Drop)
4. DanmakuToAss 弹幕防碰撞与 ASS 格式化转换
5. Multi-Platform Music Decryptor (QMC, KGM, KWM, NCM)
6. ACG Password Memory Book & 归档密码快速试探匹配
"""

import io
import json
import os
import shutil
import struct
import tempfile
import threading
import time
import zipfile
import pytest
from PIL import Image

# 1. ModelManager
from toolbox.core.model_manager import ModelManager, MODEL_REGISTRY

# 2. SuperResolution
from toolbox.plugins.image_master.upscale_engine import upscale_image_file

# 3. LocalCloud
from toolbox.core.local_cloud import ChieriLocalCloudService

# 4. DanmakuToAss
from toolbox.plugins.media_downloader.danmaku_to_ass import DanmakuConverter, convert_danmaku_xml_to_ass

# 5. MultiPlatform Decryptor
from toolbox.plugins.ncm_decryptor.decryptor import (
    decrypt_qmc, decrypt_kgm, decrypt_kwm, decrypt_music_file,
    scan_music_files, ENCRYPTED_AUDIO_EXTENSIONS
)

# 6. Archive Password Book
from toolbox.plugins.archive_manager.password_book import (
    AcgPasswordBook, check_archive_encryption_status,
    test_single_password, auto_match_archive_password
)
from toolbox.plugins.archive_manager.engine import create_archive, extract_archive


# ============================================================================
# 1. ModelManager Tests
# ============================================================================
def test_model_manager_registry_and_urls():
    mgr = ModelManager()
    models = mgr.get_available_models()
    assert "real-cugan" in models
    assert "realesr-animevideov3" in models
    assert "waifu2x-cunet" in models

    # Check mirror resolution
    cugan_info = mgr.get_model_info("real-cugan")
    assert cugan_info is not None
    assert "mirrors" in cugan_info
    assert "fast_china" in cugan_info["mirrors"]
    assert "hf_mirror" in cugan_info["mirrors"]

    # Verify model presence detection
    assert mgr.is_model_ready("non_existent_model") is False


# ============================================================================
# 2. SuperResolution Tests
# ============================================================================
def test_super_resolution_rgba_preservation():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a small 32x32 RGBA test image with transparency
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        # Draw a semi-transparent red circle/box
        for x in range(8, 24):
            for y in range(8, 24):
                img.putpixel((x, y), (255, 100, 150, 200))

        src_path = os.path.join(tmpdir, "test_input.png")
        out_path = os.path.join(tmpdir, "test_output.png")
        img.save(src_path, format="PNG")

        ok, msg = upscale_image_file(
            input_path=src_path,
            output_path=out_path,
            scale=2,
            tile_size=16,
            tile_pad=4
        )
        assert ok is True
        assert os.path.isfile(out_path)

        out_img = Image.open(out_path)
        assert out_img.size == (64, 64)
        assert out_img.mode == "RGBA"
        # Check that transparent border is still transparent
        corner_pixel = out_img.getpixel((0, 0))
        assert corner_pixel[3] == 0
        # Check center is opaque/semi-opaque
        center_pixel = out_img.getpixel((32, 32))
        assert center_pixel[3] > 100


# ============================================================================
# 3. LocalCloud HTTP & Service Tests
# ============================================================================
def test_local_cloud_service_endpoints():
    import urllib.request
    import urllib.error

    service = ChieriLocalCloudService(http_port=18765, udp_port=33333)
    service.start()
    time.sleep(0.4)

    try:
        # 1. Ping
        req = urllib.request.urlopen("http://127.0.0.1:18765/api/ping", timeout=3)
        assert req.status == 200
        data = json.loads(req.read().decode("utf-8"))
        assert data.get("status") == "ok"
        assert "hostname" in data

        # 2. Models list
        req = urllib.request.urlopen("http://127.0.0.1:18765/api/models", timeout=3)
        assert req.status == 200
        data = json.loads(req.read().decode("utf-8"))
        assert "models" in data
        assert len(data["models"]) > 0

        # 3. Clipboard sync
        post_data = json.dumps({"text": "Chieri Cross Device Sync Test"}).encode("utf-8")
        post_req = urllib.request.Request(
            "http://127.0.0.1:18765/api/clipboard",
            data=post_data,
            headers={"Content-Type": "application/json"}
        )
        req = urllib.request.urlopen(post_req, timeout=3)
        assert req.status == 200
        res = json.loads(req.read().decode("utf-8"))
        assert res.get("status") == "ok"

        # 4. Upscale endpoint
        img = Image.new("RGB", (16, 16), (255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw_img = buf.getvalue()

        up_req = urllib.request.Request(
            "http://127.0.0.1:18765/api/upscale",
            data=raw_img,
            headers={"Content-Type": "image/png", "X-Scale": "2"}
        )
        req = urllib.request.urlopen(up_req, timeout=5)
        assert req.status == 200
        out_buf = io.BytesIO(req.read())
        res_img = Image.open(out_buf)
        assert res_img.size == (32, 32)

    finally:
        service.stop()


# ============================================================================
# 4. DanmakuToAss Converter Tests
# ============================================================================
def test_danmaku_to_ass_conversion():
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <i>
        <chatserver>chat.bilibili.com</chatserver>
        <chatid>12345678</chatid>
        <mission>0</mission>
        <d p="1.50000,1,25,16777215,1600000000,0,ffffffff,123456">第一条滚动弹幕！</d>
        <d p="1.80000,5,25,16711680,1600000001,0,ffffffff,123457">第二条顶部弹幕！</d>
        <d p="2.10000,4,25,65280,1600000002,0,ffffffff,123458">第三条底部弹幕！</d>
    </i>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        xml_path = os.path.join(tmpdir, "danmaku.xml")
        ass_path = os.path.join(tmpdir, "danmaku.ass")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(sample_xml)

        ok, msg = convert_danmaku_xml_to_ass(xml_path, ass_path, title="Danmaku Test")
        assert ok is True
        assert os.path.isfile(ass_path)

        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "[Script Info]" in content
        assert "Title: Danmaku Test" in content
        assert "[V4+ Styles]" in content
        assert "[Events]" in content
        assert "第一条滚动弹幕！" in content
        assert "第二条顶部弹幕！" in content
        assert "第三条底部弹幕！" in content
        assert "\\move" in content
        assert "\\an8" in content
        assert "\\an2" in content


# ============================================================================
# 5. Multi-Platform Music Decryption Tests
# ============================================================================
def test_qmc_decryption():
    with tempfile.TemporaryDirectory() as tmpdir:
        qmc_path = os.path.join(tmpdir, "test.qmc0")
        out_dir = os.path.join(tmpdir, "out")

        # Create simulated QMC encrypted payload
        # Standard QMC uses QMC_STATIC_MAP XOR
        from toolbox.plugins.ncm_decryptor.decryptor import QMC_STATIC_MAP
        raw_mp3_header = b"\xFF\xFB\x90\x44" + b"\x00" * 256
        enc_bytes = bytearray()
        for i, b in enumerate(raw_mp3_header):
            enc_bytes.append(b ^ QMC_STATIC_MAP[i % len(QMC_STATIC_MAP)])

        with open(qmc_path, "wb") as f:
            f.write(enc_bytes)

        ok, out_file, meta = decrypt_qmc(qmc_path, out_dir)
        assert ok is True
        assert os.path.isfile(out_file)
        assert out_file.endswith(".mp3")
        with open(out_file, "rb") as f:
            head = f.read(4)
        assert head == b"\xFF\xFB\x90\x44"


def test_kgm_decryption():
    with tempfile.TemporaryDirectory() as tmpdir:
        kgm_path = os.path.join(tmpdir, "test.kgm")
        out_dir = os.path.join(tmpdir, "out")

        # Create simulated KGM encrypted payload (magic "\x7c\xd5\x32\xeb")
        raw_flac_header = b"fLaC" + b"\x00" * 256
        kgm_header = b"\x7c\xd5\x32\xeb" + (b"\x00" * 56)  # 60 bytes header
        enc_bytes = bytearray(kgm_header)
        for i, b in enumerate(raw_flac_header):
            enc_bytes.append(b ^ 0x66)

        with open(kgm_path, "wb") as f:
            f.write(enc_bytes)

        ok, out_file, meta = decrypt_kgm(kgm_path, out_dir)
        assert ok is True
        assert os.path.isfile(out_file)
        assert out_file.endswith(".flac")
        with open(out_file, "rb") as f:
            head = f.read(4)
        assert head == b"fLaC"


def test_kwm_decryption():
    with tempfile.TemporaryDirectory() as tmpdir:
        kwm_path = os.path.join(tmpdir, "test.kwm")
        out_dir = os.path.join(tmpdir, "out")

        # Create simulated KWM encrypted payload
        raw_mp3_header = b"\xFF\xFB\x90\x44" + b"\x00" * 256
        kwm_header = b"yeelion" + b"\x00" * 25
        enc_bytes = bytearray(kwm_header)
        mask = b"kuwo_music_2016"
        for i, b in enumerate(raw_mp3_header):
            enc_bytes.append(b ^ mask[i % len(mask)])

        with open(kwm_path, "wb") as f:
            f.write(enc_bytes)

        ok, out_file, meta = decrypt_kwm(kwm_path, out_dir)
        assert ok is True
        assert os.path.isfile(out_file)
        assert out_file.endswith(".mp3")
        with open(out_file, "rb") as f:
            head = f.read(4)
        assert head == b"\xFF\xFB\x90\x44"


# ============================================================================
# 6. ACG Password Memory Book & Archive Auto-Match Tests
# ============================================================================
def test_acg_password_book_crud():
    book = AcgPasswordBook()
    # Add custom password
    assert book.add_password("my_custom_gal_pwd") is True
    assert "my_custom_gal_pwd" in book.get_custom_passwords()
    assert book.get_all_passwords()[0] == "my_custom_gal_pwd"

    # Remove custom password
    assert book.remove_password("my_custom_gal_pwd") is True
    assert "my_custom_gal_pwd" not in book.get_custom_passwords()


def test_archive_password_auto_matching():
    with tempfile.TemporaryDirectory() as tmpdir:
        src_file = os.path.join(tmpdir, "secret.txt")
        with open(src_file, "w", encoding="utf-8") as f:
            f.write("Secret Anime Asset Content!")

        # Create 7z encrypted with pre-seeded password '初音'
        arch_7z = os.path.join(tmpdir, "secret.7z")
        ok, msg = create_archive([src_file], arch_7z, format_type="7z", password="初音")
        assert ok is True

        # Test encryption status check
        is_enc, is_hdr, _ = check_archive_encryption_status(arch_7z)
        assert is_enc is True

        # Test single password verification
        assert test_single_password(arch_7z, "wrong_password", header_encrypted=is_hdr) is False
        assert test_single_password(arch_7z, "初音", header_encrypted=is_hdr) is True

        # Test full auto matching
        matched = auto_match_archive_password(arch_7z)
        assert matched == "初音"

        # Test extraction using matched password
        extract_out = os.path.join(tmpdir, "extracted")
        ok, msg = extract_archive(arch_7z, extract_out, password=matched)
        assert ok is True
        assert os.path.isfile(os.path.join(extract_out, "secret.txt"))
