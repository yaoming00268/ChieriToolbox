"""
高清屏幕录像机 - 矩形区域选区捕获遮罩 (Region Selector)
"""

from typing import Optional, Callable, Tuple
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QGuiApplication
from PySide6.QtWidgets import QWidget


class RegionSelectOverlay(QWidget):
    region_selected = Signal(int, int, int, int)  # (x, y, w, h)

    def __init__(self, on_selected: Optional[Callable[[int, int, int, int], None]] = None, parent=None):
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.on_selected = on_selected

        screens = QGuiApplication.screens()
        virtual_geo = QRect()
        for s in screens:
            virtual_geo = virtual_geo.united(s.geometry())
        if virtual_geo.isEmpty():
            virtual_geo = QRect(0, 0, 1920, 1080)
        self.virtual_geo = virtual_geo
        self.setGeometry(virtual_geo)
        self.setCursor(Qt.CrossCursor)

        self.start_pos: Optional[QPoint] = None
        self.current_pos: Optional[QPoint] = None
        self.is_selecting: bool = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.current_pos = event.pos()
            self.is_selecting = True
            self.update()
        elif event.button() == Qt.RightButton:
            self.close()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.current_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            if self.start_pos and self.current_pos:
                rect = QRect(self.start_pos, self.current_pos).normalized()
                if rect.width() > 20 and rect.height() > 20:
                    global_x = self.virtual_geo.x() + rect.x()
                    global_y = self.virtual_geo.y() + rect.y()
                    global_w = rect.width()
                    global_h = rect.height()

                    # 根据选区中心坐标嗅探屏幕及 DPR 物理换算
                    center_pt = QPoint(global_x + global_w // 2, global_y + global_h // 2)
                    screen = QGuiApplication.screenAt(center_pt) or QGuiApplication.primaryScreen()
                    dpr = screen.devicePixelRatio() if screen else 1.0

                    # 获取该屏幕逻辑与物理坐标基准
                    screen_geo = screen.geometry() if screen else QRect(0, 0, 1920, 1080)
                    rel_logical_x = global_x - screen_geo.x()
                    rel_logical_y = global_y - screen_geo.y()

                    # 匹配屏幕物理原点 (避免跨不同缩放比多屏幕时 global_x 被全量乘以副屏 DPR 产生偏移错位)
                    try:
                        from toolbox.plugins.screen_recorder.engine import get_available_screens
                        screens_meta = get_available_screens()
                        screen_phys_x = None
                        screen_phys_y = None
                        for sm in screens_meta:
                            if sm.get("logical_x") == screen_geo.x() and sm.get("logical_y") == screen_geo.y():
                                screen_phys_x = sm.get("x", 0)
                                screen_phys_y = sm.get("y", 0)
                                break
                        if screen_phys_x is None:
                            screen_phys_x = int(round(screen_geo.x() * dpr))
                            screen_phys_y = int(round(screen_geo.y() * dpr))
                    except Exception:
                        screen_phys_x = int(round(screen_geo.x() * dpr))
                        screen_phys_y = int(round(screen_geo.y() * dpr))

                    phys_x = screen_phys_x + int(round(rel_logical_x * dpr))
                    phys_y = screen_phys_y + int(round(rel_logical_y * dpr))
                    phys_w = int(round(global_w * dpr))
                    phys_h = int(round(global_h * dpr))
                    phys_w = phys_w - (phys_w % 2)
                    phys_h = phys_h - (phys_h % 2)

                    self.region_selected.emit(phys_x, phys_y, phys_w, phys_h)
                    if self.on_selected:
                        self.on_selected(phys_x, phys_y, phys_w, phys_h)
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))

        if self.start_pos and self.current_pos:
            rect = QRect(self.start_pos, self.current_pos).normalized()
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(rect, Qt.transparent)

            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor("#38bdf8"), 2, Qt.DashLine))
            painter.drawRect(rect)

            tag_text = f"{rect.width()} x {rect.height()}"
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(15, 23, 42, 220))
            tag_rect = QRect(rect.left(), max(0, rect.top() - 24), 95, 22)
            painter.drawRoundedRect(tag_rect, 4, 4)

            painter.setPen(QColor("#ffffff"))
            painter.drawText(tag_rect, Qt.AlignCenter, tag_text)
        painter.end()
