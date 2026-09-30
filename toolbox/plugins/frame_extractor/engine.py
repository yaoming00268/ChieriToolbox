"""
视频与动图逐帧解压工具 - 核心提取引擎 (Engine)
支持将任意主流视频格式 (MP4/MKV/AVI/MOV/FLV/WebM) 及动图 (GIF/WebP) 高速解压解包为独立单帧序列图像。
"""

import os
import subprocess
from typing import List, Tuple, Optional
from PIL import Image, ImageSequence
from PySide6.QtCore import QThread, Signal
from toolbox.core.paths import find_ffmpeg_executable

SUPPORTED_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".gif", ".webp", ".m4v"}


def is_supported_media(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXTS


def extract_gif_frames(
    input_path: str,
    output_dir: str,
    format_choice: str = "PNG",
    jpg_quality: int = 95
) -> Tuple[bool, str, int]:
    """使用 Pillow 高精度提取 GIF / 动图帧序列"""
    try:
        os.makedirs(output_dir, exist_ok=True)
        count = 0
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        ext = format_choice.lower()
        if ext == "jpg":
            ext = "jpeg"

        with Image.open(input_path) as im:
            for idx, frame in enumerate(ImageSequence.Iterator(im)):
                out_name = f"{base_name}_frame_{idx + 1:05d}.{format_choice.lower()}"
                out_path = os.path.join(output_dir, out_name)
                # 转换色彩通道
                if format_choice.upper() in ("JPG", "JPEG"):
                    rgb_frame = frame.convert("RGB")
                    rgb_frame.save(out_path, format="JPEG", quality=jpg_quality, optimize=True)
                else:
                    frame.save(out_path, format=format_choice.upper())
                count += 1
        return True, "", count
    except Exception as e:
        return False, str(e), 0


def extract_video_frames(
    input_path: str,
    output_dir: str,
    format_choice: str = "PNG",
    mode: str = "all",
    fps_val: float = 1.0,
    interval_sec: float = 1.0,
    jpg_quality: int = 95,
    ffmpeg_exe: Optional[str] = None
) -> Tuple[bool, str, int]:
    """
    使用内置 FFmpeg 引擎提取视频帧
    模式:
      - 'all': 逐帧全量提取
      - 'fps': 采样特定帧率 (fps_val 帧/秒)
      - 'interval': 按时间间隔提取 (每 interval_sec 秒提取 1 帧)
      - 'keyframe': 仅提取关键帧 (I-Frames)
    """
    try:
        ffmpeg_bin = ffmpeg_exe or find_ffmpeg_executable()
        if not ffmpeg_bin or not os.path.isfile(ffmpeg_bin):
            return False, "未找到有效的 FFmpeg 引擎二进制文件", 0

        os.makedirs(output_dir, exist_ok=True)
        import time
        start_time = time.time() - 1.0
        existing_mtimes = {}
        for f in os.listdir(output_dir):
            try:
                existing_mtimes[f] = os.path.getmtime(os.path.join(output_dir, f))
            except OSError:
                pass
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        out_ext = format_choice.lower()
        if out_ext == "jpeg":
            out_ext = "jpg"

        out_pattern = os.path.join(output_dir, f"{base_name}_frame_%06d.{out_ext}")

        cmd = [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-i", input_path
        ]

        sync_args = []
        if mode == "keyframe":
            cmd.extend(["-vf", "select='eq(pict_type,PICT_TYPE_I)'"])
            sync_args = ["-fps_mode", "vfr"]
        elif mode == "fps":
            cmd.extend(["-vf", f"fps={fps_val}"])
        elif mode == "interval":
            cmd.extend(["-vf", f"fps=1/{max(0.01, interval_sec)}"])
        else:
            # 逐帧全部提取
            sync_args = ["-fps_mode", "passthrough"]

        cmd.extend(sync_args)

        if out_ext == "jpg":
            cmd.extend(["-qscale:v", str(max(1, min(31, int((100 - jpg_quality) / 3) + 1)))])

        cmd.append(out_pattern)

        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
            creationflags=creationflags,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        # 若新版 -fps_mode 在较旧 FFmpeg 上不支持，自动回退到经典 -vsync 参数
        if proc.returncode != 0 and sync_args and ("fps_mode" in proc.stderr.lower() or "unrecognized" in proc.stderr.lower()):
            legacy_sync = ["-vsync", "vfr"] if mode == "keyframe" else ["-vsync", "0"]
            fallback_cmd = [x for x in cmd if x not in sync_args]
            # 插入在 out_pattern 之前
            fallback_cmd.insert(-1, legacy_sync[0])
            fallback_cmd.insert(-1, legacy_sync[1])
            proc = subprocess.run(
                fallback_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=creationflags,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

        if proc.returncode != 0:
            return False, f"FFmpeg 提取异常: {proc.stderr.strip()}", 0

        # 统计输出目录新提取或更新的文件数
        created_files = []
        for f in os.listdir(output_dir):
            if f.startswith(f"{base_name}_frame_") and f.endswith(f".{out_ext}"):
                p = os.path.join(output_dir, f)
                try:
                    mtime = os.path.getmtime(p)
                    if f not in existing_mtimes or mtime > existing_mtimes[f] or mtime >= start_time:
                        created_files.append(f)
                except OSError:
                    pass
        return True, "", len(created_files)
    except Exception as e:
        return False, str(e), 0


class FrameExtractorWorker(QThread):
    progress = Signal(int, int, str)                 # (当前索引, 总数, 文件名)
    item_finished = Signal(str, bool, int, str)      # (文件路径, 是否成功, 帧数量, 备注)
    log = Signal(str)
    all_finished = Signal(int, int, int)             # (成功任务数, 失败任务数, 总提取图片数)

    def __init__(
        self,
        files: List[str],
        output_dir: str,
        create_subfolder: bool,
        format_choice: str,
        mode: str,
        fps_val: float,
        interval_sec: float,
        jpg_quality: int,
        parent=None
    ):
        super().__init__(parent)
        self.files = files
        self.output_dir = output_dir
        self.create_subfolder = create_subfolder
        self.format_choice = format_choice
        self.mode = mode
        self.fps_val = fps_val
        self.interval_sec = interval_sec
        self.jpg_quality = jpg_quality
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        success_tasks = 0
        fail_tasks = 0
        total_frames = 0
        total = len(self.files)

        self.log.emit(f"开始批量逐帧解压任务，共 {total} 个文件...")

        for idx, file_path in enumerate(self.files):
            if self._is_cancelled:
                self.log.emit("用户已中止逐帧解压操作。")
                break

            base_name = os.path.basename(file_path)
            name_no_ext, ext = os.path.splitext(base_name)
            self.progress.emit(idx + 1, total, base_name)

            if self.create_subfolder:
                dest_dir = os.path.join(self.output_dir, f"{name_no_ext}_frames")
            else:
                dest_dir = self.output_dir

            if ext.lower() in (".gif", ".webp"):
                ok, err, count = extract_gif_frames(
                    file_path,
                    dest_dir,
                    format_choice=self.format_choice,
                    jpg_quality=self.jpg_quality
                )
                if not ok and ext.lower() == ".webp":
                    # 若 Pillow 提取 WebP 失败，回退至 FFmpeg 引擎提取
                    ok, err, count = extract_video_frames(
                        file_path,
                        dest_dir,
                        format_choice=self.format_choice,
                        mode=self.mode,
                        fps_val=self.fps_val,
                        interval_sec=self.interval_sec,
                        jpg_quality=self.jpg_quality
                    )
            else:
                ok, err, count = extract_video_frames(
                    file_path,
                    dest_dir,
                    format_choice=self.format_choice,
                    mode=self.mode,
                    fps_val=self.fps_val,
                    interval_sec=self.interval_sec,
                    jpg_quality=self.jpg_quality
                )

            if ok:
                success_tasks += 1
                total_frames += count
                msg = f"解压完成，共提取 {count} 张图片 -> {dest_dir}"
                self.log.emit(f"成功: {base_name} | {msg}")
                self.item_finished.emit(file_path, True, count, msg)
            else:
                fail_tasks += 1
                self.log.emit(f"失败: {base_name} | {err}")
                self.item_finished.emit(file_path, False, 0, err)

        self.all_finished.emit(success_tasks, fail_tasks, total_frames)
