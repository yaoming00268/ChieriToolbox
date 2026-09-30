"""
osu!mania 皮肤调校工作台 - UI 主界面
"""

import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSlider, QSpinBox, QGroupBox,
    QFileDialog, QMessageBox, QInputDialog, QScrollArea, QFormLayout
)
from toolbox.core.config_manager import ConfigManager
from .skin_parser import SkinParser
from .preview_area import ManiaPreviewArea


class OsuSkinStudioWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.parser = SkinParser()
        self.current_skin_dir = ""
        self.init_ui()
        self.load_settings()

    def handle_initial_paths(self, paths: list):
        """处理外部传入的皮肤文件夹或 skin.ini 路径"""
        for p in paths:
            if os.path.isdir(p):
                self._load_skin(p)
                break
            elif os.path.isfile(p) and os.path.basename(p).lower() == "skin.ini":
                self._load_skin(os.path.dirname(p))
                break

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. 顶部操作栏
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.lbl_skin_name = QLabel("当前未载入皮肤文件夹")
        self.lbl_skin_name.setObjectName("skinNameLabel")
        top_bar.addWidget(self.lbl_skin_name, 1)

        btn_open = QPushButton("打开皮肤文件夹")
        btn_open.clicked.connect(self._select_skin_dir)
        top_bar.addWidget(btn_open)

        btn_new = QPushButton("新建 Mania 皮肤")
        btn_new.clicked.connect(self._create_new_skin)
        top_bar.addWidget(btn_new)

        top_bar.addWidget(QLabel("预览比例:"))
        self.combo_ratio = QComboBox()
        self.combo_ratio.addItems(["16:9", "4:3", "21:9"])
        self.combo_ratio.currentTextChanged.connect(self._on_ratio_changed)
        top_bar.addWidget(self.combo_ratio)

        top_bar.addWidget(QLabel("键位 (Keys):"))
        self.combo_keys = QComboBox()
        self.combo_keys.addItems(["4", "5", "6", "7", "8", "9"])
        self.combo_keys.currentTextChanged.connect(self._on_keys_changed)
        top_bar.addWidget(self.combo_keys)

        main_layout.addLayout(top_bar)

        # 2. 中部：左侧参数面板，右侧实时舞台预览画布
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        # 左侧：配置面板
        left_group = QGroupBox("Mania 核心参数实时微调")
        left_layout = QVBoxLayout(left_group)
        left_layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        # 判定线高度 HitPosition (滑块 + 数字微调)
        hit_box = QHBoxLayout()
        self.slider_hit = QSlider(Qt.Horizontal)
        self.slider_hit.setRange(200, 480)
        self.slider_hit.setValue(400)
        self.spin_hit = QSpinBox()
        self.spin_hit.setRange(200, 480)
        self.spin_hit.setValue(400)
        self.slider_hit.valueChanged.connect(self.spin_hit.setValue)
        self.spin_hit.valueChanged.connect(self.slider_hit.setValue)
        self.spin_hit.valueChanged.connect(self._on_param_modified)
        hit_box.addWidget(self.slider_hit, 1)
        hit_box.addWidget(self.spin_hit)
        form.addRow(QLabel("判定线 HitPosition:"), hit_box)

        # 舞台左偏移 ColumnStart
        start_box = QHBoxLayout()
        self.slider_start = QSlider(Qt.Horizontal)
        self.slider_start.setRange(0, 500)
        self.slider_start.setValue(136)
        self.spin_start = QSpinBox()
        self.spin_start.setRange(0, 500)
        self.spin_start.setValue(136)
        self.slider_start.valueChanged.connect(self.spin_start.setValue)
        self.spin_start.valueChanged.connect(self.slider_start.setValue)
        self.spin_start.valueChanged.connect(self._on_param_modified)
        start_box.addWidget(self.slider_start, 1)
        start_box.addWidget(self.spin_start)
        form.addRow(QLabel("舞台起始偏移 ColumnStart:"), start_box)

        # 轨道各列宽度 ColumnWidth
        self.le_col_width = QLineEdit("60,60,60,60")
        self.le_col_width.setPlaceholderText("用英文逗号分隔每列宽度，例如 60,60,60,60")
        self.le_col_width.textChanged.connect(self._on_param_modified)
        form.addRow(QLabel("列宽数组 ColumnWidth:"), self.le_col_width)

        left_layout.addLayout(form)
        left_layout.addStretch()

        btn_save = QPushButton("保存到 skin.ini")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save_skin_ini)
        left_layout.addWidget(btn_save)

        content_layout.addWidget(left_group, 1)

        # 右侧：实时渲染画布
        self.preview_canvas = ManiaPreviewArea(self.parser)
        content_layout.addWidget(self.preview_canvas, 2)

        main_layout.addLayout(content_layout, 1)

    def _select_skin_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择 osu! 皮肤文件夹")
        if d:
            self._load_skin(d)

    def _load_skin(self, directory: str):
        self.current_skin_dir = directory
        ini_path = os.path.join(directory, "skin.ini")
        if os.path.exists(ini_path):
            self.parser.load(ini_path)
            skin_name = self.parser.general.get("Name", os.path.basename(directory))
            self.lbl_skin_name.setText(f"当前皮肤: {skin_name} ({directory})")
        else:
            self.lbl_skin_name.setText(f"当前皮肤: {os.path.basename(directory)} (无 skin.ini，已载入默认模板)")

        self.preview_canvas.set_skin_dir(directory)
        self._sync_ui_from_parser()

    def _create_new_skin(self):
        parent_dir = QFileDialog.getExistingDirectory(self, "选择存放新皮肤的目录")
        if not parent_dir:
            return
        name, ok = QInputDialog.getText(self, "新建皮肤", "请输入皮肤名称:")
        if ok and name.strip():
            skin_dir = os.path.join(parent_dir, name.strip())
            os.makedirs(skin_dir, exist_ok=True)
            ini_path = os.path.join(skin_dir, "skin.ini")
            with open(ini_path, "w", encoding="utf-8") as f:
                f.write(f"[General]\nName: {name.strip()}\nAuthor: Chieri\nVersion: latest\n\n[Mania]\nKeys: 4\nColumnStart: 136\nColumnWidth: 60,60,60,60\nHitPosition: 400\n")
            self._load_skin(skin_dir)
            QMessageBox.information(self, "创建成功", f"新皮肤 [{name.strip()}] 创建就绪！")

    def _sync_ui_from_parser(self):
        keys = self.combo_keys.currentText()
        sec = self.parser.get_mania_section(keys) or {}

        try:
            hp = int(float(sec.get("HitPosition", "400")))
            self.spin_hit.setValue(hp)
        except ValueError:
            self.spin_hit.setValue(400)

        try:
            cs = int(float(sec.get("ColumnStart", "136")))
            self.spin_start.setValue(cs)
        except ValueError:
            self.spin_start.setValue(136)

        cw = sec.get("ColumnWidth", "60,60,60,60")
        self.le_col_width.setText(cw)

        self.preview_canvas.set_keys(keys)
        self.preview_canvas.update()

    def _on_keys_changed(self, keys: str):
        self._sync_ui_from_parser()

    def _on_ratio_changed(self, ratio: str):
        self.preview_canvas.set_aspect_ratio(ratio)

    def _on_param_modified(self):
        keys = self.combo_keys.currentText()
        sec = self.parser.get_mania_section(keys)
        if sec is None:
            sec = {"Keys": keys}

        sec["HitPosition"] = str(self.spin_hit.value())
        sec["ColumnStart"] = str(self.spin_start.value())
        sec["ColumnWidth"] = self.le_col_width.text().strip()

        self.parser.update_or_add_mania_section(keys, sec)
        self.preview_canvas.update()

    def _save_skin_ini(self):
        if not self.current_skin_dir:
            QMessageBox.warning(self, "提示", "尚未打开或创建皮肤目录。")
            return

        ini_path = os.path.join(self.current_skin_dir, "skin.ini")
        try:
            self._on_param_modified()
            self.parser.save(ini_path)
            QMessageBox.information(self, "保存成功", f"skin.ini 已成功写入并更新！")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入文件异常: {e}")

    def load_settings(self):
        cfg = self.config.get_plugin_config("osu_skin_studio", {})
        last_dir = cfg.get("last_skin_dir", "")
        if last_dir and os.path.isdir(last_dir):
            self._load_skin(last_dir)

    def save_settings(self):
        cfg = {
            "last_skin_dir": self.current_skin_dir
        }
        self.config.set_plugin_config("osu_skin_studio", cfg)
