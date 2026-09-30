"""
工具箱 (Toolbox) - 核心多媒体引擎基座 (Media Engine)
统筹 FFmpeg/FFprobe 子进程调度、优雅终止、多媒体文件统一扫描与安全原子覆写。
"""

import os
import sys
import time
import shutil
import subprocess
from typing import List, Tuple, Optional, Callable, Dict, Any, Set

from toolbox.core.paths import find_ffmpeg_executable

AUDIO_EXTENSIONS: Set[str] = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"}
VIDEO_EXTENSIONS: Set[str] = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v", ".ts"}
IMAGE_EXTENSIONS: Set[str] = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif", ".ico"}


class SafeFFmpegProcess:
    """
    安全包装的 FFmpeg/FFprobe 子进程管理器。
    支持 Windows 静默启动、优雅退出 (q\n)、存活探测与异常退出清理。
    """

    def __init__(self, cmd: List[str], text_mode: bool = True):
        self.cmd = cmd
        self.text_mode = text_mode
        self.process: Optional[subprocess.Popen] = None

    def start(self) -> Tuple[bool, str]:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        try:
            self.process = subprocess.Popen(
                self.cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=creationflags,
                text=self.text_mode,
                encoding="utf-8" if self.text_mode else None,
                errors="replace" if self.text_mode else None
            )
            return True, ""
        except Exception as e:
            return False, f"启动 FFmpeg 进程失败: {e}"

    def check_alive_after_ms(self, ms: int = 300) -> Tuple[bool, str]:
        """等待 ms 毫秒，验证子进程是否意外崩溃退出"""
        if not self.process:
            return False, "进程未初始化"
        time.sleep(ms / 1000.0)
        poll_res = self.process.poll()
        if poll_res is not None:
            err_msg = ""
            try:
                _, stderr_out = self.process.communicate(timeout=0.5)
                err_msg = stderr_out.strip() if stderr_out else ""
            except Exception:
                pass
            return False, f"FFmpeg 启动即崩溃 (代码 {poll_res}): {err_msg}"
        return True, ""

    def send_quit(self, timeout_sec: float = 3.0):
        """向 FFmpeg 发送 q 字符以实现优雅断开与文件写尾"""
        if not self.process:
            return
        try:
            if self.process.stdin:
                if self.text_mode:
                    self.process.stdin.write("q\n")
                else:
                    self.process.stdin.write(b"q\n")
                self.process.stdin.flush()
            self.process.wait(timeout=timeout_sec)
        except Exception:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
        finally:
            self.process = None

    def run_sync(self, timeout: Optional[float] = None) -> Tuple[int, str, str]:
        """同步运行命令并等待返回 (returncode, stdout, stderr)"""
        ok, err = self.start()
        if not ok:
            return -1, "", err
        try:
            stdout_data, stderr_data = self.process.communicate(timeout=timeout)
            return self.process.returncode, stdout_data or "", stderr_data or ""
        except subprocess.TimeoutExpired:
            self.process.kill()
            return -1, "", "执行超时已强行终止"
        except Exception as e:
            return -1, "", str(e)


class MediaScanner:
    """统一多媒体文件扫描器"""

    @staticmethod
    def is_audio(filepath: str) -> bool:
        ext = os.path.splitext(filepath)[1].lower()
        return ext in AUDIO_EXTENSIONS

    @staticmethod
    def is_video(filepath: str) -> bool:
        ext = os.path.splitext(filepath)[1].lower()
        return ext in VIDEO_EXTENSIONS

    @staticmethod
    def is_image(filepath: str) -> bool:
        ext = os.path.splitext(filepath)[1].lower()
        return ext in IMAGE_EXTENSIONS

    @staticmethod
    def scan_directory(
        directory: str,
        media_types: Tuple[str, ...] = ("audio", "video"),
        recursive: bool = False
    ) -> List[str]:
        """扫描目录下指定类型的多媒体文件，并返回规范排序后的路径列表"""
        valid_exts: Set[str] = set()
        if "audio" in media_types:
            valid_exts |= AUDIO_EXTENSIONS
        if "video" in media_types:
            valid_exts |= VIDEO_EXTENSIONS
        if "image" in media_types:
            valid_exts |= IMAGE_EXTENSIONS

        results = []
        if not os.path.isdir(directory):
            return results

        if recursive:
            for root, _, files in os.walk(directory):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in valid_exts:
                        results.append(os.path.normpath(os.path.join(root, f)))
        else:
            for f in os.listdir(directory):
                p = os.path.join(directory, f)
                if os.path.isfile(p):
                    ext = os.path.splitext(f)[1].lower()
                    if ext in valid_exts:
                        results.append(os.path.normpath(p))

        results.sort()
        return results


def atomic_replace_file(src: str, dst: str) -> Tuple[bool, str]:
    """
    具备跨磁盘安全回退特性的原子文件替换工具。
    在同卷下优先使用 os.replace，失败时回退至 shutil.copy2 + os.remove。
    """
    if not os.path.exists(src):
        return False, f"源暂存文件不存在: {src}"
    try:
        os.replace(src, dst)
        return True, ""
    except Exception as e:
        try:
            shutil.copy2(src, dst)
            os.remove(src)
            return True, ""
        except Exception as e2:
            return False, f"原子覆写失败: {e2} (初次尝试: {e})"
