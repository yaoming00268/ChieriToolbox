"""
音频格式批量转换引擎 - 基于 FFmpeg
支持多格式音频互转、采样率、比特率与声道重采样配置。
"""

import os
import subprocess
from typing import List, Optional, Tuple
from PySide6.QtCore import QThread, Signal

from toolbox.core.paths import find_ffmpeg_executable

SUPPORTED_AUDIO_EXTS = {
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma",
    ".aiff", ".aif", ".alac", ".opus", ".ape", ".ac3", ".dts"
}


def scan_audio_files(paths: List[str]) -> List[str]:
    """递归扫描给定路径集合中的所有有效音频文件"""
    result = []
    for p in paths:
        if os.path.isfile(p):
            ext = os.path.splitext(p)[1].lower()
            if ext in SUPPORTED_AUDIO_EXTS:
                norm = os.path.normpath(p)
                if norm not in result:
                    result.append(norm)
        elif os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in SUPPORTED_AUDIO_EXTS:
                        norm = os.path.normpath(os.path.join(root, f))
                        if norm not in result:
                            result.append(norm)
    return result


def convert_audio(
    input_audio: str,
    output_audio: str,
    fmt: str = "mp3",
    bitrate: Optional[str] = "320k",
    sample_rate: Optional[int] = None,
    channels: Optional[int] = None,
    ffmpeg_path: Optional[str] = None
) -> Tuple[bool, str]:
    """转换单个音频文件格式"""
    ff = ffmpeg_path or find_ffmpeg_executable()
    if not ff or not os.path.isfile(ff):
        return False, "未找到 FFmpeg 核心引擎，请确认 bin/ffmpeg.exe 存在。"

    os.makedirs(os.path.dirname(os.path.abspath(output_audio)), exist_ok=True)

    cmd = [ff, "-y", "-i", input_audio]

    fmt_lower = fmt.lower()
    if fmt_lower == "mp3":
        cmd.extend(["-c:a", "libmp3lame"])
        if bitrate:
            cmd.extend(["-b:a", bitrate])
    elif fmt_lower == "flac":
        cmd.extend(["-c:a", "flac"])
    elif fmt_lower == "wav":
        cmd.extend(["-c:a", "pcm_s16le"])
    elif fmt_lower in ("aac", "m4a"):
        cmd.extend(["-c:a", "aac"])
        if bitrate:
            cmd.extend(["-b:a", bitrate])
    elif fmt_lower == "ogg":
        cmd.extend(["-c:a", "libvorbis"])
        if bitrate:
            cmd.extend(["-b:a", bitrate])
    elif fmt_lower == "wma":
        cmd.extend(["-c:a", "wmav2"])
        if bitrate:
            cmd.extend(["-b:a", bitrate])
    else:
        cmd.extend(["-c:a", "libmp3lame"])
        if bitrate:
            cmd.extend(["-b:a", bitrate])

    # 采样率配置
    if sample_rate:
        cmd.extend(["-ar", str(sample_rate)])

    # 声道配置
    if channels:
        cmd.extend(["-ac", str(channels)])

    cmd.append(output_audio)

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=300
        )
        if proc.returncode == 0 and os.path.exists(output_audio):
            return True, output_audio
        else:
            return False, proc.stderr[-400:] if proc.stderr else f"退出码: {proc.returncode}"
    except subprocess.TimeoutExpired:
        return False, "音频转换处理超时 (超过 300 秒)"
    except Exception as e:
        return False, str(e)


class AudioConvertWorker(QThread):
    """音频批量转换工作线程"""
    file_started = Signal(str, int, int)
    file_finished = Signal(str, bool, str)
    progress_changed = Signal(int)
    batch_finished = Signal(int, int)
    log_message = Signal(str)

    def __init__(
        self,
        file_paths: List[str],
        output_format: str = "mp3",
        bitrate: Optional[str] = "320k",
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        custom_output_dir: Optional[str] = None
    ):
        super().__init__()
        self.file_paths = file_paths
        self.output_format = output_format.lower()
        self.bitrate = bitrate
        self.sample_rate = sample_rate
        self.channels = channels
        self.custom_output_dir = custom_output_dir
        self._is_cancelled = False
        self.ffmpeg_path = find_ffmpeg_executable()

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        total = len(self.file_paths)
        if total == 0:
            self.batch_finished.emit(0, 0)
            return

        success_count = 0
        failed_count = 0
        self.log_message.emit(f"[启动] 音频批量转换开始，共 {total} 个音频文件")

        for idx, audio_path in enumerate(self.file_paths, 1):
            if self._is_cancelled:
                self.log_message.emit("[取消] 用户已中止批量转换任务。")
                break

            base_name = os.path.splitext(os.path.basename(audio_path))[0]
            out_filename = f"{base_name}.{self.output_format}"

            if self.custom_output_dir and str(self.custom_output_dir).strip():
                out_dir = os.path.abspath(str(self.custom_output_dir).strip())
                os.makedirs(out_dir, exist_ok=True)
            else:
                out_dir = os.path.dirname(audio_path)

            target_path = os.path.join(out_dir, out_filename)

            # 防止覆盖同格式同名文件
            if os.path.normpath(audio_path) == os.path.normpath(target_path):
                target_path = os.path.join(out_dir, f"{base_name}_converted.{self.output_format}")

            self.file_started.emit(os.path.basename(audio_path), idx, total)
            self.log_message.emit(f"[{idx}/{total}] 转换: {os.path.basename(audio_path)} -> {os.path.basename(target_path)}")

            ok, detail = convert_audio(
                input_audio=audio_path,
                output_audio=target_path,
                fmt=self.output_format,
                bitrate=self.bitrate,
                sample_rate=self.sample_rate,
                channels=self.channels,
                ffmpeg_path=self.ffmpeg_path
            )

            if ok:
                success_count += 1
                self.file_finished.emit(os.path.basename(audio_path), True, target_path)
                self.log_message.emit(f"[成功] 转换完成: {target_path}")
            else:
                failed_count += 1
                self.file_finished.emit(os.path.basename(audio_path), False, detail)
                self.log_message.emit(f"[失败] 转换失败 ({os.path.basename(audio_path)}): {detail}")

            pct = int((idx / total) * 100)
            self.progress_changed.emit(pct)

        self.progress_changed.emit(100)
        self.log_message.emit(f"[汇总] 转换结束: 成功 {success_count} 项, 失败 {failed_count} 项")
        self.batch_finished.emit(success_count, failed_count)
