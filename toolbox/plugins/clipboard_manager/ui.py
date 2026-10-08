"""
剪贴板管理器 (Clipboard Manager) - UI 界面
集成系统剪贴板监听、无限历史看板、实时敏感信息脱敏与常用短语秒发。
"""

import time
from typing import Optional
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QClipboard
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QCheckBox,
    QTabWidget, QTextEdit, QMessageBox, QFrame, QInputDialog
)

from toolbox.ui.icons import get_icon, get_pixmap
from .engine import ClipboardHistoryManager, ClipboardHistoryItem


class ClipboardItemCard(QFrame):
    """单个剪贴板条目可视化展示卡片"""
    def __init__(self, item: ClipboardHistoryItem, desensitize: bool, on_copy: callable, on_delete: callable, parent=None):
        super().__init__(parent)
        self.item = item
        self.on_copy = on_copy
        self.on_delete = on_delete

        self.setStyleSheet("""
            QFrame {
                background: rgba(128, 128, 128, 0.06);
                border: 1px solid rgba(128, 128, 128, 0.14);
                border-radius: 8px;
            }
            QFrame:hover {
                background: rgba(59, 130, 246, 0.10);
                border: 1px solid #3b82f6;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # 类型标识或缩略图
        self.lbl_thumb = QLabel()
        if item.item_type == "image" and item.preview_pixmap:
            self.lbl_thumb.setPixmap(item.preview_pixmap)
        else:
            self.lbl_thumb.setPixmap(get_pixmap("clipboard", size=20))
        layout.addWidget(self.lbl_thumb)

        # 文本信息
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)

        display_txt = item.get_display_text(desensitize)
        # 单行精炼展示
        summary = display_txt.splitlines()[0] if display_txt.splitlines() else display_txt
        if len(summary) > 75:
            summary = summary[:75] + "..."

        self.lbl_text = QLabel(summary)
        self.lbl_text.setStyleSheet("font-size: 13px; font-weight: 500;")
        text_layout.addWidget(self.lbl_text)

        # 底部元数据: 时间 + 敏感标签
        meta_row = QHBoxLayout()
        time_str = time.strftime("%H:%M:%S", time.localtime(item.timestamp))
        lbl_meta = QLabel(f"记录于 {time_str} · {len(item.content)} 字符")
        lbl_meta.setStyleSheet("color: #64748b; font-size: 11px;")
        meta_row.addWidget(lbl_meta)

        if item.has_sensitive:
            tags = "/".join(item.sensitive_types)
            lbl_tag = QLabel(f"敏感信息打码 [{tags}]")
            lbl_tag.setStyleSheet("color: #ef4444; font-size: 10px; font-weight: bold; background: rgba(239, 68, 68, 0.1); padding: 1px 4px; border-radius: 3px;")
            meta_row.addWidget(lbl_tag)

        meta_row.addStretch()
        text_layout.addLayout(meta_row)
        layout.addLayout(text_layout, 1)

        # 操作按钮
        btn_copy = QPushButton("复制")
        btn_copy.setFixedSize(50, 26)
        btn_copy.setStyleSheet("font-size: 11px;")
        btn_copy.clicked.connect(lambda: self.on_copy(self.item))
        layout.addWidget(btn_copy)

        btn_pin = QPushButton("置顶" if not item.is_pinned else "已置顶")
        btn_pin.setFixedSize(55, 26)
        btn_pin.setStyleSheet(f"font-size: 11px; {'background: #2563eb; color: white;' if item.is_pinned else ''}")
        btn_pin.clicked.connect(self._toggle_pin)
        layout.addWidget(btn_pin)

        btn_del = QPushButton("删除")
        btn_del.setFixedSize(50, 26)
        btn_del.setStyleSheet("font-size: 11px; color: #ef4444;")
        btn_del.clicked.connect(lambda: self.on_delete(self.item))
        layout.addWidget(btn_del)

    def _toggle_pin(self):
        self.item.is_pinned = not self.item.is_pinned
        # 刷新视图
        top_view = self.window()
        if hasattr(top_view, "_refresh_history_list"):
            top_view._refresh_history_list()


class ClipboardManagerWidget(QWidget):
    """剪贴板管理器主界面"""
    _history_manager = ClipboardHistoryManager(max_items=100)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mgr = self._history_manager
        self.desensitize = True

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # 头部说明
        top_bar = QHBoxLayout()
        tip = QLabel("<b>千绘莉无限剪贴板历史看板</b><br><span style='color:#64748b; font-size:12px;'>监听历史剪贴、常用短语秒发，智能识别手机号/身份证/Token并打码保护。</span>")
        tip.setWordWrap(True)
        top_bar.addWidget(tip, 1)

        self.btn_clear = QPushButton("清空历史")
        self.btn_clear.clicked.connect(self._clear_history)
        top_bar.addWidget(self.btn_clear)
        main_layout.addLayout(top_bar)

        # 选项卡
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_history_page(), get_icon("clipboard", size=14), "剪贴板历史")
        self.tabs.addTab(self._build_snippets_page(), get_icon("sparkles", size=14), "常用短语看板")
        main_layout.addWidget(self.tabs, 1)

        # 监听系统剪贴板变动
        self._setup_clipboard_listener()
        self.destroyed.connect(self.cleanup)
        self._refresh_history_list()

    def _setup_clipboard_listener(self):
        cb = QGuiApplication.clipboard()
        cb.dataChanged.connect(self._on_clipboard_changed)

    def cleanup(self):
        """断开全局系统剪贴板监听信号，杜绝失效回调与 C++ 析构后访问异常"""
        if getattr(self, "_is_cleaned_up", False):
            return
        self._is_cleaned_up = True
        try:
            cb = QGuiApplication.clipboard()
            cb.dataChanged.disconnect(self._on_clipboard_changed)
        except (RuntimeError, Exception):
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def _on_clipboard_changed(self):
        cb = QGuiApplication.clipboard()
        mime = cb.mimeData()
        if mime.hasText():
            text = cb.text()
            item = self.mgr.add_text(text)
            if item:
                self._refresh_history_list()
        elif mime.hasImage():
            pix = cb.pixmap()
            if not pix.isNull():
                item = self.mgr.add_image(pix)
                if item:
                    self._refresh_history_list()

    def _build_history_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        filter_row = QHBoxLayout()
        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText("过滤搜索剪贴板历史内容...")
        self.le_search.textChanged.connect(self._refresh_history_list)
        filter_row.addWidget(self.le_search, 1)

        self.cb_desensitize = QCheckBox("隐私保护 (敏感信息自动打码)")
        self.cb_desensitize.setChecked(True)
        self.cb_desensitize.toggled.connect(self._toggle_desensitize)
        filter_row.addWidget(self.cb_desensitize)
        layout.addLayout(filter_row)

        self.list_history = QListWidget()
        self.list_history.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
            }
            QListWidget::item {
                margin-bottom: 4px;
            }
        """)
        self.list_history.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_history, 1)
        return w

    def _build_snippets_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        row_top = QHBoxLayout()
        row_top.addWidget(QLabel("<b>预置常用短语与代码段</b> (双击或点击右侧复制)"))
        btn_add = QPushButton("新建短语")
        btn_add.clicked.connect(self._add_snippet)
        row_top.addStretch()
        row_top.addWidget(btn_add)
        layout.addLayout(row_top)

        self.list_snippets = QListWidget()
        self._refresh_snippets_list()
        layout.addWidget(self.list_snippets, 1)
        return w

    def _refresh_snippets_list(self):
        self.list_snippets.clear()
        for snip in self.mgr.pinned_snippets:
            item = QListWidgetItem()
            card = QFrame()
            card.setStyleSheet("background: rgba(128, 128, 128, 0.06); border-radius: 6px; padding: 6px;")
            l = QHBoxLayout(card)
            l.addWidget(QLabel(f"<b>{snip['title']}</b>: {snip['content'][:40]}..."), 1)
            btn = QPushButton("复制")
            btn.clicked.connect(lambda checked=False, s=snip['content']: self._copy_snippet_content(s))
            l.addWidget(btn)
            item.setSizeHint(card.sizeHint())
            self.list_snippets.addItem(item)
            self.list_snippets.setItemWidget(item, card)

    def _add_snippet(self):
        title, ok1 = QInputDialog.getText(self, "新建常用短语", "输入短语标题:")
        if not ok1 or not title:
            return
        content, ok2 = QInputDialog.getMultiLineText(self, "新建常用短语", "输入短语正文内容:")
        if not ok2 or not content:
            return
        self.mgr.pinned_snippets.append({"title": title.strip(), "content": content.strip()})
        self._refresh_snippets_list()

    def _copy_snippet_content(self, text: str):
        cb = QGuiApplication.clipboard()
        cb.setText(text)
        QMessageBox.information(self, "复制成功", "短语已复制到剪贴板！")

    def _toggle_desensitize(self, checked: bool):
        self.desensitize = checked
        self._refresh_history_list()

    def _refresh_history_list(self):
        self.list_history.clear()
        q = self.le_search.text().strip().lower()
        for item in self.mgr.items:
            if q and q not in item.content.lower():
                continue
            lw_item = QListWidgetItem()
            lw_item.setData(Qt.UserRole, item)
            card = ClipboardItemCard(
                item,
                desensitize=self.desensitize,
                on_copy=self._copy_item,
                on_delete=self._delete_item,
                parent=self.list_history
            )
            lw_item.setSizeHint(card.sizeHint())
            self.list_history.addItem(lw_item)
            self.list_history.setItemWidget(lw_item, card)

    def _copy_item(self, item: ClipboardHistoryItem, notify: bool = False):
        cb = QGuiApplication.clipboard()
        if item.item_type == "text":
            cb.setText(item.content)
            top = self.window()
            if hasattr(top, "status_bar") and top.status_bar:
                top.status_bar.showMessage("已复制到系统剪贴板", 2000)
            elif notify:
                QMessageBox.information(self, "已复制", "条目已写入剪贴板。")
        elif item.item_type == "image":
            pix = getattr(item, "full_pixmap", None) or item.preview_pixmap
            if pix and not pix.isNull():
                cb.setPixmap(pix)
                top = self.window()
                if hasattr(top, "status_bar") and top.status_bar:
                    top.status_bar.showMessage("图片已复制到系统剪贴板", 2000)
                elif notify:
                    QMessageBox.information(self, "已复制", "图片已写入剪贴板。")

    def _delete_item(self, item: ClipboardHistoryItem):
        if item in self.mgr.items:
            self.mgr.items.remove(item)
            self._refresh_history_list()

    def _on_item_double_clicked(self, lw_item: QListWidgetItem):
        item = lw_item.data(Qt.UserRole)
        if not item:
            card = self.list_history.itemWidget(lw_item)
            if card and hasattr(card, "item"):
                item = card.item
        if item:
            self._copy_item(item)

    def _clear_history(self):
        self.mgr.clear()
        self._refresh_history_list()

    def load_settings(self):
        from toolbox.core.config_manager import ConfigManager
        cfg = ConfigManager().get_plugin_config("clipboard_manager")
        if "desensitize" in cfg:
            self.desensitize = bool(cfg.get("desensitize", True))
            if hasattr(self, "cb_desensitize"):
                self.cb_desensitize.setChecked(self.desensitize)

    def save_settings(self):
        from toolbox.core.config_manager import ConfigManager
        ConfigManager().set_plugin_config("clipboard_manager", {
            "desensitize": getattr(self, "desensitize", True)
        })
