"""
模拟键入与极速粘贴助手 - UI 界面
"""

import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QKeySequenceEdit, QDoubleSpinBox, QCheckBox,
    QGroupBox, QListWidget, QListWidgetItem, QInputDialog, QMessageBox
)
from toolbox.core.config_manager import ConfigManager
from toolbox.core.theme import ThemeManager
from .worker import PasteSimulatorWorker


class AutoInputWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self.theme_manager = ThemeManager()
        self.worker = PasteSimulatorWorker(self)
        self.init_ui()
        self.load_config()

    def handle_initial_paths(self, paths: list):
        """处理外部传入的文本或文本文件路径"""
        if paths:
            first_p = paths[0]
            if os.path.isfile(first_p):
                try:
                    with open(first_p, "r", encoding="utf-8", errors="ignore") as f:
                        self.txt_content.setText(f.read())
                except Exception:
                    pass
            else:
                self.txt_content.setText(first_p)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. 顶部状态指示栏
        status_bar = QHBoxLayout()
        self.lbl_status_badge = QLabel()
        self._update_badge_status("状态: 未启动", "normal")
        status_bar.addWidget(self.lbl_status_badge)
        status_bar.addStretch()

        self.btn_toggle_listen = QPushButton("开启全局热键监听")
        self.btn_toggle_listen.setObjectName("primaryBtn")
        self.btn_toggle_listen.setMinimumWidth(160)
        self.btn_toggle_listen.clicked.connect(self._toggle_listening)
        status_bar.addWidget(self.btn_toggle_listen)
        main_layout.addLayout(status_bar)

        # 2. 中部核心区：左侧文本与短语库，右侧参数设置
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        # 左侧：文本输入与预设短语
        left_box = QVBoxLayout()
        left_box.setSpacing(8)

        lbl_text_tip = QLabel("待键入的目标文本内容 (当开启剪贴板模式时此内容被忽略):")
        left_box.addWidget(lbl_text_tip)

        self.txt_content = QTextEdit()
        self.txt_content.setPlaceholderText("在此输入或粘贴需要自动模拟输入的文本内容...")
        self.txt_content.textChanged.connect(self._on_text_changed)
        left_box.addWidget(self.txt_content, 2)

        # 常用短语库
        phrase_group = QGroupBox("常用短语预设 (双击快速填入)")
        phrase_layout = QVBoxLayout(phrase_group)
        self.list_phrases = QListWidget()
        self.list_phrases.itemDoubleClicked.connect(self._on_phrase_double_clicked)
        phrase_layout.addWidget(self.list_phrases)

        phrase_btns = QHBoxLayout()
        btn_add_p = QPushButton("新增短语")
        btn_add_p.clicked.connect(self._add_phrase)
        btn_del_p = QPushButton("删除选中")
        btn_del_p.clicked.connect(self._delete_phrase)
        phrase_btns.addWidget(btn_add_p)
        phrase_btns.addWidget(btn_del_p)
        phrase_layout.addLayout(phrase_btns)

        left_box.addWidget(phrase_group, 1)
        content_layout.addLayout(left_box, 3)

        # 右侧：设置面板
        right_group = QGroupBox("参数配置")
        right_layout = QVBoxLayout(right_group)
        right_layout.setSpacing(14)

        # 热键设置
        right_layout.addWidget(QLabel("触发全局快捷键:"))
        self.key_edit = QKeySequenceEdit()
        self.key_edit.setKeySequence(QKeySequence("Ctrl+Alt+V"))
        self.key_edit.keySequenceChanged.connect(self._on_setting_changed)
        right_layout.addWidget(self.key_edit)

        # 键入延时
        right_layout.addWidget(QLabel("字间输入间隔延迟 (秒):"))
        self.sp_delay = QDoubleSpinBox()
        self.sp_delay.setDecimals(3)
        self.sp_delay.setRange(0.001, 1.0)
        self.sp_delay.setSingleStep(0.005)
        self.sp_delay.setValue(0.030)
        self.sp_delay.valueChanged.connect(self._on_setting_changed)
        right_layout.addWidget(self.sp_delay)

        # 模式勾选
        self.cb_clipboard = QCheckBox("直接取用当前系统剪贴板文本")
        self.cb_clipboard.toggled.connect(self._on_setting_changed)
        right_layout.addWidget(self.cb_clipboard)

        right_layout.addStretch()

        tip_box = QLabel("<b>使用说明</b>：<br>"
                        "• 本工具通过底层模拟真实物理击键，可轻松应对网页、远程终端、银行安全控件等防粘贴场景；<br>"
                        "• 按下设定热键前，请确保鼠标光标已定位在目标输入框中。")
        tip_box.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.4;")
        tip_box.setWordWrap(True)
        right_layout.addWidget(tip_box)

        content_layout.addWidget(right_group, 2)
        main_layout.addLayout(content_layout, 1)

        # 绑定 Worker 状态
        self.worker.status_changed.connect(self._on_worker_status)

    def load_config(self):
        cfg = self.config_manager.get_plugin_config("auto_input", {
            "hotkey": "Ctrl+Alt+V",
            "delay": 0.03,
            "use_clipboard": False,
            "text": "Hello, Chieri Toolbox!",
            "phrases": [
                "已收到，非常感谢！",
                "请查收附件文档。",
                "Antigravity Agentic Assistant"
            ]
        })
        self.key_edit.setKeySequence(QKeySequence(cfg.get("hotkey", "Ctrl+Alt+V")))
        self.sp_delay.setValue(cfg.get("delay", 0.03))
        self.cb_clipboard.setChecked(cfg.get("use_clipboard", False))
        self.txt_content.setPlainText(cfg.get("text", ""))

        self.list_phrases.clear()
        for p in cfg.get("phrases", []):
            self.list_phrases.addItem(p)

        self._update_worker_config()

    def save_config(self):
        phrases = [self.list_phrases.item(i).text() for i in range(self.list_phrases.count())]
        cfg = {
            "hotkey": self.key_edit.keySequence().toString(),
            "delay": self.sp_delay.value(),
            "use_clipboard": self.cb_clipboard.isChecked(),
            "text": self.txt_content.toPlainText(),
            "phrases": phrases
        }
        self.config_manager.set_plugin_config("auto_input", cfg)

    save_settings = save_config
    load_settings = load_config

    def _on_text_changed(self):
        self.worker.set_text(self.txt_content.toPlainText())
        self.save_config()

    def _on_setting_changed(self):
        self._update_worker_config()
        self.save_config()

    def _update_worker_config(self):
        seq_str = self.key_edit.keySequence().toString() or "Ctrl+Alt+V"
        self.worker.update_config(
            hotkey=seq_str,
            delay=self.sp_delay.value(),
            use_clipboard=self.cb_clipboard.isChecked(),
            text=self.txt_content.toPlainText()
        )

    def _update_badge_status(self, text: str, state: str = "normal"):
        self.lbl_status_badge.setText(text)
        is_dark = self.theme_manager.is_dark() if hasattr(self, "theme_manager") else True
        if state == "active":
            color = "#4ade80" if is_dark else "#15803d"
        elif state == "busy":
            color = "#facc15" if is_dark else "#b45309"
        else:
            color = "#94a3b8" if is_dark else "#64748b"
        self.lbl_status_badge.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 14px;")

    def _toggle_listening(self):
        if self.worker.is_running:
            self.worker.stop_listening()
            self.btn_toggle_listen.setText("开启全局热键监听")
            self.btn_toggle_listen.setStyleSheet("")
            self._update_badge_status("状态: 已停止监听", "normal")
        else:
            self._update_worker_config()
            ok, msg = self.worker.start_listening()
            if ok:
                self.btn_toggle_listen.setText("停止监听")
                self.btn_toggle_listen.setStyleSheet("background-color: #dc2626; color: white;")
                self._update_badge_status("状态: 全局热键监听中", "active")
            else:
                QMessageBox.warning(self, "启动失败", msg)

    def _on_worker_status(self, text: str):
        if "模拟输入中" in text:
            self._update_badge_status(text, "busy")
        elif "监听中" in text:
            self._update_badge_status("状态: 全局热键监听中", "active")

    def _on_phrase_double_clicked(self, item: QListWidgetItem):
        self.txt_content.setPlainText(item.text())

    def _add_phrase(self):
        text, ok = QInputDialog.getText(self, "新增短语", "请输入常用短语文本:")
        if ok and text.strip():
            self.list_phrases.addItem(text.strip())
            self.save_config()

    def _delete_phrase(self):
        row = self.list_phrases.currentRow()
        if row >= 0:
            self.list_phrases.takeItem(row)
            self.save_config()

    def on_deactivated(self):
        """当用户切出此插件时，为安全起见自动暂停热键钩子"""
        if self.worker.is_running:
            self.worker.stop_listening()
            self.btn_toggle_listen.setText("开启全局热键监听")
            self.btn_toggle_listen.setStyleSheet("")
            self.lbl_status_badge.setText("状态: 切换离开，已自动挂起监听")
            self.lbl_status_badge.setStyleSheet("color: #71717a; font-weight: bold; font-size: 14px;")
