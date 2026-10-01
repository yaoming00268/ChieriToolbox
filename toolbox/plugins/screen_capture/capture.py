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
    """PixPin 风格全屏遮罩选区与工具条"""
    captured = Signal(QPixmap, str)  # (pixmap, action: 'copy' / 'save' / 'pin')

    def __init__(self, full_pixmap: QPixmap, on_finish: Optional[Callable] = None, parent=None):
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.full_pixmap = full_pixmap
        self.on_finish = on_finish

        self.start_pos: Optional[QPoint] = None
        self.current_pos: Optional[QPoint] = None
        self.is_selecting: bool = False
        self.selected_rect: Optional[QRect] = None

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

    def _finalize_action(self, action: str):
        if self.selected_rect and not self.full_pixmap.isNull():
            cropped = self.full_pixmap.copy(self.selected_rect)
            self.captured.emit(cropped, action)
            if self.on_finish:
                self.on_finish(cropped, action)
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
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

        painter.end()


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


def find_vertical_overlap(top_img: Image.Image, bottom_img: Image.Image, min_overlap: int = 20, max_overlap: Optional[int] = None) -> int:
    """计算连续滚动截图在垂直方向上的重合行高"""
    from PIL import ImageChops, ImageStat
    if top_img.size[0] != bottom_img.size[0]:
        return 0
    w = top_img.size[0]
    h1 = top_img.size[1]
    h2 = bottom_img.size[1]
    if max_overlap is None:
        max_overlap = min(h1, h2) - 10
    if max_overlap <= min_overlap:
        return 0

    best_overlap = 0
    best_diff = 999999.0

    step = 2 if (max_overlap - min_overlap) < 300 else 4
    for h in range(min_overlap, max_overlap, step):
        strip1 = top_img.crop((0, h1 - h, w, h1))
        strip2 = bottom_img.crop((0, 0, w, h))
        diff = ImageChops.difference(strip1, strip2)
        stat = ImageStat.Stat(diff)
        avg = sum(stat.mean)
        if avg < 1.0:
            return h
        if avg < best_diff:
            best_diff = avg
            best_overlap = h

    if best_diff < 5.0:
        return best_overlap
    return 0


def stitch_long_screenshot(pixmaps: List[QPixmap]) -> QPixmap:
    """
    长截图垂直智能无缝拼接
    支持将多段连续滚动截取的画面按垂直方向自动识别重合边界并消除重复区域合成一体化长图。
    """
    if not pixmaps:
        return QPixmap()
    if len(pixmaps) == 1:
        return pixmaps[0]

    try:
        pil_images = [_qpixmap_to_pil(p) for p in pixmaps]
        stitched = pil_images[0]

        for next_img in pil_images[1:]:
            # 保证宽度一致
            if next_img.size[0] != stitched.size[0]:
                next_img = next_img.resize((stitched.size[0], int(next_img.size[1] * stitched.size[0] / next_img.size[0])), Image.Resampling.LANCZOS)

            overlap_h = find_vertical_overlap(stitched, next_img)
            new_h = stitched.size[1] + next_img.size[1] - overlap_h
            new_canvas = Image.new("RGBA", (stitched.size[0], new_h), (0, 0, 0, 0))
            new_canvas.paste(stitched, (0, 0))
            new_canvas.paste(next_img, (0, stitched.size[1] - overlap_h))
            stitched = new_canvas

        return _pil_to_qpixmap(stitched)
    except Exception:
        # 回退至平铺模式
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
