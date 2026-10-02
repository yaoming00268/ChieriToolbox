"""
高清屏幕录像机 - 核心录屏引擎 (Screen Recorder Engine)
基于 FFmpeg gdigrab 驱动，支持全屏、窗口与自定义矩形区域无损录像，集成音频混流与精准进程管控。
"""

import os
import sys
import time
import threading
import ctypes
import subprocess
from typing import List, Optional, Tuple, Dict, Any
from PySide6.QtCore import QObject, Signal, QTimer
from toolbox.core.paths import find_ffmpeg_executable, get_audio_input_devices


def get_virtual_desktop_rect() -> Tuple[int, int, int, int]:
    """获取所有屏幕组成的物理虚拟桌面包围盒 (x, y, w, h)，支持负坐标副屏"""
    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            vx = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
            vy = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
            vw = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
            vh = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
            if vw > 0 and vh > 0:
                return vx, vy, vw - (vw % 2), vh - (vh % 2)
        except Exception:
            pass

    try:
        from PySide6.QtGui import QGuiApplication
        screens = QGuiApplication.screens()
        if not screens:
            return 0, 0, 1920, 1080
        if len(screens) == 1:
            s = screens[0]
            dpr = s.devicePixelRatio()
            g = s.geometry()
            w = int(round(g.width() * dpr))
            h = int(round(g.height() * dpr))
            return 0, 0, w - (w % 2), h - (h % 2)

        min_x = min(int(round(s.geometry().x() * s.devicePixelRatio())) for s in screens)
        min_y = min(int(round(s.geometry().y() * s.devicePixelRatio())) for s in screens)
        max_r = max(int(round((s.geometry().x() + s.geometry().width()) * s.devicePixelRatio())) for s in screens)
        max_b = max(int(round((s.geometry().y() + s.geometry().height()) * s.devicePixelRatio())) for s in screens)
        w = max_r - min_x
        h = max_b - min_y
        return min_x, min_y, w - (w % 2), h - (h % 2)
    except Exception:
        return 0, 0, 1920, 1080


def get_available_screens() -> List[Dict[str, Any]]:
    """枚举系统中当前所有可用显示器屏幕及其物理分辨率位置 (支持负坐标副屏及 High-DPI 缩放物理坐标校准)"""
    screens_info = []
    try:
        from PySide6.QtGui import QGuiApplication
        screens = QGuiApplication.screens()

        # 尝试通过 Windows 原生 API 精确获取各显示器物理矩形
        win32_monitors = []
        if sys.platform == "win32":
            try:
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                class RECT(ctypes.Structure):
                    _fields_ = [('left', wintypes.LONG), ('top', wintypes.LONG), ('right', wintypes.LONG), ('bottom', wintypes.LONG)]
                class MONITORINFOEXW(ctypes.Structure):
                    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', RECT), ('rcWork', RECT), ('dwFlags', wintypes.DWORD), ('szDevice', wintypes.WCHAR * 32)]

                def _proc(hMon, hdc, lprc, data):
                    info = MONITORINFOEXW()
                    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
                    user32.GetMonitorInfoW(hMon, ctypes.byref(info))
                    win32_monitors.append((
                        info.rcMonitor.left,
                        info.rcMonitor.top,
                        info.rcMonitor.right - info.rcMonitor.left,
                        info.rcMonitor.bottom - info.rcMonitor.top,
                        bool(info.dwFlags & 1),
                        str(info.szDevice).strip()
                    ))
                    return True

                MonitorEnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM)
                user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_proc), 0)
            except Exception:
                win32_monitors = []

        used_w32_indices = set()
        for idx, s in enumerate(screens):
            geom = s.geometry()
            dpr = s.devicePixelRatio()
            is_primary = (s == QGuiApplication.primaryScreen())

            matched_w32 = None
            matched_i = -1
            if win32_monitors:
                s_name = s.name().strip().replace("\\\\", "\\").upper()
                for i, m in enumerate(win32_monitors):
                    if i in used_w32_indices:
                        continue
                    if m[5] and m[5].replace("\\\\", "\\").upper() == s_name:
                        matched_w32 = m
                        matched_i = i
                        break
                if not matched_w32 and is_primary:
                    for i, m in enumerate(win32_monitors):
                        if i in used_w32_indices:
                            continue
                        if m[4]:
                            matched_w32 = m
                            matched_i = i
                            break
                if not matched_w32:
                    best_dist = float("inf")
                    calc_x = geom.x() * dpr
                    calc_y = geom.y() * dpr
                    for i, m in enumerate(win32_monitors):
                        if i in used_w32_indices:
                            continue
                        dist = (m[0] - calc_x) ** 2 + (m[1] - calc_y) ** 2
                        if dist < best_dist:
                            best_dist = dist
                            matched_w32 = m
                            matched_i = i

            if matched_i >= 0:
                used_w32_indices.add(matched_i)

            if matched_w32:
                phys_x, phys_y, phys_w, phys_h, *_ = matched_w32
            else:
                phys_w = int(round(geom.width() * dpr))
                phys_h = int(round(geom.height() * dpr))
                phys_x = int(round(geom.x() * dpr))
                phys_y = int(round(geom.y() * dpr))

            phys_w = phys_w - (phys_w % 2)
            phys_h = phys_h - (phys_h % 2)

            title = f"屏幕 {idx + 1}: {phys_w}x{phys_h}"
            if abs(dpr - 1.0) > 0.01:
                title += f" (缩放 {int(round(dpr * 100))}%)"
            if is_primary:
                title += " (主显示器)"
            screens_info.append({
                "index": idx,
                "title": title,
                "name": s.name(),
                "x": phys_x,
                "y": phys_y,
                "width": phys_w,
                "height": phys_h,
                "logical_x": geom.x(),
                "logical_y": geom.y(),
                "logical_width": geom.width(),
                "logical_height": geom.height(),
                "dpr": dpr,
                "is_primary": is_primary
            })
    except Exception:
        pass
    return screens_info


def get_audio_output_devices() -> List[str]:
    """枚举系统中当前可用的音频输出/扬声器及立体声混音回路设备"""
    devices = []
    try:
        from PySide6.QtCore import QCoreApplication
        if not QCoreApplication.instance():
            QCoreApplication([])
        from PySide6.QtMultimedia import QMediaDevices
        for dev in QMediaDevices.audioOutputs():
            desc = dev.description().strip()
            if desc and desc not in devices:
                devices.append(desc)
    except Exception:
        pass

    # 探测 DirectShow 音频设备中可能的立体声混音或虚拟音频驱动
    ffmpeg_bin = find_ffmpeg_executable()
    if ffmpeg_bin and os.path.isfile(ffmpeg_bin):
        try:
            startupinfo = None
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            cmd = [ffmpeg_bin, "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
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
            in_audio = False
            for line in proc.stderr.splitlines():
                if "DirectShow audio devices" in line:
                    in_audio = True
                    continue
                if "DirectShow video devices" in line:
                    in_audio = False
                    continue
                if in_audio and '"]' in line and '"' in line:
                    parts = line.split('"')
                    if len(parts) >= 2:
                        d_name = parts[1].strip()
                        if d_name and not d_name.startswith("@") and d_name not in devices:
                            # 优先将混音/扬声器类设备保留
                            if any(k in d_name.lower() for k in ("stereo", "mix", "cable", "扬声器", "speaker", "output")):
                                devices.insert(0, d_name)
                            else:
                                devices.append(d_name)
        except Exception:
            pass

    return devices


def get_visible_windows() -> List[str]:
    """探测系统中当前可见且拥有标题栏的顶层窗口列表"""
    titles = []
    if sys.platform == "win32":
        try:
            EnumWindows = ctypes.windll.user32.EnumWindows
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            GetWindowTextW = ctypes.windll.user32.GetWindowTextW
            IsWindowVisible = ctypes.windll.user32.IsWindowVisible

            def callback(hwnd, extra):
                if IsWindowVisible(hwnd):
                    buf = ctypes.create_unicode_buffer(512)
                    GetWindowTextW(hwnd, buf, 512)
                    t = buf.value.strip()
                    if t and len(t) > 1 and t not in ("Program Manager", "Default IME", "MSCTFIME UI"):
                        titles.append(t)
                return True

            EnumWindows(EnumWindowsProc(callback), 0)
        except Exception:
            pass
    return sorted(list(set(titles)))


class ScreenRecorderEngine(QObject):
    tick = Signal(float)          # 录屏时长更新 (秒)
    status_changed = Signal(str)  # 状态: IDLE / RECORDING / PAUSED / FINISHED / ERROR
    finished = Signal(str, float) # (产物路径, 总录制秒数)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process: Optional[subprocess.Popen] = None
        self.is_recording: bool = False
        self.is_paused: bool = False
        self.output_path: str = ""
        self.start_time: float = 0.0
        self._pause_start_time: float = 0.0
        self._total_paused_duration: float = 0.0

        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self._on_timer)

    def start_recording(
        self,
        output_path: str,
        mode: str = "fullscreen",           # 'fullscreen' / 'screen' / 'window' / 'rect'
        window_title: str = "",
        rect: Optional[Tuple[int, int, int, int]] = None, # (x, y, w, h)
        screen_rect: Optional[Tuple[int, int, int, int]] = None, # (x, y, w, h)
        fps: int = 30,
        crf: int = 23,
        format_choice: str = "MP4",
        record_audio: bool = False,
        audio_device: str = "",
        system_audio_device: str = "",
        mic_device: str = "",
        draw_mouse: bool = True
    ) -> Tuple[bool, str]:
        """组装 FFmpeg 命令并启动录屏后台进程"""
        ffmpeg_bin = find_ffmpeg_executable()
        if not ffmpeg_bin or not os.path.isfile(ffmpeg_bin):
            return False, "未找到有效的 FFmpeg 引擎二进制文件"

        self.output_path = output_path
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        cmd = [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "gdigrab",
            "-framerate", str(fps),
            "-draw_mouse", "1" if draw_mouse else "0"
        ]

        # 视频画面输入源
        if mode == "window" and window_title:
            cmd.extend(["-i", f"title={window_title}"])
        elif mode == "rect" and rect:
            rx, ry, rw, rh = rect
            rw = rw - (rw % 2)
            rh = rh - (rh % 2)
            cmd.extend([
                "-offset_x", str(rx),
                "-offset_y", str(ry),
                "-video_size", f"{rw}x{rh}",
                "-i", "desktop"
            ])
        elif screen_rect:
            sx, sy, sw, sh = screen_rect
            sw = sw - (sw % 2)
            sh = sh - (sh % 2)
            cmd.extend([
                "-offset_x", str(sx),
                "-offset_y", str(sy),
                "-video_size", f"{sw}x{sh}",
                "-i", "desktop"
            ])
        else:
            # 全屏录制 (支持多显示器跨屏与负坐标副屏)
            vx, vy, vw, vh = get_virtual_desktop_rect()
            if vx != 0 or vy != 0:
                cmd.extend([
                    "-offset_x", str(vx),
                    "-offset_y", str(vy),
                    "-video_size", f"{vw}x{vh}",
                    "-i", "desktop"
                ])
            else:
                cmd.extend(["-i", "desktop"])

        # OBS 级音频选择机制 (系统声音与麦克风双轨混音)
        audio_sources = []

        def _resolve_audio_source(dev_name: str, is_mic: bool) -> Optional[Tuple[str, str]]:
            dev_str = dev_name.strip() if dev_name else ""
            if not dev_str or any(kw in dev_str for kw in ("不录制", "无设备", "未检测到")):
                return None

            if is_mic:
                mics = get_audio_input_devices()
                dev = dev_str if "默认" not in dev_str else (mics[0] if mics else "")
                if dev and dev not in ("默认音频输入设备", "无设备"):
                    return ("dshow", f"audio={dev}")
                return None
            else:
                # 系统内录：优先使用 Windows 官方推荐的 WASAPI Loopback 驱动
                try:
                    creationflags_chk = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                    chk = subprocess.run([ffmpeg_bin, "-devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creationflags_chk, timeout=3)
                    has_wasapi = "wasapi" in chk.stdout.lower() or "wasapi" in chk.stderr.lower()
                except Exception:
                    has_wasapi = False

                if has_wasapi:
                    return ("wasapi", "default")

                # 若当前 FFmpeg 未内置 wasapi，检查 DirectShow 中是否存在立体声混音或虚拟音频驱动 (VB-Cable 等)
                outs = get_audio_output_devices()
                loopback_cands = [o for o in outs if any(k in o.lower() for k in ("stereo", "mix", "cable", "混音", "loopback"))]
                if loopback_cands:
                    return ("dshow", f"audio={loopback_cands[0]}")
                if any(k in dev_str.lower() for k in ("stereo", "mix", "cable", "混音", "loopback")):
                    return ("dshow", f"audio={dev_str}")
                # 避免将不可作为 DirectShow 录入源的实体扬声器传入导致 FFmpeg 立即报错中断
                return None

        s_src = _resolve_audio_source(system_audio_device, is_mic=False) if system_audio_device else None
        m_src = _resolve_audio_source(mic_device, is_mic=True) if mic_device else None

        if s_src:
            audio_sources.append(s_src)
        if m_src and m_src not in audio_sources:
            audio_sources.append(m_src)

        # 兼容旧参数调用
        if not audio_sources and record_audio and audio_device:
            legacy_src = _resolve_audio_source(audio_device, is_mic=True)
            if legacy_src:
                audio_sources.append(legacy_src)

        has_audio = len(audio_sources) > 0
        for fmt_type, src in audio_sources:
            cmd.extend(["-f", fmt_type, "-i", src])

        fmt = format_choice.upper()
        if fmt == "GIF":
            cmd.extend(["-vf", f"fps={min(24, fps)},scale=trunc(iw/2)*2:trunc(ih/2)*2"])
        else:
            cmd.extend([
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "ultrafast",
                "-crf", str(crf)
            ])
            if len(audio_sources) == 2:
                # 混音系统声音 (1:a) 与麦克风 (2:a)，增加重采样防止采样率不一致崩溃
                cmd.extend([
                    "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                    "-map", "0:v",
                    "-map", "[aout]",
                    "-c:a", "aac",
                    "-b:a", "160k",
                    "-ar", "48000",
                    "-ac", "2"
                ])
            elif len(audio_sources) == 1:
                cmd.extend([
                    "-map", "0:v",
                    "-map", "1:a",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-ar", "48000",
                    "-ac", "2"
                ])

        cmd.append(output_path)

        startupinfo = None
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
        except Exception as e:
            return False, f"创建录屏进程失败: {e}"

        self.is_recording = True
        self.is_paused = False
        self.start_time = time.time()
        self._pause_start_time = 0.0
        self._total_paused_duration = 0.0
        self.timer.start()
        self.status_changed.emit("RECORDING")
        return True, ""

    def pause_recording(self) -> Tuple[bool, str]:
        """暂停录屏 (挂起 FFmpeg 进程与计时器)"""
        if not self.is_recording or self.is_paused or not self.process:
            return False, "当前未在录屏或已经处于暂停状态"

        if sys.platform == "win32":
            try:
                h_proc = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, self.process.pid)
                if h_proc:
                    ctypes.windll.ntdll.NtSuspendProcess(h_proc)
                    ctypes.windll.kernel32.CloseHandle(h_proc)
                    self.is_paused = True
                    self._pause_start_time = time.time()
                    self.status_changed.emit("PAUSED")
                    return True, "录屏已暂停"
            except Exception as e:
                return False, f"挂起录屏进程失败: {e}"

        self.is_paused = True
        self._pause_start_time = time.time()
        self.status_changed.emit("PAUSED")
        return True, "录屏已暂停"

    def resume_recording(self) -> Tuple[bool, str]:
        """继续录屏 (恢复 FFmpeg 进程与计时器)"""
        if not self.is_recording or not self.is_paused or not self.process:
            return False, "当前未处于暂停状态"

        if sys.platform == "win32":
            try:
                h_proc = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, self.process.pid)
                if h_proc:
                    ctypes.windll.ntdll.NtResumeProcess(h_proc)
                    ctypes.windll.kernel32.CloseHandle(h_proc)
            except Exception as e:
                return False, f"恢复录屏进程失败: {e}"

        self.is_paused = False
        if self._pause_start_time > 0:
            self._total_paused_duration += time.time() - self._pause_start_time
            self._pause_start_time = 0.0
        self.status_changed.emit("RECORDING")
        return True, "录屏已恢复继续"

    def stop_recording(self) -> Tuple[bool, str]:
        """安全停止录屏并封装视频容器"""
        if not self.is_recording:
            return False, "当前未处于录屏状态"

        if self.is_paused:
            self.resume_recording()

        self.timer.stop()
        total_duration = max(0.1, (time.time() - self.start_time) - self._total_paused_duration)
        self.is_recording = False
        self.is_paused = False

        proc = self.process
        self.process = None
        output_path = self.output_path

        if proc:
            try:
                # 发送 'q' 触发 ffmpeg 正常写入 moov 尾部
                proc.stdin.write(b"q\n")
                proc.stdin.flush()
            except Exception:
                pass

        self.status_changed.emit("FINALIZING")

        def _async_wait():
            if proc:
                try:
                    proc.wait(timeout=4)
                except Exception:
                    try:
                        proc.terminate()
                    except Exception:
                        pass

            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                self.status_changed.emit("ERROR")
                return

            self.status_changed.emit("FINISHED")
            self.finished.emit(output_path, total_duration)

        t = threading.Thread(target=_async_wait, daemon=True)
        t.start()
        return True, ""

    def _on_timer(self):
        if self.is_recording and not self.is_paused:
            dur = max(0.0, (time.time() - self.start_time) - self._total_paused_duration)
            self.tick.emit(dur)
