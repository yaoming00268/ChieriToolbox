"""
高清录音工具 - UI 界面
提供高采样率麦克风录制、声波电平动态可视化、定时计量与历史音频回放。
"""

import os
import time
import subprocess
from typing import Optional, List, Dict, Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QGroupBox, QLineEdit, QFileDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.icons import get_icon, get_pixmap
from toolbox.core.paths import find_ffmpeg_executable, get_audio_input_devices
from .engine import AudioRecorderSession
from .visualizer import WaveformVisualizer


def format_seconds(seconds: float) -> str:
    """格式化秒数为 HH:MM:SS.s"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    fraction = int((seconds - int(seconds)) * 10)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{fraction}"


class AudioRecorderWidget(QWidget):
    PLUGIN_ID = "audio_recorder"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self.session = AudioRecorderSession(self)
        self.history_records: List[Dict[str, Any]] = []

        self.init_ui()
        self.init_connections()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(14)

        # 1. 顶部 Header
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("mic", color="#3b82f6", size=26))
        header.addWidget(icon_lbl)

        title_lbl = QLabel("高清录音工具 (Microphone Recorder)")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title_lbl)

        badge_lbl = QLabel("无损采集 · 动态电平可视化")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header.addStretch()
        layout.addLayout(header)

        # 2. 硬件与格式配置组
        cfg_group = QGroupBox("输入设备与音频参数")
        cfg_layout = QVBoxLayout(cfg_group)
        cfg_layout.setSpacing(8)

        row_dev = QHBoxLayout()
        row_dev.addWidget(QLabel("麦克风设备:"))
        self.combo_device = QComboBox()
        self._refresh_devices()
        row_dev.addWidget(self.combo_device, 1)

        self.btn_refresh_dev = QPushButton("刷新设备")
        self.btn_refresh_dev.setIcon(get_icon("refresh", size=14))
        self.btn_refresh_dev.clicked.connect(self._refresh_devices)
        row_dev.addWidget(self.btn_refresh_dev)

        cfg_layout.addLayout(row_dev)

        # 参数行
        row_params = QHBoxLayout()
        row_params.setSpacing(12)

        row_params.addWidget(QLabel("导出格式:"))
        self.combo_format = QComboBox()
        self.combo_format.addItems(["MP3", "WAV", "AAC", "FLAC"])
        row_params.addWidget(self.combo_format)

        row_params.addWidget(QLabel("比特率:"))
        self.combo_bitrate = QComboBox()
        self.combo_bitrate.addItems(["320k (极高品质)", "256k (高保真)", "192k (标准CD)", "128k (标准压缩)"])
        row_params.addWidget(self.combo_bitrate)

        row_params.addWidget(QLabel("采样率:"))
        self.combo_rate = QComboBox()
        self.combo_rate.addItems(["48000 Hz (专业级)", "44100 Hz (CD级)"])
        row_params.addWidget(self.combo_rate)

        row_params.addWidget(QLabel("声道:"))
        self.combo_channels = QComboBox()
        self.combo_channels.addItems(["双声道 (立体声)", "单声道"])
        row_params.addWidget(self.combo_channels)

        row_params.addStretch()
        cfg_layout.addLayout(row_params)

        # 存储路径行
        row_path = QHBoxLayout()
        row_path.addWidget(QLabel("保存目录:"))
        self.le_save_dir = QLineEdit()
        row_path.addWidget(self.le_save_dir, 1)

        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.setIcon(get_icon("folder", size=14))
        self.btn_browse.clicked.connect(self._browse_save_dir)
        row_path.addWidget(self.btn_browse)

        cfg_layout.addLayout(row_path)
        layout.addWidget(cfg_group)

        # 3. 核心视觉仪表盘与波形展示区
        dashboard = QGroupBox("实时录音状态与声波电平")
        dash_layout = QVBoxLayout(dashboard)
        dash_layout.setContentsMargins(18, 14, 18, 14)
        dash_layout.setSpacing(10)
        dash_layout.setAlignment(Qt.AlignCenter)

        # 计时器大字号展示
        self.lbl_timer = QLabel("00:00:00.0")
        self.lbl_timer.setStyleSheet("font-size: 32px; font-weight: bold; font-family: Consolas, monospace;")
        self.lbl_timer.setAlignment(Qt.AlignCenter)
        dash_layout.addWidget(self.lbl_timer)

        # 状态提示胶囊
        self.lbl_state = QLabel("空闲就绪 · 随时可录制")
        self.lbl_state.setStyleSheet("color: #64748b; font-size: 13px; font-weight: 500;")
        self.lbl_state.setAlignment(Qt.AlignCenter)
        dash_layout.addWidget(self.lbl_state)

        # 动态音频声波可视化控件
        self.visualizer = WaveformVisualizer(num_bars=36, parent=self)
        dash_layout.addWidget(self.visualizer)

        # 操作控制按钮栏
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(12)
        ctrl_layout.setAlignment(Qt.AlignCenter)

        self.btn_record = QPushButton("开始录音")
        self.btn_record.setObjectName("primaryBtn")
        self.btn_record.setIcon(get_icon("mic", color="#ffffff", size=16))
        self.btn_record.setFixedSize(120, 38)
        self.btn_record.clicked.connect(self._toggle_record)
        ctrl_layout.addWidget(self.btn_record)

        self.btn_pause = QPushButton("暂停录音")
        self.btn_pause.setIcon(get_icon("pause", size=15))
        self.btn_pause.setFixedSize(110, 38)
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._toggle_pause)
        ctrl_layout.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("停止并保存")
        self.btn_stop.setObjectName("dangerBtn")
        self.btn_stop.setIcon(get_icon("stop", size=14))
        self.btn_stop.setFixedSize(120, 38)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_record)
        ctrl_layout.addWidget(self.btn_stop)

        dash_layout.addLayout(ctrl_layout)
        layout.addWidget(dashboard)

        # 4. 历史录音文件记录表
        history_group = QGroupBox("最近录音文件清单")
        h_layout = QVBoxLayout(history_group)
        h_layout.setContentsMargins(10, 8, 10, 8)
        h_layout.setSpacing(6)

        self.table_history = QTableWidget()
        self.table_history.setColumnCount(4)
        self.table_history.setHorizontalHeaderLabels(["文件名称", "录音时长", "文件大小", "生成路径"])
        self.table_history.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_history.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_history.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_history.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_history.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_history.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_history.setFixedHeight(120)
        h_layout.addWidget(self.table_history)

        row_tbl_actions = QHBoxLayout()
        row_tbl_actions.addStretch()

        self.btn_play_selected = QPushButton("播放试听")
        self.btn_play_selected.setIcon(get_icon("play", size=13))
        self.btn_play_selected.clicked.connect(self._play_selected)
        row_tbl_actions.addWidget(self.btn_play_selected)

        self.btn_open_folder = QPushButton("打开保存目录")
        self.btn_open_folder.setIcon(get_icon("folder", size=13))
        self.btn_open_folder.clicked.connect(self._open_folder)
        row_tbl_actions.addWidget(self.btn_open_folder)

        h_layout.addLayout(row_tbl_actions)
        layout.addWidget(history_group)

    def init_connections(self):
        self.session.tick.connect(self._on_tick)
        self.session.level_updated.connect(self.visualizer.set_level)
        self.session.status_changed.connect(self._on_status_changed)
        self.session.finished.connect(self._on_record_finished)

    def _refresh_devices(self):
        curr = self.combo_device.currentText()
        devs = get_audio_input_devices()
        self.combo_device.clear()
        for d in devs:
            self.combo_device.addItem(d)
        if curr in devs:
            self.combo_device.setCurrentText(curr)

    def _browse_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择录音保存目录", self.le_save_dir.text())
        if d:
            self.le_save_dir.setText(d)
            self.save_settings()

    def _toggle_record(self):
        if self.session.is_recording:
            return

        save_dir = self.le_save_dir.text().strip()
        if not save_dir:
            save_dir = os.path.join(os.path.expanduser("~"), "Music", "ToolboxRecordings")
            self.le_save_dir.setText(save_dir)
        os.makedirs(save_dir, exist_ok=True)

        fmt = self.combo_format.currentText().lower()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_file = os.path.join(save_dir, f"Record_{timestamp}.{fmt}")

        device = self.combo_device.currentText()
        br_map = {0: "320k", 1: "256k", 2: "192k", 3: "128k"}
        bitrate = br_map.get(self.combo_bitrate.currentIndex(), "192k")
        rate = 48000 if self.combo_rate.currentIndex() == 0 else 44100
        channels = 2 if self.combo_channels.currentIndex() == 0 else 1

        self.save_settings()
        ok, err = self.session.start_recording(
            device_name=device,
            output_path=out_file,
            format_choice=fmt,
            sample_rate=rate,
            channels=channels,
            bitrate=bitrate
        )

        if not ok:
            QMessageBox.critical(self, "启动录音失败", err)
            return

        self.btn_record.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("暂停录音")
        self.btn_stop.setEnabled(True)
        self.visualizer.set_state(active=True, paused=False)

    def _toggle_pause(self):
        if not self.session.is_recording:
            return

        if self.session.is_paused:
            self.session.resume_recording()
            self.btn_pause.setText("暂停录音")
            self.visualizer.set_state(active=True, paused=False)
        else:
            self.session.pause_recording()
            self.btn_pause.setText("继续录音")
            self.visualizer.set_state(active=True, paused=True)

    def _stop_record(self):
        self.session.stop_recording()
        self.btn_record.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.visualizer.set_state(active=False)

    def _on_tick(self, dur_sec: float):
        self.lbl_timer.setText(format_seconds(dur_sec))

    def _on_status_changed(self, state: str):
        if state == "RECORDING":
            self.lbl_state.setText("正在录音中... 音频流实时写入")
            self.lbl_state.setStyleSheet("color: #10b981; font-size: 13px; font-weight: bold;")
        elif state == "PAUSED":
            self.lbl_state.setText("录音已暂停")
            self.lbl_state.setStyleSheet("color: #f59e0b; font-size: 13px; font-weight: bold;")
        elif state == "FINISHED":
            self.lbl_state.setText("录音已完成并保存至本地")
            self.lbl_state.setStyleSheet("color: #3b82f6; font-size: 13px;")
        elif state == "ERROR":
            self.lbl_state.setText("录音异常终止")
            self.lbl_state.setStyleSheet("color: #ef4444; font-size: 13px;")

    def _on_record_finished(self, out_path: str, duration: float):
        if not os.path.exists(out_path):
            return

        size = os.path.getsize(out_path)
        base = os.path.basename(out_path)
        item_data = {
            "name": base,
            "duration": format_seconds(duration),
            "size": f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024*1024):.2f} MB",
            "path": out_path
        }
        self.history_records.insert(0, item_data)
        self._render_history_table()
        self.save_settings()

    def _render_history_table(self):
        self.table_history.setRowCount(0)
        for r_idx, rec in enumerate(self.history_records[:20]):
            self.table_history.insertRow(r_idx)
            item_name = QTableWidgetItem(rec["name"])
            item_name.setIcon(get_icon("music", size=14))
            item_name.setData(Qt.UserRole, rec["path"])
            self.table_history.setItem(r_idx, 0, item_name)
            self.table_history.setItem(r_idx, 1, QTableWidgetItem(rec["duration"]))
            self.table_history.setItem(r_idx, 2, QTableWidgetItem(rec["size"]))
            self.table_history.setItem(r_idx, 3, QTableWidgetItem(rec["path"]))

    def _play_selected(self):
        rows = self.table_history.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "请先在历史列表中选中需要试听的录音。")
            return

        item = self.table_history.item(rows[0].row(), 0)
        p = item.data(Qt.UserRole)
        if p and os.path.exists(p):
            # 优先调用本地 ffplay 极速无黑框播放，否则调用系统默认播放器
            from toolbox.core.paths import get_bin_path
            ffplay_exe = get_bin_path("ffplay.exe")
            if ffplay_exe and os.path.isfile(ffplay_exe):
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                subprocess.Popen([ffplay_exe, "-nodisp", "-autoexit", p], creationflags=creationflags)
            else:
                os.startfile(p)

    def _open_folder(self):
        save_dir = self.le_save_dir.text().strip()
        if save_dir and os.path.exists(save_dir):
            os.startfile(os.path.normpath(save_dir))
        else:
            QMessageBox.information(self, "提示", "保存目录尚不存在。")

    def load_settings(self):
        cfg = self.config_manager.get_plugin_config(self.PLUGIN_ID, {})
        dev = cfg.get("device", "")
        if dev and self.combo_device.findText(dev) >= 0:
            self.combo_device.setCurrentText(dev)
        self.combo_format.setCurrentIndex(cfg.get("format_idx", 0))
        self.combo_bitrate.setCurrentIndex(cfg.get("bitrate_idx", 2))
        self.combo_rate.setCurrentIndex(cfg.get("rate_idx", 0))
        self.combo_channels.setCurrentIndex(cfg.get("channels_idx", 0))

        default_dir = os.path.join(os.path.expanduser("~"), "Music", "ToolboxRecordings")
        self.le_save_dir.setText(cfg.get("save_dir", default_dir))
        self.history_records = cfg.get("history", [])
        self._render_history_table()

    def save_settings(self):
        cfg = {
            "device": self.combo_device.currentText(),
            "format_idx": self.combo_format.currentIndex(),
            "bitrate_idx": self.combo_bitrate.currentIndex(),
            "rate_idx": self.combo_rate.currentIndex(),
            "channels_idx": self.combo_channels.currentIndex(),
            "save_dir": self.le_save_dir.text(),
            "history": self.history_records[:20]
        }
        self.config_manager.set_plugin_config(self.PLUGIN_ID, cfg)
