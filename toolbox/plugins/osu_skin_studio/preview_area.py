"""
osu!mania 皮肤调校工作台 - 舞台实时渲染画布
"""

import os
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtWidgets import QWidget
from .render_utils import get_mania_layout


class ManiaPreviewArea(QWidget):
    def __init__(self, parser, parent=None):
        super().__init__(parent)
        self.parser = parser
        self.skin_dir = ""
        self.current_keys = "4"
        self.aspect_ratio = 16.0 / 9.0
        self.init_ui()

    def init_ui(self):
        self.setMinimumSize(400, 480)
        self.setStyleSheet("background-color: #09090b; border: 1px solid #27272a; border-radius: 8px;")

    def set_skin_dir(self, directory: str):
        self.skin_dir = directory
        self.update()

    def set_keys(self, keys: str):
        self.current_keys = str(keys)
        self.update()

    def set_aspect_ratio(self, ratio_str: str):
        if ratio_str == "4:3":
            self.aspect_ratio = 4.0 / 3.0
        elif ratio_str == "21:9":
            self.aspect_ratio = 21.0 / 9.0
        else:
            self.aspect_ratio = 16.0 / 9.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 绘制背景
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(15, 15, 18))

        # 计算视口缩放与宽高比
        virtual_h = 480.0
        virtual_w = virtual_h * self.aspect_ratio
        scale = h / virtual_h
        offset_x = max(0.0, (w - virtual_w * scale) / 2.0)

        # 绘制游戏视野区域 (Playfield)
        painter.fillRect(QRectF(offset_x, 0, virtual_w * scale, h), QColor(24, 24, 28))

        # 读取 Mania 节配置
        section = self.parser.get_mania_section(self.current_keys) or {}
        try:
            keys_num = int(self.current_keys)
        except ValueError:
            keys_num = 4

        col_widths, hit_pos, upside_down, col_start = get_mania_layout(section, keys_num)

        playfield_center = virtual_w / 2.0
        playfield_left = playfield_center - 320.0
        absolute_col_start = playfield_left + col_start

        curr_x = offset_x + absolute_col_start * scale
        visual_hit_y = hit_pos * scale
        if upside_down:
            visual_hit_y = h - visual_hit_y

        # 1. 绘制轨道舞台背景与轨道线
        total_w = sum(col_widths) * scale
        painter.fillRect(QRectF(curr_x, 0, total_w, h), QColor(10, 10, 12, 230))

        col_x_cursor = curr_x
        rail_pen = QPen(QColor(60, 60, 70), 1)
        painter.setPen(rail_pen)

        for i, cw in enumerate(col_widths):
            actual_cw = cw * scale
            # 绘制右边界线
            painter.drawLine(int(col_x_cursor + actual_cw), 0, int(col_x_cursor + actual_cw), h)

            # 绘制模拟音符
            note_color = QColor(56, 189, 248) if (i % 2 == 0) else QColor(244, 63, 94)
            painter.fillRect(QRectF(col_x_cursor + 2, visual_hit_y - 80 * (i + 1), actual_cw - 4, 18), note_color)

            # 底部按键位置
            painter.fillRect(QRectF(col_x_cursor + 2, visual_hit_y, actual_cw - 4, 30), QColor(80, 80, 95, 180))

            col_x_cursor += actual_cw

        # 绘制舞台左边界线
        painter.drawLine(int(curr_x), 0, int(curr_x), h)

        # 2. 绘制判定线 (HitPosition)
        hit_pen = QPen(QColor(239, 68, 68), 2)
        painter.setPen(hit_pen)
        painter.drawLine(int(curr_x), int(visual_hit_y), int(curr_x + total_w), int(visual_hit_y))

        # 3. 绘制文字标签
        painter.setPen(QColor(244, 244, 245))
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        painter.drawText(int(curr_x + 6), int(visual_hit_y - 6), f"判定线 HitPosition: {int(hit_pos)}")
