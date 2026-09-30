"""
YouTube 视频下载引擎 - 基于 yt-dlp 与 FFmpeg
支持视频解析、画质选择、独立音视频流合并与代理配置。
"""

import os
import re
import shutil
import subprocess
from typing import Dict, List, Optional
from PySide6.QtCore import QThread, Signal

from toolbox.core.paths import find_ffmpeg_executable, sanitize_filename


def _get_node_runtime() -> Optional[str]:
    """探测系统 Node.js 运行时路径用于执行现代 YouTube 播放器脚本"""
    node = shutil.which("node")
    if node:
        return node
    for p in [r"C:\Program Files\nodejs\node.exe", r"C:\Program Files (x86)\nodejs\node.exe"]:
        if os.path.isfile(p):
            return p
    return None


class VideoInfoExtractor(QThread):
    """异步解析视频元数据与可用分辨率流"""
    success = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        url: str,
        proxy: Optional[str] = None,
        cookie_file: Optional[str] = None,
        browser_cookies: Optional[str] = None
    ):
        super().__init__()
        self.url = url.strip()
        self.proxy = proxy.strip() if proxy else None
        self.cookie_file = cookie_file.strip() if cookie_file else None
        self.browser_cookies = browser_cookies.strip() if browser_cookies else None

    def run(self):
        try:
            import yt_dlp

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "extract_flat": False,
            }
            if self.proxy:
                ydl_opts["proxy"] = self.proxy

            if self.cookie_file and os.path.isfile(self.cookie_file):
                ydl_opts["cookiefile"] = self.cookie_file
            elif self.browser_cookies:
                ydl_opts["cookiesfrombrowser"] = (self.browser_cookies,)

            node_path = _get_node_runtime()
            if node_path:
                ydl_opts["js_runtimes"] = {"node": {"path": node_path}}

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if not info:
                    self.error.emit("无法解析视频信息，请检查链接或网络代理。")
                    return

                # 整理视频信息
                title = info.get("title", "未命名视频")
                duration = info.get("duration", 0)
                uploader = info.get("uploader", "未知作者")
                thumbnail = info.get("thumbnail", "")
                webpage_url = info.get("webpage_url", self.url)

                # 收集可用画质列表
                formats = info.get("formats", [])
                resolutions = set()
                has_audio = False
                for f in formats:
                    h = f.get("height")
                    if h:
                        resolutions.add(h)
                    if f.get("acodec") != "none" or f.get("vcodec") == "none":
                        has_audio = True

                sorted_res = sorted(list(resolutions), reverse=True)

                data = {
                    "url": webpage_url,
                    "title": title,
                    "duration": duration,
                    "uploader": uploader,
                    "thumbnail": thumbnail,
                    "resolutions": sorted_res,
                    "has_audio": has_audio,
                    "raw_info": info,
                }
                self.success.emit(data)

        except Exception as e:
            err_msg = str(e)
            if "Sign in to confirm you" in err_msg or "bot" in err_msg.lower():
                err_msg = (
                    "YouTube 触发了安全人机验证 (Sign in to confirm you're not a bot)。\n"
                    "建议：在下方导入 Cookie 文件 (cookies.txt)、指定浏览器 Cookie 或更换代理 IP 后重试。"
                )
            self.error.emit(f"解析失败: {err_msg}")


class YoutubeDownloadWorker(QThread):
    """YouTube 视频下载执行线程"""
    progress_changed = Signal(int, str)      # (百分比, 状态文本)
    speed_changed = Signal(str)             # 下载速度 / ETA
    log_message = Signal(str)               # 详细日志输出
    finished_task = Signal(bool, str)       # (是否成功, 文件路径或错误原因)

    def __init__(
        self,
        url: str,
        save_dir: str,
        quality_mode: str = "best",
        target_resolution: Optional[int] = None,
        audio_only: bool = False,
        audio_format: str = "mp3",
        proxy: Optional[str] = None,
        cookie_file: Optional[str] = None,
        browser_cookies: Optional[str] = None
    ):
        super().__init__()
        self.url = url.strip()
        self.save_dir = save_dir
        self.quality_mode = quality_mode
        self.target_resolution = target_resolution
        self.audio_only = audio_only
        self.audio_format = audio_format
        self.proxy = proxy.strip() if proxy else None
        self.cookie_file = cookie_file.strip() if cookie_file else None
        self.browser_cookies = browser_cookies.strip() if browser_cookies else None
        self._is_cancelled = False
        self.ffmpeg_path = find_ffmpeg_executable()

    def cancel(self):
        self._is_cancelled = True

    def _progress_hook(self, d: dict):
        if self._is_cancelled:
            raise Exception("用户已取消下载。")

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            pct = int((downloaded / total * 100)) if total > 0 else 0
            pct = max(0, min(95, pct))

            speed = d.get("speed", 0)
            eta = d.get("eta", 0)

            speed_str = f"{speed / (1024 * 1024):.2f} MB/s" if speed else "计算中..."
            eta_str = f"{eta} 秒" if eta else "计算中"
            info_str = f"速度: {speed_str} | 预计剩余: {eta_str}"

            self.progress_changed.emit(pct, f"正在下载数据... ({pct}%)")
            self.speed_changed.emit(info_str)

        elif status == "finished":
            self.progress_changed.emit(96, "下载完成，正在混流处理...")
            self.log_message.emit("[处理] 媒体流下载完毕，正在调用 FFmpeg 处理...")

    def run(self):
        try:
            import yt_dlp

            os.makedirs(self.save_dir, exist_ok=True)
            self.log_message.emit(f"[启动] 开始准备下载: {self.url}")
            if self.proxy:
                self.log_message.emit(f"[网络] 已启用代理通道: {self.proxy}")

            out_template = os.path.join(self.save_dir, "%(title)s.%(ext)s")

            ydl_opts = {
                "outtmpl": out_template,
                "progress_hooks": [self._progress_hook],
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }

            if self.proxy:
                ydl_opts["proxy"] = self.proxy

            if self.cookie_file and os.path.isfile(self.cookie_file):
                ydl_opts["cookiefile"] = self.cookie_file
            elif self.browser_cookies:
                ydl_opts["cookiesfrombrowser"] = (self.browser_cookies,)

            node_path = _get_node_runtime()
            if node_path:
                ydl_opts["js_runtimes"] = {"node": {"path": node_path}}

            if self.ffmpeg_path:
                ydl_opts["ffmpeg_location"] = os.path.dirname(self.ffmpeg_path)

            if self.audio_only:
                # 仅下载音频
                ydl_opts["format"] = "bestaudio/best"
                if self.ffmpeg_path:
                    ydl_opts["postprocessors"] = [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": self.audio_format,
                        "preferredquality": "320",
                    }]
            else:
                # 视频 + 音频最佳混流
                if self.target_resolution:
                    ydl_opts["format"] = f"bestvideo[height<={self.target_resolution}]+bestaudio/best[height<={self.target_resolution}]/best"
                else:
                    ydl_opts["format"] = "bestvideo+bestaudio/best"

                ydl_opts["merge_output_format"] = "mp4"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                raw_filename = ydl.prepare_filename(info)
                if self.audio_only and self.ffmpeg_path:
                    base, _ = os.path.splitext(raw_filename)
                    cand = f"{base}.{self.audio_format}"
                    filename = cand if os.path.isfile(cand) else (raw_filename if os.path.isfile(raw_filename) else cand)
                elif not self.audio_only:
                    base, _ = os.path.splitext(raw_filename)
                    cand = f"{base}.mp4"
                    filename = cand if os.path.isfile(cand) else (raw_filename if os.path.isfile(raw_filename) else cand)
                else:
                    filename = raw_filename

            self.progress_changed.emit(100, "下载与混流全部完成！")
            self.speed_changed.emit("任务完成")
            self.log_message.emit(f"[成功] 文件保存至: {filename}")
            self.finished_task.emit(True, filename)

        except Exception as e:
            if "用户已取消" in str(e):
                self.log_message.emit("[取消] 下载任务已被用户中止。")
                self.finished_task.emit(False, "已取消")
            else:
                self.log_message.emit(f"[错误] 下载失败: {str(e)}")
                self.finished_task.emit(False, str(e))
