"""
图片与视频体积压缩 - 核心压缩引擎 (Engine)
集成立体化无损与有损图像压缩 (WebP / MozJPEG / Pillow) 及 FFmpeg H.264 / HEVC / AV1 CRF 视频极限压制算法。
"""

import os
import time
import threading
import subprocess
from typing import List, Tuple, Optional, Callable
from PIL import Image
from PySide6.QtCore import QThread, Signal
from toolbox.core.paths import find_ffmpeg_executable

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v", ".ts"}


def format_bytes(size_bytes: int) -> str:
    """格式化字节大小显示"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def is_image_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in IMAGE_EXTENSIONS


def is_video_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in VIDEO_EXTENSIONS


def compress_image(
    input_path: str,
    output_path: str,
    format_choice: str = "WEBP",
    quality: int = 80,
    max_dimension: int = 0
) -> Tuple[bool, str, int, int]:
    """
    单张图像压缩处理
    返回: (成功与否, 错误信息, 压缩前字节数, 压缩后字节数)
    """
    tmp_target = None
    try:
        before_size = os.path.getsize(input_path)
        out_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(out_dir, exist_ok=True)
        is_same_file = (os.path.normcase(os.path.abspath(input_path)) == os.path.normcase(os.path.abspath(output_path)))
        tmp_target = os.path.join(out_dir, f"._tmp_cmp_{os.getpid()}_{os.path.basename(output_path)}") if is_same_file else None
        save_target = tmp_target if is_same_file else output_path

        with Image.open(input_path) as raw_im:
            raw_im.load()
            orig_fmt = raw_im.format or "PNG"
            im = raw_im.copy()

        # 缩放处理
        if max_dimension > 0:
            w, h = im.size
            if max(w, h) > max_dimension:
                scale = max_dimension / float(max(w, h))
                new_w = max(1, int(w * scale))
                new_h = max(1, int(h * scale))
                im = im.resize((new_w, new_h), Image.Resampling.LANCZOS)

        fmt = format_choice.upper()

        if fmt == "WEBP":
            # 转换至 RGB 或 RGBA 以保证 WebP 兼容性
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.mode else "RGB")
            im.save(save_target, format="WEBP", quality=quality, method=6)
        elif fmt in ("JPEG", "JPG"):
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            im.save(save_target, format="JPEG", quality=quality, optimize=True, subsampling=2)
        else:
            # 保持原格式优化
            if orig_fmt.upper() in ("JPEG", "JPG") and im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            im.save(save_target, format=orig_fmt, optimize=True, quality=quality)

        if tmp_target and os.path.exists(tmp_target):
            os.replace(tmp_target, output_path)

        after_size = os.path.getsize(output_path)
        return True, "", before_size, after_size
    except Exception as e:
        if tmp_target and os.path.exists(tmp_target):
            try:
                os.remove(tmp_target)
            except Exception:
                pass
        return False, str(e), 0, 0


def compress_video(
    input_path: str,
    output_path: str,
    codec: str = "H.264",
    crf: int = 26,
    preset: str = "medium",
    audio_bitrate: str = "128k",
    scale_height: int = 0,
    ffmpeg_exe: Optional[str] = None,
    cancel_callback: Optional[Callable[[], bool]] = None,
    process_callback: Optional[Callable[[subprocess.Popen], None]] = None
) -> Tuple[bool, str, int, int]:
    """
    单视频批量高压处理
    返回: (成功与否, 错误信息, 压缩前字节数, 压缩后字节数)
    """
    tmp_target = None
    try:
        ffmpeg_bin = ffmpeg_exe or find_ffmpeg_executable()
        if not ffmpeg_bin or not os.path.isfile(ffmpeg_bin):
            return False, "未找到有效的 FFmpeg 引擎二进制文件", 0, 0

        before_size = os.path.getsize(input_path)
        out_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(out_dir, exist_ok=True)

        is_same_file = (os.path.normcase(os.path.abspath(input_path)) == os.path.normcase(os.path.abspath(output_path)))
        tmp_target = os.path.join(out_dir, f"._tmp_vid_{os.getpid()}_{os.path.basename(output_path)}") if is_same_file else None
        target_output = tmp_target if is_same_file else output_path

        # 视频编码器参数构建
        if "265" in codec or "HEVC" in codec:
            vcodec_args = ["-c:v", "libx265", "-tag:v", "hvc1"]
        elif "AV1" in codec:
            vcodec_args = ["-c:v", "libsvtav1"]
        else:
            vcodec_args = ["-c:v", "libx264", "-pix_fmt", "yuv420p"]

        cmd = [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-i", input_path
        ]
        cmd.extend(vcodec_args)
        cmd.extend(["-crf", str(crf), "-preset", preset])

        if scale_height > 0:
            cmd.extend(["-vf", f"scale=-2:{scale_height}"])

        if audio_bitrate == "copy":
            cmd.extend(["-c:a", "copy"])
        else:
            cmd.extend(["-c:a", "aac", "-b:a", audio_bitrate])

        cmd.append(target_output)

        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        def _run_cancellable(command: List[str]) -> Tuple[int, str]:
            p = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=creationflags,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            if process_callback:
                process_callback(p)

            stderr_lines = []

            def _drain_stderr():
                try:
                    if p.stderr:
                        for line in p.stderr:
                            stderr_lines.append(line)
                except Exception:
                    pass

            drain_thread = threading.Thread(target=_drain_stderr, daemon=True)
            drain_thread.start()

            while p.poll() is None:
                if cancel_callback and cancel_callback():
                    try:
                        p.terminate()
                        p.wait(timeout=1.0)
                    except Exception:
                        try:
                            p.kill()
                        except Exception:
                            pass
                    return -999, "用户已中止压缩任务"
                time.sleep(0.1)

            drain_thread.join(timeout=1.0)
            err_out = "".join(stderr_lines)
            return p.returncode, err_out

        ret_code, err_msg = _run_cancellable(cmd)
        if ret_code == -999:
            if is_same_file and tmp_target and os.path.exists(tmp_target):
                try:
                    os.remove(tmp_target)
                except Exception:
                    pass
            return False, "用户已中止压缩任务", 0, 0

        if ret_code != 0:
            # 若 libsvtav1 不可用，自动尝试回退至 libx264
            if "AV1" in codec:
                fallback_cmd = [
                    ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error",
                    "-i", input_path, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", str(crf), "-preset", preset
                ]
                if scale_height > 0:
                    fallback_cmd.extend(["-vf", f"scale=-2:{scale_height}"])
                fallback_cmd.extend(["-c:a", "aac", "-b:a", audio_bitrate, target_output])
                ret_code2, err_msg2 = _run_cancellable(fallback_cmd)
                if ret_code2 == -999:
                    if is_same_file and tmp_target and os.path.exists(tmp_target):
                        try:
                            os.remove(tmp_target)
                        except Exception:
                            pass
                    return False, "用户已中止压缩任务", 0, 0
                if ret_code2 == 0 and os.path.exists(target_output):
                    if is_same_file and tmp_target and os.path.exists(tmp_target):
                        os.replace(tmp_target, output_path)
                    after_size = os.path.getsize(output_path)
                    return True, "", before_size, after_size
            if is_same_file and tmp_target and os.path.exists(tmp_target):
                try:
                    os.remove(tmp_target)
                except Exception:
                    pass
            return False, f"FFmpeg 编码失败: {err_msg.strip()}", 0, 0

        if is_same_file and tmp_target and os.path.exists(tmp_target):
            os.replace(tmp_target, output_path)

        after_size = os.path.getsize(output_path)
        return True, "", before_size, after_size
    except Exception as e:
        if tmp_target and os.path.exists(tmp_target):
            try:
                os.remove(tmp_target)
            except Exception:
                pass
        return False, str(e), 0, 0


class MediaCompressorWorker(QThread):
    progress = Signal(int, int, str)                          # (当前索引, 总数, 文件名)
    item_finished = Signal(str, bool, int, int, str)          # (文件路径, 是否成功, 前大小, 后大小, 备注)
    log = Signal(str)
    all_finished = Signal(int, int)                           # (成功数, 失败数)

    def __init__(
        self,
        files: List[str],
        output_dir: str,
        same_dir: bool,
        image_params: dict,
        video_params: dict,
        parent=None
    ):
        super().__init__(parent)
        self.files = files
        self.output_dir = output_dir
        self.same_dir = same_dir
        self.image_params = image_params
        self.video_params = video_params
        self._is_cancelled = False
        self._current_proc = None

    def cancel(self):
        self._is_cancelled = True
        if self._current_proc:
            try:
                self._current_proc.terminate()
            except Exception:
                pass

    def run(self):
        success_count = 0
        fail_count = 0
        total = len(self.files)

        self.log.emit(f"开始批量压缩处理，待处理任务总数: {total}")

        for idx, file_path in enumerate(self.files):
            if self._is_cancelled:
                self.log.emit("用户已中止压缩任务。")
                break

            base_name = os.path.basename(file_path)
            name_no_ext, ext = os.path.splitext(base_name)
            self.progress.emit(idx + 1, total, base_name)

            if is_image_file(file_path):
                # 图像处理
                target_fmt = self.image_params.get("format", "WEBP")
                out_ext = ".webp" if target_fmt == "WEBP" else (".jpg" if target_fmt in ("JPEG", "JPG") else ext)
                if self.same_dir:
                    out_dir = os.path.dirname(file_path)
                    out_name = f"{name_no_ext}_compressed{out_ext}"
                else:
                    out_dir = self.output_dir
                    out_name = f"{name_no_ext}{out_ext}"
                out_path = os.path.join(out_dir, out_name)
                if os.path.abspath(out_path) == os.path.abspath(file_path):
                    out_path = os.path.join(out_dir, f"{name_no_ext}_compressed{out_ext}")

                ok, err, b_sz, a_sz = compress_image(
                    file_path,
                    out_path,
                    format_choice=target_fmt,
                    quality=self.image_params.get("quality", 80),
                    max_dimension=self.image_params.get("max_dimension", 0)
                )

                if ok:
                    success_count += 1
                    saved_pct = (1.0 - (a_sz / max(1, b_sz))) * 100.0
                    msg = f"体积削减 {saved_pct:.1f}% ({format_bytes(b_sz)} -> {format_bytes(a_sz)})"
                    self.log.emit(f"图片压缩成功: {base_name} | {msg}")
                    self.item_finished.emit(file_path, True, b_sz, a_sz, msg)
                else:
                    fail_count += 1
                    self.log.emit(f"图片压缩失败: {base_name} | {err}")
                    self.item_finished.emit(file_path, False, 0, 0, err)

            elif is_video_file(file_path):
                # 视频处理
                if self.same_dir:
                    out_dir = os.path.dirname(file_path)
                    out_name = f"{name_no_ext}_compressed.mp4"
                else:
                    out_dir = self.output_dir
                    out_name = f"{name_no_ext}.mp4"
                out_path = os.path.join(out_dir, out_name)
                if os.path.abspath(out_path) == os.path.abspath(file_path):
                    out_path = os.path.join(out_dir, f"{name_no_ext}_compressed.mp4")

                ok, err, b_sz, a_sz = compress_video(
                    file_path,
                    out_path,
                    codec=self.video_params.get("codec", "H.264"),
                    crf=self.video_params.get("crf", 26),
                    preset=self.video_params.get("preset", "medium"),
                    audio_bitrate=self.video_params.get("audio_bitrate", "128k"),
                    scale_height=self.video_params.get("scale_height", 0),
                    cancel_callback=lambda: self._is_cancelled,
                    process_callback=lambda p: setattr(self, "_current_proc", p)
                )
                self._current_proc = None

                if ok:
                    success_count += 1
                    saved_pct = (1.0 - (a_sz / max(1, b_sz))) * 100.0
                    msg = f"体积削减 {saved_pct:.1f}% ({format_bytes(b_sz)} -> {format_bytes(a_sz)})"
                    self.log.emit(f"视频压缩成功: {base_name} | {msg}")
                    self.item_finished.emit(file_path, True, b_sz, a_sz, msg)
                else:
                    fail_count += 1
                    self.log.emit(f"视频压缩失败: {base_name} | {err}")
                    self.item_finished.emit(file_path, False, 0, 0, err)
            else:
                fail_count += 1
                self.log.emit(f"跳过不支持的文件格式: {base_name}")
                self.item_finished.emit(file_path, False, 0, 0, "格式不受支持")

        self.all_finished.emit(success_count, fail_count)
