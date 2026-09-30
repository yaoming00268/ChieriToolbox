"""
文件批量整理大师 - UI 界面
包含名称重命名、后缀修改、目录扁平化三大功能选项卡。
"""

import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel,
    QLineEdit, QSpinBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QTextEdit, QRadioButton, QButtonGroup,
    QCheckBox
)
from toolbox.core.config_manager import ConfigManager
from toolbox.ui.components.drag_drop_box import ModernFileListWidget
from .logic import scan_files, FileRenameEngine, FolderFlattenEngine


class FileSuiteWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.init_ui()
        self.load_settings()

    def handle_initial_paths(self, paths: list):
        """处理外部传入的文件或文件夹路径"""
        valid_paths = [p for p in paths if os.path.exists(p)]
        if valid_paths:
            self.fl_name.add_paths(valid_paths)
            dirs = [p for p in valid_paths if os.path.isdir(p)]
            if dirs:
                self.fl_flatten.add_paths(dirs)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_name_tab(), "批量名称重命名")
        self.tabs.addTab(self._create_ext_tab(), "批量后缀转换")
        self.tabs.addTab(self._create_flatten_tab(), "提取并扁平化目录")

        main_layout.addWidget(self.tabs)

    # ---------------- 选项卡 1: 文件名批量重命名 ----------------
    def _create_name_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(16)

        # 左侧：拖拽文件列表
        left_box = QVBoxLayout()
        self.fl_name = ModernFileListWidget("待重命名文件", "可拖入文件或文件夹")
        self.fl_name.paths_changed.connect(self._on_name_inputs_changed)
        left_box.addWidget(self.fl_name)
        layout.addLayout(left_box, 1)

        # 右侧：重命名规则与对照预览表格
        right_box = QVBoxLayout()
        right_box.setSpacing(8)

        # 模式切换
        mode_layout = QHBoxLayout()
        self.rb_seq = QRadioButton("序号/模板递增")
        self.rb_rep = QRadioButton("查找与替换")
        self.rb_seq.setChecked(True)
        self.rb_seq.toggled.connect(self._on_rename_mode_changed)

        bg = QButtonGroup(widget)
        bg.addButton(self.rb_seq)
        bg.addButton(self.rb_rep)
        mode_layout.addWidget(self.rb_seq)
        mode_layout.addWidget(self.rb_rep)
        mode_layout.addStretch()
        right_box.addLayout(mode_layout)

        # 模板参数区
        self.param_seq_widget = QWidget()
        seq_layout = QHBoxLayout(self.param_seq_widget)
        seq_layout.setContentsMargins(0, 0, 0, 0)
        self.le_pattern = QLineEdit()
        self.le_pattern.setPlaceholderText("基础名称(可用 {n} 代表序号, 如 photo_{n})")
        self.le_pattern.textChanged.connect(self._update_name_preview)
        seq_layout.addWidget(self.le_pattern, 2)

        seq_layout.addWidget(QLabel("起始号:"))
        self.sp_start = QSpinBox()
        self.sp_start.setRange(0, 99999)
        self.sp_start.setValue(1)
        self.sp_start.valueChanged.connect(self._update_name_preview)
        seq_layout.addWidget(self.sp_start)

        seq_layout.addWidget(QLabel("补零位数:"))
        self.sp_digits = QSpinBox()
        self.sp_digits.setRange(1, 10)
        self.sp_digits.setValue(2)
        self.sp_digits.valueChanged.connect(self._update_name_preview)
        seq_layout.addWidget(self.sp_digits)
        right_box.addWidget(self.param_seq_widget)

        # 替换参数区
        self.param_rep_widget = QWidget()
        self.param_rep_widget.setVisible(False)
        rep_layout = QHBoxLayout(self.param_rep_widget)
        rep_layout.setContentsMargins(0, 0, 0, 0)
        self.le_find = QLineEdit()
        self.le_find.setPlaceholderText("查找文本...")
        self.le_find.textChanged.connect(self._update_name_preview)
        self.le_replace = QLineEdit()
        self.le_replace.setPlaceholderText("替换为...")
        self.le_replace.textChanged.connect(self._update_name_preview)
        self.cb_regex = QCheckBox("正则表达式")
        self.cb_regex.toggled.connect(self._update_name_preview)
        rep_layout.addWidget(self.le_find, 1)
        rep_layout.addWidget(self.le_replace, 1)
        rep_layout.addWidget(self.cb_regex)
        right_box.addWidget(self.param_rep_widget)

        # 预览对照表格
        self.tbl_name_preview = QTableWidget(0, 2)
        self.tbl_name_preview.setHorizontalHeaderLabels(["当前原文件名", "重命名后预览"])
        self.tbl_name_preview.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right_box.addWidget(self.tbl_name_preview, 1)

        # 执行按钮与日志
        btn_exec_name = QPushButton("确认执行批量重命名")
        btn_exec_name.setObjectName("primaryBtn")
        btn_exec_name.clicked.connect(self._execute_name_rename)
        right_box.addWidget(btn_exec_name)

        layout.addLayout(right_box, 2)
        self.current_name_plan = []
        return widget

    def _on_rename_mode_changed(self):
        is_seq = self.rb_seq.isChecked()
        self.param_seq_widget.setVisible(is_seq)
        self.param_rep_widget.setVisible(not is_seq)
        self._update_name_preview()

    def _on_name_inputs_changed(self):
        self._update_name_preview()

    def _update_name_preview(self):
        paths = self.fl_name.get_paths()
        files = scan_files(paths, recursive=True)

        if not files:
            self.tbl_name_preview.setRowCount(0)
            self.current_name_plan = []
            return

        if self.rb_seq.isChecked():
            pattern = self.le_pattern.text().strip()
            plan = FileRenameEngine.preview_template_rename(
                files,
                pattern=pattern or "file",
                start_index=self.sp_start.value(),
                pad_digits=self.sp_digits.value()
            )
        else:
            find_str = self.le_find.text()
            replace_str = self.le_replace.text()
            plan = FileRenameEngine.preview_replace_rename(
                files,
                find_str=find_str,
                replace_str=replace_str,
                use_regex=self.cb_regex.isChecked()
            )

        self.current_name_plan = plan
        self.tbl_name_preview.setRowCount(len(plan))
        for row, (_, _, old_n, new_n) in enumerate(plan):
            item_old = QTableWidgetItem(old_n)
            item_new = QTableWidgetItem(new_n)
            if old_n != new_n:
                item_new.setForeground(Qt.GlobalColor.darkCyan)
            self.tbl_name_preview.setItem(row, 0, item_old)
            self.tbl_name_preview.setItem(row, 1, item_new)

    def _execute_name_rename(self):
        if not self.current_name_plan:
            QMessageBox.information(self, "提示", "当前没有可重命名的文件列表。")
            return

        res = FileRenameEngine.execute_rename(self.current_name_plan)
        msg = f"重命名完成！成功: {res['success']} 个，跳过: {res['skipped']} 个。"
        if res["errors"]:
            msg += f"\n部分错误:\n" + "\n".join(res["errors"][:5])
        QMessageBox.information(self, "执行结果", msg)
        self._update_name_preview()

    # ---------------- 选项卡 2: 批量后缀转换 ----------------
    def _create_ext_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(16)

        left_box = QVBoxLayout()
        self.fl_ext = ModernFileListWidget("待修改后缀文件", "可拖入文件或文件夹")
        self.fl_ext.paths_changed.connect(self._update_ext_preview)
        left_box.addWidget(self.fl_ext)
        layout.addLayout(left_box, 1)

        right_box = QVBoxLayout()
        right_box.setSpacing(8)

        inputs_layout = QHBoxLayout()
        self.le_old_ext = QLineEdit()
        self.le_old_ext.setPlaceholderText("原后缀过滤 (留空或 * 代表所有)")
        self.le_old_ext.textChanged.connect(self._update_ext_preview)
        inputs_layout.addWidget(self.le_old_ext)

        self.le_new_ext = QLineEdit()
        self.le_new_ext.setPlaceholderText("目标新后缀 (如: png 或 md)")
        self.le_new_ext.textChanged.connect(self._update_ext_preview)
        inputs_layout.addWidget(self.le_new_ext)
        right_box.addLayout(inputs_layout)

        self.tbl_ext_preview = QTableWidget(0, 2)
        self.tbl_ext_preview.setHorizontalHeaderLabels(["当前文件名", "新后缀后文件名"])
        self.tbl_ext_preview.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right_box.addWidget(self.tbl_ext_preview, 1)

        btn_exec_ext = QPushButton("确认统一修改文件后缀")
        btn_exec_ext.setObjectName("primaryBtn")
        btn_exec_ext.clicked.connect(self._execute_ext_rename)
        right_box.addWidget(btn_exec_ext)

        layout.addLayout(right_box, 2)
        self.current_ext_plan = []
        return widget

    def _update_ext_preview(self):
        paths = self.fl_ext.get_paths()
        files = scan_files(paths, recursive=True)
        if not files or not self.le_new_ext.text().strip():
            self.tbl_ext_preview.setRowCount(0)
            self.current_ext_plan = []
            return

        plan = FileRenameEngine.preview_extension_rename(
            files,
            old_ext_filter=self.le_old_ext.text().strip(),
            new_ext=self.le_new_ext.text().strip()
        )
        self.current_ext_plan = plan
        self.tbl_ext_preview.setRowCount(len(plan))
        for row, (_, _, old_n, new_n) in enumerate(plan):
            item_old = QTableWidgetItem(old_n)
            item_new = QTableWidgetItem(new_n)
            if old_n != new_n:
                item_new.setForeground(Qt.GlobalColor.darkCyan)
            self.tbl_ext_preview.setItem(row, 0, item_old)
            self.tbl_ext_preview.setItem(row, 1, item_new)

    def _execute_ext_rename(self):
        if not self.current_ext_plan:
            QMessageBox.information(self, "提示", "当前没有可修改后缀的文件。")
            return

        res = FileRenameEngine.execute_rename(self.current_ext_plan)
        msg = f"后缀修改完成！成功: {res['success']} 个，跳过: {res['skipped']} 个。"
        if res["errors"]:
            msg += f"\n错误信息:\n" + "\n".join(res["errors"][:5])
        QMessageBox.information(self, "执行结果", msg)
        self._update_ext_preview()

    # ---------------- 选项卡 3: 提取并扁平化目录 ----------------
    def _create_flatten_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        tip = QLabel("<b>功能说明</b>：选择子文件夹后，系统会将该文件夹内的所有文件安全转移至其父级文件夹中，遇到同名文件自动增加序号递增防覆盖，并在提取完成后自动删除已清空的子文件夹。")
        tip.setObjectName("helperTipLabel")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self.fl_flatten = ModernFileListWidget("待提取子文件夹列表", "请拖入需要上移并清理的子文件夹")
        layout.addWidget(self.fl_flatten, 1)

        btn_exec_flatten = QPushButton("执行提取到父目录并删除空文件夹")
        btn_exec_flatten.setObjectName("primaryBtn")
        btn_exec_flatten.clicked.connect(self._execute_flatten)
        layout.addWidget(btn_exec_flatten)

        self.txt_flatten_log = QTextEdit()
        self.txt_flatten_log.setReadOnly(True)
        self.txt_flatten_log.setPlaceholderText("操作日志将在此展示...")
        self.txt_flatten_log.setFixedHeight(120)
        layout.addWidget(self.txt_flatten_log)

        return widget

    def _execute_flatten(self):
        folders = self.fl_flatten.get_paths()
        if not folders:
            QMessageBox.information(self, "提示", "请先添加待处理的文件夹。")
            return

        res = FolderFlattenEngine.flatten_folders(folders)
        log = f"提取完成！共安全转移文件 {res['moved_count']} 个，清理空目录 {res['cleaned_folders']} 个。\n"
        if res["errors"]:
            log += "警告/错误:\n" + "\n".join(res["errors"])
        self.txt_flatten_log.setText(log)
        self.fl_flatten.clear()
        QMessageBox.information(self, "操作完成", f"已成功转移 {res['moved_count']} 个文件。")

    def load_settings(self):
        cfg = self.config.get_plugin_config("file_suite", {})
        tab_idx = cfg.get("tab_idx", 0)
        if 0 <= tab_idx < self.tabs.count():
            self.tabs.setCurrentIndex(tab_idx)

    def save_settings(self):
        cfg = {
            "tab_idx": self.tabs.currentIndex()
        }
        self.config.set_plugin_config("file_suite", cfg)
