"""
高清录音工具 - 核心录音与转码引擎 (Engine)
基于 FFmpeg dshow 底层捕获与 QtMultimedia 设备探测，支持精准时长计量、波形反馈与多格式压制。
"""

import os
import shutil
import sys
import time
import threading
import subprocess
from typing import List, Optional, Tuple
from PySide6.QtCore import QObject, Signal, QTimer
from toolbox.core.paths import find_ffmpeg_executable, get_audio_input_devices


def _suspend_process(pid: int):
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ntdll = ctypes.windll.ntdll
        PROCESS_ALL_ACCESS = 0x1F0FFF
        handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if handle:
            ntdll.NtSuspendProcess(handle)
            kernel32.CloseHandle(handle)
    except Exception:
        pass


def _resume_process(pid: int):
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ntdll = ctypes.windll.ntdll
        PROCESS_ALL_ACCESS = 0x1F0FFF
        handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if handle:
            ntdll.NtResumeProcess(handle)
            kernel32.CloseHandle(handle)
    except Exception:
        pass


class AudioRecorderSession(QObject):
    tick = Signal(float)              # 当前录制持续时长 (秒)
    status_changed = Signal(str)      # 状态文本: IDLE / RECORDING / PAUSED / FINISHED / ERROR
    level_updated = Signal(float)     # 实时模拟音量电平 (0.0 ~ 1.0)
    finished = Signal(str, float)     # (最终保存路径, 总时长秒)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.device_name: str = ""
        self.output_path: str = ""
        self.format_choice: str = "MP3"
        self.sample_rate: int = 44100
        self.channels: int = 2
        self.bitrate: str = "192k"

        self.process: Optional[subprocess.Popen] = None
        self.temp_wav_path: str = ""
        self.is_recording: bool = False
        self.is_paused: bool = False
        self.start_time: float = 0.0
        self.accumulated_seconds: float = 0.0

        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._on_timer)

    def start_recording(
        self,
        device_name: str,
        output_path: str,
        format_choice: str = "MP3",
        sample_rate: int = 44100,
        channels: int = 2,
        bitrate: str = "192k"
    ) -> Tuple[bool, str]:
        """启动录音进程"""
        ffmpeg_bin = find_ffmpeg_executable()
        if not ffmpeg_bin or not os.path.isfile(ffmpeg_bin):
            return False, "未找到有效的 FFmpeg 引擎二进制文件"

        self.device_name = device_name
        self.output_path = output_path
        self.format_choice = format_choice.upper()
        self.sample_rate = sample_rate
        self.channels = channels
        self.bitrate = bitrate

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        self.temp_wav_path = os.path.splitext(output_path)[0] + "_temp.wav"

        # 构建 FFmpeg dshow 录制命令
        # 兼容性：优先选用系统真实枚举到的 DirectShow 原生设备
        actual_dev = self.device_name
        if not actual_dev or actual_dev in ("默认音频输入设备", "default"):
            devs = get_audio_input_devices()
            real_devs = [d for d in devs if d not in ("默认音频输入设备", "default")]
            if real_devs:
                actual_dev = real_devs[0]
            else:
                return False, "未检测到可用的系统音频输入设备（麦克风），请检查硬件连接。"

        audio_target = f"audio={actual_dev}"
        cmd = [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "dshow",
            "-i", audio_target,
            "-ac", str(self.channels),
            "-ar", str(self.sample_rate),
            self.temp_wav_path
        ]

        startupinfo = None
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
                text=True,
                encoding="utf-8",
                errors="ignore"
            )
        except Exception as e:
            return False, f"创建录音进程失败: {e}"

        # 启动存活检查（等待 300ms 验证子进程未立即闪退崩溃）
        time.sleep(0.3)
        poll_res = self.process.poll()
        if poll_res is not None:
            self.process = None
            return False, f"录音引擎启动失败 (退出码 {poll_res}): 设备可能被占用或不支持当前采样参数"

        self.is_recording = True
        self.is_paused = False
        self.accumulated_seconds = 0.0
        self.start_time = time.time()
        self.timer.start()
        self.status_changed.emit("RECORDING")
        return True, ""

    def pause_recording(self):
        """暂停录制计时并挂起音频捕获进程"""
        if self.is_recording and not self.is_paused:
            self.accumulated_seconds += time.time() - self.start_time
            self.is_paused = True
            if self.process:
                _suspend_process(self.process.pid)
            self.status_changed.emit("PAUSED")

    def resume_recording(self):
        """恢复录制"""
        if self.is_recording and self.is_paused:
            if self.process:
                _resume_process(self.process.pid)
            self.start_time = time.time()
            self.is_paused = False
            self.status_changed.emit("RECORDING")

    def stop_recording(self) -> Tuple[bool, str]:
        """停止录音并将其规范化压制转码至用户指定的输出格式"""
        if not self.is_recording:
            return False, "当前未在录音状态"

        self.timer.stop()
        total_duration = self.accumulated_seconds
        if not self.is_paused:
            total_duration += time.time() - self.start_time
        elif self.process:
            # 恢复进程以接收退出信号
            _resume_process(self.process.pid)

        self.is_recording = False
        self.is_paused = False

        # 向 FFmpeg 发送 'q' 字符以实现优雅断开与文件写尾
        if self.process:
            try:
                if self.process.stdin:
                    try:
                        self.process.stdin.write("q\n")
                        self.process.stdin.flush()
                    except TypeError:
                        self.process.stdin.write(b"q\n")
                        self.process.stdin.flush()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.terminate()
                except Exception:
                    pass
            self.process = None

        # 检查临时录制文件
        if not os.path.exists(self.temp_wav_path) or os.path.getsize(self.temp_wav_path) == 0:
            self.status_changed.emit("ERROR")
            return False, "录音数据为空，请确认麦克风是否已插好并授予录音权限。"

        # 转码至目标输出格式
        ffmpeg_bin = find_ffmpeg_executable()
        out_fmt = self.format_choice
        temp_wav = self.temp_wav_path
        out_path = self.output_path
        bitrate = self.bitrate

        if out_fmt == "WAV":
            # 具备原子覆写特性的安全替换
            try:
                os.replace(temp_wav, out_path)
            except Exception:
                try:
                    shutil.copy2(temp_wav, out_path)
                    os.remove(temp_wav)
                except Exception as e2:
                    self.status_changed.emit("ERROR")
                    return False, f"保存录音文件失败: {e2}"
            self.status_changed.emit("FINISHED")
            self.finished.emit(out_path, total_duration)
            return True, ""
        else:
            self.status_changed.emit("TRANSCODING")

            def _async_transcode():
                out_dir = os.path.dirname(os.path.abspath(out_path))
                temp_transcode = os.path.join(out_dir, f"._rec_trans_{os.getpid()}_{os.path.basename(out_path)}")
                cmd = [
                    ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error",
                    "-i", temp_wav
                ]
                if out_fmt == "MP3":
                    cmd.extend(["-c:a", "libmp3lame", "-b:a", bitrate])
                elif out_fmt == "AAC":
                    cmd.extend(["-c:a", "aac", "-b:a", bitrate])
                elif out_fmt == "FLAC":
                    cmd.extend(["-c:a", "flac"])

                cmd.append(temp_transcode)
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                p_res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)

                if p_res.returncode == 0 and os.path.exists(temp_transcode) and os.path.getsize(temp_transcode) > 0:
                    try:
                        os.replace(temp_transcode, out_path)
                    except Exception:
                        try:
                            shutil.copy2(temp_transcode, out_path)
                            os.remove(temp_transcode)
                        except Exception:
                            self.status_changed.emit("ERROR")
                            return
                    try:
                        if os.path.exists(temp_wav):
                            os.remove(temp_wav)
                    except Exception:
                        pass
                    self.status_changed.emit("FINISHED")
                    self.finished.emit(out_path, total_duration)
                else:
                    if os.path.exists(temp_transcode):
                        try:
                            os.remove(temp_transcode)
                        except Exception:
                            pass
                    self.status_changed.emit("ERROR")

            t = threading.Thread(target=_async_transcode, daemon=True)
            t.start()
            return True, ""

    def _on_timer(self):
        if not self.is_recording:
            return

        if not self.is_paused:
            dur = self.accumulated_seconds + (time.time() - self.start_time)
            self.tick.emit(dur)

            # 模拟动态波形电平跳动
            import math, random
            t = time.time()
            base = 0.4 + 0.3 * math.sin(t * 5.0)
            noise = random.uniform(-0.15, 0.25)
            level = max(0.05, min(0.95, base + noise))
            self.level_updated.emit(level)
        else:
            self.level_updated.emit(0.0)


AudioRecorderEngine = AudioRecorderSession
