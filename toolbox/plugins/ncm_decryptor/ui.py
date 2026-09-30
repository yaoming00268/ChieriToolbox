"""
网易云音乐 NCM 格式解密 - UI 界面
批量拖入 .ncm 加密文件，秒级逆向解密为标准 MP3 / FLAC，无损还原内嵌封面与 ID3 元标签。
"""

import os
import subprocess
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QProgressBar, QTextEdit, QRadioButton,
    QButtonGroup, QLineEdit, QFileDialog, QGroupBox
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.components.drag_drop_box import ModernFileListWidget
from toolbox.ui.icons import get_icon, get_pixmap
from .decryptor import scan_ncm_files, NcmBatchWorker


class NcmDecryptorWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.worker: Optional[NcmBatchWorker] = None
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
        icon_lbl.setPixmap(get_pixmap("lock", color="#f59e0b", size=26))
        header_layout.addWidget(icon_lbl)

        title_lbl = QLabel("网易云音乐 NCM 格式解密还原")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_lbl)

        badge_lbl = QLabel("纯算法秒级解密 · 自动恢复封面")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #f59e0b; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header_layout.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # 2. 核心文件拖拽列表
        self.fl_ncms = ModernFileListWidget(
            title="待解密 NCM 文件列表",
            hint="可拖入任意网易云音乐下载的 .ncm 文件或包含 ncm 的文件夹"
        )
        layout.addWidget(self.fl_ncms, 1)

        # 3. 解密选项与输出设置
        opts_group = QGroupBox("解密选项与输出设置")
        opts_layout = QVBoxLayout(opts_group)
        opts_layout.setSpacing(10)

        self.cb_embed_tags = QCheckBox("自动解析并写入 ID3/FLAC 歌曲标题、歌手、专辑信息与内嵌高清封面")
        self.cb_embed_tags.setChecked(True)
        opts_layout.addWidget(self.cb_embed_tags)

        # 目录选择
        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(10)

        self.btn_group_dir = QButtonGroup(self)
        self.rb_same_dir = QRadioButton("保存在原 NCM 文件所在目录")
        self.rb_same_dir.setChecked(True)
        self.rb_custom_dir = QRadioButton("保存在指定目录:")
        self.btn_group_dir.addButton(self.rb_same_dir)
        self.btn_group_dir.addButton(self.rb_custom_dir)
        self.rb_custom_dir.toggled.connect(self._toggle_custom_dir)

        dir_layout.addWidget(self.rb_same_dir)
        dir_layout.addWidget(self.rb_custom_dir)

        self.le_custom_dir = QLineEdit()
        self.le_custom_dir.setEnabled(False)
        self.le_custom_dir.setText(self.config.get("ncm_decryptor_save_dir", ""))
        dir_layout.addWidget(self.le_custom_dir, 1)

        self.btn_browse_dir = QPushButton("浏览...")
        self.btn_browse_dir.setIcon(get_icon("folder", size=14))
        self.btn_browse_dir.setEnabled(False)
        self.btn_browse_dir.clicked.connect(self._browse_custom_dir)
        dir_layout.addWidget(self.btn_browse_dir)

        opts_layout.addLayout(dir_layout)
        layout.addWidget(opts_group)

        # 4. 执行控制
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.btn_start = QPushButton("开始解密还原")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_start.setIcon(get_icon("play", size=16))
        self.btn_start.setFixedHeight(36)
        self.btn_start.clicked.connect(self._start_decryption)
        action_layout.addWidget(self.btn_start, 1)

        self.btn_cancel = QPushButton("中止")
        self.btn_cancel.setObjectName("dangerBtn")
        self.btn_cancel.setIcon(get_icon("clear", size=14))
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_decryption)
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
        self.log_console.setPlaceholderText("解密日志输出...")
        layout.addWidget(self.log_console)

    def _toggle_custom_dir(self, checked: bool):
        self.le_custom_dir.setEnabled(checked)
        self.btn_browse_dir.setEnabled(checked)

    def _browse_custom_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "选择输出文件夹", self.le_custom_dir.text())
        if chosen:
            self.le_custom_dir.setText(chosen)
            self.config.set("ncm_decryptor_save_dir", chosen)

    def _open_output_dir(self):
        if self.rb_custom_dir.isChecked() and self.le_custom_dir.text().strip():
            target = self.le_custom_dir.text().strip()
        else:
            paths = self.fl_ncms.get_paths()
            target = os.path.dirname(paths[0]) if paths else os.path.expanduser("~")

        if os.path.exists(target):
            subprocess.Popen(f'explorer "{os.path.normpath(target)}"')
        else:
            self._log("[提示] 目标目录不存在。")

    def _start_decryption(self):
        raw_paths = self.fl_ncms.get_paths()
        if not raw_paths:
            self._log("[提示] 请先添加待解密的 .ncm 文件。")
            return

        valid_ncms = scan_ncm_files(raw_paths)
        if not valid_ncms:
            self._log("[提示] 列表中未包含有效的 .ncm 文件。")
            return

        custom_dir = None
        if self.rb_custom_dir.isChecked():
            custom_dir = self.le_custom_dir.text().strip()
            if not custom_dir:
                self._log("[提示] 请指定自定义输出目录。")
                return

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("开始解密...")

        self.worker = NcmBatchWorker(
            file_paths=valid_ncms,
            custom_output_dir=custom_dir,
            embed_tags=self.cb_embed_tags.isChecked()
        )
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.file_started.connect(lambda f, i, t: self.lbl_status.setText(f"正在解密 ({i}/{t}): {f}"))
        self.worker.log_message.connect(self._log)
        self.worker.batch_finished.connect(self._on_batch_finished)
        self.worker.start()

    def _cancel_decryption(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.lbl_status.setText("正在中止...")
            self.btn_cancel.setEnabled(False)

    def _on_batch_finished(self, success: int, failed: int):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.lbl_status.setText(f"解密完成: 成功 {success} 首, 失败 {failed} 首")

    def _log(self, text: str):
        self.log_console.append(text)

    def handle_initial_paths(self, paths: list):
        if paths:
            self.fl_ncms.set_paths(paths)

    def load_settings(self):
        cfg = self.config.get_plugin_config("ncm_decryptor", {})
        self.cb_embed_tags.setChecked(cfg.get("embed_tags", True))
        use_custom = cfg.get("use_custom_dir", False)
        if use_custom:
            self.rb_custom_dir.setChecked(True)
        else:
            self.rb_same_dir.setChecked(True)
        self.le_custom_dir.setText(cfg.get("custom_dir", self.config.get("ncm_decryptor_save_dir", "")))

    def save_settings(self):
        cfg = {
            "embed_tags": self.cb_embed_tags.isChecked(),
            "use_custom_dir": self.rb_custom_dir.isChecked(),
            "custom_dir": self.le_custom_dir.text()
        }
        self.config.set_plugin_config("ncm_decryptor", cfg)
