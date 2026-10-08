"""
水印工坊 (Watermark Studio) - UI 界面
提供多图批量平铺文字水印、证件防诈专用隐私水印与无损隐形盲水印提取。
"""

import os
from typing import List
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QSlider, QColorDialog, QFileDialog, QMessageBox,
    QProgressBar, QGroupBox, QGridLayout, QFrame
)

from toolbox.ui.icons import get_icon
from .engine import add_text_watermark, add_id_privacy_watermark, embed_blind_watermark, extract_blind_watermark


class WatermarkBatchWorker(QThread):
    """批量加流水印异步后台工作线程"""
    progress = Signal(int, str)
    finished = Signal(int, int)

    def __init__(self, file_paths: List[str], output_dir: str, mode: str, params: dict, parent=None):
        super().__init__(parent)
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.mode = mode
        self.params = params
        self._cancelled = False

    def requestInterruption(self):
        self._cancelled = True
        super().requestInterruption()

    def isInterruptionRequested(self) -> bool:
        return self._cancelled or super().isInterruptionRequested()

    def run(self):
        success = 0
        total = len(self.file_paths)
        for i, src in enumerate(self.file_paths):
            if self.isInterruptionRequested():
                break
            fname = os.path.basename(src)
            out_name = f"WM_{fname}"
            if self.mode == "blind":
                out_name = os.path.splitext(fname)[0] + "_blind.png"
            out_path = os.path.join(self.output_dir, out_name)

            self.progress.emit(int((i / total) * 100), f"正在处理: {fname}")

            ok = False
            if self.mode == "text":
                ok = add_text_watermark(
                    src, out_path,
                    text=self.params["text"],
                    tiled=self.params["tiled"],
                    angle=self.params["angle"],
                    opacity=self.params["opacity"],
                    font_size=self.params["font_size"],
                    color_hex=self.params["color_hex"]
                )
            elif self.mode == "id":
                ok = add_id_privacy_watermark(
                    src, out_path,
                    purpose=self.params["purpose"],
                    color_hex=self.params["color_hex"],
                    opacity=self.params["opacity"]
                )
            elif self.mode == "blind":
                ok = embed_blind_watermark(src, out_path, self.params["secret"])

            if ok:
                success += 1

        self.progress.emit(100, "处理完成")
        self.finished.emit(success, total)


class WatermarkStudioWidget(QWidget):
    """水印工坊主面板界面"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_files = []
        self.selected_color = "#ffffff"
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # 头部说明
        top_bar = QHBoxLayout()
        tip = QLabel("<b>千绘莉批量水印与证件保护大师</b><br><span style='color:#64748b; font-size:12px;'>自媒体批量防盗水印、身份证/营业执照防滥用隐私水印与肉眼不可见的隐形盲水印。</span>")
        tip.setWordWrap(True)
        top_bar.addWidget(tip, 1)

        self.btn_add_files = QPushButton("添加图片...")
        self.btn_add_files.setObjectName("primaryBtn")
        self.btn_add_files.setIcon(get_icon("file-plus", color="#ffffff", size=14))
        self.btn_add_files.clicked.connect(self._select_images)
        top_bar.addWidget(self.btn_add_files)

        self.btn_clear_list = QPushButton("清空列表")
        self.btn_clear_list.clicked.connect(self._clear_list)
        top_bar.addWidget(self.btn_clear_list)
        layout.addLayout(top_bar)

        # 核心双栏布局：左侧文件列表，右侧参数与模式设置
        center_row = QHBoxLayout()

        # 左栏：文件表格
        self.table_files = QTableWidget()
        self.table_files.setColumnCount(3)
        self.table_files.setHorizontalHeaderLabels(["文件名", "大小", "路径"])
        self.table_files.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_files.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_files.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        center_row.addWidget(self.table_files, 1)

        # 右栏：模式参数选项卡
        right_panel = QWidget()
        right_panel.setMaximumWidth(400)
        r_layout = QVBoxLayout(right_panel)
        r_layout.setContentsMargins(0, 0, 0, 0)
        r_layout.setSpacing(10)

        self.tabs_mode = QTabWidget()
        self.tabs_mode.addTab(self._build_text_mode_page(), "平铺文字水印")
        self.tabs_mode.addTab(self._build_id_mode_page(), "证件隐私水印")
        self.tabs_mode.addTab(self._build_blind_mode_page(), "隐形盲水印")
        r_layout.addWidget(self.tabs_mode, 1)

        # 底部导出与执行
        export_box = QGroupBox("输出目录与执行")
        exp_layout = QVBoxLayout(export_box)
        row_dir = QHBoxLayout()
        self.le_out_dir = QLineEdit()
        self.le_out_dir.setPlaceholderText("输出文件夹...")
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._browse_out_dir)
        row_dir.addWidget(self.le_out_dir, 1)
        row_dir.addWidget(btn_browse)
        exp_layout.addLayout(row_dir)

        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        self.pbar.setFixedHeight(8)
        self.pbar.setTextVisible(False)
        exp_layout.addWidget(self.pbar)

        self.btn_start = QPushButton("开始批量加流水印")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_start.setFixedHeight(36)
        self.btn_start.clicked.connect(self._start_batch)
        exp_layout.addWidget(self.btn_start)

        r_layout.addWidget(export_box)
        center_row.addWidget(right_panel)
        layout.addLayout(center_row, 1)

    def _build_text_mode_page(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setSpacing(10)

        l.addWidget(QLabel("水印文本:"))
        self.le_wm_text = QLineEdit("千绘莉工具箱版权所有")
        l.addWidget(self.le_wm_text)

        l.addWidget(QLabel("透明度 (0 - 255):"))
        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setRange(20, 255)
        self.slider_opacity.setValue(110)
        l.addWidget(self.slider_opacity)

        l.addWidget(QLabel("旋转角度 (-90° 至 90°):"))
        self.slider_angle = QSlider(Qt.Horizontal)
        self.slider_angle.setRange(-90, 90)
        self.slider_angle.setValue(30)
        l.addWidget(self.slider_angle)

        l.addWidget(QLabel("字体字号 (px):"))
        self.slider_font_size = QSlider(Qt.Horizontal)
        self.slider_font_size.setRange(16, 72)
        self.slider_font_size.setValue(32)
        l.addWidget(self.slider_font_size)

        row_c = QHBoxLayout()
        self.btn_pick_color = QPushButton("选择水印颜色 (当前: 白色)")
        self.btn_pick_color.clicked.connect(self._choose_color)
        row_c.addWidget(self.btn_pick_color)
        l.addLayout(row_c)

        l.addStretch()
        return w

    def _build_id_mode_page(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setSpacing(10)

        l.addWidget(QLabel("<b>专为身份证、营业执照加注防盗防诈印记</b>"))
        l.addWidget(QLabel("预置用途快捷填充:"))

        presets = ["仅供办理手机卡实名使用，复印无效", "仅供办理银行卡开户使用，复印无效", "仅供房屋租赁核验使用，复印无效"]
        for p in presets:
            btn_p = QPushButton(p)
            btn_p.setStyleSheet("text-align: left; padding: 4px;")
            btn_p.clicked.connect(lambda checked=False, val=p: self.le_id_purpose.setText(val))
            l.addWidget(btn_p)

        l.addWidget(QLabel("自定义印记文本:"))
        self.le_id_purpose = QLineEdit("仅供办理业务使用，复印无效")
        l.addWidget(self.le_id_purpose)

        l.addStretch()
        return w

    def _build_blind_mode_page(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setSpacing(10)

        l.addWidget(QLabel("<b>隐形频域盲水印 (肉眼完全不可见)</b>"))
        l.addWidget(QLabel("嵌入版权字符串:"))
        self.le_blind_secret = QLineEdit("CHIERI_COPYRIGHT_2026")
        l.addWidget(self.le_blind_secret)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        l.addWidget(sep)

        l.addWidget(QLabel("<b>从带盲水印的图片中提取版权证明</b>"))
        btn_extract = QPushButton("选择图片并提取盲水印...")
        btn_extract.clicked.connect(self._extract_blind)
        l.addWidget(btn_extract)

        l.addStretch()
        return w

    def _choose_color(self):
        col = QColorDialog.getColor(QColor(self.selected_color), self, "选择水印颜色")
        if col.isValid():
            self.selected_color = col.name(QColor.HexRgb)
            self.btn_pick_color.setText(f"选择水印颜色 (当前: {self.selected_color})")

    def _select_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择图片文件", "", "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if files:
            for f in files:
                if f not in self.image_files:
                    self.image_files.append(f)
            self._render_files()

    def _render_files(self):
        self.table_files.setRowCount(len(self.image_files))
        for r, f in enumerate(self.image_files):
            fname = os.path.basename(f)
            sz = f"{os.path.getsize(f) / 1024:.1f} KB" if os.path.exists(f) else "-"
            self.table_files.setItem(r, 0, QTableWidgetItem(fname))
            self.table_files.setItem(r, 1, QTableWidgetItem(sz))
            self.table_files.setItem(r, 2, QTableWidgetItem(f))

    def _clear_list(self):
        self.image_files.clear()
        self.table_files.setRowCount(0)

    def _browse_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择水印保存目录")
        if d:
            self.le_out_dir.setText(d)

    def _start_batch(self):
        if not self.image_files:
            QMessageBox.warning(self, "提示", "请先添加至少一张待处理图片！")
            return
        out_dir = self.le_out_dir.text().strip()
        if not out_dir:
            out_dir = os.path.join(os.path.dirname(self.image_files[0]), "Watermarked_Output")
            self.le_out_dir.setText(out_dir)
        os.makedirs(out_dir, exist_ok=True)

        tab_idx = self.tabs_mode.currentIndex()
        if tab_idx == 0:
            mode = "text"
            params = {
                "text": self.le_wm_text.text().strip() or "千绘莉工具箱",
                "tiled": True,
                "angle": self.slider_angle.value(),
                "opacity": self.slider_opacity.value(),
                "font_size": self.slider_font_size.value(),
                "color_hex": self.selected_color
            }
        elif tab_idx == 1:
            mode = "id"
            params = {
                "purpose": self.le_id_purpose.text().strip() or "仅供业务使用，复印无效",
                "color_hex": "#dc2626",
                "opacity": 130
            }
        else:
            mode = "blind"
            params = {
                "secret": self.le_blind_secret.text().strip() or "CHIERI_COPYRIGHT"
            }

        self.btn_start.setEnabled(False)
        from toolbox.core.task_manager import GlobalTaskManager, TaskStatus
        mode_names = {"text": "平铺文字水印", "id": "证件隐私水印", "blind": "隐形盲水印"}
        self.current_task_id = GlobalTaskManager.instance().register_manual_task(
            title=f"批量加注水印 - {mode_names.get(mode, mode)} ({len(self.image_files)} 张)",
            plugin_id="watermark_studio",
            max_progress=100
        )

        self.worker = WatermarkBatchWorker(self.image_files, out_dir, mode, params, self)
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.finished.connect(self._on_batch_finished)
        self.worker.start()

    def _on_worker_progress(self, p: int, msg: str):
        self.pbar.setValue(p)
        if getattr(self, "current_task_id", None):
            from toolbox.core.task_manager import GlobalTaskManager
            GlobalTaskManager.instance().update_progress(self.current_task_id, p, msg)

    def _on_batch_finished(self, success: int, total: int):
        self.btn_start.setEnabled(True)
        if getattr(self, "current_task_id", None):
            from toolbox.core.task_manager import GlobalTaskManager, TaskStatus
            status = TaskStatus.COMPLETED if success > 0 else TaskStatus.FAILED
            GlobalTaskManager.instance().update_status(
                self.current_task_id, status, f"处理完成: 成功 {success} / 共 {total} 张"
            )
            self.current_task_id = None
        QMessageBox.information(self, "批量加注完成", f"已成功处理 {success} / {total} 张图片！\n输出目录:\n{self.le_out_dir.text()}")

    def _extract_blind(self):
        fpath, _ = QFileDialog.getOpenFileName(self, "选择带有盲水印的 PNG 图片", "", "PNG图片 (*.png)")
        if fpath:
            secret = extract_blind_watermark(fpath)
            if secret:
                QMessageBox.information(self, "盲水印提取成功", f"从图像中成功提取到隐形版权信息:\n\n{secret}")
            else:
                QMessageBox.warning(self, "提取失败", "未在图像中检测到有效的盲水印标识。")

    def handle_initial_paths(self, paths: list):
        for p in paths:
            if isinstance(p, str) and p.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                if p not in self.image_files:
                    self.image_files.append(p)
        self._render_files()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls()]
            self.handle_initial_paths(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def cleanup(self):
        if hasattr(self, "worker") and self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.quit()
            self.worker.wait(1500)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def load_settings(self):
        from toolbox.core.config_manager import ConfigManager
        cfg = ConfigManager().get_plugin_config("watermark_studio")
        if "text" in cfg and hasattr(self, "le_wm_text"):
            self.le_wm_text.setText(cfg.get("text", "千绘莉工具箱"))
        if "opacity" in cfg and hasattr(self, "slider_opacity"):
            self.slider_opacity.setValue(cfg.get("opacity", 75))

    def save_settings(self):
        from toolbox.core.config_manager import ConfigManager
        cfg = {
            "text": self.le_wm_text.text() if hasattr(self, "le_wm_text") else "千绘莉工具箱",
            "opacity": self.slider_opacity.value() if hasattr(self, "slider_opacity") else 75
        }
        ConfigManager().set_plugin_config("watermark_studio", cfg)
