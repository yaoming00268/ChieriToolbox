"""
音频精准剪裁 - UI 界面
提供毫秒级时间码输入、截取时长自动计算、流拷贝无损剪切与重编码导出。
"""

import os
import subprocess
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QDoubleSpinBox, QGroupBox,
    QProgressBar, QTextEdit, QFileDialog, QRadioButton, QButtonGroup,
    QScrollArea, QFrame
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.icons import get_icon, get_pixmap
from .engine import (
    probe_audio_file, seconds_to_timecode, timecode_to_seconds,
    AudioCutWorker
)


class AudioCutterWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.config = ConfigManager()
        self.current_audio_path: str = ""
        self.total_duration: float = 0.0
        self.worker: Optional[AudioCutWorker] = None

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

        # 1. 顶部标题栏
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("scissors", color="#ec4899", size=26))
        header_layout.addWidget(icon_lbl)

        title_lbl = QLabel("音频精准剪裁与分割")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_lbl)

        badge_lbl = QLabel("毫秒级微调 · 无损流拷贝")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #ec4899; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header_layout.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # 2. 音频文件载入与规格概览栏
        file_group = QGroupBox("选择或拖入音频文件")
        file_box_layout = QVBoxLayout(file_group)
        file_box_layout.setContentsMargins(14, 10, 14, 10)
        file_box_layout.setSpacing(8)

        file_layout = QHBoxLayout()
        file_layout.setSpacing(8)

        self.le_file_path = QLineEdit()
        self.le_file_path.setPlaceholderText("选择或直接拖入 MP3 / WAV / FLAC / AAC / M4A 等音频文件...")
        self.le_file_path.textChanged.connect(self._on_file_changed)
        file_layout.addWidget(self.le_file_path, 1)

        self.btn_browse = QPushButton("浏览文件...")
        self.btn_browse.setIcon(get_icon("folder", size=14))
        self.btn_browse.clicked.connect(self._browse_audio_file)
        file_layout.addWidget(self.btn_browse)
        file_box_layout.addLayout(file_layout)

        # 音频属性概览行
        self.info_group = QWidget()
        info_layout = QHBoxLayout(self.info_group)
        info_layout.setContentsMargins(2, 0, 2, 0)
        info_layout.setSpacing(16)

        self.lbl_info_dur = QLabel("总时长: -")
        self.lbl_info_dur.setStyleSheet("font-size: 12px; font-weight: bold; color: #ec4899;")
        info_layout.addWidget(self.lbl_info_dur)

        self.lbl_info_codec = QLabel("编码格式: -")
        self.lbl_info_codec.setStyleSheet("font-size: 12px; color: #94a3b8;")
        info_layout.addWidget(self.lbl_info_codec)

        self.lbl_info_rate = QLabel("采样率: -")
        self.lbl_info_rate.setStyleSheet("font-size: 12px; color: #94a3b8;")
        info_layout.addWidget(self.lbl_info_rate)

        self.lbl_info_channels = QLabel("声道: -")
        self.lbl_info_channels.setStyleSheet("font-size: 12px; color: #94a3b8;")
        info_layout.addWidget(self.lbl_info_channels)

        info_layout.addStretch()
        file_box_layout.addWidget(self.info_group)

        layout.addWidget(file_group)

        # 3. 时间轴与时间码设置
        time_group = QGroupBox("剪裁时间范围设置 (秒/毫秒)")
        time_layout = QVBoxLayout(time_group)
        time_layout.setContentsMargins(14, 8, 14, 8)
        time_layout.setSpacing(6)

        # 起始时间
        start_row = QHBoxLayout()
        start_row.setSpacing(10)
        start_row.addWidget(QLabel("起始时间点:"))

        self.spin_start = QDoubleSpinBox()
        self.spin_start.setRange(0.0, 999999.0)
        self.spin_start.setDecimals(3)
        self.spin_start.setSingleStep(0.5)
        self.spin_start.setSuffix(" 秒")
        self.spin_start.setFixedWidth(115)
        self.spin_start.valueChanged.connect(self._update_duration_display)
        start_row.addWidget(self.spin_start)

        self.lbl_start_tc = QLabel("(00:00:00.000)")
        self.lbl_start_tc.setStyleSheet("color: #64748b; font-size: 12px;")
        start_row.addWidget(self.lbl_start_tc)

        self.btn_start_zero = QPushButton("归零")
        self.btn_start_zero.clicked.connect(lambda: self.spin_start.setValue(0.0))
        start_row.addWidget(self.btn_start_zero)

        self.btn_start_minus1 = QPushButton("-1秒")
        self.btn_start_minus1.clicked.connect(lambda: self.spin_start.setValue(max(0.0, self.spin_start.value() - 1.0)))
        start_row.addWidget(self.btn_start_minus1)

        self.btn_start_plus1 = QPushButton("+1秒")
        self.btn_start_plus1.clicked.connect(lambda: self.spin_start.setValue(self.spin_start.value() + 1.0))
        start_row.addWidget(self.btn_start_plus1)

        start_row.addStretch()
        time_layout.addLayout(start_row)

        # 结束时间
        end_row = QHBoxLayout()
        end_row.setSpacing(10)
        end_row.addWidget(QLabel("结束时间点:"))

        self.spin_end = QDoubleSpinBox()
        self.spin_end.setRange(0.0, 999999.0)
        self.spin_end.setDecimals(3)
        self.spin_end.setSingleStep(0.5)
        self.spin_end.setSuffix(" 秒")
        self.spin_end.setFixedWidth(115)
        self.spin_end.valueChanged.connect(self._update_duration_display)
        end_row.addWidget(self.spin_end)

        self.lbl_end_tc = QLabel("(00:00:00.000)")
        self.lbl_end_tc.setStyleSheet("color: #64748b; font-size: 12px;")
        end_row.addWidget(self.lbl_end_tc)

        self.btn_end_max = QPushButton("设为总长")
        self.btn_end_max.clicked.connect(lambda: self.spin_end.setValue(self.total_duration))
        end_row.addWidget(self.btn_end_max)

        self.btn_end_minus1 = QPushButton("-1秒")
        self.btn_end_minus1.clicked.connect(lambda: self.spin_end.setValue(max(0.0, self.spin_end.value() - 1.0)))
        end_row.addWidget(self.btn_end_minus1)

        self.btn_end_plus1 = QPushButton("+1秒")
        self.btn_end_plus1.clicked.connect(lambda: self.spin_end.setValue(self.spin_end.value() + 1.0))
        end_row.addWidget(self.btn_end_plus1)

        end_row.addStretch()
        time_layout.addLayout(end_row)

        # 选区总长显示
        self.lbl_cut_dur = QLabel("选区总长: 0.000 秒 (00:00:00.000)")
        self.lbl_cut_dur.setStyleSheet("font-size: 13px; font-weight: bold; color: #3b82f6;")
        time_layout.addWidget(self.lbl_cut_dur)

        layout.addWidget(time_group)

        # 4. 导出模式与格式配置
        export_group = QGroupBox("导出模式与参数")
        export_layout = QVBoxLayout(export_group)
        export_layout.setContentsMargins(14, 8, 14, 8)
        export_layout.setSpacing(6)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(14)

        self.mode_group = QButtonGroup(self)
        self.rb_copy = QRadioButton("无损流拷贝 (保持原音质，极速秒切)")
        self.rb_copy.setChecked(True)
        self.rb_reencode = QRadioButton("重新编码导出 (转换格式与码率)")
        self.mode_group.addButton(self.rb_copy)
        self.mode_group.addButton(self.rb_reencode)
        self.rb_reencode.toggled.connect(self._toggle_reencode_opts)

        mode_row.addWidget(self.rb_copy)
        mode_row.addWidget(self.rb_reencode)
        mode_row.addStretch()
        export_layout.addLayout(mode_row)

        # 编码微调行 (默认禁用)
        self.reencode_row = QHBoxLayout()
        self.reencode_row.setSpacing(12)

        self.reencode_row.addWidget(QLabel("导出格式:"))
        self.combo_format = QComboBox()
        self.combo_format.addItems(["MP3", "WAV", "FLAC", "AAC", "M4A", "OGG"])
        self.combo_format.setFixedWidth(80)
        self.combo_format.setEnabled(False)
        self.combo_format.currentTextChanged.connect(self._sync_output_extension)
        self.reencode_row.addWidget(self.combo_format)

        self.reencode_row.addWidget(QLabel("码率:"))
        self.combo_bitrate = QComboBox()
        self.combo_bitrate.addItems(["320k", "256k", "192k", "128k"])
        self.combo_bitrate.setFixedWidth(80)
        self.combo_bitrate.setEnabled(False)
        self.reencode_row.addWidget(self.combo_bitrate)

        self.reencode_row.addStretch()
        export_layout.addLayout(self.reencode_row)

        # 输出保存路径
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        out_row.addWidget(QLabel("输出保存路径:"))

        self.le_output_path = QLineEdit()
        out_row.addWidget(self.le_output_path, 1)

        self.btn_browse_output = QPushButton("更改保存位置...")
        self.btn_browse_output.setIcon(get_icon("folder", size=14))
        self.btn_browse_output.clicked.connect(self._browse_output_path)
        out_row.addWidget(self.btn_browse_output)

        export_layout.addLayout(out_row)
        layout.addWidget(export_group)

        # 5. 执行按钮与进度
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.btn_cut = QPushButton("开始剪裁并导出")
        self.btn_cut.setObjectName("primaryBtn")
        self.btn_cut.setIcon(get_icon("scissors", size=16))
        self.btn_cut.setFixedHeight(36)
        self.btn_cut.clicked.connect(self._start_cut)
        action_row.addWidget(self.btn_cut, 1)

        self.btn_open_dir = QPushButton("打开保存目录")
        self.btn_open_dir.setIcon(get_icon("folder", size=14))
        self.btn_open_dir.setFixedHeight(36)
        self.btn_open_dir.clicked.connect(self._open_output_dir)
        action_row.addWidget(self.btn_open_dir)

        layout.addLayout(action_row)

        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(self.lbl_status)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMinimumHeight(40)
        self.log_console.setMaximumHeight(80)
        self.log_console.setPlaceholderText("剪裁操作日志...")
        layout.addWidget(self.log_console)

    def _browse_file(self):
        """兼容性别名，对接托盘快捷栏调用"""
        self._browse_audio_file()

    def _sync_output_extension(self):
        cur = self.le_output_path.text().strip()
        if not cur:
            return
        base, _ = os.path.splitext(cur)
        if self.rb_copy.isChecked():
            if self.current_audio_path:
                _, src_ext = os.path.splitext(self.current_audio_path)
                self.le_output_path.setText(f"{base}{src_ext}")
        else:
            fmt = self.combo_format.currentText().lower()
            self.le_output_path.setText(f"{base}.{fmt}")

    def _toggle_reencode_opts(self, checked: bool):
        self.combo_format.setEnabled(checked)
        self.combo_bitrate.setEnabled(checked)
        self._sync_output_extension()

    def _browse_audio_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "选择待剪裁音频", "",
            "音频文件 (*.mp3 *.wav *.flac *.aac *.m4a *.ogg *.wma);;所有文件 (*.*)"
        )
        if f:
            self.le_file_path.setText(f)

    def _on_file_changed(self, path: str):
        path = path.strip()
        if not path or not os.path.isfile(path):
            return

        self.current_audio_path = path
        info = probe_audio_file(path)
        if "error" in info:
            self.lbl_status.setText(f"分析失败: {info['error']}")
            return

        dur = info.get("duration", 0.0)
        self.total_duration = dur
        dur_tc = info.get("duration_str", "00:00:00.000")

        self.lbl_info_dur.setText(f"总时长: {dur_tc} ({dur:.2f}秒)")
        self.lbl_info_codec.setText(f"编码: {info.get('codec_name', '-')}")
        self.lbl_info_rate.setText(f"采样率: {info.get('sample_rate', 0)} Hz")
        self.lbl_info_channels.setText(f"声道数: {info.get('channels', 0)}")

        self.spin_start.setValue(0.0)
        self.spin_end.setValue(dur)
        self._update_duration_display()

        # 生成默认输出文件名
        dir_name = os.path.dirname(path)
        base, ext = os.path.splitext(os.path.basename(path))
        default_out = os.path.join(dir_name, f"{base}_cut{ext}")
        self.le_output_path.setText(default_out)
        self.lbl_status.setText("音频信息解析成功，请调整起始和结束时间。")

    def _update_duration_display(self):
        s = self.spin_start.value()
        e = self.spin_end.value()
        self.lbl_start_tc.setText(f"({seconds_to_timecode(s)})")
        self.lbl_end_tc.setText(f"({seconds_to_timecode(e)})")

        diff = max(0.0, e - s)
        self.lbl_cut_dur.setText(f"选区总长: {diff:.3f} 秒 ({seconds_to_timecode(diff)})")

    def _browse_output_path(self):
        cur = self.le_output_path.text().strip()
        f, _ = QFileDialog.getSaveFileName(self, "保存剪裁后的音频", cur, "音频文件 (*.*)")
        if f:
            self.le_output_path.setText(f)

    def _open_output_dir(self):
        out_p = self.le_output_path.text().strip()
        target = os.path.dirname(out_p) if out_p else os.path.expanduser("~")
        if os.path.exists(target):
            subprocess.Popen(f'explorer "{os.path.normpath(target)}"')
        else:
            self.log_console.append("[提示] 目标目录不存在。")

    def _start_cut(self):
        src = self.le_file_path.text().strip()
        if not src or not os.path.isfile(src):
            self.lbl_status.setText("请先选择有效的输入音频。")
            return

        out_p = self.le_output_path.text().strip()
        if not out_p:
            self.lbl_status.setText("请指定输出保存路径。")
            return

        s = self.spin_start.value()
        e = self.spin_end.value()
        if e <= s:
            self.lbl_status.setText("结束时间必须大于起始时间。")
            return

        mode = "copy" if self.rb_copy.isChecked() else "encode"
        target_fmt = self.combo_format.currentText().lower()
        bitrate = self.combo_bitrate.currentText()

        self.btn_cut.setEnabled(False)
        self.lbl_status.setText("正在执行精准剪裁...")

        self.worker = AudioCutWorker(
            input_path=src,
            output_path=out_p,
            start_sec=s,
            end_sec=e,
            mode=mode,
            target_format=target_fmt,
            bitrate=bitrate
        )
        self.worker.log_message.connect(self.log_console.append)
        self.worker.finished.connect(self._on_cut_finished)
        self.worker.start()

    def _on_cut_finished(self, success: bool, msg: str):
        self.btn_cut.setEnabled(True)
        if success:
            self.lbl_status.setText("剪裁完成！文件已保存。")
        else:
            self.lbl_status.setText(f"剪裁失败: {msg}")

    # 拖拽事件拦截
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                fp = urls[0].toLocalFile()
                if os.path.isfile(fp):
                    self.le_file_path.setText(fp)
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)

    def handle_initial_paths(self, paths: list):
        if paths and os.path.isfile(str(paths[0])):
            self.le_file_path.setText(str(paths[0]))

    def load_settings(self):
        cfg = self.config.get_plugin_config("audio_cutter", {})
        fmt_idx = cfg.get("format_idx", 0)
        if 0 <= fmt_idx < self.combo_format.count():
            self.combo_format.setCurrentIndex(fmt_idx)
        bitrate_idx = cfg.get("bitrate_idx", 0)
        if 0 <= bitrate_idx < self.combo_bitrate.count():
            self.combo_bitrate.setCurrentIndex(bitrate_idx)
        if cfg.get("reencode", False):
            self.rb_reencode.setChecked(True)
        else:
            self.rb_copy.setChecked(True)

    def save_settings(self):
        cfg = {
            "format_idx": self.combo_format.currentIndex(),
            "bitrate_idx": self.combo_bitrate.currentIndex(),
            "reencode": self.rb_reencode.isChecked()
        }
        self.config.set_plugin_config("audio_cutter", cfg)
