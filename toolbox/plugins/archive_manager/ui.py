"""
全能压缩与解压 - UI 界面
提供多格式压缩与解压面板、密码保护、包内文件结构预览与多引擎协同调度。
"""

import os
import subprocess
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSlider, QGroupBox, QTabWidget,
    QProgressBar, QTextEdit, QFileDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.components.drag_drop_box import ModernFileListWidget
from toolbox.ui.icons import get_icon, get_pixmap
from .engine import (
    get_available_engines, list_archive_contents, ArchiveWorker
)
from .password_book import AcgPasswordBook, auto_match_archive_password, check_archive_encryption_status
from .password_dialog import AcgPasswordDialog


class ArchiveManagerWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.config = ConfigManager()
        self.worker: Optional[ArchiveWorker] = None

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
        icon_lbl.setPixmap(get_pixmap("archive", color="#eab308", size=26))
        header_layout.addWidget(icon_lbl)

        title_lbl = QLabel("全能压缩与解压缩管理器")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_lbl)

        engines = get_available_engines()
        engine_str = " · ".join(list(engines.keys()))
        badge_lbl = QLabel(f"核心引擎: {engine_str}")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #ca8a04; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header_layout.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # 2. 分页标签栏 (解压 / 压缩)
        self.tabs = QTabWidget()

        # Tab 1: 解压
        tab_extract = QWidget()
        extract_layout = QVBoxLayout(tab_extract)
        extract_layout.setContentsMargins(12, 16, 12, 12)
        extract_layout.setSpacing(12)

        # 待解压文件选择
        f_group = QGroupBox("选择压缩包")
        f_box = QHBoxLayout(f_group)
        self.le_extract_file = QLineEdit()
        self.le_extract_file.setPlaceholderText("支持拖入或选择 .zip / .7z / .rar / .tar / .gz / .lz4 压缩包...")
        self.le_extract_file.textChanged.connect(self._on_extract_file_changed)
        f_box.addWidget(self.le_extract_file, 1)

        btn_browse_archive = QPushButton("浏览压缩包...")
        btn_browse_archive.setIcon(get_icon("folder", size=14))
        btn_browse_archive.clicked.connect(self._browse_archive_file)
        f_box.addWidget(btn_browse_archive)
        extract_layout.addWidget(f_group)

        # 解压目标与密码
        out_group = QGroupBox("解压选项")
        out_box = QVBoxLayout(out_group)
        out_box.setSpacing(10)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("解压目标路径:"))
        self.le_extract_dir = QLineEdit()
        dir_row.addWidget(self.le_extract_dir, 1)
        btn_browse_dir = QPushButton("选择目录...")
        btn_browse_dir.setIcon(get_icon("folder", size=14))
        btn_browse_dir.clicked.connect(self._browse_extract_dir)
        dir_row.addWidget(btn_browse_dir)
        out_box.addLayout(dir_row)

        pwd_row = QHBoxLayout()
        pwd_row.addWidget(QLabel("解压密码:"))
        self.le_extract_pwd = QLineEdit()
        self.le_extract_pwd.setEchoMode(QLineEdit.Password)
        self.le_extract_pwd.setPlaceholderText("如有密码请在此输入，或留空自动试探...")
        pwd_row.addWidget(self.le_extract_pwd, 1)

        self.cb_show_pwd1 = QCheckBox("明文")
        self.cb_show_pwd1.toggled.connect(
            lambda c: self.le_extract_pwd.setEchoMode(QLineEdit.Normal if c else QLineEdit.Password)
        )
        pwd_row.addWidget(self.cb_show_pwd1)

        self.btn_pwd_book = QPushButton("ACG 密码本...")
        self.btn_pwd_book.setIcon(get_icon("key", size=14))
        self.btn_pwd_book.setToolTip("查看或管理二次元社区常用解压密码与个人历史记忆")
        self.btn_pwd_book.clicked.connect(self._open_password_dialog)
        pwd_row.addWidget(self.btn_pwd_book)

        btn_preview = QPushButton("预览包内文件")
        btn_preview.setIcon(get_icon("search", size=14))
        btn_preview.clicked.connect(self._preview_archive)
        pwd_row.addWidget(btn_preview)

        out_box.addLayout(pwd_row)

        auto_pwd_row = QHBoxLayout()
        self.cb_auto_pwd = QCheckBox("启用 ACG 密码本智能秒级匹配 (自动试探终点/初音/2dfan等二次元社区高频密码)")
        self.cb_auto_pwd.setChecked(True)
        auto_pwd_row.addWidget(self.cb_auto_pwd)
        out_box.addLayout(auto_pwd_row)
        extract_layout.addWidget(out_group)

        # 包内文件预览表格
        self.table_preview = QTableWidget()
        self.table_preview.setColumnCount(3)
        self.table_preview.setHorizontalHeaderLabels(["文件路径", "原始大小", "类型"])
        self.table_preview.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_preview.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_preview.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_preview.setFixedHeight(120)
        extract_layout.addWidget(self.table_preview)

        # 解压按钮
        self.btn_do_extract = QPushButton("开始解压全部文件")
        self.btn_do_extract.setObjectName("primaryBtn")
        self.btn_do_extract.setIcon(get_icon("archive", size=16))
        self.btn_do_extract.setFixedHeight(36)
        self.btn_do_extract.clicked.connect(self._start_extract)
        extract_layout.addWidget(self.btn_do_extract)

        self.tabs.addTab(tab_extract, "文件解压 (Extract)")

        # Tab 2: 压缩
        tab_compress = QWidget()
        compress_layout = QVBoxLayout(tab_compress)
        compress_layout.setContentsMargins(12, 16, 12, 12)
        compress_layout.setSpacing(12)

        # 待压缩列表
        self.fl_compress = ModernFileListWidget(
            title="待打包文件与文件夹",
            hint="可直接将需要压缩的文件或文件夹拖入此处"
        )
        compress_layout.addWidget(self.fl_compress, 1)

        # 压缩参数
        comp_opts = QGroupBox("压缩格式与安全配置")
        comp_box = QVBoxLayout(comp_opts)
        comp_box.setSpacing(10)

        c_row1 = QHBoxLayout()
        c_row1.addWidget(QLabel("压缩格式:"))
        self.combo_comp_fmt = QComboBox()
        self.combo_comp_fmt.addItems(["ZIP (.zip)", "7-Zip (.7z)", "TAR GZ (.tar.gz)", "LZ4 (.lz4)"])
        self.combo_comp_fmt.currentTextChanged.connect(self._on_comp_fmt_changed)
        c_row1.addWidget(self.combo_comp_fmt)

        c_row1.addWidget(QLabel("压缩级别 (1最快 - 9最大):"))
        self.slider_level = QSlider(Qt.Horizontal)
        self.slider_level.setRange(1, 9)
        self.slider_level.setValue(5)
        self.slider_level.setFixedWidth(120)
        c_row1.addWidget(self.slider_level)
        self.lbl_level_val = QLabel("5 (标准)")
        self.slider_level.valueChanged.connect(lambda v: self.lbl_level_val.setText(f"{v} ({'最快' if v<=2 else '最大' if v>=8 else '标准'})"))
        c_row1.addWidget(self.lbl_level_val)
        c_row1.addStretch()
        comp_box.addLayout(c_row1)

        c_row2 = QHBoxLayout()
        c_row2.addWidget(QLabel("设置密码 (可选):"))
        self.le_comp_pwd = QLineEdit()
        self.le_comp_pwd.setEchoMode(QLineEdit.Password)
        self.le_comp_pwd.setPlaceholderText("留空表示不设置密码...")
        c_row2.addWidget(self.le_comp_pwd, 1)

        self.cb_show_pwd2 = QCheckBox("显示明文")
        self.cb_show_pwd2.toggled.connect(
            lambda c: self.le_comp_pwd.setEchoMode(QLineEdit.Normal if c else QLineEdit.Password)
        )
        c_row2.addWidget(self.cb_show_pwd2)
        comp_box.addLayout(c_row2)

        c_row3 = QHBoxLayout()
        c_row3.addWidget(QLabel("输出压缩包文件:"))
        self.le_comp_out = QLineEdit()
        c_row3.addWidget(self.le_comp_out, 1)
        btn_browse_comp_out = QPushButton("更改位置...")
        btn_browse_comp_out.setIcon(get_icon("folder", size=14))
        btn_browse_comp_out.clicked.connect(self._browse_comp_out)
        c_row3.addWidget(btn_browse_comp_out)
        comp_box.addLayout(c_row3)

        compress_layout.addWidget(comp_opts)

        # 压缩按钮
        self.btn_do_compress = QPushButton("开始创建压缩包")
        self.btn_do_compress.setObjectName("primaryBtn")
        self.btn_do_compress.setIcon(get_icon("archive", size=16))
        self.btn_do_compress.setFixedHeight(36)
        self.btn_do_compress.clicked.connect(self._start_compress)
        compress_layout.addWidget(self.btn_do_compress)

        self.tabs.addTab(tab_compress, "创建压缩包 (Compress)")

        layout.addWidget(self.tabs, 1)

        # 3. 底部状态与日志
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        self.btn_open_target = QPushButton("打开目标文件夹")
        self.btn_open_target.setIcon(get_icon("folder", size=14))
        self.btn_open_target.clicked.connect(self._open_target_folder)
        bottom_row.addWidget(self.btn_open_target)

        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 12px;")
        bottom_row.addWidget(self.lbl_status, 1)

        layout.addLayout(bottom_row)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFixedHeight(85)
        self.log_console.setPlaceholderText("操作执行日志...")
        layout.addWidget(self.log_console)

    def _browse_archive_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "选择压缩包", "",
            "归档压缩包 (*.zip *.7z *.rar *.tar *.gz *.tgz *.bz2 *.xz *.lz4);;所有文件 (*.*)"
        )
        if f:
            self.le_extract_file.setText(f)

    def _on_extract_file_changed(self, path: str):
        path = path.strip()
        if path and os.path.isfile(path):
            dir_name = os.path.dirname(path)
            base = os.path.splitext(os.path.basename(path))[0]
            out_target = os.path.join(dir_name, base)
            self.le_extract_dir.setText(out_target)

    def _browse_extract_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "选择解压输出目录", self.le_extract_dir.text())
        if chosen:
            self.le_extract_dir.setText(chosen)

    def _open_password_dialog(self):
        dlg = AcgPasswordDialog(self)
        dlg.password_selected.connect(self.le_extract_pwd.setText)
        dlg.exec()

    def _on_password_matched(self, pwd: str):
        self.le_extract_pwd.setText(pwd)
        self.log_console.append(f"[密码本] 已自动填入匹配成功的解压密码: 【{pwd}】")

    def _preview_archive(self):
        arch = self.le_extract_file.text().strip()
        if not arch or not os.path.isfile(arch):
            self.lbl_status.setText("请先选择有效的压缩文件。")
            return

        pwd = self.le_extract_pwd.text().strip() or None
        if not pwd and self.cb_auto_pwd.isChecked():
            is_enc, _, _ = check_archive_encryption_status(arch)
            if is_enc:
                self.lbl_status.setText("正在通过 ACG 密码本快速匹配试探...")
                matched = auto_match_archive_password(arch)
                if matched:
                    pwd = matched
                    self.le_extract_pwd.setText(matched)
                    self.log_console.append(f"[密码本] 预览时成功匹配解压密码: 【{matched}】")
                else:
                    self.log_console.append("[密码本] 预览未匹配到预设密码，请手动输入密码。")

        self.lbl_status.setText("正在读取包内文件结构...")
        items = list_archive_contents(arch, pwd)

        self.table_preview.setRowCount(len(items))
        for row, it in enumerate(items):
            p_item = QTableWidgetItem(it.get("Path", ""))
            sz = it.get("Size", 0)
            sz_str = f"{sz / 1024:.1f} KB" if sz > 1024 else f"{sz} B"
            s_item = QTableWidgetItem(sz_str)
            t_item = QTableWidgetItem("文件夹" if it.get("Folder") else "文件")
            self.table_preview.setItem(row, 0, p_item)
            self.table_preview.setItem(row, 1, s_item)
            self.table_preview.setItem(row, 2, t_item)

        self.lbl_status.setText(f"预览完成，共包含 {len(items)} 个条目。")

    def _start_extract(self):
        arch = self.le_extract_file.text().strip()
        if not arch or not os.path.isfile(arch):
            self.lbl_status.setText("请先选择有效的压缩包。")
            return

        out_dir = self.le_extract_dir.text().strip()
        if not out_dir:
            self.lbl_status.setText("请指定解压目标目录。")
            return

        pwd = self.le_extract_pwd.text().strip() or None
        self.btn_do_extract.setEnabled(False)
        self.lbl_status.setText("解压执行中...")

        self.worker = ArchiveWorker(
            "extract",
            archive_path=arch,
            output_dir=out_dir,
            password=pwd,
            auto_match_password=self.cb_auto_pwd.isChecked()
        )
        self.worker.log_message.connect(self.log_console.append)
        self.worker.password_matched.connect(self._on_password_matched)
        self.worker.finished.connect(self._on_archive_finished)
        self.worker.start()

    def _on_comp_fmt_changed(self, text: str):
        paths = self.fl_compress.get_paths()
        if paths:
            first = paths[0]
            dir_name = os.path.dirname(first)
            base = os.path.splitext(os.path.basename(first))[0]
            ext = ".zip"
            if "7z" in text: ext = ".7z"
            elif "tar" in text: ext = ".tar.gz"
            elif "lz4" in text: ext = ".lz4"
            self.le_comp_out.setText(os.path.join(dir_name, f"{base}_archive{ext}"))

    def _browse_comp_out(self):
        cur = self.le_comp_out.text().strip()
        f, _ = QFileDialog.getSaveFileName(self, "选择压缩包保存路径", cur, "所有文件 (*.*)")
        if f:
            self.le_comp_out.setText(f)

    def _start_compress(self):
        sources = self.fl_compress.get_paths()
        if not sources:
            self.lbl_status.setText("请先添加需要打包的文件或文件夹。")
            return

        out_arch = self.le_comp_out.text().strip()
        if not out_arch:
            # 自动生成
            first = sources[0]
            dir_name = os.path.dirname(first)
            base = os.path.splitext(os.path.basename(first))[0]
            fmt_raw = self.combo_comp_fmt.currentText()
            ext = ".zip"
            if "7z" in fmt_raw: ext = ".7z"
            elif "tar" in fmt_raw: ext = ".tar.gz"
            elif "lz4" in fmt_raw: ext = ".lz4"
            out_arch = os.path.join(dir_name, f"{base}_archive{ext}")
            self.le_comp_out.setText(out_arch)

        fmt_type = "zip"
        raw_fmt = self.combo_comp_fmt.currentText()
        if "7z" in raw_fmt: fmt_type = "7z"
        elif "tar" in raw_fmt: fmt_type = "tar.gz"
        elif "lz4" in fmt_raw: fmt_type = "lz4"

        pwd = self.le_comp_pwd.text().strip() or None
        lvl = self.slider_level.value()

        self.btn_do_compress.setEnabled(False)
        self.lbl_status.setText("正在打包压缩...")

        self.worker = ArchiveWorker(
            "compress",
            source_paths=sources,
            output_archive=out_arch,
            format_type=fmt_type,
            password=pwd,
            compression_level=lvl
        )
        self.worker.log_message.connect(self.log_console.append)
        self.worker.finished.connect(self._on_archive_finished)
        self.worker.start()

    def _on_archive_finished(self, success: bool, msg: str):
        self.btn_do_extract.setEnabled(True)
        self.btn_do_compress.setEnabled(True)
        if success:
            self.lbl_status.setText("任务圆满完成！")
            self.log_console.append(f"[完成] {msg}")
            if self.tabs.currentIndex() == 0:
                pwd = self.le_extract_pwd.text().strip()
                if pwd:
                    AcgPasswordBook().add_password(pwd)
        else:
            self.lbl_status.setText(f"操作失败: {msg}")
            self.log_console.append(f"[失败] {msg}")

    def _open_target_folder(self):
        if self.tabs.currentIndex() == 0:
            target = self.le_extract_dir.text().strip()
        else:
            p = self.le_comp_out.text().strip()
            target = os.path.dirname(p) if p else ""

        if target and os.path.exists(target):
            subprocess.Popen(f'explorer "{os.path.normpath(target)}"')
        else:
            self.log_console.append("[提示] 目标目录尚未生成或不存在。")

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
                ext = os.path.splitext(fp)[1].lower()
                if ext in (".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".lz4"):
                    self.tabs.setCurrentIndex(0)
                    self.le_extract_file.setText(fp)
                else:
                    self.tabs.setCurrentIndex(1)
                    self.fl_compress.set_paths([u.toLocalFile() for u in urls])
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def handle_initial_paths(self, paths: list):
        if paths:
            first = str(paths[0])
            ext = os.path.splitext(first)[1].lower()
            if ext in (".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".lz4"):
                self.tabs.setCurrentIndex(0)
                self.le_extract_file.setText(first)
            else:
                self.tabs.setCurrentIndex(1)
                self.fl_compress.set_paths([str(p) for p in paths])

    def load_settings(self):
        cfg = self.config.get_plugin_config("archive_manager", {})
        tab_idx = cfg.get("tab_idx", 0)
        if 0 <= tab_idx < self.tabs.count():
            self.tabs.setCurrentIndex(tab_idx)
        comp_fmt_idx = cfg.get("comp_fmt_idx", 0)
        if 0 <= comp_fmt_idx < self.combo_comp_fmt.count():
            self.combo_comp_fmt.setCurrentIndex(comp_fmt_idx)
        self.slider_level.setValue(cfg.get("level", 5))
        if "extract_dir" in cfg:
            self.le_extract_dir.setText(cfg["extract_dir"])
        self.cb_auto_pwd.setChecked(cfg.get("auto_match_pwd", True))

    def save_settings(self):
        cfg = {
            "tab_idx": self.tabs.currentIndex(),
            "comp_fmt_idx": self.combo_comp_fmt.currentIndex(),
            "level": self.slider_level.value(),
            "extract_dir": self.le_extract_dir.text(),
            "auto_match_pwd": self.cb_auto_pwd.isChecked()
        }
        self.config.set_plugin_config("archive_manager", cfg)
