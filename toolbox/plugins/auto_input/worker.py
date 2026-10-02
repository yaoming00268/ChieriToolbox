"""
模拟键入与极速粘贴助手 - 输入执行核心
支持全局热键监听、字间延迟模拟输入、目标窗口焦点保护。
"""

import sys
import time
import ctypes
from typing import Optional, Tuple
from PySide6.QtCore import QObject, Signal, QThread

# 尝试导入 keyboard 与 pyperclip
try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False


class TypingWorker(QThread):
    finished_typing = Signal(str)

    def __init__(self, text: str, delay: float, use_clipboard: bool, parent=None):
        super().__init__(parent)
        self.text = text
        self.delay = delay
        self.use_clipboard = use_clipboard
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def run(self):
        # 稍微等待热键弹起
        time.sleep(0.2)
        if self._stop_flag:
            return

        target_text = ""
        if self.use_clipboard and HAS_PYPERCLIP:
            target_text = pyperclip.paste()
        else:
            target_text = self.text

        if not target_text:
            self.finished_typing.emit("警告: 待键入文本内容为空")
            return

        target_hwnd = ctypes.windll.user32.GetForegroundWindow() if sys.platform == "win32" else 0

        try:
            for char in target_text:
                if self._stop_flag:
                    break

                # 保留可见字符与回车换行制表符
                if not char.isprintable() and char not in ('\n', '\r', '\t'):
                    continue

                if sys.platform == "win32":
                    curr_hwnd = ctypes.windll.user32.GetForegroundWindow()
                    if curr_hwnd != target_hwnd:
                        self.finished_typing.emit("检测到前台窗口焦点切换，模拟键入已安全自动停止")
                        return

                keyboard.write(char)
                sleep_end = time.time() + self.delay
                while time.time() < sleep_end:
                    if self._stop_flag:
                        break
                    time.sleep(min(0.01, max(0.001, sleep_end - time.time())))

            if not self._stop_flag:
                self.finished_typing.emit(f"输入完成 (共 {len(target_text)} 字符)，继续监听中...")
            else:
                self.finished_typing.emit("输入已中止")
        except Exception as e:
            self.finished_typing.emit(f"模拟输入错误: {e}")


class PasteSimulatorWorker(QObject):
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text_to_paste = ""
        self.hotkey_str = "Ctrl+Alt+V"
        self.delay = 0.03
        self.use_clipboard = False
        self.is_running = False
        self._hotkey_hook = None
        self._typing_worker: Optional[TypingWorker] = None

    def update_config(self, hotkey: str, delay: float, use_clipboard: bool, text: str):
        self.hotkey_str = hotkey
        self.delay = delay
        self.use_clipboard = use_clipboard
        self.text_to_paste = text

        if self.is_running:
            # 重新应用监听
            self.stop_listening()
            self.start_listening()

    def set_text(self, text: str):
        self.text_to_paste = text

    def start_listening(self) -> Tuple[bool, str]:
        if not HAS_KEYBOARD:
            msg = "系统未安装 keyboard 库，无法启用全局快捷键监听"
            self.status_changed.emit(msg)
            return False, msg

        self.stop_listening()
        norm_hotkey = self.hotkey_str.lower().replace("meta", "windows")

        try:
            self._hotkey_hook = keyboard.add_hotkey(norm_hotkey, self._on_hotkey_triggered)
            self.is_running = True
            msg = f"全局监听已开启 · 快捷键 [{self.hotkey_str}] 就绪"
            self.status_changed.emit(msg)
            return True, msg
        except Exception as e:
            self.is_running = False
            msg = f"热键绑定失败: {e}"
            self.status_changed.emit(msg)
            return False, msg

    @property
    def is_typing(self) -> bool:
        return self._typing_worker is not None and self._typing_worker.isRunning()

    def stop_listening(self):
        if self._typing_worker:
            if self._typing_worker.isRunning():
                self._typing_worker.stop()
                self._typing_worker.wait(1500)
            self._typing_worker = None

        if self._hotkey_hook and HAS_KEYBOARD:
            try:
                keyboard.remove_hotkey(self._hotkey_hook)
            except Exception:
                pass
            self._hotkey_hook = None
        self.is_running = False
        self.status_changed.emit("已停止监听")

    def _on_hotkey_triggered(self):
        if self.is_typing:
            if self._typing_worker:
                self._typing_worker.stop()
            return

        self.status_changed.emit("正在模拟输入中...")
        self._typing_worker = TypingWorker(self.text_to_paste, self.delay, self.use_clipboard)
        self._typing_worker.finished_typing.connect(self._on_typing_finished)
        self._typing_worker.start()

    def _on_typing_finished(self, msg: str):
        self.status_changed.emit(msg)
