"""
图片与视频体积压缩 - UI 界面
全功能支持批量拖拽图片与视频极速压制，并具备会话级参数独立记忆。
"""

import os
import subprocess
from typing import Optional, List
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QProgressBar, QTextEdit, QRadioButton,
    QButtonGroup, QLineEdit, QFileDialog, QGroupBox, QSlider,
    QTabWidget, QMessageBox
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.components.drag_drop_box import ModernFileListWidget
from toolbox.ui.icons import get_icon, get_pixmap
from .engine import MediaCompressorWorker, is_image_file, is_video_file, format_bytes


class MediaCompressorWidget(QWidget):
    PLUGIN_ID = "media_compressor"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self.worker: Optional[MediaCompressorWorker] = None
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
        icon_lbl.setPixmap(get_pixmap("zap", color="#3b82f6", size=26))
        header.addWidget(icon_lbl)

        title_lbl = QLabel("图片与视频体积压缩 (极速体积瘦身)")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title_lbl)

        badge_lbl = QLabel("WebP / MozJPEG / H.264 / HEVC / AV1")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header.addStretch()
        layout.addLayout(header)

        # 2. 核心文件拖拽列表
        self.fl_media = ModernFileListWidget(
            title="待压缩媒体文件列表",
            hint="可拖入任意 PNG / JPG / WEBP / BMP 图片或 MP4 / MKV / MOV / AVI / FLV 等视频文件或文件夹"
        )
        layout.addWidget(self.fl_media, 1)

        # 3. 压缩算法参数配置选项卡
        param_tabs = QTabWidget()
        param_tabs.setFixedHeight(120)

        # 图像参数选项卡
        tab_img = QWidget()
        img_layout = QVBoxLayout(tab_img)
        img_layout.setContentsMargins(12, 10, 12, 10)
        img_row = QHBoxLayout()
        img_row.setSpacing(14)

        img_row.addWidget(QLabel("图片目标格式:"))
        self.combo_img_fmt = QComboBox()
        self.combo_img_fmt.addItems(["WebP (极致体积推荐)", "JPEG (高保真通用)", "保持原格式 (原图优化)"])
        img_row.addWidget(self.combo_img_fmt)

        img_row.addWidget(QLabel("画质质量 (1-100):"))
        self.slider_img_quality = QSlider(Qt.Horizontal)
        self.slider_img_quality.setRange(10, 100)
        self.slider_img_quality.setValue(80)
        self.slider_img_quality.setFixedWidth(120)
        self.lbl_img_quality = QLabel("80")
        self.slider_img_quality.valueChanged.connect(lambda v: self.lbl_img_quality.setText(str(v)))
        img_row.addWidget(self.slider_img_quality)
        img_row.addWidget(self.lbl_img_quality)

        img_row.addWidget(QLabel("最大边长缩放:"))
        self.combo_img_scale = QComboBox()
        self.combo_img_scale.addItems(["不缩放 (保持原图分辨率)", "限制在 1920px (全高清)", "限制在 1280px (高清)", "限制在 800px (缩略图)"])
        img_row.addWidget(self.combo_img_scale)

        img_row.addStretch()
        img_layout.addLayout(img_row)
        param_tabs.addTab(tab_img, "图像压缩参数")

        # 视频参数选项卡
        tab_video = QWidget()
        video_layout = QVBoxLayout(tab_video)
        video_layout.setContentsMargins(12, 10, 12, 10)
        video_row = QHBoxLayout()
        video_row.setSpacing(14)

        video_row.addWidget(QLabel("视频编码核心:"))
        self.combo_vid_codec = QComboBox()
        self.combo_vid_codec.addItems(["H.264 (兼容性佳)", "H.265 (HEVC 高压缩率)", "AV1 (开放先进编码)"])
        video_row.addWidget(self.combo_vid_codec)

        video_row.addWidget(QLabel("CRF 压制级别 (18-35):"))
        self.slider_vid_crf = QSlider(Qt.Horizontal)
        self.slider_vid_crf.setRange(18, 35)
        self.slider_vid_crf.setValue(26)
        self.slider_vid_crf.setFixedWidth(100)
        self.lbl_vid_crf = QLabel("26")
        self.slider_vid_crf.valueChanged.connect(lambda v: self.lbl_vid_crf.setText(str(v)))
        video_row.addWidget(self.slider_vid_crf)
        video_row.addWidget(self.lbl_vid_crf)

        video_row.addWidget(QLabel("预设速度:"))
        self.combo_vid_preset = QComboBox()
        self.combo_vid_preset.addItems(["medium (推荐平衡)", "fast (较快速度)", "slow (更高压缩比)"])
        video_row.addWidget(self.combo_vid_preset)

        video_row.addWidget(QLabel("分辨率:"))
        self.combo_vid_res = QComboBox()
        self.combo_vid_res.addItems(["原分辨率", "1080P", "720P", "480P"])
        video_row.addWidget(self.combo_vid_res)

        video_row.addStretch()
        video_layout.addLayout(video_row)
        param_tabs.addTab(tab_video, "视频压缩参数")

        layout.addWidget(param_tabs)

        # 4. 保存路径设置
        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(10)

        self.btn_group_dir = QButtonGroup(self)
        self.rb_same_dir = QRadioButton("保存至源文件同级目录 (添加 _compressed 后缀)")
        self.rb_same_dir.setChecked(True)
        self.rb_custom_dir = QRadioButton("输出至指定文件夹:")
        self.btn_group_dir.addButton(self.rb_same_dir)
        self.btn_group_dir.addButton(self.rb_custom_dir)
        self.rb_custom_dir.toggled.connect(self._toggle_custom_dir)

        dir_layout.addWidget(self.rb_same_dir)
        dir_layout.addWidget(self.rb_custom_dir)

        self.le_custom_dir = QLineEdit()
        self.le_custom_dir.setEnabled(False)
        dir_layout.addWidget(self.le_custom_dir, 1)

        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.setIcon(get_icon("folder", size=14))
        self.btn_browse.setEnabled(False)
        self.btn_browse.clicked.connect(self._browse_custom_dir)
        dir_layout.addWidget(self.btn_browse)

        layout.addLayout(dir_layout)

        # 5. 执行控制
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.btn_start = QPushButton("开始批量极速压缩")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_start.setIcon(get_icon("zap", size=16))
        self.btn_start.setFixedHeight(36)
        self.btn_start.clicked.connect(self._start_compression)
        action_layout.addWidget(self.btn_start, 1)

        self.btn_cancel = QPushButton("中止")
        self.btn_cancel.setObjectName("dangerBtn")
        self.btn_cancel.setIcon(get_icon("clear", size=14))
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_compression)
        action_layout.addWidget(self.btn_cancel)

        self.btn_open_dir = QPushButton("打开输出目录")
        self.btn_open_dir.setIcon(get_icon("folder", size=14))
        self.btn_open_dir.setFixedHeight(36)
        self.btn_open_dir.clicked.connect(self._open_output_dir)
        action_layout.addWidget(self.btn_open_dir)

        layout.addLayout(action_layout)

        # 进度与日志输出
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.log_view = QTextEdit()
        self.log_view.setFixedHeight(90)
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("压缩执行状态与日志...")
        layout.addWidget(self.log_view)

    def _toggle_custom_dir(self, checked: bool):
        self.le_custom_dir.setEnabled(checked)
        self.btn_browse.setEnabled(checked)

    def _browse_custom_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.le_custom_dir.text())
        if d:
            self.le_custom_dir.setText(d)
            self.save_settings()

    def load_settings(self):
        """恢复历史配置参数"""
        cfg = self.config_manager.get_plugin_config(self.PLUGIN_ID, {})
        self.combo_img_fmt.setCurrentIndex(cfg.get("img_fmt_idx", 0))
        self.slider_img_quality.setValue(cfg.get("img_quality", 80))
        self.combo_img_scale.setCurrentIndex(cfg.get("img_scale_idx", 0))

        self.combo_vid_codec.setCurrentIndex(cfg.get("vid_codec_idx", 0))
        self.slider_vid_crf.setValue(cfg.get("vid_crf", 26))
        self.combo_vid_preset.setCurrentIndex(cfg.get("vid_preset_idx", 0))
        self.combo_vid_res.setCurrentIndex(cfg.get("vid_res_idx", 0))

        use_custom = cfg.get("use_custom_dir", False)
        if use_custom:
            self.rb_custom_dir.setChecked(True)
        else:
            self.rb_same_dir.setChecked(True)
        self.le_custom_dir.setText(cfg.get("custom_dir", ""))

    def save_settings(self):
        """保存当前用户设置至专属配置"""
        cfg = {
            "img_fmt_idx": self.combo_img_fmt.currentIndex(),
            "img_quality": self.slider_img_quality.value(),
            "img_scale_idx": self.combo_img_scale.currentIndex(),
            "vid_codec_idx": self.combo_vid_codec.currentIndex(),
            "vid_crf": self.slider_vid_crf.value(),
            "vid_preset_idx": self.combo_vid_preset.currentIndex(),
            "vid_res_idx": self.combo_vid_res.currentIndex(),
            "use_custom_dir": self.rb_custom_dir.isChecked(),
            "custom_dir": self.le_custom_dir.text()
        }
        self.config_manager.set_plugin_config(self.PLUGIN_ID, cfg)

    def handle_initial_paths(self, paths: List[str]):
        valid = [p for p in paths if is_image_file(p) or is_video_file(p) or os.path.isdir(p)]
        if valid:
            self.fl_media.add_paths(valid)

    def _start_compression(self):
        files = self.fl_media.get_all_files()
        if not files:
            QMessageBox.information(self, "提示", "请先拖入或添加需要压缩的图片或视频文件。")
            return

        same_dir = self.rb_same_dir.isChecked()
        out_dir = self.le_custom_dir.text().strip()
        if not same_dir:
            if not out_dir:
                QMessageBox.warning(self, "提示", "请选择有效的自定义输出目录。")
                return
            os.makedirs(out_dir, exist_ok=True)

        self.save_settings()

        # 映射图像参数
        fmt_map = {0: "WEBP", 1: "JPEG", 2: "KEEP"}
        scale_map = {0: 0, 1: 1920, 2: 1280, 3: 800}
        img_params = {
            "format": fmt_map.get(self.combo_img_fmt.currentIndex(), "WEBP"),
            "quality": self.slider_img_quality.value(),
            "max_dimension": scale_map.get(self.combo_img_scale.currentIndex(), 0)
        }

        # 映射视频参数
        codec_map = {0: "H.264", 1: "H.265", 2: "AV1"}
        preset_map = {0: "medium", 1: "fast", 2: "slow"}
        res_map = {0: 0, 1: 1080, 2: 720, 3: 480}
        video_params = {
            "codec": codec_map.get(self.combo_vid_codec.currentIndex(), "H.264"),
            "crf": self.slider_vid_crf.value(),
            "preset": preset_map.get(self.combo_vid_preset.currentIndex(), "medium"),
            "scale_height": res_map.get(self.combo_vid_res.currentIndex(), 0),
            "audio_bitrate": "128k"
        }

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log_view.clear()

        self.worker = MediaCompressorWorker(
            files=files,
            output_dir=out_dir,
            same_dir=same_dir,
            image_params=img_params,
            video_params=video_params
        )
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.log.connect(self._append_log)
        self.worker.all_finished.connect(self._on_all_finished)
        self.worker.start()

    def _cancel_compression(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)

    def _on_worker_progress(self, current: int, total: int, filename: str):
        pct = int(current / max(1, total) * 100)
        self.progress_bar.setValue(pct)

    def _append_log(self, text: str):
        self.log_view.append(text)

    def _on_all_finished(self, success: int, fail: int):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setValue(100)
        self._append_log(f"任务完成！成功压缩 {success} 个，失败 {fail} 个。")
        QMessageBox.information(self, "完成", f"批量压缩处理已完成！\n成功: {success} 个 | 失败: {fail} 个")

    def _open_output_dir(self):
        if self.rb_same_dir.isChecked():
            files = self.fl_media.get_all_files()
            target = os.path.dirname(files[0]) if files else ""
        else:
            target = self.le_custom_dir.text().strip()

        if target and os.path.exists(target):
            os.startfile(os.path.normpath(target))
        else:
            QMessageBox.information(self, "提示", "尚未指定有效的输出目录或暂无可打开的目录。")
