"""
图像格式转换与缩放工坊 - UI 界面
"""

import os
from typing import Optional, List, Tuple
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel,
    QLineEdit, QSpinBox, QPushButton, QComboBox, QRadioButton,
    QButtonGroup, QCheckBox, QProgressBar, QTextEdit, QFileDialog,
    QMessageBox
)
from toolbox.core.config_manager import ConfigManager
from toolbox.ui.components.drag_drop_box import ModernFileListWidget
from .converter import SUPPORTED_FORMATS
from .resizer import ImageBatchWorker
from .upscale_engine import SuperResolutionBatchWorker
from toolbox.core.model_manager import ModelManager
from toolbox.ui.components.model_manager_widget import ModelManagerDialog


class ImageMasterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.worker = None
        self.upscale_worker: Optional[SuperResolutionBatchWorker] = None
        self.init_ui()
        self.load_settings()

    def handle_initial_paths(self, paths: list):
        """处理外部传入的图片文件或文件夹"""
        valid_images = []
        for p in paths:
            if os.path.isfile(p):
                ext = os.path.splitext(p)[1].lower().lstrip(".")
                if ext.upper() in SUPPORTED_FORMATS:
                    valid_images.append(p)
            elif os.path.isdir(p):
                valid_images.append(p)
        if valid_images:
            self.fl_images.add_paths(valid_images)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 上半部分：左侧文件列表 + 右侧参数选项卡
        top_h_layout = QHBoxLayout()
        top_h_layout.setSpacing(16)

        # 1. 左侧：拖拽图片列表
        self.fl_images = ModernFileListWidget("待处理图片列表", "支持 PNG, JPG, WEBP, BMP, ICO, TIFF, GIF")
        top_h_layout.addWidget(self.fl_images, 1)

        # 2. 右侧：功能选项卡
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_convert_tab(), "格式批量转换")
        self.tabs.addTab(self._create_resize_tab(), "尺寸批量缩放")
        self.tabs.addTab(self._create_upscale_tab(), "AI 动漫超分辨率")
        top_h_layout.addWidget(self.tabs, 1)

        main_layout.addLayout(top_h_layout, 1)

        # 下半部分：输出目录、进度条、日志控制台与启动按钮
        bottom_box = QVBoxLayout()
        bottom_box.setSpacing(8)

        # 输出目录选择
        out_layout = QHBoxLayout()
        out_layout.addWidget(QLabel("保存输出目录:"))
        self.le_out_dir = QLineEdit()
        default_out = os.path.join(os.path.expanduser("~"), "Pictures", "Toolbox_Images")
        self.le_out_dir.setText(default_out)
        out_layout.addWidget(self.le_out_dir, 1)
        btn_browse_out = QPushButton("浏览...")
        btn_browse_out.clicked.connect(self._browse_out_dir)
        out_layout.addWidget(btn_browse_out)
        bottom_box.addLayout(out_layout)

        # 进度与控制
        ctl_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        ctl_layout.addWidget(self.progress_bar, 1)

        self.btn_start = QPushButton("开始批量处理")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_start.setMinimumWidth(130)
        self.btn_start.clicked.connect(self._start_task)
        ctl_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_task)
        ctl_layout.addWidget(self.btn_stop)
        bottom_box.addLayout(ctl_layout)

        # 实时日志
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setPlaceholderText("处理日志将实时滚动输出在此...")
        self.txt_log.setFixedHeight(110)
        bottom_box.addWidget(self.txt_log)

        main_layout.addLayout(bottom_box)

    def _create_convert_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 目标格式
        fmt_layout = QHBoxLayout()
        fmt_layout.addWidget(QLabel("目标导出格式:"))
        self.combo_format = QComboBox()
        self.combo_format.addItems(SUPPORTED_FORMATS)
        self.combo_format.setCurrentText("PNG")
        fmt_layout.addWidget(self.combo_format)
        fmt_layout.addStretch()
        layout.addLayout(fmt_layout)

        # 压缩品质
        q_layout = QHBoxLayout()
        q_layout.addWidget(QLabel("输出画质(针对 JPG/WEBP):"))
        self.sp_quality = QSpinBox()
        self.sp_quality.setRange(10, 100)
        self.sp_quality.setValue(90)
        q_layout.addWidget(self.sp_quality)
        q_layout.addWidget(QLabel("%"))
        q_layout.addStretch()
        layout.addLayout(q_layout)

        tip = QLabel("<b>特性说明</b>：<br>"
                     "• 包含透明通道的图片转 JPG/BMP 时将智能平铺纯白底色，杜绝黑底异常；<br>"
                     "• 转为 ICO 时自动生成 16x16 到 256x256 的多规格图标。")
        tip.setObjectName("helperTipLabel")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        layout.addStretch()
        return widget

    def _create_resize_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 缩放模式
        self.rb_pct = QRadioButton("按百分比缩放 (保持原图比例)")
        self.rb_fixed = QRadioButton("按目标像素分辨率缩放")
        self.rb_crop = QRadioButton("居中智能裁切至目标分辨率 (填充裁切)")
        self.rb_pct.setChecked(True)
        bg = QButtonGroup(widget)
        bg.addButton(self.rb_pct)
        bg.addButton(self.rb_fixed)
        bg.addButton(self.rb_crop)
        self.rb_pct.toggled.connect(self._on_resize_mode_toggled)
        self.rb_fixed.toggled.connect(self._on_resize_mode_toggled)
        self.rb_crop.toggled.connect(self._on_resize_mode_toggled)

        layout.addWidget(self.rb_pct)
        layout.addWidget(self.rb_fixed)
        layout.addWidget(self.rb_crop)

        # 百分比参数
        self.box_pct = QWidget()
        bp_layout = QHBoxLayout(self.box_pct)
        bp_layout.setContentsMargins(0, 0, 0, 0)
        bp_layout.addWidget(QLabel("缩放比例:"))
        self.sp_pct = QSpinBox()
        self.sp_pct.setRange(1, 1000)
        self.sp_pct.setValue(50)
        bp_layout.addWidget(self.sp_pct)
        bp_layout.addWidget(QLabel("%"))
        bp_layout.addStretch()
        layout.addWidget(self.box_pct)

        # 分辨率参数
        self.box_fixed = QWidget()
        self.box_fixed.setVisible(False)
        bf_layout = QHBoxLayout(self.box_fixed)
        bf_layout.setContentsMargins(0, 0, 0, 0)
        bf_layout.addWidget(QLabel("宽:"))
        self.sp_w = QSpinBox()
        self.sp_w.setRange(1, 16384)
        self.sp_w.setValue(1920)
        bf_layout.addWidget(self.sp_w)
        bf_layout.addWidget(QLabel("高:"))
        self.sp_h = QSpinBox()
        self.sp_h.setRange(1, 16384)
        self.sp_h.setValue(1080)
        bf_layout.addWidget(self.sp_h)
        self.cb_keep_ratio = QCheckBox("保持纵横比")
        self.cb_keep_ratio.setChecked(True)
        bf_layout.addWidget(self.cb_keep_ratio)
        layout.addWidget(self.box_fixed)

        tip = QLabel("采用 Lanczos 高品质重采样插值算法，缩放清晰细腻。")
        tip.setObjectName("helperTipLabel")
        layout.addWidget(tip)
        layout.addStretch()
        return widget

    def _create_upscale_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 1. 模型选择与管理
        m_layout = QHBoxLayout()
        m_layout.addWidget(QLabel("超分模型:"))
        self.combo_upscale_model = QComboBox()
        self.combo_upscale_model.addItem("Real-ESRGAN AnimeVideo-v3 (极速二次元模型)", "realesr-animevideov3")
        self.combo_upscale_model.addItem("Real-ESRGAN Anime-6B (二次元主力画集模型)", "anime_6B")
        self.combo_upscale_model.addItem("Real-CUGAN 2x 保守版 (保留原图神韵质感)", "pro-conservative-up2x")
        self.combo_upscale_model.addItem("Real-CUGAN 2x 无降噪纯净版", "pro-no-denoise-up2x")
        self.combo_upscale_model.addItem("Real-CUGAN 2x 强力去噪去马赛克", "pro-denoise3x-up2x")
        self.combo_upscale_model.addItem("Waifu2x CUnet 二次元超分", "waifu2x-cunet")
        self.combo_upscale_model.currentIndexChanged.connect(self._sync_upscale_model_status)
        m_layout.addWidget(self.combo_upscale_model, 1)

        self.btn_open_model_hub = QPushButton("按需下载/管理权重...")
        self.btn_open_model_hub.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: white; border-radius: 4px;
                padding: 4px 10px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        self.btn_open_model_hub.clicked.connect(self._open_model_manager_dialog)
        m_layout.addWidget(self.btn_open_model_hub)
        layout.addLayout(m_layout)

        # 本地就绪状态提示
        self.lbl_upscale_model_status = QLabel()
        self.lbl_upscale_model_status.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.lbl_upscale_model_status)
        self._sync_upscale_model_status()

        # 2. 放大倍率
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("超分倍率:"))
        self.combo_scale = QComboBox()
        self.combo_scale.addItem("2x 放大 (推荐/兼顾速度与质量)", 2)
        self.combo_scale.addItem("3x 放大", 3)
        self.combo_scale.addItem("4x 极致超分", 4)
        scale_layout.addWidget(self.combo_scale)
        scale_layout.addStretch()
        layout.addLayout(scale_layout)

        # 3. 切块大小与降噪
        t_layout = QHBoxLayout()
        t_layout.addWidget(QLabel("动态切块尺寸:"))
        self.combo_block_size = QComboBox()
        self.combo_block_size.addItem("1000 px (标准/防显存爆仓)", 1000)
        self.combo_block_size.addItem("500 px (低显存/防 OOM)", 500)
        self.combo_block_size.addItem("2000 px (高性能大图)", 2000)
        t_layout.addWidget(self.combo_block_size)

        t_layout.addWidget(QLabel("降噪模式:"))
        self.combo_denoise = QComboBox()
        self.combo_denoise.addItem("保守版 (保留原图质感)", "conservative")
        self.combo_denoise.addItem("纯净无降噪 (线条最锐利)", "no_denoise")
        self.combo_denoise.addItem("强力去噪 (去除重度马赛克与杂点)", "denoise3x")
        t_layout.addWidget(self.combo_denoise)
        t_layout.addStretch()
        layout.addLayout(t_layout)

        tip = QLabel("<b>超分黑科技</b>：<br>"
                     "• 严格遵守防体积膨胀：大模型权重按需下载，严禁强塞入安装包；<br>"
                     "• 独家透明图层保护算法，透明立绘/表情包超分边缘绝不发绿发黑；<br>"
                     "• 大图自动分块切片推理并无缝边缘羽化混合，杜绝切块拼接撕裂。")
        tip.setObjectName("helperTipLabel")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        layout.addStretch()
        return widget

    def _sync_upscale_model_status(self):
        mid = self.combo_upscale_model.currentData()
        mm = ModelManager()
        is_ready = mm.is_model_ready(mid)
        if is_ready:
            self.lbl_upscale_model_status.setText("状态: 本地权重已就绪 (Ready)")
            self.lbl_upscale_model_status.setStyleSheet("color: #22c55e; font-size: 11px;")
        else:
            self.lbl_upscale_model_status.setText("状态: 尚未下载该模型权重 (可使用内置动漫重构流水线，或点击右侧按需高速下载)")
            self.lbl_upscale_model_status.setStyleSheet("color: #f59e0b; font-size: 11px;")

    def _open_model_manager_dialog(self):
        dlg = ModelManagerDialog(self, category_filter="super_resolution")
        dlg.exec()
        self._sync_upscale_model_status()

    def _on_resize_mode_toggled(self):
        is_pct = self.rb_pct.isChecked()
        self.box_pct.setVisible(is_pct)
        self.box_fixed.setVisible(not is_pct)
        self.cb_keep_ratio.setVisible(self.rb_fixed.isChecked())

    def _browse_out_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出保存目录")
        if dir_path:
            self.le_out_dir.setText(dir_path)

    def _start_task(self):
        paths = self.fl_images.get_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先添加待处理的图片。")
            return

        out_dir = self.le_out_dir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "提示", "请指定输出保存目录。")
            return

        cur_tab = self.tabs.currentIndex()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)
        self.txt_log.clear()

        # 选项卡 2: AI 超分辨率
        if cur_tab == 2:
            model_id = self.combo_upscale_model.currentData()
            scale = int(self.combo_scale.currentData())
            block_size = int(self.combo_block_size.currentData())
            denoise = self.combo_denoise.currentData()

            self.txt_log.append(f"[开始] 启动 AI 动漫超分辨率放大: {len(paths)} 个图片 | 模型: {model_id} | 倍率: {scale}x...")
            os.makedirs(out_dir, exist_ok=True)
            tasks = []
            for p in paths:
                base, ext = os.path.splitext(os.path.basename(p))
                target_name = f"{base}_upscale_{scale}x{ext if ext else '.png'}"
                dst = os.path.join(out_dir, target_name)
                tasks.append((p, dst))

            self.upscale_worker = SuperResolutionBatchWorker(
                tasks=tasks,
                scale=scale,
                model_id=model_id,
                block_size=block_size,
                denoise_level=denoise
            )
            self.upscale_worker.progress.connect(self._on_upscale_progress)
            self.upscale_worker.item_finished.connect(self._on_upscale_item)
            self.upscale_worker.all_finished.connect(self._on_upscale_finished)
            self.upscale_worker.start()
            return

        # 选项卡 0/1: 格式转换与尺寸缩放
        task_type = "convert" if cur_tab == 0 else "resize"
        self.txt_log.append(f"[开始] 开始执行任务 [{task_type}]，共 {len(paths)} 个图片...")

        if self.rb_pct.isChecked():
            resize_mode = "percent"
        elif self.rb_crop.isChecked():
            resize_mode = "crop"
        else:
            resize_mode = "fixed"

        self.worker = ImageBatchWorker(
            task_type=task_type,
            file_paths=paths,
            output_dir=out_dir,
            target_format=self.combo_format.currentText(),
            quality=self.sp_quality.value(),
            resize_mode=resize_mode,
            scale_pct=float(self.sp_pct.value()),
            target_w=self.sp_w.value(),
            target_h=self.sp_h.value(),
            keep_ratio=self.cb_keep_ratio.isChecked()
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.log_message.connect(self.txt_log.append)
        self.worker.task_finished.connect(self._on_finished)
        self.worker.start()

    def _stop_task(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        if self.upscale_worker and self.upscale_worker.isRunning():
            self.upscale_worker.cancel()
        self.btn_stop.setEnabled(False)

    def _on_upscale_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.txt_log.append(msg)

    def _on_upscale_item(self, src: str, dst: str, ok: bool):
        tag = "[√] 成功" if ok else "[×] 失败"
        self.txt_log.append(f"{tag}: {os.path.basename(src)} -> {os.path.basename(dst)}")

    def _on_upscale_finished(self, results: list):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        succ = sum(1 for _, _, ok in results if ok)
        fail = len(results) - succ
        self.txt_log.append(f"[完成] AI 超分辨率处理完成！成功: {succ} 个，失败: {fail} 个。")
        QMessageBox.information(self, "完成", f"AI 超分辨率完成！成功: {succ} 个，失败: {fail} 个。")

    def _on_progress(self, current, total):
        pct = int(current / total * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)

    def _on_finished(self, success_cnt, fail_cnt):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.txt_log.append(f"[完成] 任务完成！成功: {success_cnt} 个，失败: {fail_cnt} 个。")
        QMessageBox.information(self, "完成", f"批量处理完成！成功: {success_cnt} 个，失败: {fail_cnt} 个。")

    def load_settings(self):
        cfg = self.config.get_plugin_config("image_master", {})
        fmt_idx = cfg.get("format_idx", 0)
        if 0 <= fmt_idx < self.combo_format.count():
            self.combo_format.setCurrentIndex(fmt_idx)
        self.sp_quality.setValue(cfg.get("quality", 85))
        tab_idx = cfg.get("tab_idx", 0)
        if 0 <= tab_idx < self.tabs.count():
            self.tabs.setCurrentIndex(tab_idx)
        self.sp_pct.setValue(cfg.get("scale_pct", 50))
        self.sp_w.setValue(cfg.get("target_w", 1920))
        self.sp_h.setValue(cfg.get("target_h", 1080))
        self.cb_keep_ratio.setChecked(cfg.get("keep_ratio", True))
        if "out_dir" in cfg:
            self.le_out_dir.setText(cfg["out_dir"])
        if hasattr(self, "combo_upscale_model") and "upscale_model_idx" in cfg:
            m_idx = cfg["upscale_model_idx"]
            if 0 <= m_idx < self.combo_upscale_model.count():
                self.combo_upscale_model.setCurrentIndex(m_idx)
        if hasattr(self, "combo_scale") and "scale_idx" in cfg:
            s_idx = cfg["scale_idx"]
            if 0 <= s_idx < self.combo_scale.count():
                self.combo_scale.setCurrentIndex(s_idx)

    def save_settings(self):
        cfg = {
            "format_idx": self.combo_format.currentIndex(),
            "quality": self.sp_quality.value(),
            "tab_idx": self.tabs.currentIndex(),
            "scale_pct": self.sp_pct.value(),
            "target_w": self.sp_w.value(),
            "target_h": self.sp_h.value(),
            "keep_ratio": self.cb_keep_ratio.isChecked(),
            "out_dir": self.le_out_dir.text(),
            "upscale_model_idx": self.combo_upscale_model.currentIndex() if hasattr(self, "combo_upscale_model") else 0,
            "scale_idx": self.combo_scale.currentIndex() if hasattr(self, "combo_scale") else 0
        }
        self.config.set_plugin_config("image_master", cfg)
