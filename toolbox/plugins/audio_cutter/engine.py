"""
音频精准剪裁引擎 - 基于 FFmpeg 与 FFprobe
支持微秒/毫秒级时间轴截取、流拷贝极速无损剪切与重编码高质量导出。
"""

import json
import os
import shutil
import subprocess
import time
from typing import Dict, Optional, Tuple
from PySide6.QtCore import QThread, Signal

from toolbox.core.paths import find_ffmpeg_executable


def find_ffprobe_executable() -> Optional[str]:
    """寻找可用的 ffprobe 可执行文件路径"""
    try:
        from toolbox.core.paths import get_bin_path
        local_ffprobe = get_bin_path("ffprobe.exe")
        if local_ffprobe and os.path.isfile(local_ffprobe):
            return local_ffprobe
    except Exception:
        pass
    sys_ffprobe = shutil.which("ffprobe")
    if sys_ffprobe:
        return sys_ffprobe
    return None


def seconds_to_timecode(seconds: float) -> str:
    """将秒数转为标准时间码 HH:MM:SS.mmm"""
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_secs = total_ms // 1000
    s = total_secs % 60
    total_mins = total_secs // 60
    m = total_mins % 60
    h = total_mins // 60
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def timecode_to_seconds(tc: str) -> float:
    """将时间码解析为秒数浮点值"""
    tc = tc.strip()
    if not tc:
        return 0.0

    parts = tc.split(":")
    if len(parts) == 3:
        h = float(parts[0])
        m = float(parts[1])
        s = float(parts[2])
        return h * 3600 + m * 60 + s
    elif len(parts) == 2:
        m = float(parts[0])
        s = float(parts[1])
        return m * 60 + s
    elif len(parts) == 1:
        return float(parts[0])
    return 0.0


def probe_audio_file(audio_path: str) -> Dict:
    """通过 ffprobe 提取音频的详细时长与规格数据"""
    if not os.path.isfile(audio_path):
        return {"error": "文件不存在"}

    ffprobe = find_ffprobe_executable()
    if not ffprobe:
        return {"error": "未找到 ffprobe 核心引擎"}

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        audio_path
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10
        )
        if proc.returncode != 0:
            return {"error": f"ffprobe 分析失败: {proc.stderr[:200]}"}

        data = json.loads(proc.stdout)
        fmt = data.get("format", {})
        duration = float(fmt.get("duration", 0.0))
        bit_rate = int(fmt.get("bit_rate", 0))

        # 找音频流
        audio_stream = {}
        for s in data.get("streams", []):
            if s.get("codec_type") == "audio":
                audio_stream = s
                break

        sample_rate = int(audio_stream.get("sample_rate", 0))
        channels = int(audio_stream.get("channels", 0))
        codec_name = audio_stream.get("codec_name", "")

        return {
            "duration": duration,
            "duration_str": seconds_to_timecode(duration),
            "bit_rate": bit_rate,
            "sample_rate": sample_rate,
            "channels": channels,
            "codec_name": codec_name,
            "size_bytes": os.path.getsize(audio_path)
        }
    except Exception as e:
        return {"error": str(e)}


def cut_audio(
    input_path: str,
    output_path: str,
    start_sec: float,
    end_sec: float,
    mode: str = "copy",
    target_format: str = "mp3",
    bitrate: str = "320k",
    ffmpeg_path: Optional[str] = None
) -> Tuple[bool, str]:
    """执行音频剪裁任务"""
    ff = ffmpeg_path or find_ffmpeg_executable()
    if not ff:
        return False, "未找到 FFmpeg 核心引擎"

    if end_sec <= start_sec:
        return False, "结束时间必须大于起始时间。"

    duration = end_sec - start_sec
    abs_out = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_out), exist_ok=True)

    # 检测输入文件与输出文件是否为同一文件（防止 -y 导致原文件被瞬间截断为 0 字节损坏）
    is_same_file = (os.path.normcase(os.path.abspath(input_path)) == os.path.normcase(abs_out))
    if is_same_file:
        out_dir = os.path.dirname(abs_out)
        temp_filename = f"._cut_tmp_{os.getpid()}_{int(time.time() * 1000)}_{os.path.basename(abs_out)}"
        actual_target = os.path.join(out_dir, temp_filename)
    else:
        actual_target = abs_out

    # 构造精确裁剪命令
    # 在流拷贝模式下使用输入前 -ss 实现快速定位
    # 在重编码模式下将 -ss 与 -t 置于输入后，进行无损解码与微秒级精准采样对齐
    if mode == "copy":
        cmd = [
            ff, "-y",
            "-ss", f"{start_sec:.3f}",
            "-t", f"{duration:.3f}",
            "-i", input_path,
            "-c", "copy"
        ]
    else:
        cmd = [
            ff, "-y",
            "-i", input_path,
            "-ss", f"{start_sec:.3f}",
            "-t", f"{duration:.3f}"
        ]
        fmt_lower = target_format.lower()
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

    cmd.append(actual_target)

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
            timeout=120
        )
        if proc.returncode == 0 and os.path.exists(actual_target) and os.path.getsize(actual_target) > 0:
            if is_same_file:
                from toolbox.core.media_engine import atomic_replace_file
                ok_rep, err_rep = atomic_replace_file(actual_target, abs_out)
                if not ok_rep:
                    if os.path.exists(actual_target):
                        try:
                            os.remove(actual_target)
                        except Exception:
                            pass
                    return False, f"原子覆写原文件失败: {err_rep}"
            return True, abs_out
        else:
            if is_same_file and os.path.exists(actual_target):
                try:
                    os.remove(actual_target)
                except Exception:
                    pass
            return False, proc.stderr[-400:] if proc.stderr else f"FFmpeg 错误码: {proc.returncode}"
    except Exception as e:
        if is_same_file and os.path.exists(actual_target):
            try:
                os.remove(actual_target)
            except Exception:
                pass
        return False, str(e)


class AudioCutWorker(QThread):
    """音频剪裁异步工作线程"""
    finished = Signal(bool, str)
    log_message = Signal(str)

    def __init__(
        self,
        input_path: str,
        output_path: str,
        start_sec: float,
        end_sec: float,
        mode: str = "copy",
        target_format: str = "mp3",
        bitrate: str = "320k"
    ):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.mode = mode
        self.target_format = target_format
        self.bitrate = bitrate

    def run(self):
        self.log_message.emit(
            f"[开始剪切] 时间范围: {seconds_to_timecode(self.start_sec)} -> {seconds_to_timecode(self.end_sec)} "
            f"(时长: {self.end_sec - self.start_sec:.3f}秒, 模式: {self.mode})"
        )
        ok, res = cut_audio(
            input_path=self.input_path,
            output_path=self.output_path,
            start_sec=self.start_sec,
            end_sec=self.end_sec,
            mode=self.mode,
            target_format=self.target_format,
            bitrate=self.bitrate
        )
        if ok:
            self.log_message.emit(f"[成功] 剪裁音频已保存至: {res}")
        else:
            self.log_message.emit(f"[失败] 剪切失败: {res}")

        self.finished.emit(ok, res)
