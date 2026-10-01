"""
专业截图工具 (PixPin风) - UI 界面
集成矩形截图、智能窗口嗅探、全屏截图、滚动长截图、桌面贴图置顶与快捷配置。
"""

import os
import time
from typing import Optional, List, Dict, Any
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtGui import QGuiApplication, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QCheckBox, QComboBox, QLineEdit, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QKeySequenceEdit, QGridLayout, QTabWidget, QFrame, QScrollArea
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.icons import get_icon, get_pixmap
from .capture import (
    grab_fullscreen, grab_window_under_cursor, SnipOverlay,
    PinnedImageViewer, stitch_long_screenshot
)


class CaptureSignalBridge(QObject):
    sig_rect = Signal()
    sig_win = Signal()
    sig_full = Signal()
    sig_long = Signal()


class XboxCaptureOverlayWidget(QWidget):
    """
    类 Xbox Game Bar 悬浮快速截屏控制坞 (HUD Overlay)
    置顶无边框半透明深色亚克力胶囊设计，支持桌面全屏自由拖拽、各截图模式一键直达与收起。
    """
    def __init__(self, capture_widget: "ScreenCaptureWidget"):
        super().__init__(None)
        self.capture_widget = capture_widget
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._drag_pos = None
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)

        container = QFrame()
        container.setObjectName("xboxPillContainer")
        container.setStyleSheet("""
            QFrame#xboxPillContainer {
                background-color: rgba(23, 23, 29, 0.94);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 20px;
                padding: 2px 8px;
            }
            QPushButton {
                background-color: transparent;
                color: #e2e8f0;
                border: none;
                border-radius: 12px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.16);
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: rgba(59, 130, 246, 0.4);
                color: #ffffff;
            }
            QLabel {
                color: #94a3b8;
                font-size: 12px;
            }
        """)
        c_layout = QHBoxLayout(container)
        c_layout.setContentsMargins(4, 3, 4, 3)
        c_layout.setSpacing(6)

        handle_lbl = QLabel(" ⠿ ")
        handle_lbl.setToolTip("按住鼠标左键可自由拖动悬浮截屏坞")
        handle_lbl.setStyleSheet("color: #64748b; font-size: 14px; font-weight: bold;")
        handle_lbl.setCursor(Qt.SizeAllCursor)
        c_layout.addWidget(handle_lbl)

        brand_lbl = QLabel("Xbox Snip")
        brand_lbl.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px; margin-right: 4px;")
        c_layout.addWidget(brand_lbl)

        sep1 = QLabel("│")
        sep1.setStyleSheet("color: #475569;")
        c_layout.addWidget(sep1)

        self.btn_xbox_rect = QPushButton(" 矩形")
        self.btn_xbox_rect.setIcon(get_icon("scissors", color="#38bdf8", size=14))
        self.btn_xbox_rect.setToolTip("矩形选区截图 (点击后隐藏控制坞并开启全屏选区)")
        self.btn_xbox_rect.clicked.connect(self.capture_widget._start_rectangular_snip)
        c_layout.addWidget(self.btn_xbox_rect)

        self.btn_xbox_win = QPushButton(" 窗口")
        self.btn_xbox_win.setIcon(get_icon("window", color="#a855f7", size=14))
        self.btn_xbox_win.setToolTip("窗口智能嗅探截图 (直接截取鼠标所在活动窗口)")
        self.btn_xbox_win.clicked.connect(self.capture_widget._start_window_snip)
        c_layout.addWidget(self.btn_xbox_win)

        self.btn_xbox_full = QPushButton(" 全屏")
        self.btn_xbox_full.setIcon(get_icon("monitor", color="#10b981", size=14))
        self.btn_xbox_full.setToolTip("全屏快速截图 (毫秒级捕获整屏画面)")
        self.btn_xbox_full.clicked.connect(self.capture_widget._start_fullscreen_snip)
        c_layout.addWidget(self.btn_xbox_full)

        self.btn_xbox_long = QPushButton(" 长图分段")
        self.btn_xbox_long.setIcon(get_icon("file-plus", color="#f59e0b", size=14))
        self.btn_xbox_long.setToolTip("捕获当前屏幕作为滚动长截图的新分段")
        self.btn_xbox_long.clicked.connect(self.capture_widget._add_long_segment)
        c_layout.addWidget(self.btn_xbox_long)

        sep2 = QLabel("│")
        sep2.setStyleSheet("color: #475569;")
        c_layout.addWidget(sep2)

        btn_settings = QPushButton()
        btn_settings.setIcon(get_icon("settings", color="#94a3b8", size=14))
        btn_settings.setToolTip("打开截图工具主面板与配置")
        btn_settings.clicked.connect(self._open_main_window)
        c_layout.addWidget(btn_settings)

        btn_close = QPushButton()
        btn_close.setIcon(get_icon("clear", color="#ef4444", size=13))
        btn_close.setToolTip("关闭悬浮截屏坞")
        btn_close.clicked.connect(self._close_overlay)
        c_layout.addWidget(btn_close)

        layout.addWidget(container)
        self.adjustSize()

    def _open_main_window(self):
        w = self.capture_widget.window()
        if w:
            w.show()
            w.raise_()
            w.activateWindow()

    def _close_overlay(self):
        self.capture_widget.cb_xbox_overlay.setChecked(False)
        self.hide()

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

    def showEvent(self, event):
        super().showEvent(event)
        if self.pos().x() <= 0 and self.pos().y() <= 0:
            screen = QGuiApplication.primaryScreen()
            if screen:
                geo = screen.geometry()
                x = geo.x() + (geo.width() - self.width()) // 2
                y = geo.y() + 32
                self.move(x, y)


class ScreenCaptureWidget(QWidget):
    PLUGIN_ID = "screen_capture"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self.pinned_windows: List[PinnedImageViewer] = []
        self.long_segments: List[QPixmap] = []
        self.history_items: List[Dict[str, Any]] = []
        self._shortcuts: List[QShortcut] = []
        self._global_hotkey_hooks = []
        self.xbox_overlay: Optional[XboxCaptureOverlayWidget] = None

        self._bridge = CaptureSignalBridge(self)
        self._bridge.sig_rect.connect(self._start_rectangular_snip)
        self._bridge.sig_win.connect(self._start_window_snip)
        self._bridge.sig_full.connect(self._start_fullscreen_snip)
        self._bridge.sig_long.connect(self._trigger_long_snip_shortcut)

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(10)
        self.scroll_area.setWidget(container)
        root_layout.addWidget(self.scroll_area)

        # 1. 顶部 Header
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("scissors", color="#3b82f6", size=26))
        header.addWidget(icon_lbl)

        title_lbl = QLabel("专业屏幕截图工具 (PixPin 质感)")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title_lbl)

        badge_lbl = QLabel("矩形选区 · 窗口嗅探 · 滚动长图 · 桌面贴图")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header.addStretch()
        layout.addLayout(header)

        # 2. 各截图模式独立设置与启动标签页 (点击标签按钮进入该截图方式的设置页)
        self.mode_tabs = QTabWidget()
        self.mode_tabs.setMinimumHeight(210)

        # Tab 0: 矩形区域截图设置页
        page_rect = QWidget()
        l_rect = QVBoxLayout(page_rect)
        l_rect.setContentsMargins(14, 14, 14, 14)
        l_rect.setSpacing(12)

        top_rect = QHBoxLayout()
        tip_rect = QLabel("<b>矩形区域截图 (自由框选)</b><br><span style='color:#64748b; font-size:12px;'>自由拖拽十字准星选取屏幕矩形范围，支持边缘微调、精准尺寸刻度与标注贴图。</span>")
        tip_rect.setWordWrap(True)
        top_rect.addWidget(tip_rect, 1)

        self.btn_snip = QPushButton("立即开始矩形截图")
        self.btn_snip.setObjectName("primaryBtn")
        self.btn_snip.setIcon(get_icon("scissors", color="#ffffff", size=15))
        self.btn_snip.setFixedHeight(36)
        self.btn_snip.clicked.connect(self._start_rectangular_snip)
        top_rect.addWidget(self.btn_snip)
        l_rect.addLayout(top_rect)

        grp_rect_cfg = QGroupBox("矩形选区参数与独立快捷键")
        grp_rect_cfg.setMinimumHeight(135)
        g_rect = QGridLayout(grp_rect_cfg)
        g_rect.setHorizontalSpacing(14)
        g_rect.setVerticalSpacing(8)
        g_rect.setRowMinimumHeight(0, 32)
        g_rect.setRowMinimumHeight(1, 28)
        g_rect.setRowMinimumHeight(2, 28)
        g_rect.setColumnStretch(2, 1)

        g_rect.addWidget(QLabel("矩形截图快捷键:"), 0, 0)
        self.edit_key_rect = QKeySequenceEdit(QKeySequence("F1"))
        self.edit_key_rect.setMinimumHeight(28)
        self.edit_key_rect.setMaximumWidth(160)
        self.edit_key_rect.keySequenceChanged.connect(self._on_shortcuts_changed)
        g_rect.addWidget(self.edit_key_rect, 0, 1)

        self.cb_rect_magnifier = QCheckBox("框选时显示高倍放大镜与 RGB 颜色参考")
        self.cb_rect_magnifier.setChecked(True)
        self.cb_rect_magnifier.toggled.connect(self.save_settings)
        g_rect.addWidget(self.cb_rect_magnifier, 1, 0, 1, 3)

        self.cb_rect_guide = QCheckBox("显示九宫格黄金分割比例构图参考辅助线")
        self.cb_rect_guide.setChecked(True)
        self.cb_rect_guide.toggled.connect(self.save_settings)
        g_rect.addWidget(self.cb_rect_guide, 2, 0, 1, 3)

        l_rect.addWidget(grp_rect_cfg)
        l_rect.addStretch()
        self.mode_tabs.addTab(page_rect, get_icon("scissors", size=14), "矩形区域截图")

        # Tab 1: 窗口智能截图设置页
        page_win = QWidget()
        l_win = QVBoxLayout(page_win)
        l_win.setContentsMargins(14, 14, 14, 14)
        l_win.setSpacing(12)

        top_win = QHBoxLayout()
        tip_win = QLabel("<b>窗口智能截图 (系统窗体嗅探)</b><br><span style='color:#64748b; font-size:12px;'>将鼠标移动至任意应用程序、弹窗或对话框上方，自动高亮吸附窗口物理边缘并截取。</span>")
        tip_win.setWordWrap(True)
        top_win.addWidget(tip_win, 1)

        self.btn_window_snip = QPushButton("立即智能截取窗口")
        self.btn_window_snip.setObjectName("primaryBtn")
        self.btn_window_snip.setIcon(get_icon("window", color="#ffffff", size=15))
        self.btn_window_snip.setFixedHeight(36)
        self.btn_window_snip.clicked.connect(self._start_window_snip)
        top_win.addWidget(self.btn_window_snip)
        l_win.addLayout(top_win)

        grp_win_cfg = QGroupBox("窗口嗅探参数与独立快捷键")
        grp_win_cfg.setMinimumHeight(135)
        g_win = QGridLayout(grp_win_cfg)
        g_win.setHorizontalSpacing(14)
        g_win.setVerticalSpacing(8)
        g_win.setRowMinimumHeight(0, 32)
        g_win.setRowMinimumHeight(1, 28)
        g_win.setRowMinimumHeight(2, 28)
        g_win.setColumnStretch(2, 1)

        g_win.addWidget(QLabel("窗口截图快捷键:"), 0, 0)
        self.edit_key_win = QKeySequenceEdit(QKeySequence("F2"))
        self.edit_key_win.setMinimumHeight(28)
        self.edit_key_win.setMaximumWidth(160)
        self.edit_key_win.keySequenceChanged.connect(self._on_shortcuts_changed)
        g_win.addWidget(self.edit_key_win, 0, 1)

        self.cb_win_border = QCheckBox("鼠标悬停时实时绘制蓝色高亮吸附框")
        self.cb_win_border.setChecked(True)
        self.cb_win_border.toggled.connect(self.save_settings)
        g_win.addWidget(self.cb_win_border, 1, 0, 1, 3)

        self.cb_win_shadow = QCheckBox("包含 Windows 桌面窗口边缘的原生半透明投影与外边框")
        self.cb_win_shadow.setChecked(False)
        self.cb_win_shadow.toggled.connect(self.save_settings)
        g_win.addWidget(self.cb_win_shadow, 2, 0, 1, 3)

        l_win.addWidget(grp_win_cfg)
        l_win.addStretch()
        self.mode_tabs.addTab(page_win, get_icon("window", size=14), "窗口智能截图")

        # Tab 2: 全屏快速截图设置页
        page_full = QWidget()
        l_full = QVBoxLayout(page_full)
        l_full.setContentsMargins(14, 14, 14, 14)
        l_full.setSpacing(12)

        top_full = QHBoxLayout()
        tip_full = QLabel("<b>全屏快速截图 (毫秒级整屏捕获)</b><br><span style='color:#64748b; font-size:12px;'>瞬时捕捉整块屏幕或多显示器桌面全景，自动存入剪贴板或输出目录。</span>")
        tip_full.setWordWrap(True)
        top_full.addWidget(tip_full, 1)

        self.btn_full_snip = QPushButton("立即全屏快速截图")
        self.btn_full_snip.setObjectName("primaryBtn")
        self.btn_full_snip.setIcon(get_icon("monitor", color="#ffffff", size=15))
        self.btn_full_snip.setFixedHeight(36)
        self.btn_full_snip.clicked.connect(self._start_fullscreen_snip)
        top_full.addWidget(self.btn_full_snip)
        l_full.addLayout(top_full)

        grp_full_cfg = QGroupBox("全屏捕获参数与独立快捷键")
        grp_full_cfg.setMinimumHeight(145)
        g_full = QGridLayout(grp_full_cfg)
        g_full.setHorizontalSpacing(14)
        g_full.setVerticalSpacing(8)
        g_full.setRowMinimumHeight(0, 32)
        g_full.setRowMinimumHeight(1, 30)
        g_full.setRowMinimumHeight(2, 30)
        g_full.setColumnStretch(2, 1)

        g_full.addWidget(QLabel("全屏截图快捷键:"), 0, 0)
        self.edit_key_full = QKeySequenceEdit(QKeySequence("F3"))
        self.edit_key_full.setMinimumHeight(28)
        self.edit_key_full.setMaximumWidth(160)
        self.edit_key_full.keySequenceChanged.connect(self._on_shortcuts_changed)
        g_full.addWidget(self.edit_key_full, 0, 1)

        g_full.addWidget(QLabel("截图延时:"), 1, 0)
        self.combo_full_delay = QComboBox()
        self.combo_full_delay.addItems(["无延迟 (立即捕获)", "倒计时 3 秒", "倒计时 5 秒", "倒计时 10 秒"])
        self.combo_full_delay.setMaximumWidth(220)
        self.combo_full_delay.currentIndexChanged.connect(self.save_settings)
        g_full.addWidget(self.combo_full_delay, 1, 1)

        g_full.addWidget(QLabel("多显示器范围:"), 2, 0)
        self.combo_full_scope = QComboBox()
        self.combo_full_scope.addItems(["当前主显示器", "全桌面跨屏虚拟拼接"])
        self.combo_full_scope.setMaximumWidth(220)
        self.combo_full_scope.currentIndexChanged.connect(self.save_settings)
        g_full.addWidget(self.combo_full_scope, 2, 1)

        l_full.addWidget(grp_full_cfg)
        l_full.addStretch()
        self.mode_tabs.addTab(page_full, get_icon("monitor", size=14), "全屏快速截图")

        # Tab 3: 滚动长截图设置页
        page_long = QWidget()
        l_long = QVBoxLayout(page_long)
        l_long.setContentsMargins(14, 14, 14, 14)
        l_long.setSpacing(12)

        top_long = QHBoxLayout()
        tip_long = QLabel("<b>滚动长截图无缝拼接工作台</b><br><span style='color:#64748b; font-size:12px;'>支持滚动页面并多次捕获屏幕分段画面，底层自动拼接缝合成单张超长完整大图。</span>")
        tip_long.setWordWrap(True)
        top_long.addWidget(tip_long, 1)

        self.lbl_long_info = QLabel("已捕获 0 段画面")
        self.lbl_long_info.setStyleSheet("color: #64748b; font-weight: 500;")
        top_long.addWidget(self.lbl_long_info)
        l_long.addLayout(top_long)

        long_action_row = QHBoxLayout()
        self.btn_add_segment = QPushButton("捕获当前屏为新分段")
        self.btn_add_segment.setIcon(get_icon("file-plus", size=13))
        self.btn_add_segment.clicked.connect(self._add_long_segment)
        long_action_row.addWidget(self.btn_add_segment)

        self.btn_finish_long = QPushButton("完成并合并拼接长图")
        self.btn_finish_long.setObjectName("primaryBtn")
        self.btn_finish_long.setIcon(get_icon("check", color="#ffffff", size=13))
        self.btn_finish_long.setEnabled(False)
        self.btn_finish_long.clicked.connect(self._finish_long_snip)
        long_action_row.addWidget(self.btn_finish_long)

        self.btn_clear_long = QPushButton("清空分段")
        self.btn_clear_long.setIcon(get_icon("trash", size=13))
        self.btn_clear_long.clicked.connect(self._clear_long_segments)
        long_action_row.addWidget(self.btn_clear_long)
        long_action_row.addStretch()
        l_long.addLayout(long_action_row)

        grp_long_cfg = QGroupBox("长截图参数与独立快捷键")
        grp_long_cfg.setMinimumHeight(145)
        g_long = QGridLayout(grp_long_cfg)
        g_long.setHorizontalSpacing(14)
        g_long.setVerticalSpacing(8)
        g_long.setRowMinimumHeight(0, 32)
        g_long.setRowMinimumHeight(1, 30)
        g_long.setRowMinimumHeight(2, 28)
        g_long.setColumnStretch(2, 1)

        g_long.addWidget(QLabel("长截图分段快捷键:"), 0, 0)
        self.edit_key_long = QKeySequenceEdit(QKeySequence("F4"))
        self.edit_key_long.setMinimumHeight(28)
        self.edit_key_long.setMaximumWidth(160)
        self.edit_key_long.keySequenceChanged.connect(self._on_shortcuts_changed)
        g_long.addWidget(self.edit_key_long, 0, 1)

        g_long.addWidget(QLabel("拼接方向:"), 1, 0)
        self.combo_long_dir = QComboBox()
        self.combo_long_dir.addItems(["纵向向下拼接 (垂直长图)", "横向向右拼接 (水平全景)"])
        self.combo_long_dir.setMaximumWidth(240)
        self.combo_long_dir.currentIndexChanged.connect(self.save_settings)
        g_long.addWidget(self.combo_long_dir, 1, 1)

        self.cb_long_overlap = QCheckBox("开启特征重叠区去重与像素平滑消除缝合")
        self.cb_long_overlap.setChecked(True)
        self.cb_long_overlap.toggled.connect(self.save_settings)
        g_long.addWidget(self.cb_long_overlap, 2, 0, 1, 3)

        l_long.addWidget(grp_long_cfg)
        l_long.addStretch()
        self.mode_tabs.addTab(page_long, get_icon("file-plus", size=14), "滚动长截图")

        layout.addWidget(self.mode_tabs)

        # 3. 通用输出偏好与全局截屏组件
        pref_box = QGroupBox("通用输出偏好与全局截屏组件")
        pref_layout = QVBoxLayout(pref_box)
        pref_layout.setContentsMargins(14, 12, 14, 12)
        pref_layout.setSpacing(10)

        # 选项第 1 行
        row_toggles1 = QHBoxLayout()
        row_toggles1.setSpacing(14)
        self.cb_copy = QCheckBox("截图后自动复制到系统剪贴板")
        self.cb_copy.setChecked(True)
        self.cb_copy.toggled.connect(self.save_settings)
        row_toggles1.addWidget(self.cb_copy)

        self.cb_save = QCheckBox("截图后自动静默保存至指定文件夹")
        self.cb_save.setChecked(False)
        self.cb_save.toggled.connect(self.save_settings)
        row_toggles1.addWidget(self.cb_save)
        row_toggles1.addStretch()
        pref_layout.addLayout(row_toggles1)

        # 选项第 2 行 (贴图与格式)
        row_toggles2 = QHBoxLayout()
        row_toggles2.setSpacing(14)
        self.cb_pin = QCheckBox("截图后自动在桌面上贴图置顶 (Pin)")
        self.cb_pin.setChecked(False)
        self.cb_pin.toggled.connect(self.save_settings)
        row_toggles2.addWidget(self.cb_pin)

        row_toggles2.addWidget(QLabel("默认格式:"))
        self.combo_fmt = QComboBox()
        self.combo_fmt.addItems(["PNG", "JPG", "BMP"])
        self.combo_fmt.setFixedWidth(80)
        self.combo_fmt.currentIndexChanged.connect(self.save_settings)
        row_toggles2.addWidget(self.combo_fmt)
        row_toggles2.addStretch()
        pref_layout.addLayout(row_toggles2)

        # 类 Xbox 截屏组件配置行
        row_xbox = QHBoxLayout()
        row_xbox.setSpacing(12)
        self.cb_xbox_overlay = QCheckBox("采用类 Xbox 悬浮快捷截屏控制坞")
        self.cb_xbox_overlay.setToolTip("开启后将在屏幕顶层显示半透明浮动控制胶囊，支持随时随地自由拖动并一键启动矩形、窗口、全屏及长截图")
        self.cb_xbox_overlay.toggled.connect(self._on_xbox_overlay_toggled)
        row_xbox.addWidget(self.cb_xbox_overlay)

        self.btn_toggle_xbox = QPushButton("唤起/隐藏悬浮控制坞")
        self.btn_toggle_xbox.setIcon(get_icon("monitor", size=13))
        self.btn_toggle_xbox.clicked.connect(self._toggle_xbox_overlay_visible)
        row_xbox.addWidget(self.btn_toggle_xbox)
        row_xbox.addStretch()
        pref_layout.addLayout(row_xbox)

        # 保存目录行与全局重置
        row_dir = QHBoxLayout()
        row_dir.setSpacing(8)
        row_dir.addWidget(QLabel("保存目录:"))
        self.le_save_dir = QLineEdit()
        self.le_save_dir.editingFinished.connect(self.save_settings)
        row_dir.addWidget(self.le_save_dir, 1)

        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.setIcon(get_icon("folder", size=14))
        self.btn_browse.clicked.connect(self._browse_dir)
        row_dir.addWidget(self.btn_browse)

        self.btn_reset_keys = QPushButton("恢复全部快捷键")
        self.btn_reset_keys.setIcon(get_icon("refresh", size=13))
        self.btn_reset_keys.clicked.connect(self._reset_default_shortcuts)
        row_dir.addWidget(self.btn_reset_keys)

        pref_layout.addLayout(row_dir)
        layout.addWidget(pref_box)

        # 4. 最近截图历史清单
        hist_box = QGroupBox("最近截图清单")
        hist_layout = QVBoxLayout(hist_box)
        hist_layout.setContentsMargins(12, 10, 12, 10)
        hist_layout.setSpacing(8)

        self.table_hist = QTableWidget()
        self.table_hist.setColumnCount(4)
        self.table_hist.setHorizontalHeaderLabels(["名称", "分辨率", "文件大小", "保存路径"])
        self.table_hist.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_hist.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_hist.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_hist.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_hist.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_hist.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_hist.setMinimumHeight(110)
        hist_layout.addWidget(self.table_hist)

        row_h_act = QHBoxLayout()
        row_h_act.addStretch()

        self.btn_pin_selected = QPushButton("贴图置顶")
        self.btn_pin_selected.setIcon(get_icon("external-link", size=13))
        self.btn_pin_selected.clicked.connect(self._pin_selected_history)
        row_h_act.addWidget(self.btn_pin_selected)

        self.btn_copy_selected = QPushButton("复制图片")
        self.btn_copy_selected.setIcon(get_icon("copy", size=13))
        self.btn_copy_selected.clicked.connect(self._copy_selected_history)
        row_h_act.addWidget(self.btn_copy_selected)

        self.btn_open_dir = QPushButton("打开保存目录")
        self.btn_open_dir.setIcon(get_icon("folder", size=13))
        self.btn_open_dir.clicked.connect(self._open_save_dir)
        row_h_act.addWidget(self.btn_open_dir)

        hist_layout.addLayout(row_h_act)
        layout.addWidget(hist_box)
        self.mode_tabs.currentChanged.connect(self.save_settings)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存目录", self.le_save_dir.text())
        if d:
            self.le_save_dir.setText(d)
            self.save_settings()

    def _on_xbox_overlay_toggled(self, checked: bool):
        if checked:
            if not self.xbox_overlay:
                self.xbox_overlay = XboxCaptureOverlayWidget(self)
            if self.isVisible():
                self.xbox_overlay.show()
                self.xbox_overlay.raise_()
        else:
            if self.xbox_overlay:
                self.xbox_overlay.hide()
        self.save_settings()

    def _toggle_xbox_overlay_visible(self):
        if not self.cb_xbox_overlay.isChecked():
            self.cb_xbox_overlay.setChecked(True)
        else:
            if not self.xbox_overlay:
                self.xbox_overlay = XboxCaptureOverlayWidget(self)
            if self.xbox_overlay.isVisible():
                self.xbox_overlay.hide()
            else:
                self.xbox_overlay.show()
                self.xbox_overlay.raise_()

    def _on_snip_overlay_closed(self):
        if getattr(self, "_window_was_visible", True) and self.window():
            self.window().show()
            self.window().raise_()
        if hasattr(self, "xbox_overlay") and self.xbox_overlay and self.cb_xbox_overlay.isChecked():
            self.xbox_overlay.show()
            self.xbox_overlay.raise_()

    def _start_rectangular_snip(self):
        """启动 PixPin 矩形区域截图覆盖"""
        self._window_was_visible = self.window().isVisible() if self.window() else False
        if self.window():
            self.window().hide()
        if hasattr(self, "xbox_overlay") and self.xbox_overlay:
            self.xbox_overlay.hide()
        QTimer.singleShot(250, self._do_rectangular_snip)

    def _do_rectangular_snip(self):
        full_pix = grab_fullscreen()
        overlay = SnipOverlay(full_pix, on_finish=self._handle_capture_result)
        overlay.destroyed.connect(self._on_snip_overlay_closed)
        overlay.show()

    def _start_window_snip(self):
        """启动窗口截图"""
        self._window_was_visible = self.window().isVisible() if self.window() else False
        if self.window():
            self.window().hide()
        if hasattr(self, "xbox_overlay") and self.xbox_overlay:
            self.xbox_overlay.hide()
        QTimer.singleShot(250, self._do_window_snip)

    def _do_window_snip(self):
        pix, rect = grab_window_under_cursor()
        if getattr(self, "_window_was_visible", True) and self.window():
            self.window().show()
            self.window().raise_()
        if hasattr(self, "xbox_overlay") and self.xbox_overlay and self.cb_xbox_overlay.isChecked():
            if self.isVisible():
                self.xbox_overlay.show()
                self.xbox_overlay.raise_()
        if not pix.isNull():
            self._handle_capture_result(pix, "copy")

    def _start_fullscreen_snip(self):
        """快速全屏截图"""
        delay = 0
        if hasattr(self, "combo_full_delay"):
            idx = self.combo_full_delay.currentIndex()
            delays = [0, 3, 5, 10]
            delay = delays[idx] if idx < len(delays) else 0

        self._window_was_visible = self.window().isVisible() if self.window() else False
        if self.window():
            self.window().hide()
        if hasattr(self, "xbox_overlay") and self.xbox_overlay:
            self.xbox_overlay.hide()

        wait_ms = max(250, delay * 1000)
        QTimer.singleShot(wait_ms, self._do_fullscreen_snip)

    def _do_fullscreen_snip(self):
        pix = grab_fullscreen()
        if getattr(self, "_window_was_visible", True) and self.window():
            self.window().show()
            self.window().raise_()
        if hasattr(self, "xbox_overlay") and self.xbox_overlay and self.cb_xbox_overlay.isChecked():
            if self.isVisible():
                self.xbox_overlay.show()
                self.xbox_overlay.raise_()
        if not pix.isNull():
            self._handle_capture_result(pix, "copy")

    def _add_long_segment(self):
        """长截图：捕获当前屏幕作为拼接段"""
        self._window_was_visible = self.window().isVisible() if self.window() else False
        if self.window():
            self.window().hide()
        if hasattr(self, "xbox_overlay") and self.xbox_overlay:
            self.xbox_overlay.hide()
        QTimer.singleShot(250, self._do_add_long_segment)

    def _do_add_long_segment(self):
        pix = grab_fullscreen()
        if getattr(self, "_window_was_visible", True) and self.window():
            self.window().show()
            self.window().raise_()
        if hasattr(self, "xbox_overlay") and self.xbox_overlay and self.cb_xbox_overlay.isChecked():
            if self.isVisible():
                self.xbox_overlay.show()
                self.xbox_overlay.raise_()
        if not pix.isNull():
            self.long_segments.append(pix)
            self.lbl_long_info.setText(f"已捕获 {len(self.long_segments)} 段画面")
            self.btn_finish_long.setEnabled(True)

    def _finish_long_snip(self):
        if not self.long_segments:
            return
        combined = stitch_long_screenshot(self.long_segments)
        self.long_segments.clear()
        self.lbl_long_info.setText("已捕获 0 段画面")
        self.btn_finish_long.setEnabled(False)
        self._handle_capture_result(combined, "save")

    def _clear_long_segments(self):
        self.long_segments.clear()
        self.lbl_long_info.setText("已捕获 0 段画面")
        self.btn_finish_long.setEnabled(False)

    def _handle_capture_result(self, pixmap: QPixmap, requested_action: str = "copy"):
        """统一处理截图产物：剪贴板 / 保存 / 桌面贴图"""
        if pixmap.isNull():
            return

        fmt = self.combo_fmt.currentText().lower()
        save_dir = self.le_save_dir.text().strip()
        if not save_dir:
            save_dir = os.path.join(os.path.expanduser("~"), "Pictures", "ToolboxScreenshots")
            self.le_save_dir.setText(save_dir)
        os.makedirs(save_dir, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"Screenshot_{timestamp}.{fmt}"
        filepath = os.path.join(save_dir, filename)

        # 1. 复制到剪贴板
        if requested_action == "copy" or self.cb_copy.isChecked():
            cb = QGuiApplication.clipboard()
            cb.setPixmap(pixmap)

        # 2. 保存文件
        if requested_action == "save" or self.cb_save.isChecked():
            pixmap.save(filepath, fmt.upper())

        # 3. 桌面贴图
        if requested_action == "pin" or self.cb_pin.isChecked():
            viewer = PinnedImageViewer(pixmap)
            viewer.closed.connect(lambda v: self.pinned_windows.remove(v) if v in self.pinned_windows else None)
            self.pinned_windows.append(viewer)
            viewer.show()

        # 记录到历史
        file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        sz_str = f"{file_size / 1024:.1f} KB" if file_size else "-"
        hist_item = {
            "name": filename,
            "res": f"{pixmap.width()} x {pixmap.height()}",
            "size": sz_str,
            "path": filepath,
            "pixmap": pixmap
        }
        self.history_items.insert(0, hist_item)
        self._render_history()
        self.save_settings()

    def _render_history(self):
        self.table_hist.setRowCount(0)
        for r_idx, item in enumerate(self.history_items[:15]):
            self.table_hist.insertRow(r_idx)
            item_name = QTableWidgetItem(item["name"])
            item_name.setIcon(get_icon("image", size=14))
            item_name.setData(Qt.UserRole, item)
            self.table_hist.setItem(r_idx, 0, item_name)
            self.table_hist.setItem(r_idx, 1, QTableWidgetItem(item["res"]))
            self.table_hist.setItem(r_idx, 2, QTableWidgetItem(item["size"]))
            self.table_hist.setItem(r_idx, 3, QTableWidgetItem(item["path"]))

    def _pin_selected_history(self):
        rows = self.table_hist.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table_hist.item(rows[0].row(), 0)
        data = item.data(Qt.UserRole)
        pix = data.get("pixmap")
        if not pix and os.path.exists(data.get("path", "")):
            pix = QPixmap(data["path"])
        if pix and not pix.isNull():
            viewer = PinnedImageViewer(pix)
            viewer.closed.connect(lambda v: self.pinned_windows.remove(v) if v in self.pinned_windows else None)
            self.pinned_windows.append(viewer)
            viewer.show()

    def _copy_selected_history(self):
        rows = self.table_hist.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table_hist.item(rows[0].row(), 0)
        data = item.data(Qt.UserRole)
        pix = data.get("pixmap")
        if not pix and os.path.exists(data.get("path", "")):
            pix = QPixmap(data["path"])
        if pix:
            QGuiApplication.clipboard().setPixmap(pix)
            QMessageBox.information(self, "已复制", "选中的截图已复制到系统剪贴板。")

    def _open_save_dir(self):
        d = self.le_save_dir.text().strip()
        if d and os.path.exists(d):
            os.startfile(os.path.normpath(d))
        else:
            QMessageBox.information(self, "提示", "尚未生成截图目录。")

    def _pin_clipboard_or_last(self):
        """剪贴板快速贴图置顶或贴出上一张截图"""
        cb = QGuiApplication.clipboard()
        pix = cb.pixmap()
        if (not pix or pix.isNull()) and self.history_items:
            last = self.history_items[0]
            pix = last.get("pixmap")
            if not pix and os.path.exists(last.get("path", "")):
                pix = QPixmap(last["path"])
        if pix and not pix.isNull():
            viewer = PinnedImageViewer(pix)
            viewer.closed.connect(lambda v: self.pinned_windows.remove(v) if v in self.pinned_windows else None)
            self.pinned_windows.append(viewer)
            viewer.show()
        else:
            # 剪贴板中无有效图片且无历史记录，降级触发矩形截图
            self._start_rectangular_snip()

    def _trigger_long_snip_shortcut(self):
        """长截图快捷键触发：若已有分段则直接捕获下一分段，否则开启长截图首段"""
        self._add_long_segment()

    def _on_shortcuts_changed(self):
        self._setup_shortcuts()
        self.save_settings()

    def _reset_default_shortcuts(self):
        self.edit_key_rect.setKeySequence(QKeySequence("F1"))
        self.edit_key_win.setKeySequence(QKeySequence("F2"))
        self.edit_key_full.setKeySequence(QKeySequence("F3"))
        self.edit_key_long.setKeySequence(QKeySequence("F4"))
        self._setup_shortcuts()
        self.save_settings()

    def _clear_global_hotkeys(self):
        try:
            import keyboard
            for hook in self._global_hotkey_hooks:
                try:
                    keyboard.remove_hotkey(hook)
                except Exception:
                    pass
        except Exception:
            pass
        self._global_hotkey_hooks.clear()

    def _setup_shortcuts(self):
        """刷新应用内快捷键与系统全局热键"""
        # 1. 清理已有 QShortcut
        for sc in self._shortcuts:
            sc.setEnabled(False)
            sc.setParent(None)
            sc.deleteLater()
        self._shortcuts.clear()

        # 2. 清理全局热键
        self._clear_global_hotkeys()

        # 3. 注册应用内 QShortcut
        sc_map = [
            (self.edit_key_rect.keySequence(), self._start_rectangular_snip),
            (self.edit_key_win.keySequence(), self._start_window_snip),
            (self.edit_key_full.keySequence(), self._start_fullscreen_snip),
            (self.edit_key_long.keySequence(), self._trigger_long_snip_shortcut),
        ]
        for seq, callback in sc_map:
            if not seq.isEmpty():
                sc = QShortcut(seq, self)
                sc.setContext(Qt.ApplicationShortcut)
                sc.activated.connect(callback)
                self._shortcuts.append(sc)

        # 4. 更新按钮与标签页辅助文本
        r_str = self.edit_key_rect.keySequence().toString()
        w_str = self.edit_key_win.keySequence().toString()
        f_str = self.edit_key_full.keySequence().toString()
        l_str = self.edit_key_long.keySequence().toString()
        self.btn_snip.setText(f"立即开始矩形截图 ({r_str})" if r_str else "立即开始矩形截图")
        self.btn_window_snip.setText(f"立即智能截取窗口 ({w_str})" if w_str else "立即智能截取窗口")
        self.btn_full_snip.setText(f"立即全屏快速截图 ({f_str})" if f_str else "立即全屏快速截图")

        if hasattr(self, "mode_tabs"):
            self.mode_tabs.setTabText(0, f"矩形区域截图 ({r_str})" if r_str else "矩形区域截图")
            self.mode_tabs.setTabText(1, f"窗口智能截图 ({w_str})" if w_str else "窗口智能截图")
            self.mode_tabs.setTabText(2, f"全屏快速截图 ({f_str})" if f_str else "全屏快速截图")
            self.mode_tabs.setTabText(3, f"滚动长截图 ({l_str})" if l_str else "滚动长截图")

        # 5. 注册全局热键 (若 keyboard 库就绪)
        try:
            import keyboard
            def _bind_global(seq_str, bridge_signal):
                if not seq_str:
                    return
                kb_str = seq_str.lower().replace("ctrl", "ctrl").replace("meta", "windows")
                try:
                    hook = keyboard.add_hotkey(kb_str, bridge_signal.emit, suppress=False)
                    self._global_hotkey_hooks.append(hook)
                except Exception:
                    pass

            _bind_global(r_str, self._bridge.sig_rect)
            _bind_global(w_str, self._bridge.sig_win)
            _bind_global(f_str, self._bridge.sig_full)
            _bind_global(self.edit_key_long.keySequence().toString(), self._bridge.sig_long)
        except Exception:
            pass

    def load_settings(self):
        cfg = self.config_manager.get_plugin_config(self.PLUGIN_ID, {})
        self.cb_copy.setChecked(cfg.get("auto_copy", True))
        self.cb_save.setChecked(cfg.get("auto_save", False))
        self.cb_pin.setChecked(cfg.get("auto_pin", False))
        self.combo_fmt.setCurrentIndex(cfg.get("fmt_idx", 0))

        default_dir = os.path.join(os.path.expanduser("~"), "Pictures", "ToolboxScreenshots")
        self.le_save_dir.setText(cfg.get("save_dir", default_dir))

        self.edit_key_rect.setKeySequence(QKeySequence(cfg.get("key_rect", "F1")))
        self.edit_key_win.setKeySequence(QKeySequence(cfg.get("key_win", "F2")))
        self.edit_key_full.setKeySequence(QKeySequence(cfg.get("key_full", "F3")))
        self.edit_key_long.setKeySequence(QKeySequence(cfg.get("key_long", "F4")))

        tab_idx = cfg.get("mode_tab_idx", 0)
        if hasattr(self, "mode_tabs") and 0 <= tab_idx < self.mode_tabs.count():
            self.mode_tabs.setCurrentIndex(tab_idx)

        if hasattr(self, "cb_xbox_overlay"):
            self.cb_xbox_overlay.blockSignals(True)
            self.cb_xbox_overlay.setChecked(cfg.get("xbox_overlay", False))
            self.cb_xbox_overlay.blockSignals(False)
        if hasattr(self, "combo_full_delay"):
            self.combo_full_delay.setCurrentIndex(cfg.get("full_delay_idx", 0))
        if hasattr(self, "combo_full_scope"):
            self.combo_full_scope.setCurrentIndex(cfg.get("full_scope_idx", 0))
        if hasattr(self, "combo_long_dir"):
            self.combo_long_dir.setCurrentIndex(cfg.get("long_dir_idx", 0))
        if hasattr(self, "cb_long_overlap"):
            self.cb_long_overlap.setChecked(cfg.get("long_overlap", True))
        if hasattr(self, "cb_rect_magnifier"):
            self.cb_rect_magnifier.setChecked(cfg.get("rect_magnifier", True))
        if hasattr(self, "cb_rect_guide"):
            self.cb_rect_guide.setChecked(cfg.get("rect_guide", True))
        if hasattr(self, "cb_win_border"):
            self.cb_win_border.setChecked(cfg.get("win_border", True))
        if hasattr(self, "cb_win_shadow"):
            self.cb_win_shadow.setChecked(cfg.get("win_shadow", False))

        self._setup_shortcuts()

    def save_settings(self):
        if not hasattr(self, "cb_copy") or not hasattr(self, "edit_key_rect"):
            return
        cfg = {
            "auto_copy": self.cb_copy.isChecked(),
            "auto_save": self.cb_save.isChecked(),
            "auto_pin": self.cb_pin.isChecked(),
            "fmt_idx": self.combo_fmt.currentIndex(),
            "save_dir": self.le_save_dir.text(),
            "key_rect": self.edit_key_rect.keySequence().toString(),
            "key_win": self.edit_key_win.keySequence().toString(),
            "key_full": self.edit_key_full.keySequence().toString(),
            "key_long": self.edit_key_long.keySequence().toString(),
            "mode_tab_idx": self.mode_tabs.currentIndex() if hasattr(self, "mode_tabs") else 0,
            "xbox_overlay": self.cb_xbox_overlay.isChecked() if hasattr(self, "cb_xbox_overlay") else False,
            "full_delay_idx": self.combo_full_delay.currentIndex() if hasattr(self, "combo_full_delay") else 0,
            "full_scope_idx": self.combo_full_scope.currentIndex() if hasattr(self, "combo_full_scope") else 0,
            "long_dir_idx": self.combo_long_dir.currentIndex() if hasattr(self, "combo_long_dir") else 0,
            "long_overlap": self.cb_long_overlap.isChecked() if hasattr(self, "cb_long_overlap") else True,
            "rect_magnifier": self.cb_rect_magnifier.isChecked() if hasattr(self, "cb_rect_magnifier") else True,
            "rect_guide": self.cb_rect_guide.isChecked() if hasattr(self, "cb_rect_guide") else True,
            "win_border": self.cb_win_border.isChecked() if hasattr(self, "cb_win_border") else True,
            "win_shadow": self.cb_win_shadow.isChecked() if hasattr(self, "cb_win_shadow") else False,
        }
        self.config_manager.set_plugin_config(self.PLUGIN_ID, cfg)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "cb_xbox_overlay") and self.cb_xbox_overlay.isChecked():
            if not self.xbox_overlay:
                self.xbox_overlay = XboxCaptureOverlayWidget(self)
            self.xbox_overlay.show()
            self.xbox_overlay.raise_()

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, "xbox_overlay") and self.xbox_overlay:
            self.xbox_overlay.hide()

    def on_deactivated(self):
        if hasattr(self, "xbox_overlay") and self.xbox_overlay:
            self.xbox_overlay.hide()

    def cleanup(self):
        self._clear_global_hotkeys()
        for sc in self._shortcuts:
            try:
                sc.setEnabled(False)
            except Exception:
                pass
        self._shortcuts.clear()

        for v in list(self.pinned_windows):
            try:
                v.close()
            except Exception:
                pass
        self.pinned_windows.clear()

        if hasattr(self, "xbox_overlay") and self.xbox_overlay:
            try:
                self.xbox_overlay.close()
            except Exception:
                pass
            self.xbox_overlay = None
