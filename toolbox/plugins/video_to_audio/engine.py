"""
批量视频转音频引擎 - 基于 FFmpeg
批量提取 MP3 / FLAC / WAV / AAC / M4A / OGG 音频流。
"""

import os
import subprocess
from typing import List, Optional
from PySide6.QtCore import QThread, Signal

from toolbox.core.paths import find_ffmpeg_executable

SUPPORTED_VIDEO_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm",
    ".ts", ".m4v", ".rmvb", ".mpg", ".mpeg", ".vob", ".3gp"
}


def scan_video_files(paths: List[str]) -> List[str]:
    """递归扫描给定路径集合中的所有有效视频文件"""
    result = []
    for p in paths:
        if os.path.isfile(p):
            ext = os.path.splitext(p)[1].lower()
            if ext in SUPPORTED_VIDEO_EXTS:
                norm = os.path.normpath(p)
                if norm not in result:
                    result.append(norm)
        elif os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in SUPPORTED_VIDEO_EXTS:
                        norm = os.path.normpath(os.path.join(root, f))
                        if norm not in result:
                            result.append(norm)
    return result


def extract_audio(
    input_video: str,
    output_audio: str,
    fmt: str = "mp3",
    bitrate: str = "320k",
    channels: Optional[int] = None,
    sample_rate: Optional[int] = None,
    ffmpeg_path: Optional[str] = None
) -> tuple[bool, str]:
    """调用 FFmpeg 抽取单个视频文件的音频"""
    ff = ffmpeg_path or find_ffmpeg_executable()
    if not ff or not os.path.isfile(ff):
        return False, "未找到 FFmpeg 核心引擎，请确认 bin/ffmpeg.exe 存在。"

    os.makedirs(os.path.dirname(os.path.abspath(output_audio)), exist_ok=True)

    cmd = [ff, "-y", "-i", input_video, "-vn"]

    # 声道设置
    if channels:
        cmd.extend(["-ac", str(channels)])

    # 采样率设置
    if sample_rate:
        cmd.extend(["-ar", str(sample_rate)])

    # 编码器与码率
    fmt_lower = fmt.lower()
    if fmt_lower == "mp3":
        cmd.extend(["-c:a", "libmp3lame", "-b:a", bitrate])
    elif fmt_lower == "flac":
        cmd.extend(["-c:a", "flac"])
    elif fmt_lower == "wav":
        cmd.extend(["-c:a", "pcm_s16le"])
    elif fmt_lower in ("aac", "m4a"):
        cmd.extend(["-c:a", "aac", "-b:a", bitrate])
    elif fmt_lower == "ogg":
        cmd.extend(["-c:a", "libvorbis", "-b:a", bitrate])
    else:
        cmd.extend(["-c:a", "libmp3lame", "-b:a", bitrate])

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
            return False, proc.stderr[-400:] if proc.stderr else f"FFmpeg 退出码: {proc.returncode}"
    except subprocess.TimeoutExpired:
        return False, "视频转音频处理超时 (超过 300 秒)"
    except Exception as e:
        return False, str(e)


class VideoToAudioWorker(QThread):
    """批量视频抽取音频工作线程"""
    file_started = Signal(str, int, int)    # (文件名, 当前索引, 总数)
    file_finished = Signal(str, bool, str)  # (文件名, 是否成功, 输出路径或错误信息)
    progress_changed = Signal(int)         # 百分比 0-100
    batch_finished = Signal(int, int)      # (成功总数, 失败总数)
    log_message = Signal(str)

    def __init__(
        self,
        file_paths: List[str],
        output_format: str = "mp3",
        bitrate: str = "320k",
        custom_output_dir: Optional[str] = None,
        channels: Optional[int] = None
    ):
        super().__init__()
        self.file_paths = file_paths
        self.output_format = output_format.lower()
        self.bitrate = bitrate
        self.custom_output_dir = custom_output_dir
        self.channels = channels
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

        self.log_message.emit(f"[启动] 批量抽取音频任务开始，共 {total} 个视频文件")

        for idx, video_path in enumerate(self.file_paths, 1):
            if self._is_cancelled:
                self.log_message.emit("[取消] 用户已中止批量抽取任务。")
                break

            base_name = os.path.splitext(os.path.basename(video_path))[0]
            out_filename = f"{base_name}.{self.output_format}"

            if self.custom_output_dir and str(self.custom_output_dir).strip():
                out_dir = os.path.abspath(str(self.custom_output_dir).strip())
                os.makedirs(out_dir, exist_ok=True)
            else:
                out_dir = os.path.dirname(video_path)

            target_path = os.path.join(out_dir, out_filename)

            self.file_started.emit(os.path.basename(video_path), idx, total)
            self.log_message.emit(f"[{idx}/{total}] 正在转换: {os.path.basename(video_path)} -> {out_filename}")

            ok, detail = extract_audio(
                input_video=video_path,
                output_audio=target_path,
                fmt=self.output_format,
                bitrate=self.bitrate,
                channels=self.channels,
                ffmpeg_path=self.ffmpeg_path
            )

            if ok:
                success_count += 1
                self.file_finished.emit(os.path.basename(video_path), True, target_path)
                self.log_message.emit(f"[完成] 抽取成功: {target_path}")
            else:
                failed_count += 1
                self.file_finished.emit(os.path.basename(video_path), False, detail)
                self.log_message.emit(f"[失败] 抽取失败 ({os.path.basename(video_path)}): {detail}")

            pct = int((idx / total) * 100)
            self.progress_changed.emit(pct)

        self.progress_changed.emit(100)
        self.log_message.emit(f"[汇总] 任务结束: 成功 {success_count} 项, 失败 {failed_count} 项")
        self.batch_finished.emit(success_count, failed_count)
