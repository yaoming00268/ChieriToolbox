"""
B站媒体下载器 - 下载与转码合并引擎
"""

import os
import re
import shutil
import subprocess
import time
import threading
import requests
from typing import Optional, Callable, Tuple, List, Dict, Any
from PySide6.QtCore import QThread, Signal
from .api import HEADERS, normalize_cookie, QUALITY_MAP


from toolbox.core.paths import find_ffmpeg_executable, sanitize_filename


def get_task_target_filename(task: dict, audio_only: bool = False, audio_format: str = "mp3") -> str:
    """计算单个下载任务对应的最终目标文件名"""
    title = str(task.get("title") or "video")
    part = str(task.get("part") or "")
    if not part or part == title or part in title:
        full_title = title
    elif title in part:
        full_title = part
    else:
        full_title = f"{title}_{part}"
    clean_title = sanitize_filename(full_title)
    if audio_only:
        fmt = (task.get("audio_format") or audio_format or "mp3").lower().strip()
        if fmt not in ("mp3", "m4a", "wav", "flac", "aac", "ogg"):
            fmt = "mp3"
        return f"{clean_title}.{fmt}"
    else:
        return f"{clean_title}.mp4"


def check_item_downloaded(task: dict, save_dir: str, audio_only: bool = False, audio_format: str = "mp3") -> Tuple[bool, str]:
    """检测指定任务在目标目录中是否已存在且完整 (> 1KB)"""
    if not save_dir or not os.path.isdir(save_dir):
        return False, ""
    filename = get_task_target_filename(task, audio_only=audio_only, audio_format=audio_format)
    target_path = os.path.join(save_dir, filename)
    if os.path.isfile(target_path) and os.path.getsize(target_path) > 1024:
        return True, target_path
    if not audio_only:
        alt_name = os.path.splitext(filename)[0] + "_video.mp4"
        alt_path = os.path.join(save_dir, alt_name)
        if os.path.isfile(alt_path) and os.path.getsize(alt_path) > 1024:
            return True, alt_path
    return False, target_path


class MediaDownloadWorker(QThread):
    progress_changed = Signal(int, str)  # (百分比, 状态描述)
    log_message = Signal(str)            # 日志信息
    finished_task = Signal(bool, str)    # (成功布尔值, 最终保存路径或错误原因)
    paused_status = Signal(bool)          # 是否处于暂停状态

    def __init__(
        self,
        video_url: str = "",
        audio_url: str = "",
        save_dir: str = "",
        title: str = "",
        audio_only: bool = False,
        audio_format: str = "mp3",
        ffmpeg_path: Optional[str] = None,
        cookie: Optional[str] = None,
        headers: Optional[dict] = None,
        proxies: Optional[dict] = None,
        cid: Optional[Any] = None,
        download_danmaku: bool = True
    ):
        super().__init__()
        self.video_url = video_url
        self.audio_url = audio_url
        self.save_dir = save_dir
        self.title = sanitize_filename(title)
        self.audio_only = audio_only
        self.audio_format = (audio_format or "mp3").lower().strip()
        self.ffmpeg_path = ffmpeg_path or find_ffmpeg_executable()
        self.cookie = normalize_cookie(cookie) if cookie else ""
        self.custom_headers = headers or {}
        self.proxies = proxies
        self.cid = cid
        self.download_danmaku = download_danmaku
        self._is_cancelled = False
        self._is_paused = False
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._last_pct = 0
        self._last_status = ""
        self._proc: Optional[subprocess.Popen] = None
        self._current_resp: Optional[requests.Response] = None

    def pause(self):
        if not self._is_paused and not self._is_cancelled:
            self._is_paused = True
            self._pause_event.clear()
            self.paused_status.emit(True)
            self.log_message.emit("[暂停] 下载已暂停。")
            self.progress_changed.emit(self._last_pct, "下载已暂停 (点击继续恢复)")

    def resume(self):
        if self._is_paused and not self._is_cancelled:
            self._is_paused = False
            self._pause_event.set()
            self.paused_status.emit(False)
            self.log_message.emit("[继续] 正在恢复下载...")
            self.progress_changed.emit(self._last_pct, self._last_status or "正在恢复下载...")

    def cancel(self):
        self._is_cancelled = True
        self._is_paused = False
        self._pause_event.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        if hasattr(self, "_current_resp") and self._current_resp:
            try:
                self._current_resp.close()
            except Exception:
                pass

    def run(self):
        if not self.save_dir:
            self.save_dir = os.getcwd()
        try:
            os.makedirs(self.save_dir, exist_ok=True)
        except Exception as e:
            self.log_message.emit(f"[错误] 创建保存目录失败: {e}")
            self.finished_task.emit(False, f"创建保存目录失败: {e}")
            return

        v_temp = os.path.join(self.save_dir, f".part_{self.title}_v.m4s")
        a_temp = os.path.join(self.save_dir, f".part_{self.title}_a.m4s")
        download_success = False

        try:
            # 1. 如果只要音频
            if self.audio_only:
                if not self.audio_url:
                    self.log_message.emit("[错误] 未找到可用音频流")
                    self.finished_task.emit(False, "未找到可用音频流")
                    return

                self.log_message.emit("[音频] 正在下载音频流...")
                ok = self._download_stream(self.audio_url, a_temp, "音频", weight=0.9)
                if not ok:
                    return

                if self._is_cancelled:
                    self.finished_task.emit(False, "已取消")
                    return

                # 支持多种音频导出格式: mp3, m4a, wav, flac, aac, ogg
                target_fmt = self.audio_format if self.audio_format in ("mp3", "m4a", "wav", "flac", "aac", "ogg") else "mp3"
                out_audio = os.path.join(self.save_dir, f"{self.title}.{target_fmt}")

                if self.ffmpeg_path and os.path.exists(self.ffmpeg_path):
                    self.log_message.emit(f"[转码] 正在通过 FFmpeg 转码为高品质 {target_fmt.upper()} 音频...")
                    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

                    if target_fmt == "mp3":
                        codec_args = ["-vn", "-acodec", "libmp3lame", "-q:a", "2"]
                    elif target_fmt == "m4a":
                        codec_args = ["-vn", "-c:a", "aac", "-b:a", "192k"]
                    elif target_fmt == "wav":
                        codec_args = ["-vn"]
                    elif target_fmt == "flac":
                        codec_args = ["-vn", "-c:a", "flac"]
                    elif target_fmt == "aac":
                        codec_args = ["-vn", "-c:a", "aac", "-b:a", "192k"]
                    elif target_fmt == "ogg":
                        codec_args = ["-vn", "-c:a", "libvorbis", "-q:a", "4"]
                    else:
                        codec_args = ["-vn", "-acodec", "libmp3lame", "-q:a", "2"]

                    cmd = [self.ffmpeg_path, "-y", "-i", a_temp] + codec_args + [out_audio]
                    self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
                    ret = self._proc.wait()
                    if self._is_cancelled:
                        self.finished_task.emit(False, "已取消")
                        return

                    if ret != 0 or not os.path.exists(out_audio) or os.path.getsize(out_audio) == 0:
                        self.log_message.emit(f"[错误] FFmpeg 音频转码为 {target_fmt.upper()} 失败 (退出码: {ret})")
                        self.finished_task.emit(False, f"FFmpeg 音频转码为 {target_fmt.upper()} 失败")
                        return

                    if os.path.exists(a_temp):
                        try:
                            os.remove(a_temp)
                        except Exception:
                            pass
                else:
                    if target_fmt != "m4a":
                        self.log_message.emit(f"[警告] 未检测到 FFmpeg，无法转码为 {target_fmt.upper()}，已保留原始 AAC 音频流 (.m4a)")
                    out_audio = os.path.join(self.save_dir, f"{self.title}.m4a")
                    try:
                        shutil.move(a_temp, out_audio)
                    except Exception as e:
                        self.finished_task.emit(False, f"保存音频失败: {e}")
                        return

                self.progress_changed.emit(100, f"音频下载与导出 ({target_fmt.upper()}) 完成！")
                download_success = True
                self.finished_task.emit(True, out_audio)
                return

            # 2. 正常视频+音频下载: 先下载音频流 (如果存在)
            if self.audio_url:
                self.log_message.emit("[音频] 正在下载音频流...")
                ok = self._download_stream(self.audio_url, a_temp, "音频", weight=0.4)
                if not ok:
                    return

            if self._is_cancelled:
                self.finished_task.emit(False, "已取消")
                return

            # 下载视频流
            if not self.video_url:
                self.log_message.emit("[错误] 视频流地址为空")
                self.finished_task.emit(False, "视频流地址为空")
                return

            self.log_message.emit("[视频] 正在下载视频流...")
            ok = self._download_stream(self.video_url, v_temp, "视频", weight=0.5, offset=40 if self.audio_url else 0.0)
            if not ok:
                return

            if self._is_cancelled:
                self.finished_task.emit(False, "已取消")
                return

            # 3. 合并音视频
            out_mp4 = os.path.join(self.save_dir, f"{self.title}.mp4")
            has_audio = bool(self.audio_url and os.path.exists(a_temp) and os.path.getsize(a_temp) > 0)

            if not self.ffmpeg_path or not os.path.exists(self.ffmpeg_path):
                self.log_message.emit("[警告] 未检测到 FFmpeg，无法自动混流。保留分离的媒体文件。")
                out_v = os.path.join(self.save_dir, f"{self.title}_video.mp4")
                shutil.move(v_temp, out_v)
                if has_audio:
                    out_a = os.path.join(self.save_dir, f"{self.title}_audio.m4a")
                    shutil.move(a_temp, out_a)
                self.finished_task.emit(True, out_v)
                return

            self.progress_changed.emit(92, "正在使用 FFmpeg 极速合并音视频...")
            self.log_message.emit("[混流] 正在执行音视频混流合并...")

            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

            last_stderr = ""
            if has_audio:
                # 优先尝试无损 stream copy (-c:v copy -c:a copy)
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-i", v_temp,
                    "-i", a_temp,
                    "-c:v", "copy",
                    "-c:a", "copy",
                    out_mp4
                ]
                self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=creationflags)
                _, stderr_out = self._proc.communicate()
                ret = self._proc.returncode
                if stderr_out:
                    last_stderr = stderr_out.decode("utf-8", errors="ignore")
                if self._is_cancelled:
                    self.finished_task.emit(False, "已取消")
                    return
                # 若 copy 不兼容则回退到 AAC 转码混流
                if ret != 0:
                    self.log_message.emit("[混流] 音频流复制不兼容，回退为 AAC 编码混流...")
                    cmd_fallback = [
                        self.ffmpeg_path, "-y",
                        "-i", v_temp,
                        "-i", a_temp,
                        "-c:v", "copy",
                        "-c:a", "aac",
                        out_mp4
                    ]
                    self._proc = subprocess.Popen(cmd_fallback, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=creationflags)
                    _, stderr_out = self._proc.communicate()
                    if stderr_out:
                        last_stderr = stderr_out.decode("utf-8", errors="ignore")
            else:
                # 无音频轨仅处理视频轨
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-i", v_temp,
                    "-c:v", "copy",
                    out_mp4
                ]
                self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=creationflags)
                _, stderr_out = self._proc.communicate()
                if stderr_out:
                    last_stderr = stderr_out.decode("utf-8", errors="ignore")

            if self._is_cancelled:
                self.finished_task.emit(False, "已取消")
                return

            if not os.path.exists(out_mp4) or os.path.getsize(out_mp4) == 0:
                err_detail = last_stderr.strip()[-300:] if last_stderr else "未获取到 stderr 异常信息"
                self.log_message.emit(f"[错误] FFmpeg 音视频混流失败: {err_detail}")
                self.finished_task.emit(False, f"FFmpeg 音视频混流失败: {err_detail}")
                return

            # 清理临时文件
            for p in (v_temp, a_temp):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

            # 生成同名 ASS 弹幕外挂字幕 (如果启用了弹幕下载且有有效 CID)
            if not self.audio_only and self.cid and self.download_danmaku:
                try:
                    self.log_message.emit(f"[弹幕] 正在拉取 B站弹幕并转换为高精度 ASS 字幕 (CID: {self.cid})...")
                    from .danmaku_to_ass import fetch_bilibili_danmaku_xml, DanmakuToAssConverter
                    xml_text = fetch_bilibili_danmaku_xml(self.cid, sessdata=self.cookie)
                    if xml_text:
                        ass_path = os.path.splitext(out_mp4)[0] + ".ass"
                        converter = DanmakuToAssConverter()
                        ass_content = converter.convert_to_ass(xml_text, title=self.title)
                        with open(ass_path, "w", encoding="utf-8-sig") as f_ass:
                            f_ass.write(ass_content)
                        self.log_message.emit(f"[弹幕] 已成功生成同名外挂字幕: {os.path.basename(ass_path)}")
                except Exception as e_dm:
                    self.log_message.emit(f"[警告] 弹幕转换出现异常: {e_dm}")

            self.progress_changed.emit(100, "音视频下载合并完成！")
            self.log_message.emit(f"[完成] 成功保存: {out_mp4}")
            download_success = True
            self.finished_task.emit(True, out_mp4)

        except Exception as e:
            self.log_message.emit(f"[错误] 下载或合并发生异常: {e}")
            self.finished_task.emit(False, str(e))
        finally:
            if not download_success and self._is_cancelled:
                for p in (v_temp, a_temp):
                    if os.path.exists(p):
                        try:
                            os.remove(p)
                        except Exception:
                            pass

    def _download_stream(self, url: str, save_path: str, label: str, weight: float = 0.5, offset: float = 0.0) -> bool:
        max_retries = 5
        downloaded = 0
        if os.path.exists(save_path):
            downloaded = os.path.getsize(save_path)
        total_size = 0
        start_time = time.time()
        last_speed_time = start_time
        last_downloaded = downloaded

        for attempt in range(max_retries):
            while self._is_paused and not self._is_cancelled:
                self._pause_event.wait(timeout=0.2)
            if self._is_cancelled:
                self.log_message.emit(f"[已取消] 用户已取消 {label} 下载。")
                self.finished_task.emit(False, "已取消")
                return False
            try:
                headers = dict(HEADERS)
                headers["Referer"] = "https://www.bilibili.com"
                if self.cookie:
                    headers["Cookie"] = self.cookie
                if self.custom_headers:
                    headers.update(self.custom_headers)
                if downloaded > 0:
                    headers["Range"] = f"bytes={downloaded}-"

                resp = requests.get(url, headers=headers, stream=True, timeout=20, proxies=self.proxies)
                self._current_resp = resp
                try:
                    if hasattr(resp, "raise_for_status"):
                        if resp.status_code == 416 and downloaded > 0:
                            return True
                        resp.raise_for_status()

                    # 若发送了 Range 请求但服务端未按 206 返回而是返回 200 全量流，需从头覆盖写入防破坏
                    if downloaded > 0 and resp.status_code == 200:
                        downloaded = 0

                    content_length = int(resp.headers.get("content-length", 0))
                    if downloaded > 0:
                        content_range = resp.headers.get("content-range", "")
                        if content_range and "/" in content_range:
                            try:
                                total_size = int(content_range.split("/")[-1])
                            except Exception:
                                total_size = downloaded + content_length
                        else:
                            total_size = downloaded + content_length
                    else:
                        total_size = content_length

                    mode = "ab" if downloaded > 0 else "wb"
                    with open(save_path, mode) as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 128):
                            while self._is_paused and not self._is_cancelled:
                                self._pause_event.wait(timeout=0.2)
                            if self._is_cancelled:
                                self.log_message.emit(f"[已取消] 用户已取消 {label} 下载。")
                                self.finished_task.emit(False, "已取消")
                                return False

                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                now = time.time()
                                dt = now - last_speed_time
                                if dt >= 0.5:
                                    speed_kb = ((downloaded - last_downloaded) / 1024) / max(0.01, dt)
                                    last_speed_time = now
                                    last_downloaded = downloaded

                                    pct = int(offset + (downloaded / total_size * 100 * weight)) if total_size > 0 else 0
                                    self._last_pct = min(90, pct)
                                    self._last_status = f"正在下载{label}... {speed_kb:.1f} KB/s"
                                    if not self._is_paused:
                                        self.progress_changed.emit(self._last_pct, self._last_status)

                    if total_size > 0 and downloaded < total_size:
                        raise IOError(f"下载流提前截断: 已接收 {downloaded}/{total_size} 字节")
                    return True
                finally:
                    self._current_resp = None
            except Exception as e:
                had_pause = self._is_paused
                while self._is_paused and not self._is_cancelled:
                    self._pause_event.wait(timeout=0.2)
                if self._is_cancelled:
                    self.finished_task.emit(False, "已取消")
                    return False

                if downloaded > 0 and total_size > 0 and downloaded >= total_size:
                    return True

                if had_pause:
                    # 暂停期间连接超时或断开，恢复后无损发起断点续传请求，不消耗网络故障重试次数
                    self.log_message.emit(f"[{label}] 暂停已恢复，正在重新建立长连接断点续传...")
                    continue

                self.log_message.emit(f"[{label}] 网络连接波动 ({e})，正在自动断点续传重试 ({attempt + 1}/{max_retries})...")
                time.sleep(1)
                if attempt == max_retries - 1:
                    if downloaded > 0 and (total_size == 0 or downloaded >= total_size):
                        return True
                    self.log_message.emit(f"[错误] {label} 流下载失败: {e}")
                    self.finished_task.emit(False, str(e))
                    return False

        return False


class BatchMediaDownloadWorker(QThread):
    item_started = Signal(int, int, str)          # (当前序号1起, 总任务数, 标题)
    progress_changed = Signal(int, str)           # (总体百分比, 状态描述)
    log_message = Signal(str)                     # 日志信息
    item_finished = Signal(int, int, bool, str)   # (当前序号, 总任务数, 是否成功, 保存路径或错误)
    batch_finished = Signal(int, int, list)       # (成功总数, 失败总数, 成功保存的路径列表)
    paused_status = Signal(bool)                  # 暂停状态信号

    def __init__(
        self,
        api,
        tasks: list,
        save_dir: str,
        target_qn: int = 80,
        audio_only: bool = False,
        audio_format: str = "mp3",
        ffmpeg_path: Optional[str] = None,
        cookie: Optional[str] = None,
        skip_existing: bool = True,
        download_danmaku: bool = True
    ):
        super().__init__()
        self.api = api
        self.tasks = tasks
        self.save_dir = save_dir
        self.target_qn = target_qn
        self.audio_only = audio_only
        self.audio_format = (audio_format or "mp3").lower().strip()
        self.ffmpeg_path = ffmpeg_path or find_ffmpeg_executable()
        self.cookie = normalize_cookie(cookie) if cookie else ""
        self.skip_existing = skip_existing
        self.download_danmaku = download_danmaku
        self._is_cancelled = False
        self._is_paused = False
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._current_worker: Optional[MediaDownloadWorker] = None

    def pause(self):
        self._is_paused = True
        self._pause_event.clear()
        self.paused_status.emit(True)
        if self._current_worker:
            self._current_worker.pause()

    def resume(self):
        self._is_paused = False
        self._pause_event.set()
        self.paused_status.emit(False)
        if self._current_worker:
            self._current_worker.resume()

    def cancel(self):
        self._is_cancelled = True
        self._is_paused = False
        self._pause_event.set()
        if self._current_worker:
            self._current_worker.cancel()

    def run(self):
        total = len(self.tasks)
        if total == 0:
            self.batch_finished.emit(0, 0, [])
            return

        success_count = 0
        fail_count = 0
        saved_paths = []

        self.log_message.emit(f"[批量任务] 启动批量下载队列，共 {total} 项待下载任务...")

        for idx, task in enumerate(self.tasks, 1):
            while self._is_paused and not self._is_cancelled:
                self._pause_event.wait(timeout=0.2)
            if self._is_cancelled:
                self.log_message.emit("[批量任务] 用户已取消剩余批量任务。")
                break

            if not isinstance(task, dict):
                continue

            bvid = task.get("bvid", "")
            cid = task.get("cid")
            title = str(task.get("title") or f"video_{idx}")
            part = str(task.get("part") or "")
            if not part or part == title or part in title:
                full_title = title
            elif title in part:
                full_title = part
            else:
                full_title = f"{title}_{part}"

            task_qn = task.get("qn") or self.target_qn
            task_audio_fmt = (task.get("audio_format") or self.audio_format or "mp3").lower().strip()

            # 智能检测是否已存在已下载完整文件
            if self.skip_existing:
                is_done, existing_p = check_item_downloaded(task, self.save_dir, self.audio_only, task_audio_fmt)
                if is_done:
                    self.log_message.emit(f"[{idx}/{total}] [已存在] 《{full_title}》检测到已下载完整文件，自动跳过: {os.path.basename(existing_p)}")
                    success_count += 1
                    saved_paths.append(existing_p)
                    self.item_finished.emit(idx, total, True, existing_p)
                    base_pct = int((idx / total) * 100)
                    self.progress_changed.emit(min(99, base_pct), f"[{idx}/{total}] 已存在，跳过")
                    continue

            self.item_started.emit(idx, total, full_title)
            qn_name = QUALITY_MAP.get(task_qn, f"{task_qn}P")
            self.log_message.emit(f"[{idx}/{total}] 准备下载: 《{full_title}》 (指定画质: {qn_name})...")

            # 1. 如果没有 cid，调用 get_video_info 获取
            if not cid:
                while self._is_paused and not self._is_cancelled:
                    self._pause_event.wait(timeout=0.2)
                if self._is_cancelled:
                    break
                try:
                    info = self.api.get_video_info(bvid)
                    while self._is_paused and not self._is_cancelled:
                        self._pause_event.wait(timeout=0.2)
                    if self._is_cancelled:
                        break
                    if info.get("success") and info.get("pages"):
                        page_num = task.get("page", 1)
                        matched_page = None
                        for p in info["pages"]:
                            if isinstance(p, dict) and p.get("page") == page_num:
                                matched_page = p
                                break
                        if not matched_page and info["pages"] and isinstance(info["pages"][0], dict):
                            matched_page = info["pages"][0]
                        cid = matched_page.get("cid") if isinstance(matched_page, dict) else None

                    if not cid:
                        if self._is_cancelled:
                            break
                        err = info.get("error", "获取视频信息失败或未找到有效CID")
                        self.log_message.emit(f"[{idx}/{total}] [错误] {err}")
                        self.item_finished.emit(idx, total, False, err)
                        fail_count += 1
                        continue
                except Exception as e:
                    if self._is_cancelled:
                        break
                    self.log_message.emit(f"[{idx}/{total}] [错误] 获取元数据异常: {e}")
                    self.item_finished.emit(idx, total, False, str(e))
                    fail_count += 1
                    continue

            while self._is_paused and not self._is_cancelled:
                self._pause_event.wait(timeout=0.2)
            if self._is_cancelled:
                break

            # 2. 获取播放流 (使用当前任务指定的画质 task_qn)
            try:
                stream_res = self.api.get_play_streams(bvid, cid, qn=task_qn)
                while self._is_paused and not self._is_cancelled:
                    self._pause_event.wait(timeout=0.2)
                if self._is_cancelled:
                    break
                if not stream_res.get("success"):
                    err = stream_res.get("error", "获取播放流失败")
                    self.log_message.emit(f"[{idx}/{total}] [错误] {err}")
                    self.item_finished.emit(idx, total, False, err)
                    fail_count += 1
                    continue
            except Exception as e:
                if self._is_cancelled:
                    break
                self.log_message.emit(f"[{idx}/{total}] [错误] 获取播放流异常: {e}")
                self.item_finished.emit(idx, total, False, str(e))
                fail_count += 1
                continue

            v_url = stream_res.get("video_url", "")
            a_url = stream_res.get("audio_url", "")

            # 3. 创建单条工作工件并监听
            item_done = [False, False, ""]

            worker = MediaDownloadWorker(
                video_url=v_url,
                audio_url=a_url,
                save_dir=self.save_dir,
                title=full_title,
                audio_only=self.audio_only,
                audio_format=task_audio_fmt,
                ffmpeg_path=self.ffmpeg_path,
                cookie=self.cookie,
                cid=cid,
                download_danmaku=self.download_danmaku
            )

            def _on_item_progress(pct, msg):
                base_pct = int(((idx - 1) / total) * 100)
                item_contrib = int((pct / 100) * (100 / total))
                overall_pct = min(99, base_pct + item_contrib)
                self.progress_changed.emit(overall_pct, f"[{idx}/{total}] {msg}")

            def _on_item_log(msg):
                self.log_message.emit(f"[{idx}/{total}] {msg}")

            def _on_item_finished(ok, res):
                item_done[0] = True
                item_done[1] = ok
                item_done[2] = res

            worker.progress_changed.connect(_on_item_progress)
            worker.log_message.connect(_on_item_log)
            worker.finished_task.connect(_on_item_finished)

            try:
                self._current_worker = worker
                if self._is_paused:
                    worker.pause()
                worker.run()
            finally:
                self._current_worker = None

            if self._is_cancelled:
                self.log_message.emit("[批量任务] 已取消后续任务。")
                break

            if item_done[1]:
                success_count += 1
                saved_paths.append(item_done[2])
                self.item_finished.emit(idx, total, True, item_done[2])
            else:
                fail_count += 1
                self.item_finished.emit(idx, total, False, item_done[2])

        if self._is_cancelled:
            self.progress_changed.emit(int(((success_count + fail_count) / total) * 100) if total else 0, f"批量任务已取消 (已完成: {success_count}，失败: {fail_count})")
        else:
            self.progress_changed.emit(100, f"批量任务完成 (成功: {success_count}，失败: {fail_count})")
        self.batch_finished.emit(success_count, fail_count, saved_paths)


