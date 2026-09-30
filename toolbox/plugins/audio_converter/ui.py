"""
音频格式批量转换 - UI 界面
提供多格式音频互转、采样率升降频、比特率微调与声道转换。
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
from .engine import scan_audio_files, AudioConvertWorker


class AudioConverterWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.worker: Optional[AudioConvertWorker] = None
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
        icon_lbl.setPixmap(get_pixmap("refresh", color="#8b5cf6", size=26))
        header_layout.addWidget(icon_lbl)

        title_lbl = QLabel("音频格式批量转换工坊")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_lbl)

        badge_lbl = QLabel("全能编解码引擎")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #8b5cf6; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header_layout.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # 2. 待转换音频列表
        self.fl_audios = ModernFileListWidget(
            title="待转换音频文件列表",
            hint="可拖入 MP3 / WAV / FLAC / AAC / OGG / M4A / WMA / APE / OPUS 等任意音频文件或目录"
        )
        layout.addWidget(self.fl_audios, 1)

        # 3. 参数配置
        param_group = QGroupBox("输出音频规格参数")
        param_layout = QVBoxLayout(param_group)
        param_layout.setSpacing(10)

        row_params = QHBoxLayout()
        row_params.setSpacing(12)

        # 目标格式
        row_params.addWidget(QLabel("输出格式:"))
        self.combo_format = QComboBox()
        self.combo_format.addItems(["MP3", "WAV", "FLAC", "AAC", "OGG", "M4A", "WMA"])
        self.combo_format.currentTextChanged.connect(self._on_format_changed)
        row_params.addWidget(self.combo_format)

        # 比特率
        self.lbl_bitrate = QLabel("比特率:")
        row_params.addWidget(self.lbl_bitrate)
        self.combo_bitrate = QComboBox()
        self.combo_bitrate.addItems(["320k (极高)", "256k (高品质)", "192k (标准)", "128k (轻量)", "96k (广播)"])
        row_params.addWidget(self.combo_bitrate)

        # 采样率
        row_params.addWidget(QLabel("采样率:"))
        self.combo_sample_rate = QComboBox()
        self.combo_sample_rate.addItem("保持原采样率", None)
        self.combo_sample_rate.addItem("44.1 kHz (CD标准)", 44100)
        self.combo_sample_rate.addItem("48.0 kHz (专业影视)", 48000)
        self.combo_sample_rate.addItem("96.0 kHz (高解析Hi-Res)", 96000)
        row_params.addWidget(self.combo_sample_rate)

        # 声道
        row_params.addWidget(QLabel("声道:"))
        self.combo_channels = QComboBox()
        self.combo_channels.addItem("保持原声道", None)
        self.combo_channels.addItem("立体声 (2 声道)", 2)
        self.combo_channels.addItem("单声道 (1 声道)", 1)
        row_params.addWidget(self.combo_channels)

        row_params.addStretch()
        param_layout.addLayout(row_params)

        # 目录选择
        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(10)

        self.btn_group_dir = QButtonGroup(self)
        self.rb_same_dir = QRadioButton("保存到源音频同级目录")
        self.rb_same_dir.setChecked(True)
        self.rb_custom_dir = QRadioButton("保存到指定目录:")
        self.btn_group_dir.addButton(self.rb_same_dir)
        self.btn_group_dir.addButton(self.rb_custom_dir)
        self.rb_custom_dir.toggled.connect(self._toggle_custom_dir)

        dir_layout.addWidget(self.rb_same_dir)
        dir_layout.addWidget(self.rb_custom_dir)

        self.le_custom_dir = QLineEdit()
        self.le_custom_dir.setEnabled(False)
        self.le_custom_dir.setText(self.config.get("audio_converter_save_dir", ""))
        dir_layout.addWidget(self.le_custom_dir, 1)

        self.btn_browse_dir = QPushButton("浏览...")
        self.btn_browse_dir.setIcon(get_icon("folder", size=14))
        self.btn_browse_dir.setEnabled(False)
        self.btn_browse_dir.clicked.connect(self._browse_custom_dir)
        dir_layout.addWidget(self.btn_browse_dir)

        param_layout.addLayout(dir_layout)
        layout.addWidget(param_group)

        # 4. 执行控制
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.btn_start = QPushButton("开始批量音频转换")
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

        # 进度与状态
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(self.lbl_status)

        # 日志
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFixedHeight(95)
        self.log_console.setPlaceholderText("音频转换日志...")
        layout.addWidget(self.log_console)

    def _on_format_changed(self, fmt: str):
        is_lossless = fmt in ("FLAC", "WAV")
        self.lbl_bitrate.setEnabled(not is_lossless)
        self.combo_bitrate.setEnabled(not is_lossless)

    def _toggle_custom_dir(self, checked: bool):
        self.le_custom_dir.setEnabled(checked)
        self.btn_browse_dir.setEnabled(checked)

    def _browse_custom_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "选择输出文件夹", self.le_custom_dir.text())
        if chosen:
            self.le_custom_dir.setText(chosen)
            self.config.set("audio_converter_save_dir", chosen)

    def _open_output_dir(self):
        if self.rb_custom_dir.isChecked() and self.le_custom_dir.text().strip():
            target = self.le_custom_dir.text().strip()
        else:
            paths = self.fl_audios.get_paths()
            target = os.path.dirname(paths[0]) if paths else os.path.expanduser("~")

        if os.path.exists(target):
            subprocess.Popen(f'explorer "{os.path.normpath(target)}"')
        else:
            self._log("[提示] 目标目录不存在。")

    def _start_conversion(self):
        raw_paths = self.fl_audios.get_paths()
        if not raw_paths:
            self._log("[提示] 请先添加需要转换的音频文件。")
            return

        valid_audios = scan_audio_files(raw_paths)
        if not valid_audios:
            self._log("[提示] 列表中未包含支持的有效音频格式。")
            return

        fmt = self.combo_format.currentText().lower()
        bitrate_str = self.combo_bitrate.currentText().split()[0]
        sample_rate = self.combo_sample_rate.currentData()
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

        self.worker = AudioConvertWorker(
            file_paths=valid_audios,
            output_format=fmt,
            bitrate=bitrate_str if fmt not in ("flac", "wav") else None,
            sample_rate=sample_rate,
            channels=channels,
            custom_output_dir=custom_dir
        )
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.file_started.connect(lambda f, i, t: self.lbl_status.setText(f"正在转换 ({i}/{t}): {f}"))
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
            self.fl_audios.set_paths(paths)

    def load_settings(self):
        cfg = self.config.get_plugin_config("audio_converter", {})
        fmt_idx = cfg.get("format_idx", 0)
        if 0 <= fmt_idx < self.combo_format.count():
            self.combo_format.setCurrentIndex(fmt_idx)
        bitrate_idx = cfg.get("bitrate_idx", 0)
        if 0 <= bitrate_idx < self.combo_bitrate.count():
            self.combo_bitrate.setCurrentIndex(bitrate_idx)
        sr_idx = cfg.get("sample_rate_idx", 0)
        if 0 <= sr_idx < self.combo_sample_rate.count():
            self.combo_sample_rate.setCurrentIndex(sr_idx)
        ch_idx = cfg.get("channels_idx", 0)
        if 0 <= ch_idx < self.combo_channels.count():
            self.combo_channels.setCurrentIndex(ch_idx)

        use_custom = cfg.get("use_custom_dir", False)
        if use_custom:
            self.rb_custom_dir.setChecked(True)
        else:
            self.rb_same_dir.setChecked(True)
        self.le_custom_dir.setText(cfg.get("custom_dir", self.config.get("audio_converter_save_dir", "")))

    def save_settings(self):
        cfg = {
            "format_idx": self.combo_format.currentIndex(),
            "bitrate_idx": self.combo_bitrate.currentIndex(),
            "sample_rate_idx": self.combo_sample_rate.currentIndex(),
            "channels_idx": self.combo_channels.currentIndex(),
            "use_custom_dir": self.rb_custom_dir.isChecked(),
            "custom_dir": self.le_custom_dir.text()
        }
        self.config.set_plugin_config("audio_converter", cfg)
