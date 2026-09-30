"""
批量视频转音频 - UI 界面
支持拖拽各种格式视频，批量一键极速提取为 MP3 / FLAC / WAV / AAC 等纯音频。
"""

import os
import subprocess
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QProgressBar, QTextEdit, QRadioButton,
    QButtonGroup, QLineEdit, QFileDialog, QGroupBox
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.components.drag_drop_box import ModernFileListWidget
from toolbox.ui.icons import get_icon, get_pixmap
from .engine import scan_video_files, VideoToAudioWorker


class VideoToAudioWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.worker: Optional[VideoToAudioWorker] = None
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(14)

        # 1. 顶部标题栏
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("music", color="#3b82f6", size=26))
        header_layout.addWidget(icon_lbl)

        title_lbl = QLabel("批量视频转音频 (音频音轨提取)")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_lbl)

        badge_lbl = QLabel("FFmpeg 无损/高码率引擎")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header_layout.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # 2. 核心文件拖拽列表
        self.fl_videos = ModernFileListWidget(
            title="待处理视频文件列表",
            hint="可拖入任意 MP4 / MKV / AVI / MOV / FLV / WMV 等视频文件或文件夹"
        )
        layout.addWidget(self.fl_videos, 1)

        # 3. 参数配置选项
        config_group = QGroupBox("音频提取参数配置")
        config_layout = QVBoxLayout(config_group)
        config_layout.setSpacing(10)

        row_params = QHBoxLayout()
        row_params.setSpacing(14)

        # 目标格式
        row_params.addWidget(QLabel("目标音频格式:"))
        self.combo_format = QComboBox()
        self.combo_format.addItems(["MP3", "FLAC", "WAV", "AAC", "M4A", "OGG"])
        self.combo_format.currentTextChanged.connect(self._on_format_changed)
        row_params.addWidget(self.combo_format)

        # 比特率
        self.lbl_bitrate = QLabel("音频码率:")
        row_params.addWidget(self.lbl_bitrate)
        self.combo_bitrate = QComboBox()
        self.combo_bitrate.addItems(["320k (极高保真)", "256k (高保真)", "192k (标准CD级)", "128k (普通压缩)"])
        row_params.addWidget(self.combo_bitrate)

        # 声道配置
        row_params.addWidget(QLabel("声道设置:"))
        self.combo_channels = QComboBox()
        self.combo_channels.addItem("保持源声道", None)
        self.combo_channels.addItem("立体声 (2 声道)", 2)
        self.combo_channels.addItem("单声道 (1 声道)", 1)
        row_params.addWidget(self.combo_channels)

        row_params.addStretch()
        config_layout.addLayout(row_params)

        # 保存目录配置
        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(10)

        self.btn_group_dir = QButtonGroup(self)
        self.rb_same_dir = QRadioButton("保存到源视频同级目录")
        self.rb_same_dir.setChecked(True)
        self.rb_custom_dir = QRadioButton("保存到指定目录:")
        self.btn_group_dir.addButton(self.rb_same_dir)
        self.btn_group_dir.addButton(self.rb_custom_dir)
        self.rb_custom_dir.toggled.connect(self._toggle_custom_dir)

        dir_layout.addWidget(self.rb_same_dir)
        dir_layout.addWidget(self.rb_custom_dir)

        self.le_custom_dir = QLineEdit()
        self.le_custom_dir.setEnabled(False)
        self.le_custom_dir.setText(self.config.get("video_to_audio_save_dir", ""))
        dir_layout.addWidget(self.le_custom_dir, 1)

        self.btn_browse_dir = QPushButton("浏览...")
        self.btn_browse_dir.setIcon(get_icon("folder", size=14))
        self.btn_browse_dir.setEnabled(False)
        self.btn_browse_dir.clicked.connect(self._browse_custom_dir)
        dir_layout.addWidget(self.btn_browse_dir)

        config_layout.addLayout(dir_layout)
        layout.addWidget(config_group)

        # 4. 执行控制与进度
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.btn_start = QPushButton("开始批量提取音频")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_start.setIcon(get_icon("play", size=16))
        self.btn_start.setFixedHeight(36)
        self.btn_start.clicked.connect(self._start_conversion)
        action_layout.addWidget(self.btn_start, 1)

        self.btn_cancel = QPushButton("中止")
        self.btn_cancel.setObjectName("dangerBtn")
        self.btn_cancel.setIcon(get_icon("clear", size=14))
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_conversion)
        action_layout.addWidget(self.btn_cancel)

        self.btn_open_output = QPushButton("打开输出目录")
        self.btn_open_output.setIcon(get_icon("folder", size=14))
        self.btn_open_output.setFixedHeight(36)
        self.btn_open_output.clicked.connect(self._open_output_dir)
        action_layout.addWidget(self.btn_open_output)

        layout.addLayout(action_layout)

        # 进度条与状态
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(self.lbl_status)

        # 日志控制台
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFixedHeight(95)
        self.log_console.setPlaceholderText("批量任务输出日志...")
        layout.addWidget(self.log_console)

    def _on_format_changed(self, fmt: str):
        # 无损格式如 WAV / FLAC 隐藏或禁用码率
        is_lossless = fmt in ("FLAC", "WAV")
        self.lbl_bitrate.setEnabled(not is_lossless)
        self.combo_bitrate.setEnabled(not is_lossless)

    def _toggle_custom_dir(self, checked: bool):
        self.le_custom_dir.setEnabled(checked)
        self.btn_browse_dir.setEnabled(checked)

    def _browse_custom_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "选择音频输出目录", self.le_custom_dir.text())
        if chosen:
            self.le_custom_dir.setText(chosen)
            self.config.set("video_to_audio_save_dir", chosen)

    def _open_output_dir(self):
        if self.rb_custom_dir.isChecked() and self.le_custom_dir.text().strip():
            target = self.le_custom_dir.text().strip()
        else:
            paths = self.fl_videos.get_paths()
            target = os.path.dirname(paths[0]) if paths else os.path.expanduser("~")

        if os.path.exists(target):
            subprocess.Popen(f'explorer "{os.path.normpath(target)}"')
        else:
            self._log("[提示] 目标目录不存在。")

    def _start_conversion(self):
        raw_paths = self.fl_videos.get_paths()
        if not raw_paths:
            self._log("[提示] 请先添加需要提取音频的视频文件。")
            return

        valid_videos = scan_video_files(raw_paths)
        if not valid_videos:
            self._log("[提示] 列表中未包含支持的有效视频格式。")
            return

        fmt = self.combo_format.currentText().lower()
        bitrate_str = self.combo_bitrate.currentText().split()[0]
        channels = self.combo_channels.currentData()

        custom_dir = None
        if self.rb_custom_dir.isChecked():
            custom_dir = self.le_custom_dir.text().strip()
            if not custom_dir:
                self._log("[提示] 请指定自定义输出目录。")
                return

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("开始转换...")

        self.worker = VideoToAudioWorker(
            file_paths=valid_videos,
            output_format=fmt,
            bitrate=bitrate_str,
            custom_output_dir=custom_dir,
            channels=channels
        )
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.file_started.connect(lambda f, i, t: self.lbl_status.setText(f"正在处理 ({i}/{t}): {f}"))
        self.worker.log_message.connect(self._log)
        self.worker.batch_finished.connect(self._on_batch_finished)
        self.worker.start()

    def _cancel_conversion(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.lbl_status.setText("正在中止...")
            self.btn_cancel.setEnabled(False)

    def _on_batch_finished(self, success: int, failed: int):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.lbl_status.setText(f"转换结束: 成功 {success} 项, 失败 {failed} 项")

    def _log(self, text: str):
        self.log_console.append(text)

    def handle_initial_paths(self, paths: list):
        if paths:
            self.fl_videos.set_paths(paths)

    def load_settings(self):
        cfg = self.config.get_plugin_config("video_to_audio", {})
        fmt_idx = cfg.get("format_idx", 0)
        if 0 <= fmt_idx < self.combo_format.count():
            self.combo_format.setCurrentIndex(fmt_idx)
        bitrate_idx = cfg.get("bitrate_idx", 0)
        if 0 <= bitrate_idx < self.combo_bitrate.count():
            self.combo_bitrate.setCurrentIndex(bitrate_idx)
        ch_idx = cfg.get("channels_idx", 0)
        if 0 <= ch_idx < self.combo_channels.count():
            self.combo_channels.setCurrentIndex(ch_idx)

        use_custom = cfg.get("use_custom_dir", False)
        if use_custom:
            self.rb_custom_dir.setChecked(True)
        else:
            self.rb_same_dir.setChecked(True)
        self.le_custom_dir.setText(cfg.get("custom_dir", self.config.get("video_to_audio_save_dir", "")))

    def save_settings(self):
        cfg = {
            "format_idx": self.combo_format.currentIndex(),
            "bitrate_idx": self.combo_bitrate.currentIndex(),
            "channels_idx": self.combo_channels.currentIndex(),
            "use_custom_dir": self.rb_custom_dir.isChecked(),
            "custom_dir": self.le_custom_dir.text()
        }
        self.config.set_plugin_config("video_to_audio", cfg)
