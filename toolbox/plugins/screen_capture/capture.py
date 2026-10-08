"""
专业截图工具 - 核心截图、选区覆盖、长截图拼接与桌面贴图 (Capture Engine)
类 PixPin 体验：矩形截图、智能窗口嗅探、全屏抓取、滚动长图无缝拼接与多层置顶贴图。
"""

import os
import sys
import ctypes
from typing import Optional, List, Tuple, Callable
from PIL import Image
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import (
    QGuiApplication, QPixmap, QImage, QPainter, QColor, QPen,
    QBrush, QCursor, QFont, QAction
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QMenu, QFileDialog, QApplication
)
from toolbox.ui.icons import get_icon


def get_virtual_geometry() -> QRect:
    """获取系统中所有屏幕组成的虚拟桌面逻辑矩形 (支持负坐标副屏)"""
    screens = QGuiApplication.screens()
    if not screens:
        return QRect(0, 0, 1920, 1080)
    v_geo = QRect()
    for s in screens:
        v_geo = v_geo.united(s.geometry())
    return v_geo if not v_geo.isEmpty() else QRect(0, 0, 1920, 1080)


def grab_fullscreen() -> QPixmap:
    """抓取主屏幕或完整虚拟桌面全屏位图 (支持副屏负坐标及跨屏拼接)"""
    screens = QGuiApplication.screens()
    if not screens:
        return QPixmap()
    if len(screens) == 1:
        return screens[0].grabWindow(0)

    v_geo = get_virtual_geometry()
    combined = QPixmap(v_geo.size())
    combined.fill(Qt.transparent)
    painter = QPainter(combined)
    for s in screens:
        pix = s.grabWindow(0)
        if not pix.isNull():
            rel_x = s.geometry().x() - v_geo.x()
            rel_y = s.geometry().y() - v_geo.y()
            painter.drawPixmap(rel_x, rel_y, s.geometry().width(), s.geometry().height(), pix)
    painter.end()
    return combined


def get_window_rect_under_cursor() -> Optional[QRect]:
    """在 Windows 下嗅探鼠标当前悬停的顶层窗口坐标矩形"""
    if sys.platform != "win32":
        return None
    try:
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        hwnd = user32.WindowFromPoint(pt)
        # 获取根级顶级窗口
        root_hwnd = user32.GetAncestor(hwnd, 2)  # GA_ROOT
        if root_hwnd:
            hwnd = root_hwnd

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w > 10 and h > 10:
            # 准确获取窗口所在物理显示器的坐标原点，完美支持多显示器负坐标与混合 DPI 缩放
            class _MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ('cbSize', wintypes.DWORD),
                    ('rcMonitor', wintypes.RECT),
                    ('rcWork', wintypes.RECT),
                    ('dwFlags', wintypes.DWORD)
                ]

            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            m_left, m_top = 0, 0
            hmon = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
            if hmon and user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                m_left = mi.rcMonitor.left
                m_top = mi.rcMonitor.top

            # 找到鼠标所在屏幕以换算 High-DPI 缩放系数与逻辑原点
            cursor_pos = QCursor.pos()
            screen = QGuiApplication.screenAt(cursor_pos) or QGuiApplication.primaryScreen()
            dpr = screen.devicePixelRatio() if screen else 1.0
            if dpr <= 0:
                dpr = 1.0
            s_geo = screen.geometry() if screen else QRect(0, 0, 1920, 1080)

            # 核心算法：屏幕内物理偏移量除以 DPR，再加上 Qt 屏幕的逻辑原点
            log_x = s_geo.x() + int(round((rect.left - m_left) / dpr))
            log_y = s_geo.y() + int(round((rect.top - m_top) / dpr))
            log_w = int(round(w / dpr))
            log_h = int(round(h / dpr))
            return QRect(log_x, log_y, log_w, log_h)
    except Exception:
        pass
    return None


def grab_window_under_cursor() -> Tuple[QPixmap, QRect]:
    """抓取鼠标当前所在窗口 (支持副屏负坐标及跨屏嗅探)"""
    v_geo = get_virtual_geometry()
    full_pix = grab_fullscreen()
    win_rect = get_window_rect_under_cursor()
    if win_rect and not full_pix.isNull():
        # win_rect 是 Windows 全局虚拟桌面坐标，转换为 full_pix 的相对坐标
        rel_win_rect = QRect(
            win_rect.x() - v_geo.x(),
            win_rect.y() - v_geo.y(),
            win_rect.width(),
            win_rect.height()
        )
        intersect = rel_win_rect.intersected(QRect(0, 0, full_pix.width(), full_pix.height()))
        if not intersect.isEmpty():
            cropped = full_pix.copy(intersect)
            return cropped, win_rect
    return full_pix, v_geo


class PinnedImageViewer(QWidget):
    """PixPin 风格桌面置顶贴图控件：无边框、置顶、可拖拽移动、滚轮缩放与右键管理"""
    closed = Signal(object)

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.original_pixmap = pixmap
        self.current_pixmap = pixmap
        self.scale_factor: float = 1.0
        self.opacity: float = 1.0
        self._drag_pos: Optional[QPoint] = None

        self.resize(pixmap.width() + 10, pixmap.height() + 10)
        self.setCursor(Qt.SizeAllCursor)
        self.setToolTip("左键拖拽移动 · 滚轮缩放 · 双击或右键菜单关闭")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.close()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self.scale_factor = min(3.0, self.scale_factor * 1.1)
        else:
            self.scale_factor = max(0.2, self.scale_factor * 0.9)

        new_w = max(50, int(self.original_pixmap.width() * self.scale_factor))
        new_h = max(50, int(self.original_pixmap.height() * self.scale_factor))
        self.current_pixmap = self.original_pixmap.scaled(
            new_w, new_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.resize(new_w + 10, new_h + 10)
        self.update()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_copy = QAction("复制到剪贴板", self)
        act_copy.setIcon(get_icon("copy", size=14))
        act_copy.triggered.connect(self._copy_to_clipboard)
        menu.addAction(act_copy)

        act_save = QAction("保存为图片...", self)
        act_save.setIcon(get_icon("save", size=14))
        act_save.triggered.connect(self._save_to_file)
        menu.addAction(act_save)

        menu.addSeparator()
        act_close = QAction("关闭贴图 (Esc)", self)
        act_close.setIcon(get_icon("clear", size=14))
        act_close.triggered.connect(self.close)
        menu.addAction(act_close)

        menu.exec(event.globalPos())

    def _copy_to_clipboard(self):
        cb = QGuiApplication.clipboard()
        cb.setPixmap(self.original_pixmap)

    def _save_to_file(self):
        p, _ = QFileDialog.getSaveFileName(self, "保存贴图文件", "Pinned_Screenshot.png", "Images (*.png *.jpg *.bmp)")
        if p:
            self.original_pixmap.save(p)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setOpacity(self.opacity)

        # 阴影与微光边框
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.setPen(QPen(QColor(59, 130, 246, 200), 2))
        painter.drawPixmap(rect.topLeft(), self.current_pixmap)
        painter.drawRect(rect)
        painter.end()

    def closeEvent(self, event):
        self.closed.emit(self)
        super().closeEvent(event)


class SnipOverlay(QWidget):
    """PixPin 风格全屏遮罩选区、工具条与实时取色放大镜"""
    captured = Signal(QPixmap, str)  # (pixmap, action: 'copy' / 'save' / 'pin')

    def __init__(self, full_pixmap: QPixmap, on_finish: Optional[Callable] = None, show_magnifier: bool = True, parent=None):
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.full_pixmap = full_pixmap
        self._full_image = full_pixmap.toImage() if not full_pixmap.isNull() else None
        self.on_finish = on_finish
        self.show_magnifier = show_magnifier

        self.start_pos: Optional[QPoint] = None
        self.current_pos: Optional[QPoint] = None
        self.hover_pos: Optional[QPoint] = None
        self.is_selecting: bool = False
        self.selected_rect: Optional[QRect] = None
        self._copied_toast_text: str = ""
        self._copied_toast_tick: float = 0.0

        self.init_ui()

    def init_ui(self):
        v_geo = get_virtual_geometry()
        self.setGeometry(v_geo)
        self.setCursor(Qt.CrossCursor)

        # 浮动工具栏
        self.toolbar = QWidget(self)
        self.toolbar.setObjectName("snipToolbar")
        self.toolbar.setStyleSheet("""
            #snipToolbar {
                background-color: #1e2230;
                border: 1px solid #3b82f6;
                border-radius: 6px;
            }
            QPushButton {
                background-color: transparent;
                color: #f1f5f9;
                border: none;
                padding: 4px 8px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #2563eb;
                border-radius: 4px;
            }
        """)
        tb_layout = QHBoxLayout(self.toolbar)
        tb_layout.setContentsMargins(6, 4, 6, 4)
        tb_layout.setSpacing(6)

        btn_pin = QPushButton("贴图")
        btn_pin.setIcon(get_icon("external-link", color="#ffffff", size=13))
        btn_pin.clicked.connect(lambda: self._finalize_action("pin"))
        tb_layout.addWidget(btn_pin)

        btn_ocr = QPushButton("识字")
        btn_ocr.setIcon(get_icon("search", color="#ffffff", size=13))
        btn_ocr.clicked.connect(lambda: self._finalize_action("ocr"))
        tb_layout.addWidget(btn_ocr)

        btn_qr = QPushButton("扫码")
        btn_qr.setIcon(get_icon("sparkles", color="#ffffff", size=13))
        btn_qr.clicked.connect(lambda: self._finalize_action("qr"))
        tb_layout.addWidget(btn_qr)

        btn_save = QPushButton("保存")
        btn_save.setIcon(get_icon("save", color="#ffffff", size=13))
        btn_save.clicked.connect(lambda: self._finalize_action("save"))
        tb_layout.addWidget(btn_save)

        btn_copy = QPushButton("复制")
        btn_copy.setIcon(get_icon("copy", color="#ffffff", size=13))
        btn_copy.clicked.connect(lambda: self._finalize_action("copy"))
        tb_layout.addWidget(btn_copy)

        btn_cancel = QPushButton("取消")
        btn_cancel.setIcon(get_icon("clear", color="#ef4444", size=13))
        btn_cancel.clicked.connect(self.close)
        tb_layout.addWidget(btn_cancel)

        self.toolbar.setVisible(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.current_pos = event.pos()
            self.is_selecting = True
            self.selected_rect = None
            self.toolbar.setVisible(False)
            self.update()
        elif event.button() == Qt.RightButton:
            if self.selected_rect:
                self.selected_rect = None
                self.toolbar.setVisible(False)
                self.update()
            else:
                self.close()

    def mouseMoveEvent(self, event):
        self.hover_pos = event.pos()
        if self.is_selecting:
            self.current_pos = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            if self.start_pos and self.current_pos:
                rect = QRect(self.start_pos, self.current_pos).normalized()
                if rect.width() > 10 and rect.height() > 10:
                    self.selected_rect = rect
                    self._position_toolbar(rect)
                else:
                    self.selected_rect = None
            self.update()

    def _position_toolbar(self, rect: QRect):
        tb_w = self.toolbar.sizeHint().width()
        tb_h = self.toolbar.sizeHint().height()

        x = rect.right() - tb_w
        y = rect.bottom() + 8
        if y + tb_h > self.height():
            y = rect.top() - tb_h - 8
        if x < 4:
            x = 4

        self.toolbar.move(x, y)
        self.toolbar.setVisible(True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._finalize_action("copy")
        elif event.key() == Qt.Key_C:
            pos = self.current_pos if (self.is_selecting and self.current_pos) else self.hover_pos
            if pos and self._full_image and 0 <= pos.x() < self._full_image.width() and 0 <= pos.y() < self._full_image.height():
                col = self._full_image.pixelColor(pos.x(), pos.y())
                hex_str = col.name(QColor.HexRgb).upper()
                QGuiApplication.clipboard().setText(hex_str)
                self._copied_toast_text = f"已复制色值: {hex_str}"
                import time
                self._copied_toast_tick = time.time()
                self.update()

    def _finalize_action(self, action: str):
        if self.selected_rect and not self.full_pixmap.isNull():
            cropped = self.full_pixmap.copy(self.selected_rect)
            self.captured.emit(cropped, action)
            if self.on_finish:
                self.on_finish(cropped, action)
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

        # 1. 绘制底层原屏幕画面
        painter.drawPixmap(0, 0, self.full_pixmap)

        # 2. 全屏半透明黑色遮罩
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))

        # 3. 镂空选区，高亮真实屏幕
        if self.is_selecting and self.start_pos and self.current_pos:
            rect = QRect(self.start_pos, self.current_pos).normalized()
        else:
            rect = self.selected_rect

        if rect and not rect.isEmpty():
            # 还原选区内的原图
            painter.drawPixmap(rect.topLeft(), self.full_pixmap.copy(rect))

            # 边框与刻度尺寸
            painter.setPen(QPen(QColor("#38bdf8"), 2))
            painter.drawRect(rect)

            # 标注选区像素尺寸标签 (如 1920 x 1080)
            tag_text = f"{rect.width()} x {rect.height()}"
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(15, 23, 42, 220))
            tag_rect = QRect(rect.left(), max(0, rect.top() - 24), 95, 22)
            painter.drawRoundedRect(tag_rect, 4, 4)

            painter.setPen(QColor("#ffffff"))
            painter.drawText(tag_rect, Qt.AlignCenter, tag_text)

        # 4. 实时高精度取色放大镜 HUD
        focus_pos = self.current_pos if (self.is_selecting and self.current_pos) else self.hover_pos
        if self.show_magnifier and (self.selected_rect is None or self.is_selecting) and focus_pos and self._full_image:
            px_x, px_y = focus_pos.x(), focus_pos.y()
            if 0 <= px_x < self._full_image.width() and 0 <= px_y < self._full_image.height():
                self._draw_magnifier(painter, px_x, px_y)

        # 5. 复制色值成功浮动提示 (Toast)
        import time
        if self._copied_toast_text and (time.time() - self._copied_toast_tick < 1.6):
            t_w, t_h = 200, 36
            t_x = (self.width() - t_w) // 2
            t_y = 60
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(16, 185, 129, 235))
            painter.drawRoundedRect(QRect(t_x, t_y, t_w, t_h), 18, 18)
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
            painter.drawText(QRect(t_x, t_y, t_w, t_h), Qt.AlignCenter, self._copied_toast_text)

        painter.end()

    def _draw_magnifier(self, painter: QPainter, cx: int, cy: int):
        """绘制实时高倍网格放大镜与 RGB/HEX 像素分析面板"""
        cur_col = self._full_image.pixelColor(cx, cy)
        hex_str = cur_col.name(QColor.HexRgb).upper()
        rgb_str = f"RGB({cur_col.red()}, {cur_col.green()}, {cur_col.blue()})"

        box_w = 152
        box_h = 176
        # 放大镜随鼠标微移，靠近边缘自适应翻转
        offset_x = 18
        offset_y = 18
        bx = cx + offset_x
        by = cy + offset_y
        if bx + box_w > self.width() - 8:
            bx = cx - box_w - offset_x
        if by + box_h > self.height() - 8:
            by = cy - box_h - offset_y
        bx = max(8, bx)
        by = max(8, by)

        # 放大镜主框阴影与背景
        box_rect = QRect(bx, by, box_w, box_h)
        painter.setPen(QPen(QColor("#38bdf8"), 1.5))
        painter.setBrush(QColor(23, 23, 33, 240))
        painter.drawRoundedRect(box_rect, 8, 8)

        # 放大镜像素网格 (9x9 采样，放大单像素为 11x11)
        grid_r = 4  # -4 到 +4 共 9 个像素
        cell_size = 11
        grid_w = (grid_r * 2 + 1) * cell_size  # 99 px
        gx = bx + (box_w - grid_w) // 2
        gy = by + 8

        # 绘制像素网格
        for dy in range(-grid_r, grid_r + 1):
            for dx in range(-grid_r, grid_r + 1):
                sx = cx + dx
                sy = cy + dy
                if 0 <= sx < self._full_image.width() and 0 <= sy < self._full_image.height():
                    c = self._full_image.pixelColor(sx, sy)
                else:
                    c = QColor(0, 0, 0)
                cell_rect = QRect(gx + (dx + grid_r) * cell_size, gy + (dy + grid_r) * cell_size, cell_size, cell_size)
                painter.setPen(QPen(QColor(40, 44, 58), 1))
                painter.setBrush(c)
                painter.drawRect(cell_rect)

        # 中心十字准星 (锁定当前悬停像素)
        center_rect = QRect(gx + grid_r * cell_size, gy + grid_r * cell_size, cell_size, cell_size)
        painter.setPen(QPen(QColor("#ef4444"), 1.8))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(center_rect)

        # 色样预览长条
        swatch_rect = QRect(bx + 10, gy + grid_w + 6, box_w - 20, 14)
        painter.setPen(QPen(QColor(255, 255, 255, 120), 1))
        painter.setBrush(cur_col)
        painter.drawRoundedRect(swatch_rect, 3, 3)

        # 色值与坐标文字信息
        text_y = swatch_rect.bottom() + 14
        painter.setFont(QFont("Consolas", 9, QFont.Bold))
        painter.setPen(QColor("#38bdf8"))
        painter.drawText(bx + 10, text_y, hex_str)

        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#cbd5e1"))
        painter.drawText(bx + 10, text_y + 13, rgb_str)

        painter.setPen(QColor("#94a3b8"))
        painter.drawText(bx + 10, text_y + 25, f"X:{cx}  Y:{cy}  [C]复制")


def _qpixmap_to_pil(pix: QPixmap) -> Image.Image:
    qimg = pix.toImage().convertToFormat(QImage.Format_RGBA8888)
    w = qimg.width()
    h = qimg.height()
    ptr = qimg.bits()
    return Image.frombuffer("RGBA", (w, h), bytes(ptr), "raw", "RGBA", 0, 1)


def _pil_to_qpixmap(im: Image.Image) -> QPixmap:
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    qimg = QImage(data, im.size[0], im.size[1], im.size[0] * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


def find_vertical_overlap(top_img: Image.Image, bottom_img: Image.Image, min_overlap: int = 15, max_overlap: Optional[int] = None) -> int:
    """计算连续滚动截图在垂直方向上的重合行高"""
    from PIL import ImageChops, ImageStat
    if top_img.size[0] != bottom_img.size[0]:
        return 0
    w = top_img.size[0]
    h1 = top_img.size[1]
    h2 = bottom_img.size[1]
    if max_overlap is None:
        max_overlap = min(h1, h2) - 5
    if max_overlap <= min_overlap:
        return 0

    best_overlap = 0
    best_diff = 999999.0

    step = 1 if (max_overlap - min_overlap) < 300 else 2
    for h in range(max_overlap, min_overlap - 1, -step):
        strip1 = top_img.crop((0, h1 - h, w, h1))
        strip2 = bottom_img.crop((0, 0, w, h))
        diff = ImageChops.difference(strip1, strip2)
        stat = ImageStat.Stat(diff)
        avg = sum(stat.mean)
        if avg < 2.0:
            return h
        if avg < best_diff:
            best_diff = avg
            best_overlap = h

    if best_diff < 8.0:
        return best_overlap
    return 0


def find_horizontal_overlap(left_img: Image.Image, right_img: Image.Image, min_overlap: int = 15, max_overlap: Optional[int] = None) -> int:
    """计算横向拼接时的水平重合列宽"""
    from PIL import ImageChops, ImageStat
    if left_img.size[1] != right_img.size[1]:
        return 0
    w1, h = left_img.size[0], left_img.size[1]
    w2 = right_img.size[0]
    if max_overlap is None:
        max_overlap = min(w1, w2) - 5
    if max_overlap <= min_overlap:
        return 0

    best_overlap = 0
    best_diff = 999999.0
    step = 1 if (max_overlap - min_overlap) < 300 else 2
    for w in range(max_overlap, min_overlap - 1, -step):
        strip1 = left_img.crop((w1 - w, 0, w1, h))
        strip2 = right_img.crop((0, 0, w, h))
        diff = ImageChops.difference(strip1, strip2)
        stat = ImageStat.Stat(diff)
        avg = sum(stat.mean)
        if avg < 2.0:
            return w
        if avg < best_diff:
            best_diff = avg
            best_overlap = w
    if best_diff < 8.0:
        return best_overlap
    return 0


def stitch_screenshots(pixmaps: List[QPixmap], direction: str = "vertical", auto_overlap: bool = True) -> QPixmap:
    """
    智能多向长截图无缝拼接引擎
    :param pixmaps: 待拼接的多段 QPixmap
    :param direction: 'vertical' (垂直长图) 或 'horizontal' (水平长图)
    :param auto_overlap: 是否开启特征重叠区消除
    """
    if not pixmaps:
        return QPixmap()
    if len(pixmaps) == 1:
        return pixmaps[0]

    try:
        pil_images = [_qpixmap_to_pil(p) for p in pixmaps]
        stitched = pil_images[0]

        if direction == "horizontal":
            for next_img in pil_images[1:]:
                overlap_w = find_horizontal_overlap(stitched, next_img) if auto_overlap else 0
                max_h = max(stitched.size[1], next_img.size[1])
                new_w = stitched.size[0] + next_img.size[0] - overlap_w
                new_canvas = Image.new("RGBA", (new_w, max_h), (0, 0, 0, 0))
                new_canvas.paste(stitched, (0, 0))
                new_canvas.paste(next_img, (stitched.size[0] - overlap_w, 0))
                stitched = new_canvas
        else:
            for next_img in pil_images[1:]:
                overlap_h = find_vertical_overlap(stitched, next_img) if auto_overlap else 0
                max_w = max(stitched.size[0], next_img.size[0])
                new_h = stitched.size[1] + next_img.size[1] - overlap_h
                new_canvas = Image.new("RGBA", (max_w, new_h), (0, 0, 0, 0))
                new_canvas.paste(stitched, (0, 0))
                new_canvas.paste(next_img, (0, stitched.size[1] - overlap_h))
                stitched = new_canvas

        return _pil_to_qpixmap(stitched)
    except Exception:
        # 异常容错：基础平铺拼接
        if direction == "horizontal":
            total_w = sum(p.width() for p in pixmaps)
            max_h = max(p.height() for p in pixmaps)
            combined = QPixmap(total_w, max_h)
            combined.fill(Qt.transparent)
            painter = QPainter(combined)
            cur_x = 0
            for p in pixmaps:
                painter.drawPixmap(cur_x, 0, p)
                cur_x += p.width()
            painter.end()
            return combined
        else:
            total_w = max(p.width() for p in pixmaps)
            total_h = sum(p.height() for p in pixmaps)
            combined = QPixmap(total_w, total_h)
            combined.fill(Qt.transparent)
            painter = QPainter(combined)
            current_y = 0
            for p in pixmaps:
                painter.drawPixmap(0, current_y, p)
                current_y += p.height()
            painter.end()
            return combined


def stitch_long_screenshot(pixmaps: List[QPixmap], direction: str = "vertical") -> QPixmap:
    """向后兼容的垂直/通用长截图拼接入口"""
    return stitch_screenshots(pixmaps, direction=direction, auto_overlap=True)
