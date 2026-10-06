"""
网易云音乐 NCM 格式解密核心引擎
基于标准 NCM 逆向规范，纯 Python 高性能还原为 MP3/FLAC 并写入 ID3/FLAC 标签与高清封面。
"""

import base64
import json
import os
import re
import struct
from typing import Dict, List, Optional, Tuple
from PySide6.QtCore import QThread, Signal

from Crypto.Cipher import AES

CORE_KEY = bytes.fromhex("687A4852416D736F356B496E62617857")
META_KEY = bytes.fromhex("2331346C6A6B5F215C5D2630553C2728")


def sanitize_filename(name: str) -> str:
    """清理 Windows 文件名非法字符"""
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


def pkcs7_unpad(data: bytes) -> bytes:
    """PKCS7 去除填充"""
    if not data:
        return data
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        return data
    return data[:-pad_len]


ENCRYPTED_AUDIO_EXTENSIONS = (
    ".ncm", ".qmc0", ".qmc3", ".qmcflac", ".qmcogg",
    ".mflac", ".mgg", ".kgm", ".vpr", ".kwm"
)

QMC_STATIC_MAP = [
    0x77, 0x48, 0x32, 0x73, 0xDE, 0xF2, 0xC0, 0xC8, 0x95, 0xEC, 0x30, 0xB2,
    0x51, 0xC3, 0xE1, 0xA0, 0x9E, 0xE6, 0x9D, 0xCF, 0xFA, 0x7F, 0x14, 0xD1,
    0xCE, 0xB8, 0xDC, 0xC3, 0x4A, 0x67, 0x93, 0xD6, 0x28, 0xB2, 0x91, 0x70,
    0xF7, 0xD6, 0x88, 0xB4, 0xF7, 0x69, 0xB6, 0x33, 0x44, 0xCE, 0x76, 0x64,
    0x76, 0x1D, 0x49, 0xB8, 0x36, 0x44, 0x96, 0xDF, 0xF8, 0x4C, 0x37, 0x05,
    0xC9, 0xB7, 0x98, 0x2B, 0x3C, 0x6B, 0x72, 0xA1, 0xEE, 0x84, 0x4F, 0xDF,
    0x6E, 0xBF, 0x18, 0x84, 0x49, 0x42, 0x74, 0x40, 0x29, 0x43, 0xEE, 0x80,
    0x29, 0x07, 0x2C, 0x2A, 0xC5, 0x67, 0x79, 0xA2, 0x2A, 0x70, 0xF9, 0xB3,
    0x79, 0x36, 0x94, 0x7C, 0xD9, 0x04, 0xF1, 0x12, 0x8C, 0xB3, 0x63, 0xCE,
    0x46, 0x47, 0xC2, 0x5D, 0xC7, 0x5D, 0x58, 0x39, 0x89, 0xFB, 0x3C, 0x44,
    0x76, 0x1D, 0x49, 0xB8, 0x36, 0x44, 0x96, 0xDF, 0xF8, 0x4C, 0x37, 0x05,
    0xC9, 0xB7, 0x98, 0x2B, 0x3C, 0x6B, 0x72, 0xA1, 0xEE, 0x84, 0x4F, 0xDF,
    0x6E, 0xBF, 0x18, 0x84, 0x49, 0x42, 0x74, 0x40, 0x29, 0x43, 0xEE, 0x80,
    0x29, 0x07, 0x2C, 0x2A, 0xC5, 0x67, 0x79, 0xA2, 0x2A, 0x70, 0xF9, 0xB3,
    0x79, 0x36, 0x94, 0x7C, 0xD9, 0x04, 0xF1, 0x12, 0x8C, 0xB3, 0x63, 0xCE,
    0x46, 0x47, 0xC2, 0x5D, 0xC7, 0x5D, 0x58, 0x39, 0x89, 0xFB, 0x3C, 0x44
]


def _is_valid_audio_header(header: bytes) -> bool:
    """快速嗅探字节头是否为有效主流音频编码特征"""
    if header.startswith(b"fLaC") or header.startswith(b"ID3") or header.startswith(b"OggS"):
        return True
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return True
    if len(header) >= 8 and (header.startswith(b"\x00\x00\x00") or header[4:8] == b"ftyp"):
        return True
    return False


def decrypt_qmc(src_path: str, output_dir: Optional[str] = None) -> Tuple[bool, str, Dict]:
    """QQ 音乐 QMC 格式离线解密 (自适应 QMCv1 / QMCv2 变换矩阵)"""
    if not os.path.isfile(src_path):
        return False, f"文件不存在: {src_path}", {}
    try:
        with open(src_path, "rb") as f:
            data = bytearray(f.read())
        if len(data) < 16:
            return False, "QMC 文件体积过小或损坏", {}

        map_len = len(QMC_STATIC_MAP)
        # 测试算法变体: QMCv1 与 QMCv2
        peek_v1 = bytes(data[i] ^ QMC_STATIC_MAP[i % map_len] for i in range(min(16, len(data))))
        peek_v2 = bytes(data[i] ^ QMC_STATIC_MAP[(i * i + 80923) % map_len] for i in range(min(16, len(data))))

        use_v2 = _is_valid_audio_header(peek_v2) and not _is_valid_audio_header(peek_v1)
        out_buf = bytearray(len(data))
        if use_v2:
            for i in range(len(data)):
                out_buf[i] = data[i] ^ QMC_STATIC_MAP[(i * i + 80923) % map_len]
        else:
            for i in range(len(data)):
                out_buf[i] = data[i] ^ QMC_STATIC_MAP[i % map_len]

        ext = ".mp3"
        if out_buf.startswith(b"fLaC"):
            ext = ".flac"
        elif out_buf.startswith(b"OggS"):
            ext = ".ogg"
        elif out_buf.startswith(b"\x00\x00\x00\x20") or out_buf[4:8] == b"ftyp":
            ext = ".m4a"
        elif src_path.lower().endswith((".qmcflac", ".mflac")):
            ext = ".flac"
        elif src_path.lower().endswith((".qmcogg", ".mgg")):
            ext = ".ogg"

        base_name = os.path.splitext(os.path.basename(src_path))[0]
        out_d = output_dir if output_dir else os.path.dirname(src_path)
        os.makedirs(out_d, exist_ok=True)
        out_path = os.path.join(out_d, f"{base_name}{ext}")

        with open(out_path, "wb") as f_out:
            f_out.write(out_buf)

        meta = {"musicName": base_name, "format": ext.lstrip(".")}
        return True, out_path, meta
    except Exception as e:
        return False, f"QMC 解密异常: {e}", {}


def decrypt_kgm(src_path: str, output_dir: Optional[str] = None) -> Tuple[bool, str, Dict]:
    """酷狗音乐 KGM / VPR 格式离线解密"""
    if not os.path.isfile(src_path):
        return False, f"文件不存在: {src_path}", {}
    try:
        with open(src_path, "rb") as f:
            data = bytearray(f.read())
        if len(data) < 0x3c:
            return False, "KGM 文件头损坏或过短", {}

        header_len = struct.unpack("<I", data[0x10:0x14])[0] if len(data) > 0x14 else 0x3c
        if header_len < 0x2c or header_len >= len(data):
            header_len = 0x3c

        key = data[0x2c:0x3c] if len(data) >= 0x3c else b"kugoumusicmaskkey"
        audio_data = data[header_len:]
        out_buf = bytearray(len(audio_data))

        # 测试简单掩码与扩展掩码
        peek_xor = bytes(b ^ 0x66 for b in audio_data[:16])
        if _is_valid_audio_header(peek_xor):
            for i in range(len(audio_data)):
                out_buf[i] = audio_data[i] ^ 0x66
        else:
            k_len = len(key)
            for i in range(len(audio_data)):
                mask = key[i % k_len] ^ (i & 0xFF)
                b = audio_data[i] ^ mask
                b ^= (b >> 4)
                out_buf[i] = b

        ext = ".mp3"
        if out_buf.startswith(b"fLaC"):
            ext = ".flac"
        elif out_buf.startswith(b"OggS"):
            ext = ".ogg"
        elif src_path.lower().endswith(".vpr"):
            ext = ".mp3"

        base_name = os.path.splitext(os.path.basename(src_path))[0]
        out_d = output_dir if output_dir else os.path.dirname(src_path)
        os.makedirs(out_d, exist_ok=True)
        out_path = os.path.join(out_d, f"{base_name}{ext}")

        with open(out_path, "wb") as f_out:
            f_out.write(out_buf)

        meta = {"musicName": base_name, "format": ext.lstrip(".")}
        return True, out_path, meta
    except Exception as e:
        return False, f"KGM 解密异常: {e}", {}


def decrypt_kwm(src_path: str, output_dir: Optional[str] = None) -> Tuple[bool, str, Dict]:
    """酷我音乐 KWM 格式离线解密"""
    if not os.path.isfile(src_path):
        return False, f"文件不存在: {src_path}", {}
    try:
        with open(src_path, "rb") as f:
            data = bytearray(f.read())
        if len(data) < 32:
            return False, "KWM 文件过短", {}

        candidate_headers = [32, 1024, 0x18]
        candidate_masks = [b"kuwo_music_2016", b"yeelion-kuwo-tME", b"kuwo"]
        chosen_hl = 32
        chosen_mask = b"kuwo_music_2016"
        matched = False

        for hl in candidate_headers:
            if len(data) <= hl:
                continue
            for m in candidate_masks:
                peek = bytes(data[hl + i] ^ m[i % len(m)] for i in range(min(16, len(data) - hl)))
                if _is_valid_audio_header(peek):
                    chosen_hl = hl
                    chosen_mask = m
                    matched = True
                    break
            if matched:
                break

        audio_data = data[chosen_hl:]
        out_buf = bytearray(len(audio_data))
        m_len = len(chosen_mask)
        for i in range(len(audio_data)):
            out_buf[i] = audio_data[i] ^ chosen_mask[i % m_len]

        ext = ".flac" if out_buf.startswith(b"fLaC") else ".mp3"
        base_name = os.path.splitext(os.path.basename(src_path))[0]
        out_d = output_dir if output_dir else os.path.dirname(src_path)
        os.makedirs(out_d, exist_ok=True)
        out_path = os.path.join(out_d, f"{base_name}{ext}")

        with open(out_path, "wb") as f_out:
            f_out.write(out_buf)

        meta = {"musicName": base_name, "format": ext.lstrip(".")}
        return True, out_path, meta
    except Exception as e:
        return False, f"KWM 解密异常: {e}", {}


def scan_ncm_files(paths: List[str]) -> List[str]:
    """扫描指定路径集合中的所有加密音乐文件 (.ncm, .qmc, .kgm, .kwm 等)"""
    result = []
    for p in paths:
        if os.path.isfile(p):
            if any(p.lower().endswith(ext) for ext in ENCRYPTED_AUDIO_EXTENSIONS):
                norm = os.path.normpath(p)
                if norm not in result:
                    result.append(norm)
        elif os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    if any(f.lower().endswith(ext) for ext in ENCRYPTED_AUDIO_EXTENSIONS):
                        norm = os.path.normpath(os.path.join(root, f))
                        if norm not in result:
                            result.append(norm)
    return result


scan_encrypted_audio_files = scan_ncm_files
scan_music_files = scan_ncm_files


def decrypt_ncm(
    ncm_path: str,
    output_dir: Optional[str] = None,
    embed_tags: bool = True
) -> Tuple[bool, str, Dict]:
    """
    解密单个加密音乐文件 (支持网易云 NCM、QQ音乐 QMC、酷狗 KGM、酷我 KWM 等)
    :param ncm_path: 加密音乐文件路径
    :param output_dir: 输出目录，若为 None 则保存在源文件同级目录
    :param embed_tags: 是否将解析到的歌曲名、歌手、专辑及封面写回音频
    :return: (是否成功, 输出文件路径或错误信息, 元数据字典)
    """
    if not os.path.isfile(ncm_path):
        return False, f"文件不存在: {ncm_path}", {}

    ext = os.path.splitext(ncm_path)[1].lower()
    if ext in (".qmc0", ".qmc3", ".qmcflac", ".qmcogg", ".mflac", ".mgg"):
        return decrypt_qmc(ncm_path, output_dir)
    elif ext in (".kgm", ".vpr"):
        return decrypt_kgm(ncm_path, output_dir)
    elif ext in (".kwm",):
        return decrypt_kwm(ncm_path, output_dir)

    try:
        with open(ncm_path, "rb") as f:
            header = f.read(8)
            if header != b"CTENFDAM":
                # 若文件头非 NCM，尝试依据特征或扩展名做二次探测
                if ext in (".qmc0", ".qmc3", ".qmcflac", ".qmcogg", ".mflac", ".mgg"):
                    return decrypt_qmc(ncm_path, output_dir)
                if ext in (".kgm", ".vpr"):
                    return decrypt_kgm(ncm_path, output_dir)
                if ext in (".kwm",):
                    return decrypt_kwm(ncm_path, output_dir)
                return False, "非法加密文件头，文件可能已损坏或非支持的加密音乐格式。", {}

            # 2 字节保留空隙
            f.seek(2, 1)

            # 1. 解密 RC4 密钥
            key_len_bytes = f.read(4)
            if len(key_len_bytes) < 4:
                return False, "读取密钥长度失败。", {}
            key_len = struct.unpack("<I", key_len_bytes)[0]
            raw_key_data = f.read(key_len)
            xored_key = bytes([b ^ 0x64 for b in raw_key_data])
            decrypted_key = pkcs7_unpad(AES.new(CORE_KEY, AES.MODE_ECB).decrypt(xored_key))

            if not decrypted_key.startswith(b"neteasecloudmusic"):
                return False, "RC4 密钥验证头异常。", {}
            rc4_key = decrypted_key[17:]

            # 2. 解密歌曲元数据
            meta_len_bytes = f.read(4)
            if len(meta_len_bytes) < 4:
                return False, "读取元数据长度失败。", {}
            meta_len = struct.unpack("<I", meta_len_bytes)[0]
            meta_json = {}
            if meta_len > 0:
                raw_meta_data = f.read(meta_len)
                xored_meta = bytes([b ^ 0x63 for b in raw_meta_data])
                if xored_meta.startswith(b"163 key(Don't modify):"):
                    b64_content = xored_meta[22:]
                    try:
                        encrypted_meta = base64.b64decode(b64_content)
                        decrypted_meta_bytes = pkcs7_unpad(AES.new(META_KEY, AES.MODE_ECB).decrypt(encrypted_meta))
                        if decrypted_meta_bytes.startswith(b"music:"):
                            meta_str = decrypted_meta_bytes[6:].decode("utf-8", errors="ignore")
                            meta_json = json.loads(meta_str)
                    except Exception:
                        pass

            # 5. 构建 S-Box
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

            # 3 & 4. 读取内嵌专辑封面并定位真实音频流起始点
            post_meta_pos = f.tell()
            cover_data = b""
            audio_start_pos = None

            def _is_audio_header(b: bytes) -> bool:
                if len(b) < 2:
                    return False
                if b.startswith(b"fLaC") or b.startswith(b"ID3"):
                    return True
                if b[0] == 0xFF and (b[1] & 0xE0) == 0xE0:
                    return True
                return False

            # 尝试优先解析标准 NCM 结构 (5字节 CRC/gap + 4字节 cover_frame_len + 4字节 image_len)
            try:
                f.seek(post_meta_pos)
                f.seek(5, 1)
                frame_len_bytes = f.read(4)
                img_len_bytes = f.read(4)
                if len(frame_len_bytes) == 4 and len(img_len_bytes) == 4:
                    cover_frame_len = struct.unpack("<I", frame_len_bytes)[0]
                    img_len = struct.unpack("<I", img_len_bytes)[0]
                    if img_len > 0 and img_len <= cover_frame_len and cover_frame_len < 50_000_000:
                        cand_cover = f.read(img_len)
                        f.seek(cover_frame_len - img_len, 1)
                        cand_audio_pos = f.tell()
                        peek_enc = f.read(4)
                        if len(peek_enc) == 4:
                            peek_dec = bytes(a ^ b for a, b in zip(peek_enc, mask_256[:4]))
                            if _is_audio_header(peek_dec):
                                cover_data = cand_cover
                                audio_start_pos = cand_audio_pos
                    elif cover_frame_len == 0 and img_len == 0:
                        cand_audio_pos = f.tell()
                        peek_enc = f.read(4)
                        if len(peek_enc) == 4:
                            peek_dec = bytes(a ^ b for a, b in zip(peek_enc, mask_256[:4]))
                            if _is_audio_header(peek_dec):
                                audio_start_pos = cand_audio_pos
            except Exception:
                pass

            # 兼容模式：检测其它常见偏移结构 (13, 9, 5, 0 字节间隙)
            if audio_start_pos is None:
                for candidate_gap in (13, 9, 5, 0):
                    try:
                        f.seek(post_meta_pos + candidate_gap)
                        cand_img_bytes = f.read(4)
                        if len(cand_img_bytes) == 4:
                            cand_img_len = struct.unpack("<I", cand_img_bytes)[0]
                            if cand_img_len > 0 and cand_img_len < 30_000_000:
                                cand_cover = f.read(cand_img_len)
                                cand_audio_pos = f.tell()
                                peek_enc = f.read(4)
                                if len(peek_enc) == 4:
                                    peek_dec = bytes(a ^ b for a, b in zip(peek_enc, mask_256[:4]))
                                    if _is_audio_header(peek_dec):
                                        cover_data = cand_cover
                                        audio_start_pos = cand_audio_pos
                                        break
                            elif cand_img_len == 0:
                                cand_audio_pos = f.tell()
                                peek_enc = f.read(4)
                                if len(peek_enc) == 4:
                                    peek_dec = bytes(a ^ b for a, b in zip(peek_enc, mask_256[:4]))
                                    if _is_audio_header(peek_dec):
                                        audio_start_pos = cand_audio_pos
                                        break
                    except Exception:
                        pass

            if audio_start_pos is None:
                # 极端异常情况下的回退定位
                f.seek(post_meta_pos + 13)
                img_len_bytes = f.read(4)
                if len(img_len_bytes) == 4:
                    img_len = struct.unpack("<I", img_len_bytes)[0]
                    if 0 < img_len < 20_000_000:
                        cover_data = f.read(img_len)
                audio_start_pos = f.tell()

            f.seek(audio_start_pos)

            # 读取第一块解密数据以精准识别真实音频封装 (MP3 / FLAC)
            chunk_size = 32768
            first_chunk = f.read(chunk_size)
            if not first_chunk:
                return False, "NCM 音频数据流为空。", {}

            c_len = len(first_chunk)
            full_blocks = c_len // 256
            rem = c_len % 256
            mask = mask_256 * full_blocks + mask_256[:rem]
            first_dec = bytes(a ^ b for a, b in zip(first_chunk, mask))

            if first_dec.startswith(b"fLaC"):
                audio_format = "flac"
            elif first_dec.startswith(b"ID3") or (len(first_dec) >= 2 and first_dec[0] == 0xFF and (first_dec[1] & 0xE0) == 0xE0):
                audio_format = "mp3"
            else:
                meta_fmt = meta_json.get("format", "mp3").lower()
                audio_format = meta_fmt if meta_fmt in ("mp3", "flac") else "mp3"

            title = meta_json.get("musicName", "")
            artists_list = meta_json.get("artist", [])
            artists_names = []
            for art in artists_list:
                if isinstance(art, list) and len(art) > 0:
                    artists_names.append(str(art[0]))
                elif isinstance(art, dict) and "name" in art:
                    artists_names.append(str(art["name"]))
                elif isinstance(art, str):
                    artists_names.append(art)
            artist_str = "/".join(artists_names) if artists_names else ""
            album_str = meta_json.get("album", "")

            # 构造文件名
            if artist_str and title:
                out_base_name = f"{artist_str} - {title}"
            elif title:
                out_base_name = title
            else:
                out_base_name = os.path.splitext(os.path.basename(ncm_path))[0]

            out_base_name = sanitize_filename(out_base_name)
            out_filename = f"{out_base_name}.{audio_format}"

            if output_dir and str(output_dir).strip():
                save_dir = os.path.abspath(str(output_dir).strip())
                os.makedirs(save_dir, exist_ok=True)
            else:
                save_dir = os.path.dirname(os.path.abspath(ncm_path))

            output_path = os.path.join(save_dir, out_filename)
            # 目标冲突检测与自增后缀重命名，防止静默覆写已有文件
            if os.path.exists(output_path):
                counter = 1
                while os.path.exists(os.path.join(save_dir, f"{out_base_name}_{counter}.{audio_format}")):
                    counter += 1
                output_path = os.path.join(save_dir, f"{out_base_name}_{counter}.{audio_format}")

            # 7. 解密音频数据流并写入磁盘
            with open(output_path, "wb") as out_f:
                out_f.write(first_dec)
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    c_len = len(chunk)
                    full_blocks = c_len // 256
                    rem = c_len % 256
                    mask = mask_256 * full_blocks + mask_256[:rem]
                    dec_chunk = bytes(a ^ b for a, b in zip(chunk, mask))
                    out_f.write(dec_chunk)

        # 8. 写入 ID3 / FLAC 元数据与封面
        if embed_tags:
            _embed_metadata(output_path, audio_format, title, artist_str, album_str, cover_data)

        return True, output_path, meta_json

    except Exception as e:
        return False, str(e), {}


def _embed_metadata(audio_path: str, fmt: str, title: str, artist: str, album: str, cover_bytes: bytes):
    """使用 mutagen 写入歌曲标题、歌手、专辑与封面图片"""
    try:
        if fmt == "mp3":
            from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, ID3NoHeaderError
            try:
                audio = ID3(audio_path)
            except ID3NoHeaderError:
                audio = ID3()

            if title:
                audio.add(TIT2(encoding=3, text=title))
            if artist:
                audio.add(TPE1(encoding=3, text=artist))
            if album:
                audio.add(TALB(encoding=3, text=album))
            if cover_bytes:
                audio.add(APIC(
                    encoding=3,
                    mime="image/jpeg" if cover_bytes.startswith(b"\xff\xd8") else "image/png",
                    type=3,  # 封面图片
                    desc="Cover",
                    data=cover_bytes
                ))
            audio.save(audio_path, v2_version=3)

        elif fmt == "flac":
            from mutagen.flac import FLAC, Picture
            audio = FLAC(audio_path)
            if title:
                audio["title"] = title
            if artist:
                audio["artist"] = artist
            if album:
                audio["album"] = album
            if cover_bytes:
                pic = Picture()
                pic.type = 3
                pic.mime = "image/jpeg" if cover_bytes.startswith(b"\xff\xd8") else "image/png"
                pic.desc = "Cover"
                pic.data = cover_bytes
                audio.add_picture(pic)
            audio.save()

    except Exception:
        pass


decrypt_music_file = decrypt_ncm


class NcmBatchWorker(QThread):
    """NCM 格式批量解密工作线程"""
    file_started = Signal(str, int, int)
    file_finished = Signal(str, bool, str)
    progress_changed = Signal(int)
    batch_finished = Signal(int, int)
    log_message = Signal(str)

    def __init__(
        self,
        file_paths: List[str],
        custom_output_dir: Optional[str] = None,
        embed_tags: bool = True
    ):
        super().__init__()
        self.file_paths = file_paths
        self.custom_output_dir = custom_output_dir
        self.embed_tags = embed_tags
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        total = len(self.file_paths)
        if total == 0:
            self.batch_finished.emit(0, 0)
            return

        success_count = 0
        failed_count = 0
        self.log_message.emit(f"[启动] NCM 批量解密任务开始，共 {total} 个文件")

        for idx, ncm_path in enumerate(self.file_paths, 1):
            if self._is_cancelled:
                self.log_message.emit("[取消] 用户已中止批量解密。")
                break

            fname = os.path.basename(ncm_path)
            self.file_started.emit(fname, idx, total)
            self.log_message.emit(f"[{idx}/{total}] 正在解密: {fname}")

            ok, out_path, meta = decrypt_ncm(
                ncm_path=ncm_path,
                output_dir=self.custom_output_dir,
                embed_tags=self.embed_tags
            )

            if ok:
                success_count += 1
                self.file_finished.emit(fname, True, out_path)
                title = meta.get("musicName", "")
                self.log_message.emit(f"[成功] 已还原: {os.path.basename(out_path)} ({title})")
            else:
                failed_count += 1
                self.file_finished.emit(fname, False, out_path)
                self.log_message.emit(f"[失败] 解密失败 ({fname}): {out_path}")

            pct = int((idx / total) * 100)
            self.progress_changed.emit(pct)

        self.progress_changed.emit(100)
        self.log_message.emit(f"[汇总] 解密完成: 成功 {success_count} 首, 失败 {failed_count} 首")
        self.batch_finished.emit(success_count, failed_count)
