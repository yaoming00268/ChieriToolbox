"""
全能文本翻译 - UI 界面
提供多语言双向互译、免配置公开端点以及大模型/Ollama 自定义配置支持。
"""

import time
from typing import Optional
from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTextEdit, QDialog, QLineEdit, QFormLayout,
    QApplication, QSplitter
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.icons import get_icon, get_pixmap
from .engine import LANGUAGE_CODES, TranslationWorker


class TranslatorConfigDialog(QDialog):
    """大模型与 API 配置对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("翻译大模型与 API 端点配置")
        self.setMinimumWidth(480)
        self.resize(520, 440)
        self.config = ConfigManager()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        # OpenAI 兼容设置
        lbl_sec1 = QLabel("<b>OpenAI 兼容接口配置 (DeepSeek / Kimi / OpenAI 等)</b>")
        lbl_sec1.setStyleSheet("color: #3b82f6;")
        form.addRow(lbl_sec1)

        self.le_openai_url = QLineEdit()
        self.le_openai_url.setPlaceholderText("https://api.openai.com/v1 或 https://api.deepseek.com")
        self.le_openai_url.setText(self.config.get("trans_openai_base_url", "https://api.deepseek.com"))
        form.addRow("Base URL:", self.le_openai_url)

        self.le_openai_key = QLineEdit()
        self.le_openai_key.setEchoMode(QLineEdit.Password)
        self.le_openai_key.setPlaceholderText("sk-...")
        self.le_openai_key.setText(self.config.get("trans_openai_api_key", ""))
        form.addRow("API Key:", self.le_openai_key)

        self.le_openai_model = QLineEdit()
        self.le_openai_model.setPlaceholderText("deepseek-chat 或 gpt-4o-mini")
        self.le_openai_model.setText(self.config.get("trans_openai_model", "deepseek-chat"))
        form.addRow("模型名称:", self.le_openai_model)

        # Ollama 设置
        lbl_sec2 = QLabel("<b>本地 Ollama 大模型端点</b>")
        lbl_sec2.setStyleSheet("color: #10b981; margin-top: 10px;")
        form.addRow(lbl_sec2)

        self.le_ollama_host = QLineEdit()
        self.le_ollama_host.setPlaceholderText("http://localhost:11434")
        self.le_ollama_host.setText(self.config.get("trans_ollama_host", "http://localhost:11434"))
        form.addRow("Ollama Host:", self.le_ollama_host)

        self.le_ollama_model = QLineEdit()
        self.le_ollama_model.setPlaceholderText("qwen2.5:7b 或 llama3")
        self.le_ollama_model.setText(self.config.get("trans_ollama_model", "qwen2.5:7b"))
        form.addRow("Ollama 模型:", self.le_ollama_model)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("保存配置")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save_config)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

    def _save_config(self):
        self.config.set("trans_openai_base_url", self.le_openai_url.text().strip())
        self.config.set("trans_openai_api_key", self.le_openai_key.text().strip())
        self.config.set("trans_openai_model", self.le_openai_model.text().strip())
        self.config.set("trans_ollama_host", self.le_ollama_host.text().strip())
        self.config.set("trans_ollama_model", self.le_ollama_model.text().strip())
        self.accept()


class TranslatorWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.worker: Optional[TranslationWorker] = None
        self._start_time: float = 0.0

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(14)

        # 1. 顶部标题栏与引擎选择
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("languages", color="#10b981", size=26))
        header_layout.addWidget(icon_lbl)

        title_lbl = QLabel("全能文本翻译")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_lbl)

        badge_lbl = QLabel("多引擎 · 免配置/大模型")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #10b981; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header_layout.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header_layout.addStretch()

        # 翻译引擎切换
        header_layout.addWidget(QLabel("翻译引擎:"))
        self.combo_engine = QComboBox()
        self.combo_engine.addItem("免配置公开引擎 (极速直连)", "public")
        self.combo_engine.addItem("自定义 OpenAI 兼容 API", "openai")
        self.combo_engine.addItem("本地 Ollama 大模型", "ollama")
        header_layout.addWidget(self.combo_engine)

        self.btn_config = QPushButton()
        self.btn_config.setObjectName("flatIconBtn")
        self.btn_config.setIcon(get_icon("settings", size=16))
        self.btn_config.setToolTip("配置 API Key 与模型端点")
        self.btn_config.clicked.connect(self._open_config_dialog)
        header_layout.addWidget(self.btn_config)

        layout.addLayout(header_layout)

        # 2. 语言选择工具条
        lang_bar = QHBoxLayout()
        lang_bar.setSpacing(10)

        self.combo_src = QComboBox()
        self.combo_src.addItems(list(LANGUAGE_CODES.keys()))
        self.combo_src.setCurrentText("自动检测")
        self.combo_src.setFixedWidth(130)
        lang_bar.addWidget(self.combo_src)

        self.btn_swap = QPushButton()
        self.btn_swap.setObjectName("flatIconBtn")
        self.btn_swap.setIcon(get_icon("refresh", size=16))
        self.btn_swap.setToolTip("互换源语言与目标语言")
        self.btn_swap.clicked.connect(self._swap_languages)
        lang_bar.addWidget(self.btn_swap)

        self.combo_tgt = QComboBox()
        targets = [k for k in LANGUAGE_CODES.keys() if k != "自动检测"]
        self.combo_tgt.addItems(targets)
        self.combo_tgt.setCurrentText("中文 (简体)")
        self.combo_tgt.setFixedWidth(130)
        lang_bar.addWidget(self.combo_tgt)

        lang_bar.addStretch()

        self.btn_clear_src = QPushButton("清空输入")
        self.btn_clear_src.setIcon(get_icon("clear", size=14))
        self.btn_clear_src.clicked.connect(self._clear_input)
        lang_bar.addWidget(self.btn_clear_src)

        self.btn_copy_res = QPushButton("复制译文")
        self.btn_copy_res.setIcon(get_icon("copy", size=14))
        self.btn_copy_res.clicked.connect(self._copy_result)
        lang_bar.addWidget(self.btn_copy_res)

        layout.addLayout(lang_bar)

        # 3. 核心双栏文本框 (QSplitter 水平分割)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # 源文本框容器
        src_container = QWidget()
        src_vbox = QVBoxLayout(src_container)
        src_vbox.setContentsMargins(0, 0, 0, 0)
        src_vbox.setSpacing(6)

        src_header = QHBoxLayout()
        src_lbl = QLabel("<b>输入原文</b> (支持 Ctrl+Enter 快捷翻译)")
        src_header.addWidget(src_lbl)
        src_header.addStretch()
        self.lbl_src_count = QLabel("0 字符")
        self.lbl_src_count.setStyleSheet("color: #94a3b8; font-size: 11px;")
        src_header.addWidget(self.lbl_src_count)
        src_vbox.addLayout(src_header)

        self.te_source = QTextEdit()
        self.te_source.setPlaceholderText("在此键入或粘贴待翻译的文字，按下 Ctrl+Enter 或点击下方按钮翻译...")
        self.te_source.textChanged.connect(self._on_source_text_changed)
        self.te_source.installEventFilter(self)
        src_vbox.addWidget(self.te_source, 1)

        splitter.addWidget(src_container)

        # 目标译文框容器
        tgt_container = QWidget()
        tgt_vbox = QVBoxLayout(tgt_container)
        tgt_vbox.setContentsMargins(0, 0, 0, 0)
        tgt_vbox.setSpacing(6)

        tgt_header = QHBoxLayout()
        tgt_lbl = QLabel("<b>翻译结果</b>")
        tgt_header.addWidget(tgt_lbl)
        tgt_header.addStretch()
        self.lbl_tgt_count = QLabel("0 字符")
        self.lbl_tgt_count.setStyleSheet("color: #94a3b8; font-size: 11px;")
        tgt_header.addWidget(self.lbl_tgt_count)
        tgt_vbox.addLayout(tgt_header)

        self.te_target = QTextEdit()
        self.te_target.setReadOnly(True)
        self.te_target.setPlaceholderText("翻译结果将呈现于此...")
        tgt_vbox.addWidget(self.te_target, 1)

        splitter.addWidget(tgt_container)
        splitter.setSizes([450, 450])
        layout.addWidget(splitter, 1)

        # 4. 底部执行控制与状态
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(12)

        self.btn_translate = QPushButton("立即翻译")
        self.btn_translate.setObjectName("primaryBtn")
        self.btn_translate.setIcon(get_icon("languages", size=16))
        self.btn_translate.setFixedHeight(36)
        self.btn_translate.setFixedWidth(140)
        self.btn_translate.clicked.connect(self._do_translate)
        bottom_bar.addWidget(self.btn_translate)

        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 12px;")
        bottom_bar.addWidget(self.lbl_status, 1)

        layout.addLayout(bottom_bar)

    def eventFilter(self, watched, event):
        if watched == self.te_source and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and (event.modifiers() & Qt.ControlModifier):
                self._do_translate()
                return True
        return super().eventFilter(watched, event)

    def _open_config_dialog(self):
        dlg = TranslatorConfigDialog(self)
        dlg.exec()

    def _on_source_text_changed(self):
        cnt = len(self.te_source.toPlainText())
        self.lbl_src_count.setText(f"{cnt} 字符")

    def _clear_input(self):
        self.te_source.clear()
        self.te_target.clear()
        self.lbl_tgt_count.setText("0 字符")
        self.lbl_status.setText("已清空")

    def _copy_result(self):
        res = self.te_target.toPlainText().strip()
        if res:
            cb = QApplication.clipboard()
            cb.setText(res)
            self.lbl_status.setText("已将翻译结果复制至剪贴板！")

    def _swap_languages(self):
        src_text = self.combo_src.currentText()
        tgt_text = self.combo_tgt.currentText()
        if src_text == "自动检测":
            return

        # 交换文字
        s_val = self.te_source.toPlainText()
        t_val = self.te_target.toPlainText()
        self.te_source.setPlainText(t_val)
        self.te_target.setPlainText(s_val)

        # 交换下拉选项
        self.combo_src.setCurrentText(tgt_text)
        self.combo_tgt.setCurrentText(src_text)

    def _do_translate(self):
        text = self.te_source.toPlainText().strip()
        if not text:
            self.lbl_status.setText("请输入需要翻译的内容。")
            return

        engine_type = self.combo_engine.currentData()
        src_lang = self.combo_src.currentText()
        tgt_lang = self.combo_tgt.currentText()

        self.btn_translate.setEnabled(False)
        self.lbl_status.setText("正在翻译中...")
        self._start_time = time.time()

        cfg = {
            "openai_base_url": self.config.get("trans_openai_base_url", "https://api.deepseek.com"),
            "openai_api_key": self.config.get("trans_openai_api_key", ""),
            "openai_model": self.config.get("trans_openai_model", "deepseek-chat"),
            "ollama_host": self.config.get("trans_ollama_host", "http://localhost:11434"),
            "ollama_model": self.config.get("trans_ollama_model", "qwen2.5:7b")
        }

        self.worker = TranslationWorker(
            text=text,
            source_lang=src_lang,
            target_lang=tgt_lang,
            engine_type=engine_type,
            config=cfg
        )
        self.worker.finished.connect(self._on_translate_finished)
        self.worker.start()

    def _on_translate_finished(self, success: bool, result: str):
        self.btn_translate.setEnabled(True)
        elapsed = time.time() - self._start_time
        if success:
            self.te_target.setPlainText(result)
            self.lbl_tgt_count.setText(f"{len(result)} 字符")
            self.lbl_status.setText(f"翻译完成！耗时: {elapsed:.2f} 秒")
        else:
            self.lbl_status.setText(f"翻译失败: {result}")

    def handle_initial_paths(self, paths: list):
        if paths:
            joined = " ".join([str(p) for p in paths])
            self.te_source.setPlainText(joined)

    def load_settings(self):
        cfg = self.config.get_plugin_config("translator", {})
        eng_idx = cfg.get("engine_idx", 0)
        if 0 <= eng_idx < self.combo_engine.count():
            self.combo_engine.setCurrentIndex(eng_idx)
        src_idx = cfg.get("src_idx", 0)
        if 0 <= src_idx < self.combo_src.count():
            self.combo_src.setCurrentIndex(src_idx)
        tgt_idx = cfg.get("tgt_idx", 0)
        if 0 <= tgt_idx < self.combo_tgt.count():
            self.combo_tgt.setCurrentIndex(tgt_idx)

    def save_settings(self):
        cfg = {
            "engine_idx": self.combo_engine.currentIndex(),
            "src_idx": self.combo_src.currentIndex(),
            "tgt_idx": self.combo_tgt.currentIndex()
        }
        self.config.set_plugin_config("translator", cfg)
