"""
视频与动图逐帧解压 - UI 界面
支持拖拽各种格式视频与动图，自定义输出图像格式与独立文件夹，支持会话参数独立记忆。
"""

import os
from typing import Optional, List
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QProgressBar, QTextEdit, QRadioButton,
    QButtonGroup, QLineEdit, QFileDialog, QGroupBox, QSlider,
    QCheckBox, QDoubleSpinBox, QMessageBox
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.components.drag_drop_box import ModernFileListWidget
from toolbox.ui.icons import get_icon, get_pixmap
from .engine import FrameExtractorWorker, is_supported_media


class FrameExtractorWidget(QWidget):
    PLUGIN_ID = "frame_extractor"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self.worker: Optional[FrameExtractorWorker] = None
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(12)

        # 1. 顶部 Header
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("image", color="#3b82f6", size=26))
        header.addWidget(icon_lbl)

        title_lbl = QLabel("视频与动图逐帧解压 (序列帧导出)")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title_lbl)

        badge_lbl = QLabel("MP4 / GIF / WebP / MKV 序列解包")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header.addStretch()
        layout.addLayout(header)

        # 2. 待处理文件列表
        self.fl_files = ModernFileListWidget(
            title="待解压媒体文件列表",
            hint="可拖入 MP4 / MKV / AVI / MOV / FLV / WebM 视频或 GIF / WebP 动图文件与文件夹"
        )
        layout.addWidget(self.fl_files, 1)

        # 3. 解压参数配置组
        cfg_group = QGroupBox("解压输出格式与采样规则")
        cfg_layout = QVBoxLayout(cfg_group)
        cfg_layout.setSpacing(10)

        row_1 = QHBoxLayout()
        row_1.setSpacing(14)

        row_1.addWidget(QLabel("目标图片格式:"))
        self.combo_format = QComboBox()
        self.combo_format.addItems(["PNG (无损推荐)", "JPG (较小体积)", "BMP (原始位图)", "WEBP (高压缩比)"])
        self.combo_format.currentTextChanged.connect(self._on_format_changed)
        row_1.addWidget(self.combo_format)

        self.lbl_quality = QLabel("JPG 质量:")
        self.lbl_quality.setVisible(False)
        row_1.addWidget(self.lbl_quality)

        self.slider_quality = QSlider(Qt.Horizontal)
        self.slider_quality.setRange(20, 100)
        self.slider_quality.setValue(95)
        self.slider_quality.setFixedWidth(100)
        self.slider_quality.setVisible(False)
        self.lbl_quality_val = QLabel("95")
        self.lbl_quality_val.setVisible(False)
        self.slider_quality.valueChanged.connect(lambda v: self.lbl_quality_val.setText(str(v)))
        row_1.addWidget(self.slider_quality)
        row_1.addWidget(self.lbl_quality_val)

        row_1.addStretch()
        cfg_layout.addLayout(row_1)

        # 采样模式选择
        row_2 = QHBoxLayout()
        row_2.setSpacing(14)

        row_2.addWidget(QLabel("帧提取采样模式:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["全部逐帧解压 (Full)", "按帧率采样 (FPS)", "按时间间隔 (秒/帧)", "仅提取关键帧 (Keyframes 极速)"])
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        row_2.addWidget(self.combo_mode)

        self.lbl_sample_param = QLabel("帧率 (帧/秒):")
        self.lbl_sample_param.setVisible(False)
        row_2.addWidget(self.lbl_sample_param)

        self.spin_sample = QDoubleSpinBox()
        self.spin_sample.setRange(0.1, 120.0)
        self.spin_sample.setValue(1.0)
        self.spin_sample.setSingleStep(1.0)
        self.spin_sample.setVisible(False)
        row_2.addWidget(self.spin_sample)

        row_2.addStretch()
        cfg_layout.addLayout(row_2)

        # 输出目录与独立文件夹
        row_3 = QHBoxLayout()
        row_3.setSpacing(10)

        row_3.addWidget(QLabel("输出保存目录:"))
        self.le_output_dir = QLineEdit()
        self.le_output_dir.setPlaceholderText("请选择帧序列保存的目标文件夹...")
        row_3.addWidget(self.le_output_dir, 1)

        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.setIcon(get_icon("folder", size=14))
        self.btn_browse.clicked.connect(self._browse_dir)
        row_3.addWidget(self.btn_browse)

        cfg_layout.addLayout(row_3)

        self.cb_subfolder = QCheckBox("为每个视频或动图创建同名独立文件夹 (*_frames)")
        self.cb_subfolder.setChecked(True)
        cfg_layout.addWidget(self.cb_subfolder)

        layout.addWidget(cfg_group)

        # 4. 操作按钮栏
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.btn_start = QPushButton("开始逐帧解压导出")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_start.setIcon(get_icon("play", size=16))
        self.btn_start.setFixedHeight(36)
        self.btn_start.clicked.connect(self._start_extraction)
        action_layout.addWidget(self.btn_start, 1)

        self.btn_cancel = QPushButton("中止")
        self.btn_cancel.setObjectName("dangerBtn")
        self.btn_cancel.setIcon(get_icon("clear", size=14))
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_extraction)
        action_layout.addWidget(self.btn_cancel)

        self.btn_open_dir = QPushButton("打开输出目录")
        self.btn_open_dir.setIcon(get_icon("folder", size=14))
        self.btn_open_dir.setFixedHeight(36)
        self.btn_open_dir.clicked.connect(self._open_output_dir)
        action_layout.addWidget(self.btn_open_dir)

        layout.addLayout(action_layout)

        # 5. 进度条与日志
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.log_view = QTextEdit()
        self.log_view.setFixedHeight(85)
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("逐帧解压任务状态与统计...")
        layout.addWidget(self.log_view)

    def _on_format_changed(self, text: str):
        is_jpg = "JPG" in text
        self.lbl_quality.setVisible(is_jpg)
        self.slider_quality.setVisible(is_jpg)
        self.lbl_quality_val.setVisible(is_jpg)

    def _on_mode_changed(self, idx: int):
        if idx == 1:
            self.lbl_sample_param.setText("采样帧率 (帧/秒):")
            self.spin_sample.setValue(1.0)
            self.lbl_sample_param.setVisible(True)
            self.spin_sample.setVisible(True)
        elif idx == 2:
            self.lbl_sample_param.setText("时间间隔 (每 N 秒一帧):")
            self.spin_sample.setValue(1.0)
            self.lbl_sample_param.setVisible(True)
            self.spin_sample.setVisible(True)
        else:
            self.lbl_sample_param.setVisible(False)
            self.spin_sample.setVisible(False)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出文件夹", self.le_output_dir.text())
        if d:
            self.le_output_dir.setText(d)
            self.save_settings()

    def load_settings(self):
        """恢复专属配置参数"""
        cfg = self.config_manager.get_plugin_config(self.PLUGIN_ID, {})
        self.combo_format.setCurrentIndex(cfg.get("format_idx", 0))
        self.slider_quality.setValue(cfg.get("quality", 95))
        self.combo_mode.setCurrentIndex(cfg.get("mode_idx", 0))
        self.spin_sample.setValue(cfg.get("sample_val", 1.0))
        self.le_output_dir.setText(cfg.get("output_dir", ""))
        self.cb_subfolder.setChecked(cfg.get("subfolder", True))

    def save_settings(self):
        """持久化保存当前设置"""
        cfg = {
            "format_idx": self.combo_format.currentIndex(),
            "quality": self.slider_quality.value(),
            "mode_idx": self.combo_mode.currentIndex(),
            "sample_val": self.spin_sample.value(),
            "output_dir": self.le_output_dir.text(),
            "subfolder": self.cb_subfolder.isChecked()
        }
        self.config_manager.set_plugin_config(self.PLUGIN_ID, cfg)

    def handle_initial_paths(self, paths: List[str]):
        valid = [p for p in paths if is_supported_media(p) or os.path.isdir(p)]
        if valid:
            self.fl_files.add_paths(valid)

    def _start_extraction(self):
        files = self.fl_files.get_all_files()
        if not files:
            QMessageBox.information(self, "提示", "请先添加或拖入需要解压的视频或动图文件。")
            return

        out_dir = self.le_output_dir.text().strip()
        if not out_dir:
            # 默认取首个文件所在目录
            out_dir = os.path.dirname(files[0])
            self.le_output_dir.setText(out_dir)

        os.makedirs(out_dir, exist_ok=True)
        self.save_settings()

        fmt_list = ["PNG", "JPG", "BMP", "WEBP"]
        format_choice = fmt_list[self.combo_format.currentIndex()]

        mode_list = ["all", "fps", "interval", "keyframe"]
        mode = mode_list[self.combo_mode.currentIndex()]
        sample_v = self.spin_sample.value()

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log_view.clear()

        self.worker = FrameExtractorWorker(
            files=files,
            output_dir=out_dir,
            create_subfolder=self.cb_subfolder.isChecked(),
            format_choice=format_choice,
            mode=mode,
            fps_val=sample_v if mode == "fps" else 1.0,
            interval_sec=sample_v if mode == "interval" else 1.0,
            jpg_quality=self.slider_quality.value()
        )
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.log.connect(self._append_log)
        self.worker.all_finished.connect(self._on_all_finished)
        self.worker.start()

    def _cancel_extraction(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)

    def _on_worker_progress(self, current: int, total: int, filename: str):
        pct = int(current / max(1, total) * 100)
        self.progress_bar.setValue(pct)

    def _append_log(self, text: str):
        self.log_view.append(text)

    def _on_all_finished(self, success: int, fail: int, total_frames: int):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setValue(100)
        self._append_log(f"逐帧解压完成！处理任务: 成功 {success} / 失败 {fail} | 共解压输出 {total_frames} 张图片。")
        QMessageBox.information(
            self, "完成",
            f"逐帧解压任务已完成！\n成功任务: {success} 个 | 失败任务: {fail} 个\n共导出序列帧图片: {total_frames} 张"
        )

    def _open_output_dir(self):
        target = self.le_output_dir.text().strip()
        if target and os.path.exists(target):
            os.startfile(os.path.normpath(target))
        else:
            QMessageBox.information(self, "提示", "尚未指定有效的输出目录。")
