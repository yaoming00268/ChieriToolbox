"""
交互式白板 (希沃风) - 核心绘图画布引擎 (Canvas Engine)
双缓冲防闪烁架构，支持平滑手写笔、荧光记号笔、形状绘制、橡皮擦除、网格教学背景与多级历史回退。
"""

import math
from typing import List, Optional, Tuple
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import (
    QPainter, QPixmap, QColor, QPen, QBrush, QPolygon,
    QFont, QImage
)
from PySide6.QtWidgets import QWidget, QInputDialog


class WhiteboardCanvas(QWidget):
    can_undo_changed = Signal(bool)
    can_redo_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

        self.current_tool: str = "pen"           # 'pen' / 'highlighter' / 'eraser' / 'line' / 'arrow' / 'rect' / 'circle' / 'text'
        self.current_color: QColor = QColor("#2563eb")
        self.stroke_width: int = 4
        self.bg_style: str = "white"              # 'white' / 'dark' / 'green' / 'grid' / 'dots'

        self.canvas_pixmap: Optional[QPixmap] = QPixmap(800, 600)
        self.canvas_pixmap.fill(Qt.transparent)
        self.undo_stack: List[QPixmap] = [self.canvas_pixmap.copy()]
        self.redo_stack: List[QPixmap] = []
        self.max_history: int = 30

        self.start_pos: Optional[QPoint] = None
        self.last_pos: Optional[QPoint] = None
        self.current_pos: Optional[QPoint] = None
        self.is_drawing: bool = False

    def set_tool(self, tool: str):
        self.current_tool = tool

    def set_color(self, color: QColor):
        self.current_color = color

    def set_stroke_width(self, width: int):
        self.stroke_width = max(1, min(50, width))

    def set_bg_style(self, style: str):
        self.bg_style = style
        self.update()

    def resizeEvent(self, event):
        w = max(100, self.width())
        h = max(100, self.height())

        if self.canvas_pixmap is None:
            self.canvas_pixmap = QPixmap(w, h)
            self.canvas_pixmap.fill(Qt.transparent)
            self._save_undo_state()
        elif w > self.canvas_pixmap.width() or h > self.canvas_pixmap.height():
            new_pix = QPixmap(max(w, self.canvas_pixmap.width()), max(h, self.canvas_pixmap.height()))
            new_pix.fill(Qt.transparent)
            p = QPainter(new_pix)
            p.drawPixmap(0, 0, self.canvas_pixmap)
            p.end()
            self.canvas_pixmap = new_pix

        super().resizeEvent(event)

    def _save_undo_state(self):
        if self.canvas_pixmap:
            self.undo_stack.append(self.canvas_pixmap.copy())
            if len(self.undo_stack) > self.max_history:
                self.undo_stack.pop(0)
            self.redo_stack.clear()
            self.can_undo_changed.emit(len(self.undo_stack) > 1)
            self.can_redo_changed.emit(False)

    def _adapt_pixmap_size(self, pix: QPixmap) -> QPixmap:
        w = max(100, self.width(), self.canvas_pixmap.width() if self.canvas_pixmap else 100)
        h = max(100, self.height(), self.canvas_pixmap.height() if self.canvas_pixmap else 100)
        if pix.width() < w or pix.height() < h:
            new_pix = QPixmap(max(w, pix.width()), max(h, pix.height()))
            new_pix.fill(Qt.transparent)
            p = QPainter(new_pix)
            p.drawPixmap(0, 0, pix)
            p.end()
            return new_pix
        return pix.copy()

    def undo(self):
        if len(self.undo_stack) > 1:
            curr = self.undo_stack.pop()
            self.redo_stack.append(curr)
            if len(self.redo_stack) > self.max_history:
                self.redo_stack.pop(0)
            self.canvas_pixmap = self._adapt_pixmap_size(self.undo_stack[-1])
            self.can_undo_changed.emit(len(self.undo_stack) > 1)
            self.can_redo_changed.emit(True)
            self.update()

    def redo(self):
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append(state)
            if len(self.undo_stack) > self.max_history:
                self.undo_stack.pop(0)
            self.canvas_pixmap = self._adapt_pixmap_size(state)
            self.can_undo_changed.emit(True)
            self.can_redo_changed.emit(len(self.redo_stack) > 0)
            self.update()

    def clear_canvas(self):
        if self.canvas_pixmap:
            self.canvas_pixmap.fill(Qt.transparent)
            self._save_undo_state()
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.last_pos = event.pos()
            self.current_pos = event.pos()
            self.is_drawing = True

            if self.current_tool == "text":
                self._handle_text_tool(event.pos())
                self.is_drawing = False
                return

            if self.current_tool in ("pen", "highlighter", "eraser"):
                # 开始自由路径绘制
                self._draw_segment(self.last_pos, self.current_pos)
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_drawing and self.canvas_pixmap:
            self.current_pos = event.pos()
            if self.current_tool in ("pen", "highlighter", "eraser"):
                self._draw_segment(self.last_pos, self.current_pos)
                self.last_pos = self.current_pos
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_drawing:
            self.current_pos = event.pos()
            self.is_drawing = False

            # 将形状工具最终写入画布
            if self.current_tool in ("line", "arrow", "rect", "circle"):
                self._commit_shape(self.start_pos, self.current_pos)

            self._save_undo_state()
            self.update()

    def _draw_segment(self, p1: QPoint, p2: QPoint):
        if not self.canvas_pixmap:
            return

        painter = QPainter(self.canvas_pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self.current_tool == "eraser":
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            pen = QPen(Qt.transparent, self.stroke_width * 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(p1, p2)
        elif self.current_tool == "highlighter":
            hl_color = QColor(self.current_color)
            hl_color.setAlpha(90)
            pen = QPen(hl_color, self.stroke_width * 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(p1, p2)
        else:
            pen = QPen(self.current_color, self.stroke_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(p1, p2)

        painter.end()

    def _commit_shape(self, p1: QPoint, p2: QPoint):
        if not self.canvas_pixmap or not p1 or not p2:
            return

        painter = QPainter(self.canvas_pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(self.current_color, self.stroke_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        if self.current_tool == "line":
            painter.drawLine(p1, p2)
        elif self.current_tool == "arrow":
            self._draw_arrow(painter, p1, p2)
        elif self.current_tool == "rect":
            rect = QRect(p1, p2).normalized()
            painter.drawRect(rect)
        elif self.current_tool == "circle":
            rect = QRect(p1, p2).normalized()
            painter.drawEllipse(rect)

        painter.end()

    def _draw_arrow(self, painter: QPainter, p1: QPoint, p2: QPoint):
        painter.drawLine(p1, p2)
        # 计算箭头头部夹角
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        angle = math.atan2(dy, dx)
        arrow_len = max(12.0, self.stroke_width * 3.5)

        p_arrow1 = QPoint(
            int(p2.x() - arrow_len * math.cos(angle - math.pi / 6)),
            int(p2.y() - arrow_len * math.sin(angle - math.pi / 6))
        )
        p_arrow2 = QPoint(
            int(p2.x() - arrow_len * math.cos(angle + math.pi / 6)),
            int(p2.y() - arrow_len * math.sin(angle + math.pi / 6))
        )

        painter.setBrush(QBrush(self.current_color))
        poly = QPolygon([p2, p_arrow1, p_arrow2])
        painter.drawPolygon(poly)

    def _handle_text_tool(self, pos: QPoint):
        text, ok = QInputDialog.getText(self, "添加文字批注", "请输入文字内容:")
        if ok and text.strip() and self.canvas_pixmap:
            painter = QPainter(self.canvas_pixmap)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            painter.setFont(QFont("Microsoft YaHei", max(12, self.stroke_width * 4), QFont.Bold))
            painter.setPen(self.current_color)
            painter.drawText(pos.x(), pos.y(), text.strip())
            painter.end()
            self._save_undo_state()
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        w = self.width()
        h = self.height()

        # 1. 绘制白板底色与教学辅助纹理
        if self.bg_style == "dark":
            painter.fillRect(self.rect(), QColor("#1e293b"))
        elif self.bg_style == "green":
            painter.fillRect(self.rect(), QColor("#14532d"))
        elif self.bg_style == "grid":
            painter.fillRect(self.rect(), QColor("#ffffff"))
            painter.setPen(QPen(QColor("#f1f5f9"), 1))
            step = 30
            for x in range(0, w, step):
                painter.drawLine(x, 0, x, h)
            for y in range(0, h, step):
                painter.drawLine(0, y, w, y)
        elif self.bg_style == "dots":
            painter.fillRect(self.rect(), QColor("#ffffff"))
            painter.setPen(QPen(QColor("#cbd5e1"), 2))
            step = 32
            for x in range(step, w, step):
                for y in range(step, h, step):
                    painter.drawPoint(x, y)
        else:
            painter.fillRect(self.rect(), QColor("#ffffff"))

        # 2. 绘制已固化的画笔图层
        if self.canvas_pixmap:
            painter.drawPixmap(0, 0, self.canvas_pixmap)

        # 3. 若正在绘制形状，绘制实时预览动态辅助线
        if self.is_drawing and self.start_pos and self.current_pos:
            if self.current_tool in ("line", "arrow", "rect", "circle"):
                painter.setRenderHint(QPainter.Antialiasing, True)
                pen = QPen(self.current_color, self.stroke_width, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)

                p1 = self.start_pos
                p2 = self.current_pos
                if self.current_tool == "line":
                    painter.drawLine(p1, p2)
                elif self.current_tool == "arrow":
                    self._draw_arrow(painter, p1, p2)
                elif self.current_tool == "rect":
                    painter.drawRect(QRect(p1, p2).normalized())
                elif self.current_tool == "circle":
                    painter.drawEllipse(QRect(p1, p2).normalized())

        painter.end()

    def export_image(self, file_path: str) -> bool:
        """完整合成底色与笔迹并导出为高清位图"""
        try:
            w = max(100, self.width())
            h = max(100, self.height())
            export_pix = QPixmap(w, h)

            painter = QPainter(export_pix)
            # 绘制底色
            if self.bg_style == "dark":
                painter.fillRect(export_pix.rect(), QColor("#1e293b"))
            elif self.bg_style == "green":
                painter.fillRect(export_pix.rect(), QColor("#14532d"))
            elif self.bg_style == "grid":
                painter.fillRect(export_pix.rect(), QColor("#ffffff"))
                painter.setPen(QPen(QColor("#e2e8f0"), 1))
                step = 30
                for x in range(0, w, step):
                    painter.drawLine(x, 0, x, h)
                for y in range(0, h, step):
                    painter.drawLine(0, y, w, y)
            elif self.bg_style == "dots":
                painter.fillRect(export_pix.rect(), QColor("#ffffff"))
                painter.setPen(QPen(QColor("#cbd5e1"), 2))
                step = 32
                for x in range(step, w, step):
                    for y in range(step, h, step):
                        painter.drawPoint(x, y)
            else:
                painter.fillRect(export_pix.rect(), QColor("#ffffff"))

            if self.canvas_pixmap:
                painter.drawPixmap(0, 0, self.canvas_pixmap)
            painter.end()

            return export_pix.save(file_path)
        except Exception:
            return False
