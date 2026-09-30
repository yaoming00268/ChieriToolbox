"""
高清录音工具 - 动态声波可视化电平表 (Waveform Visualizer)
采用高采样率平滑贝塞尔与对称圆角频段渲染，提供极富科技感的动态音频频谱视觉反馈。
"""

import math
import random
from typing import List
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QBrush
from PySide6.QtWidgets import QWidget


class WaveformVisualizer(QWidget):
    def __init__(self, num_bars: int = 36, parent=None):
        super().__init__(parent)
        self.num_bars = num_bars
        self.bars: List[float] = [0.08] * num_bars
        self.target_level: float = 0.0
        self.is_active: bool = False
        self.is_paused: bool = False

        self.setFixedHeight(70)

        # 刷新定时器 (40 FPS 平滑动画)
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(25)
        self.anim_timer.timeout.connect(self._update_animation)
        self.anim_timer.start()

    def set_level(self, level: float):
        """传入实时音量电平 (0.0 - 1.0)"""
        self.target_level = max(0.05, min(1.0, level))

    def set_state(self, active: bool, paused: bool = False):
        self.is_active = active
        self.is_paused = paused
        if not active:
            self.target_level = 0.05

    def _update_animation(self):
        for i in range(self.num_bars):
            if self.is_active and not self.is_paused:
                dist_from_center = abs(i - (self.num_bars / 2)) / (self.num_bars / 2)
                factor = 1.0 - (0.5 * dist_from_center)
                rnd = random.uniform(0.7, 1.3)
                target = min(0.95, self.target_level * factor * rnd)
                # 平滑插值靠近目标值
                self.bars[i] += (target - self.bars[i]) * 0.35
            else:
                # 待机微弱律动
                self.bars[i] += (0.08 - self.bars[i]) * 0.2
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()

        bar_width = max(3.0, (w - (self.num_bars - 1) * 4) / float(self.num_bars))
        total_w = self.num_bars * bar_width + (self.num_bars - 1) * 4
        start_x = (w - total_w) / 2.0

        for i, val in enumerate(self.bars):
            bar_h = max(6.0, val * (h - 12))
            x = start_x + i * (bar_width + 4)
            y = (h - bar_h) / 2.0

            grad = QLinearGradient(x, y, x, y + bar_h)
            if self.is_paused:
                grad.setColorAt(0.0, QColor("#fbbf24"))
                grad.setColorAt(1.0, QColor("#d97706"))
            elif self.is_active:
                grad.setColorAt(0.0, QColor("#38bdf8"))
                grad.setColorAt(1.0, QColor("#2563eb"))
            else:
                grad.setColorAt(0.0, QColor("#475569"))
                grad.setColorAt(1.0, QColor("#334155"))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(x, y, bar_width, bar_h, 3, 3)

        painter.end()
