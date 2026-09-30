"""
高清屏幕录像机 - UI 界面
支持多屏幕/显示器选择、目标窗口与矩形区域录制；
提供 OBS 级系统声音回路与麦克风双轨混音；
支持应用内与全局录制/暂停快捷键；
集成帧率画质压制与会话参数独立记忆。
"""

import os
import time
import subprocess
from typing import Optional, List, Dict, Any, Tuple
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QGroupBox, QRadioButton, QButtonGroup,
    QLineEdit, QFileDialog, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QKeySequenceEdit,
    QSizePolicy, QGridLayout, QScrollArea, QFrame
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.icons import get_icon, get_pixmap
from .engine import (
    ScreenRecorderEngine, get_visible_windows,
    get_available_screens, get_audio_output_devices,
    get_audio_input_devices
)
from .region_selector import RegionSelectOverlay


def format_seconds(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"


class RecorderSignalBridge(QObject):
    sig_toggle_record = Signal()
    sig_toggle_pause = Signal()


class ScreenRecorderWidget(QWidget):
    PLUGIN_ID = "screen_recorder"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self.engine = ScreenRecorderEngine(self)
        self.custom_rect: Optional[Tuple[int, int, int, int]] = None
        self.history_records: List[Dict[str, Any]] = []
        self._shortcuts: List[QShortcut] = []
        self._global_hotkey_hooks = []

        self._bridge = RecorderSignalBridge(self)
        self._bridge.sig_toggle_record.connect(self._toggle_recording_action)
        self._bridge.sig_toggle_pause.connect(self._toggle_pause_action)

        self.init_ui()
        self.init_connections()
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
        icon_lbl.setPixmap(get_pixmap("video", color="#3b82f6", size=26))
        header.addWidget(icon_lbl)

        title_lbl = QLabel("高清屏幕录像机 (Screen Recorder)")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title_lbl)

        badge_lbl = QLabel("多显示器选择 · 窗口嗅探 · OBS级音频混流 · 全局快捷键")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header.addStretch()
        layout.addLayout(header)

        # 2. 录屏模式与屏幕/窗口选择
        mode_box = QGroupBox("录制目标源与显示器选择")
        m_layout = QVBoxLayout(mode_box)
        m_layout.setContentsMargins(14, 10, 14, 10)
        m_layout.setSpacing(8)

        row_mode_radios = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.rb_full = QRadioButton("屏幕/显示器录制")
        self.rb_full.setChecked(True)
        self.rb_window = QRadioButton("目标窗口录制")
        self.rb_rect = QRadioButton("自定义矩形区域")
        self.mode_group.addButton(self.rb_full, 0)
        self.mode_group.addButton(self.rb_window, 1)
        self.mode_group.addButton(self.rb_rect, 2)
        self.mode_group.idToggled.connect(self._on_mode_toggled)

        row_mode_radios.addWidget(self.rb_full)
        row_mode_radios.addWidget(self.rb_window)
        row_mode_radios.addWidget(self.rb_rect)
        row_mode_radios.addStretch()
        m_layout.addLayout(row_mode_radios)

        # 屏幕选择容器 (多显示器适配)
        self.screen_target_container = QWidget()
        sc_layout = QHBoxLayout(self.screen_target_container)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.addWidget(QLabel("选择录制屏幕:"))
        self.combo_screens = QComboBox()
        self._refresh_screen_list()
        sc_layout.addWidget(self.combo_screens, 1)

        self.btn_refresh_screens = QPushButton("刷新屏幕")
        self.btn_refresh_screens.setIcon(get_icon("refresh", size=13))
        self.btn_refresh_screens.clicked.connect(self._refresh_screen_list)
        sc_layout.addWidget(self.btn_refresh_screens)
        m_layout.addWidget(self.screen_target_container)

        # 窗口录制附加参数容器
        self.win_target_container = QWidget()
        win_layout = QHBoxLayout(self.win_target_container)
        win_layout.setContentsMargins(0, 0, 0, 0)
        win_layout.addWidget(QLabel("选择目标窗口:"))
        self.combo_windows = QComboBox()
        self._refresh_window_list()
        win_layout.addWidget(self.combo_windows, 1)

        self.btn_refresh_win = QPushButton("刷新窗口")
        self.btn_refresh_win.setIcon(get_icon("refresh", size=13))
        self.btn_refresh_win.clicked.connect(self._refresh_window_list)
        win_layout.addWidget(self.btn_refresh_win)
        self.win_target_container.setVisible(False)
        m_layout.addWidget(self.win_target_container)

        # 矩形区域附加参数容器
        self.rect_target_container = QWidget()
        rect_layout = QHBoxLayout(self.rect_target_container)
        rect_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_pick_rect = QPushButton("在屏幕上拖拽框选录制区域")
        self.btn_pick_rect.setIcon(get_icon("scissors", size=14))
        self.btn_pick_rect.clicked.connect(self._open_region_picker)
        rect_layout.addWidget(self.btn_pick_rect)

        self.lbl_rect_coords = QLabel("当前区域: 尚未选择")
        self.lbl_rect_coords.setStyleSheet("color: #64748b; font-weight: 500;")
        rect_layout.addWidget(self.lbl_rect_coords)
        rect_layout.addStretch()
        self.rect_target_container.setVisible(False)
        m_layout.addWidget(self.rect_target_container)

        layout.addWidget(mode_box)

        # 3. 编码参数与 OBS 级音频选择
        param_box = QGroupBox("视频质量与音频混流配置 (OBS 级)")
        p_layout = QVBoxLayout(param_box)
        p_layout.setContentsMargins(14, 10, 14, 10)
        p_layout.setSpacing(8)

        row_p1 = QHBoxLayout()
        row_p1.setSpacing(12)

        row_p1.addWidget(QLabel("帧率:"))
        self.combo_fps = QComboBox()
        self.combo_fps.addItems(["60 FPS (电竞流畅)", "30 FPS (标准平滑)", "15 FPS (体积节省)"])
        self.combo_fps.setCurrentIndex(1)
        self.combo_fps.setMaximumWidth(160)
        row_p1.addWidget(self.combo_fps)

        row_p1.addWidget(QLabel("画质:"))
        self.combo_quality = QComboBox()
        self.combo_quality.addItems(["极高品质 (CRF 18)", "高保真平衡 (CRF 23)", "高压缩比 (CRF 28)"])
        self.combo_quality.setCurrentIndex(1)
        self.combo_quality.setMaximumWidth(170)
        row_p1.addWidget(self.combo_quality)

        row_p1.addWidget(QLabel("格式:"))
        self.combo_fmt = QComboBox()
        self.combo_fmt.addItems(["MP4", "MKV", "GIF"])
        self.combo_fmt.setFixedWidth(80)
        row_p1.addWidget(self.combo_fmt)

        self.cb_mouse = QCheckBox("显示鼠标指针")
        self.cb_mouse.setChecked(True)
        row_p1.addWidget(self.cb_mouse)

        row_p1.addStretch()
        p_layout.addLayout(row_p1)

        # 音频源 1: 系统声音/扬声器
        row_sys_audio = QHBoxLayout()
        row_sys_audio.setSpacing(8)
        self.cb_system_audio = QCheckBox("录制系统声音 (扬声器/电脑播放音):")
        self.cb_system_audio.setChecked(False)
        self.cb_system_audio.toggled.connect(lambda c: self.combo_system_audio.setEnabled(c))
        row_sys_audio.addWidget(self.cb_system_audio)

        self.combo_system_audio = QComboBox()
        self.combo_system_audio.setEnabled(False)
        row_sys_audio.addWidget(self.combo_system_audio, 1)
        p_layout.addLayout(row_sys_audio)

        # 音频源 2: 麦克风输入
        row_mic_audio = QHBoxLayout()
        row_mic_audio.setSpacing(8)
        self.cb_mic = QCheckBox("录制麦克风 (人声输入):")
        self.cb_mic.setChecked(False)
        self.cb_mic.toggled.connect(lambda c: self.combo_mic.setEnabled(c))
        row_mic_audio.addWidget(self.cb_mic)

        self.combo_mic = QComboBox()
        self.combo_mic.setEnabled(False)
        row_mic_audio.addWidget(self.combo_mic, 1)

        self.btn_refresh_audio = QPushButton("刷新音频设备")
        self.btn_refresh_audio.setIcon(get_icon("refresh", size=13))
        self.btn_refresh_audio.clicked.connect(self._refresh_audio_devices)
        row_mic_audio.addWidget(self.btn_refresh_audio)
        p_layout.addLayout(row_mic_audio)

        # 向后兼容旧字段引用
        self.cb_audio = self.cb_mic
        self.combo_audio_dev = self.combo_mic

        self._refresh_audio_devices()

        # 视频保存目录
        row_dir = QHBoxLayout()
        row_dir.setSpacing(8)
        row_dir.addWidget(QLabel("视频保存目录:"))
        self.le_save_dir = QLineEdit()
        self.le_save_dir.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row_dir.addWidget(self.le_save_dir, 1)

        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.setIcon(get_icon("folder", size=14))
        self.btn_browse.clicked.connect(self._browse_save_dir)
        row_dir.addWidget(self.btn_browse)
        p_layout.addLayout(row_dir)

        layout.addWidget(param_box)

        # 4. 快捷键配置栏
        hk_box = QGroupBox("快捷键配置 (支持应用内与全局热键)")
        hk_layout = QHBoxLayout(hk_box)
        hk_layout.setContentsMargins(14, 10, 14, 10)
        hk_layout.setSpacing(12)

        hk_layout.addWidget(QLabel("开始/停止录制快捷键:"))
        self.edit_key_record = QKeySequenceEdit(QKeySequence("F9"))
        self.edit_key_record.setMinimumHeight(28)
        self.edit_key_record.setMaximumWidth(140)
        self.edit_key_record.keySequenceChanged.connect(self._on_shortcuts_changed)
        hk_layout.addWidget(self.edit_key_record)

        hk_layout.addWidget(QLabel("暂停/恢复录制快捷键:"))
        self.edit_key_pause = QKeySequenceEdit(QKeySequence("F10"))
        self.edit_key_pause.setMinimumHeight(28)
        self.edit_key_pause.setMaximumWidth(140)
        self.edit_key_pause.keySequenceChanged.connect(self._on_shortcuts_changed)
        hk_layout.addWidget(self.edit_key_pause)

        self.btn_reset_keys = QPushButton("恢复默认快捷键")
        self.btn_reset_keys.setIcon(get_icon("refresh", size=13))
        self.btn_reset_keys.clicked.connect(self._reset_default_shortcuts)
        hk_layout.addWidget(self.btn_reset_keys)
        hk_layout.addStretch()

        layout.addWidget(hk_box)

        # 5. 控制台仪表
        dash_box = QGroupBox("录制计时与状态控制台")
        dash_layout = QHBoxLayout(dash_box)
        dash_layout.setContentsMargins(18, 10, 18, 10)
        dash_layout.setSpacing(16)

        self.lbl_timer = QLabel("00:00:00")
        self.lbl_timer.setStyleSheet("font-size: 26px; font-weight: bold; font-family: Consolas, monospace;")
        dash_layout.addWidget(self.lbl_timer)

        self.lbl_status = QLabel("空闲就绪")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 13px; font-weight: 500;")
        dash_layout.addWidget(self.lbl_status, 1)

        self.btn_start = QPushButton("开始录屏")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_start.setIcon(get_icon("play", color="#ffffff", size=16))
        self.btn_start.setFixedSize(120, 38)
        self.btn_start.clicked.connect(self._start_recording)
        dash_layout.addWidget(self.btn_start)

        self.btn_pause = QPushButton("暂停录制")
        self.btn_pause.setIcon(get_icon("stop", size=14))
        self.btn_pause.setFixedSize(120, 38)
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._toggle_pause_action)
        dash_layout.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("停止录屏")
        self.btn_stop.setObjectName("dangerBtn")
        self.btn_stop.setIcon(get_icon("stop", size=14))
        self.btn_stop.setFixedSize(120, 38)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_recording)
        dash_layout.addWidget(self.btn_stop)

        layout.addWidget(dash_box)

        # 6. 历史录像记录表
        hist_box = QGroupBox("最近录像文件")
        hist_layout = QVBoxLayout(hist_box)
        hist_layout.setContentsMargins(12, 10, 12, 10)
        hist_layout.setSpacing(8)

        self.table_hist = QTableWidget()
        self.table_hist.setColumnCount(4)
        self.table_hist.setHorizontalHeaderLabels(["视频名称", "时长", "文件体积", "保存路径"])
        self.table_hist.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_hist.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_hist.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_hist.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_hist.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_hist.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_hist.setMinimumHeight(110)
        hist_layout.addWidget(self.table_hist)

        row_tbl_act = QHBoxLayout()
        row_tbl_act.addStretch()

        self.btn_play = QPushButton("播放视频")
        self.btn_play.setIcon(get_icon("play", size=13))
        self.btn_play.clicked.connect(self._play_selected)
        row_tbl_act.addWidget(self.btn_play)

        self.btn_open_folder = QPushButton("打开保存目录")
        self.btn_open_folder.setIcon(get_icon("folder", size=13))
        self.btn_open_folder.clicked.connect(self._open_folder)
        row_tbl_act.addWidget(self.btn_open_folder)

        hist_layout.addLayout(row_tbl_act)
        layout.addWidget(hist_box)

    def init_connections(self):
        self.engine.tick.connect(self._on_tick)
        self.engine.status_changed.connect(self._on_status_changed)
        self.engine.finished.connect(self._on_record_finished)
        self._setup_shortcuts()

    def _refresh_screen_list(self):
        curr_idx = self.combo_screens.currentIndex()
        self.combo_screens.clear()
        self.combo_screens.addItem("全屏 - 全部桌面 (跨屏幕拼合)", None)
        screens = get_available_screens()
        for s in screens:
            self.combo_screens.addItem(s["title"], s)
        if 0 <= curr_idx < self.combo_screens.count():
            self.combo_screens.setCurrentIndex(curr_idx)

    def _refresh_audio_devices(self):
        # 1. 刷新系统声音设备
        curr_sys = self.combo_system_audio.currentText()
        self.combo_system_audio.clear()
        self.combo_system_audio.addItem("默认系统音频 / 扬声器 (DirectShow / Stereo Mix)")
        for dev in get_audio_output_devices():
            if dev not in [self.combo_system_audio.itemText(i) for i in range(self.combo_system_audio.count())]:
                self.combo_system_audio.addItem(dev)
        if curr_sys:
            idx = self.combo_system_audio.findText(curr_sys)
            if idx >= 0:
                self.combo_system_audio.setCurrentIndex(idx)

        # 2. 刷新麦克风设备
        curr_mic = self.combo_mic.currentText()
        self.combo_mic.clear()
        self.combo_mic.addItem("默认麦克风 (Default Mic)")
        for dev in get_audio_input_devices():
            if dev not in [self.combo_mic.itemText(i) for i in range(self.combo_mic.count())]:
                self.combo_mic.addItem(dev)
        if curr_mic:
            idx = self.combo_mic.findText(curr_mic)
            if idx >= 0:
                self.combo_mic.setCurrentIndex(idx)

    def _on_mode_toggled(self, button, checked):
        if not checked:
            return
        m_id = self.mode_group.checkedId()
        self.screen_target_container.setVisible(m_id == 0)
        self.win_target_container.setVisible(m_id == 1)
        self.rect_target_container.setVisible(m_id == 2)

    def _refresh_window_list(self):
        curr = self.combo_windows.currentText()
        wins = get_visible_windows()
        self.combo_windows.clear()
        for w in wins:
            self.combo_windows.addItem(w)
        if curr in wins:
            self.combo_windows.setCurrentText(curr)

    def _open_region_picker(self):
        self.window().hide()
        QTimer.singleShot(250, self._do_open_region_picker)

    def _do_open_region_picker(self):
        def on_selected(x, y, w, h):
            self.custom_rect = (x, y, w, h)
            self.lbl_rect_coords.setText(f"已选区域: X={x}, Y={y}, 宽度={w}, 高度={h}")
            self.window().show()

        overlay = RegionSelectOverlay(on_selected=on_selected)
        overlay.show()

    def _browse_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择录像保存目录", self.le_save_dir.text())
        if d:
            self.le_save_dir.setText(d)
            self.save_settings()

    def _toggle_recording_action(self):
        if self.engine.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _toggle_pause_action(self):
        if not self.engine.is_recording:
            return
        if self.engine.is_paused:
            self.engine.resume_recording()
        else:
            self.engine.pause_recording()

    def _on_shortcuts_changed(self):
        self._setup_shortcuts()
        self.save_settings()

    def _reset_default_shortcuts(self):
        self.edit_key_record.setKeySequence(QKeySequence("F9"))
        self.edit_key_pause.setKeySequence(QKeySequence("F10"))
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
        # 1. 清理已有 QShortcut
        for sc in self._shortcuts:
            sc.setEnabled(False)
            sc.setParent(None)
            sc.deleteLater()
        self._shortcuts.clear()

        # 2. 清理全局热键
        self._clear_global_hotkeys()

        # 3. 注册应用内快捷键
        seq_rec = self.edit_key_record.keySequence()
        if not seq_rec.isEmpty():
            sc1 = QShortcut(seq_rec, self)
            sc1.setContext(Qt.ApplicationShortcut)
            sc1.activated.connect(self._bridge.sig_toggle_record.emit)
            self._shortcuts.append(sc1)

        seq_pause = self.edit_key_pause.keySequence()
        if not seq_pause.isEmpty():
            sc2 = QShortcut(seq_pause, self)
            sc2.setContext(Qt.ApplicationShortcut)
            sc2.activated.connect(self._bridge.sig_toggle_pause.emit)
            self._shortcuts.append(sc2)

        # 4. 注册全局热键 (若 keyboard 库就绪)
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

            _bind_global(seq_rec.toString(), self._bridge.sig_toggle_record)
            _bind_global(seq_pause.toString(), self._bridge.sig_toggle_pause)
        except Exception:
            pass

    def _start_recording(self):
        if self.engine.is_recording:
            return

        save_dir = self.le_save_dir.text().strip()
        if not save_dir:
            save_dir = os.path.join(os.path.expanduser("~"), "Videos", "ToolboxRecordings")
            self.le_save_dir.setText(save_dir)
        os.makedirs(save_dir, exist_ok=True)

        fmt = self.combo_fmt.currentText().lower()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(save_dir, f"Screen_{timestamp}.{fmt}")

        m_id = self.mode_group.checkedId()
        mode_str = "fullscreen"
        win_title = ""
        rect_val = None
        screen_rect_val = None

        if m_id == 0:
            # 屏幕录制
            screen_data = self.combo_screens.currentData()
            if isinstance(screen_data, dict):
                screen_rect_val = (
                    screen_data["x"],
                    screen_data["y"],
                    screen_data["width"],
                    screen_data["height"]
                )
                mode_str = "screen"
            else:
                mode_str = "fullscreen"
        elif m_id == 1:
            mode_str = "window"
            win_title = self.combo_windows.currentText().strip()
            if not win_title:
                QMessageBox.warning(self, "提示", "请选择有效的录制目标窗口。")
                return
        elif m_id == 2:
            mode_str = "rect"
            if not self.custom_rect:
                QMessageBox.warning(self, "提示", "请先点击框选录制区域。")
                return
            rect_val = self.custom_rect

        fps_map = {0: 60, 1: 30, 2: 15}
        fps = fps_map.get(self.combo_fps.currentIndex(), 30)

        crf_map = {0: 18, 1: 23, 2: 28}
        crf = crf_map.get(self.combo_quality.currentIndex(), 23)

        sys_audio_dev = self.combo_system_audio.currentText().strip() if self.cb_system_audio.isChecked() else ""
        mic_audio_dev = self.combo_mic.currentText().strip() if self.cb_mic.isChecked() else ""

        self.save_settings()

        ok, err = self.engine.start_recording(
            output_path=out_path,
            mode=mode_str,
            window_title=win_title,
            rect=rect_val,
            screen_rect=screen_rect_val,
            fps=fps,
            crf=crf,
            format_choice=fmt,
            record_audio=(bool(sys_audio_dev) or bool(mic_audio_dev)),
            system_audio_device=sys_audio_dev,
            mic_device=mic_audio_dev,
            draw_mouse=self.cb_mouse.isChecked()
        )

        if not ok:
            QMessageBox.critical(self, "启动录屏失败", err)
            return

        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("暂停录制")
        self.btn_pause.setIcon(get_icon("stop", size=14))
        self.btn_stop.setEnabled(True)

    def _stop_recording(self):
        self.engine.stop_recording()
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("暂停录制")
        self.btn_stop.setEnabled(False)

    def _on_tick(self, dur_sec: float):
        self.lbl_timer.setText(format_seconds(dur_sec))

    def _on_status_changed(self, state: str):
        if state == "RECORDING":
            self.lbl_status.setText("正在录屏中...")
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 13px; font-weight: bold;")
            self.btn_pause.setText("暂停录制")
            self.btn_pause.setIcon(get_icon("stop", size=14))
            self.btn_pause.setEnabled(True)
        elif state == "PAUSED":
            self.lbl_status.setText("录屏已暂停 (按快捷键继续)")
            self.lbl_status.setStyleSheet("color: #f59e0b; font-size: 13px; font-weight: bold;")
            self.btn_pause.setText("继续录制")
            self.btn_pause.setIcon(get_icon("play", size=14))
            self.btn_pause.setEnabled(True)
        elif state == "FINISHED":
            self.lbl_status.setText("录屏完成并保存")
            self.lbl_status.setStyleSheet("color: #10b981; font-size: 13px;")
            self.btn_pause.setEnabled(False)
        elif state == "ERROR":
            self.lbl_status.setText("录屏异常终止")
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 13px;")
            self.btn_pause.setEnabled(False)

    def _on_record_finished(self, out_path: str, duration: float):
        if not os.path.exists(out_path):
            return

        sz = os.path.getsize(out_path)
        base = os.path.basename(out_path)
        sz_str = f"{sz / 1024:.1f} KB" if sz < 1024 * 1024 else f"{sz / (1024*1024):.2f} MB"
        item = {
            "name": base,
            "duration": format_seconds(duration),
            "size": sz_str,
            "path": out_path
        }
        self.history_records.insert(0, item)
        self._render_history_table()
        self.save_settings()

    def _render_history_table(self):
        self.table_hist.setRowCount(0)
        for r_idx, rec in enumerate(self.history_records[:15]):
            self.table_hist.insertRow(r_idx)
            item_name = QTableWidgetItem(rec["name"])
            item_name.setIcon(get_icon("video", size=14))
            item_name.setData(Qt.UserRole, rec["path"])
            self.table_hist.setItem(r_idx, 0, item_name)
            self.table_hist.setItem(r_idx, 1, QTableWidgetItem(rec["duration"]))
            self.table_hist.setItem(r_idx, 2, QTableWidgetItem(rec["size"]))
            self.table_hist.setItem(r_idx, 3, QTableWidgetItem(rec["path"]))

    def _play_selected(self):
        rows = self.table_hist.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "请在历史列表中选择录像文件。")
            return
        p = self.table_hist.item(rows[0].row(), 0).data(Qt.UserRole)
        if p and os.path.exists(p):
            from toolbox.core.paths import get_bin_path
            ffplay_exe = get_bin_path("ffplay.exe")
            if ffplay_exe and os.path.isfile(ffplay_exe):
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                subprocess.Popen([ffplay_exe, "-autoexit", p], creationflags=creationflags)
            else:
                os.startfile(p)

    def _open_folder(self):
        save_dir = self.le_save_dir.text().strip()
        if save_dir and os.path.exists(save_dir):
            os.startfile(os.path.normpath(save_dir))
        else:
            QMessageBox.information(self, "提示", "保存目录不存在。")

    def load_settings(self):
        cfg = self.config_manager.get_plugin_config(self.PLUGIN_ID, {})
        m_id = cfg.get("mode_id", 0)
        btn = self.mode_group.button(m_id)
        if btn:
            btn.setChecked(True)
        self._on_mode_toggled(btn, True)

        self.combo_fps.setCurrentIndex(cfg.get("fps_idx", 1))
        self.combo_quality.setCurrentIndex(cfg.get("quality_idx", 1))
        self.combo_fmt.setCurrentIndex(cfg.get("fmt_idx", 0))
        self.cb_mouse.setChecked(cfg.get("draw_mouse", True))

        self.cb_system_audio.setChecked(cfg.get("record_system_audio", False))
        sys_aud_name = cfg.get("system_audio_device", "")
        if sys_aud_name:
            idx = self.combo_system_audio.findText(sys_aud_name)
            if idx >= 0:
                self.combo_system_audio.setCurrentIndex(idx)

        self.cb_mic.setChecked(cfg.get("record_audio", False) or cfg.get("record_mic", False))
        mic_name = cfg.get("mic_device", "") or cfg.get("audio_device", "")
        if mic_name:
            idx = self.combo_mic.findText(mic_name)
            if idx >= 0:
                self.combo_mic.setCurrentIndex(idx)

        key_rec = cfg.get("key_record", "F9")
        key_pause = cfg.get("key_pause", "F10")
        self.edit_key_record.setKeySequence(QKeySequence(key_rec))
        self.edit_key_pause.setKeySequence(QKeySequence(key_pause))
        self._setup_shortcuts()

        default_dir = os.path.join(os.path.expanduser("~"), "Videos", "ToolboxRecordings")
        self.le_save_dir.setText(cfg.get("save_dir", default_dir))
        self.history_records = cfg.get("history", [])
        self._render_history_table()

    def save_settings(self):
        cfg = {
            "mode_id": self.mode_group.checkedId(),
            "screen_idx": self.combo_screens.currentIndex(),
            "fps_idx": self.combo_fps.currentIndex(),
            "quality_idx": self.combo_quality.currentIndex(),
            "fmt_idx": self.combo_fmt.currentIndex(),
            "draw_mouse": self.cb_mouse.isChecked(),
            "record_audio": self.cb_mic.isChecked(),
            "record_mic": self.cb_mic.isChecked(),
            "record_system_audio": self.cb_system_audio.isChecked(),
            "mic_device": self.combo_mic.currentText(),
            "system_audio_device": self.combo_system_audio.currentText(),
            "audio_device": self.combo_mic.currentText(),
            "key_record": self.edit_key_record.keySequence().toString(),
            "key_pause": self.edit_key_pause.keySequence().toString(),
            "save_dir": self.le_save_dir.text(),
            "history": self.history_records[:15]
        }
        self.config_manager.set_plugin_config(self.PLUGIN_ID, cfg)

    def cleanup(self):
        self._clear_global_hotkeys()
        if self.engine.is_recording:
            try:
                self.engine.stop_recording()
            except Exception:
                pass
