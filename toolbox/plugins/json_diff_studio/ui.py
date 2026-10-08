"""
JSON 对比与分析工坊 (JSON Diff Studio) - UI 界面
提供双栏高精对比、同步滚动、JSON 美化/压缩/校验、语法树折叠、以及零依赖 JSONPath 交互查询。
"""

import os
import json
from typing import Optional, Any, List, Dict
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QGuiApplication, QTextCharFormat, QColor, QFont,
    QTextCursor, QBrush, QTextBlockFormat
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QTreeWidget, QTreeWidgetItem, QSplitter,
    QCheckBox, QComboBox, QLineEdit, QFileDialog, QTabWidget,
    QFrame, QMessageBox, QHeaderView
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.icons import get_icon, get_pixmap
from .engine import (
    compute_diff, format_json_str, minify_json_str,
    validate_json_str, evaluate_jsonpath
)


class JsonDiffStudioWidget(QWidget):
    PLUGIN_ID = "json_diff_studio"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self._is_syncing_scroll = False
        self._in_diff_mode = False
        self._raw_left = ""
        self._raw_right = ""

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 14, 18, 14)
        root_layout.setSpacing(10)

        # 1. 顶部 Header
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("git-compare", color="#3b82f6", size=26))
        header.addWidget(icon_lbl)

        title_lbl = QLabel("JSON 对比与分析工坊")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title_lbl)

        badge_lbl = QLabel("双栏高精对比 · 语法美化 · 结构折叠树 · JSONPath")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header.addStretch()
        root_layout.addLayout(header)

        # 2. 主功能选项卡
        self.tabs = QTabWidget()
        root_layout.addWidget(self.tabs, 1)

        # Tab 1: 双栏高精对比
        self.tab_diff = QWidget()
        self._setup_diff_tab()
        self.tabs.addTab(self.tab_diff, get_icon("git-compare", size=14), "双栏高精对比")

        # Tab 2: JSON 语法树与折叠
        self.tab_tree = QWidget()
        self._setup_tree_tab()
        self.tabs.addTab(self.tab_tree, get_icon("sliders", size=14), "语法树与结构折叠")

        # Tab 3: JSONPath 查询探索器
        self.tab_path = QWidget()
        self._setup_path_tab()
        self.tabs.addTab(self.tab_path, get_icon("search", size=14), "JSONPath 提取器")

    # =========================================================================
    # Tab 1: 双栏高精对比构建与逻辑
    # =========================================================================
    def _setup_diff_tab(self):
        layout = QVBoxLayout(self.tab_diff)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 工具栏
        tb_layout = QHBoxLayout()
        tb_layout.setSpacing(8)

        self.btn_run_diff = QPushButton("执行双栏对比")
        self.btn_run_diff.setObjectName("primaryBtn")
        self.btn_run_diff.setIcon(get_icon("git-compare", color="#ffffff", size=13))
        self.btn_run_diff.clicked.connect(self._run_diff)
        tb_layout.addWidget(self.btn_run_diff)

        self.btn_format_both = QPushButton("两边一键美化")
        self.btn_format_both.setIcon(get_icon("sparkles", size=13))
        self.btn_format_both.clicked.connect(self._format_both)
        tb_layout.addWidget(self.btn_format_both)

        self.btn_minify_both = QPushButton("两边一键压缩")
        self.btn_minify_both.setIcon(get_icon("scissors", size=13))
        self.btn_minify_both.clicked.connect(self._minify_both)
        tb_layout.addWidget(self.btn_minify_both)

        self.btn_swap = QPushButton("左右交换")
        self.btn_swap.setIcon(get_icon("refresh", size=13))
        self.btn_swap.clicked.connect(self._swap_panes)
        tb_layout.addWidget(self.btn_swap)

        self.btn_open_left = QPushButton("导入左侧...")
        self.btn_open_left.setIcon(get_icon("folder", size=13))
        self.btn_open_left.clicked.connect(lambda: self._open_file(self.edit_left))
        tb_layout.addWidget(self.btn_open_left)

        self.btn_open_right = QPushButton("导入右侧...")
        self.btn_open_right.setIcon(get_icon("folder", size=13))
        self.btn_open_right.clicked.connect(lambda: self._open_file(self.edit_right))
        tb_layout.addWidget(self.btn_open_right)

        self.btn_clear_diff = QPushButton("清空")
        self.btn_clear_diff.setIcon(get_icon("trash", size=13))
        self.btn_clear_diff.clicked.connect(self._clear_diff)
        tb_layout.addWidget(self.btn_clear_diff)

        tb_layout.addStretch()

        self.cb_sync_scroll = QCheckBox("同步滚动")
        self.cb_sync_scroll.setChecked(True)
        tb_layout.addWidget(self.cb_sync_scroll)

        layout.addLayout(tb_layout)

        # 双栏文本区域
        splitter = QSplitter(Qt.Horizontal)

        # 左栏
        left_box = QWidget()
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        lh_layout = QHBoxLayout()
        lh_lbl = QLabel("<b>左侧 (Original / 原始基准)</b>")
        lh_layout.addWidget(lh_lbl)
        lh_layout.addStretch()
        btn_copy_l = QPushButton("复制")
        btn_copy_l.setMaximumWidth(60)
        btn_copy_l.clicked.connect(self._copy_left)
        lh_layout.addWidget(btn_copy_l)
        left_layout.addLayout(lh_layout)

        self.edit_left = QPlainTextEdit()
        self.edit_left.setPlaceholderText("在此粘贴左侧原始 JSON 或文本...")
        self.edit_left.setFont(QFont("Consolas", 10))
        self.edit_left.textChanged.connect(self._on_left_text_changed)
        left_layout.addWidget(self.edit_left)
        splitter.addWidget(left_box)

        # 右栏
        right_box = QWidget()
        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        rh_layout = QHBoxLayout()
        rh_lbl = QLabel("<b>右侧 (Modified / 修改比对)</b>")
        rh_layout.addWidget(rh_lbl)
        rh_layout.addStretch()
        btn_copy_r = QPushButton("复制")
        btn_copy_r.setMaximumWidth(60)
        btn_copy_r.clicked.connect(self._copy_right)
        rh_layout.addWidget(btn_copy_r)
        right_layout.addLayout(rh_layout)

        self.edit_right = QPlainTextEdit()
        self.edit_right.setPlaceholderText("在此粘贴右侧修改后 JSON 或文本...")
        self.edit_right.setFont(QFont("Consolas", 10))
        self.edit_right.textChanged.connect(self._on_right_text_changed)
        right_layout.addWidget(self.edit_right)
        splitter.addWidget(right_box)

        splitter.setSizes([500, 500])
        layout.addWidget(splitter, 1)

        # 绑定同步滚动
        self.edit_left.verticalScrollBar().valueChanged.connect(self._sync_scroll_left_to_right)
        self.edit_right.verticalScrollBar().valueChanged.connect(self._sync_scroll_right_to_left)

        # 底部指标栏
        bot_layout = QHBoxLayout()
        self.lbl_diff_stats = QLabel("就绪 · 请输入两段文本并点击【执行双栏对比】")
        self.lbl_diff_stats.setStyleSheet("color: #64748b; font-size: 12px;")
        bot_layout.addWidget(self.lbl_diff_stats)
        bot_layout.addStretch()
        layout.addLayout(bot_layout)

    def _on_left_text_changed(self):
        if self._in_diff_mode:
            self._in_diff_mode = False
            self.lbl_diff_stats.setText("左侧文本已变更，请点击【执行双栏对比】重新比对")
        self._raw_left = self.edit_left.toPlainText()

    def _on_right_text_changed(self):
        if self._in_diff_mode:
            self._in_diff_mode = False
            self.lbl_diff_stats.setText("右侧文本已变更，请点击【执行双栏对比】重新比对")
        self._raw_right = self.edit_right.toPlainText()

    def _copy_left(self):
        text = self._raw_left if (self._in_diff_mode and getattr(self, "_raw_left", None)) else self.edit_left.toPlainText()
        QGuiApplication.clipboard().setText(text)

    def _copy_right(self):
        text = self._raw_right if (self._in_diff_mode and getattr(self, "_raw_right", None)) else self.edit_right.toPlainText()
        QGuiApplication.clipboard().setText(text)

    def _sync_scroll_left_to_right(self, val):
        if self.cb_sync_scroll.isChecked() and not self._is_syncing_scroll:
            self._is_syncing_scroll = True
            self.edit_right.verticalScrollBar().setValue(val)
            self._is_syncing_scroll = False

    def _sync_scroll_right_to_left(self, val):
        if self.cb_sync_scroll.isChecked() and not self._is_syncing_scroll:
            self._is_syncing_scroll = True
            self.edit_left.verticalScrollBar().setValue(val)
            self._is_syncing_scroll = False

    def _format_both(self):
        ok1, f1, _ = format_json_str(self.edit_left.toPlainText())
        if ok1:
            self.edit_left.setPlainText(f1)
            self._raw_left = f1
        ok2, f2, _ = format_json_str(self.edit_right.toPlainText())
        if ok2:
            self.edit_right.setPlainText(f2)
            self._raw_right = f2
        self._in_diff_mode = False
        self._run_diff()

    def _minify_both(self):
        ok1, m1, _ = minify_json_str(self.edit_left.toPlainText())
        if ok1:
            self.edit_left.setPlainText(m1)
            self._raw_left = m1
        ok2, m2, _ = minify_json_str(self.edit_right.toPlainText())
        if ok2:
            self.edit_right.setPlainText(m2)
            self._raw_right = m2
        self._in_diff_mode = False
        self._run_diff()

    def _swap_panes(self):
        t1 = self._raw_left if (self._in_diff_mode and self._raw_left) else self.edit_left.toPlainText()
        t2 = self._raw_right if (self._in_diff_mode and self._raw_right) else self.edit_right.toPlainText()
        self._raw_left, self._raw_right = t2, t1
        self._in_diff_mode = False
        self.edit_left.setPlainText(t2)
        self.edit_right.setPlainText(t1)
        self._run_diff()

    def _open_file(self, target_editor: QPlainTextEdit):
        path, _ = QFileDialog.getOpenFileName(self, "选择文本或 JSON 文件", "", "文本/JSON (*.json *.txt *.js *.py *.xml *.log);;所有文件 (*.*)")
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                    target_editor.setPlainText(content)
                    if target_editor is self.edit_left:
                        self._raw_left = content
                    else:
                        self._raw_right = content
                    self._in_diff_mode = False
            except Exception as e:
                QMessageBox.warning(self, "读取失败", f"无法打开文件: {e}")

    def _clear_diff(self):
        self._in_diff_mode = False
        self._raw_left = ""
        self._raw_right = ""
        self.edit_left.clear()
        self.edit_right.clear()
        self.lbl_diff_stats.setText("内容已清空")

    def _run_diff(self):
        t1 = getattr(self, "_raw_left", None)
        if t1 is None or not self._in_diff_mode:
            t1 = self.edit_left.toPlainText()
            self._raw_left = t1
        t2 = getattr(self, "_raw_right", None)
        if t2 is None or not self._in_diff_mode:
            t2 = self.edit_right.toPlainText()
            self._raw_right = t2

        diff_res = compute_diff(t1, t2)
        stats = diff_res["stats"]

        # 构建高亮显示
        left_rows = diff_res["left_rows"]
        right_rows = diff_res["right_rows"]

        self._in_diff_mode = True
        self._apply_diff_highlight(self.edit_left, left_rows)
        self._apply_diff_highlight(self.edit_right, right_rows)

        summary = (
            f"对比完成: <span style='color:#10b981; font-weight:bold;'>+{stats['additions']} 行新增</span> | "
            f"<span style='color:#ef4444; font-weight:bold;'>-{stats['deletions']} 行删除</span> | "
            f"<span style='color:#f59e0b; font-weight:bold;'>~{stats['modifications']} 行修改</span> | "
            f"{stats['equals']} 行对齐一致"
        )
        self.lbl_diff_stats.setText(summary)

    def _apply_diff_highlight(self, editor: QPlainTextEdit, rows: List[Dict[str, Any]]):
        """将对齐的 diff 结果格式化并带字符级高亮颜色呈现在文本编辑器中"""
        editor.blockSignals(True)
        cursor = editor.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.removeSelectedText()

        fmt_insert = QTextBlockFormat()
        fmt_insert.setBackground(QColor(16, 185, 129, 45))

        fmt_delete = QTextBlockFormat()
        fmt_delete.setBackground(QColor(239, 68, 68, 45))

        fmt_replace = QTextBlockFormat()
        fmt_replace.setBackground(QColor(245, 158, 11, 45))

        fmt_equal = QTextBlockFormat()
        fmt_equal.setBackground(Qt.transparent)

        char_fmt = QTextCharFormat()
        char_fmt.setFont(QFont("Consolas", 10))

        fmt_inline_insert = QTextCharFormat()
        fmt_inline_insert.setFont(QFont("Consolas", 10))
        fmt_inline_insert.setBackground(QColor(16, 185, 129, 130))
        fmt_inline_insert.setFontWeight(QFont.Bold)

        fmt_inline_delete = QTextCharFormat()
        fmt_inline_delete.setFont(QFont("Consolas", 10))
        fmt_inline_delete.setBackground(QColor(239, 68, 68, 130))
        fmt_inline_delete.setFontWeight(QFont.Bold)

        fmt_inline_replace = QTextCharFormat()
        fmt_inline_replace.setFont(QFont("Consolas", 10))
        fmt_inline_replace.setBackground(QColor(245, 158, 11, 140))
        fmt_inline_replace.setFontWeight(QFont.Bold)

        for idx, row in enumerate(rows):
            rtype = row["type"]
            text = row["text"]
            if idx > 0:
                cursor.insertBlock()

            if rtype == "insert":
                cursor.setBlockFormat(fmt_insert)
            elif rtype == "delete":
                cursor.setBlockFormat(fmt_delete)
            elif rtype == "replace":
                cursor.setBlockFormat(fmt_replace)
            else:
                cursor.setBlockFormat(fmt_equal)

            inline_spans = row.get("inline", [])
            if inline_spans and rtype in ("replace", "delete", "insert"):
                # 排序并逐段应用字符级差异高亮
                spans = sorted(inline_spans, key=lambda s: s[0])
                curr_pos = 0
                active_fmt = (
                    fmt_inline_insert if rtype == "insert"
                    else (fmt_inline_delete if rtype == "delete" else fmt_inline_replace)
                )
                for start, end in spans:
                    if start > curr_pos:
                        cursor.insertText(text[curr_pos:start], char_fmt)
                    cursor.insertText(text[start:end], active_fmt)
                    curr_pos = max(curr_pos, end)
                if curr_pos < len(text):
                    cursor.insertText(text[curr_pos:], char_fmt)
            else:
                cursor.insertText(text, char_fmt)

        editor.blockSignals(False)

    # =========================================================================
    # Tab 2: 语法树与结构折叠构建与逻辑
    # =========================================================================
    def _setup_tree_tab(self):
        layout = QVBoxLayout(self.tab_tree)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        tb_layout = QHBoxLayout()
        self.btn_parse_tree = QPushButton("解析构建结构树")
        self.btn_parse_tree.setObjectName("primaryBtn")
        self.btn_parse_tree.setIcon(get_icon("sliders", color="#ffffff", size=13))
        self.btn_parse_tree.clicked.connect(self._build_tree_from_text)
        tb_layout.addWidget(self.btn_parse_tree)

        btn_expand_all = QPushButton("全部展开")
        btn_expand_all.clicked.connect(lambda: self.tree_view.expandAll())
        tb_layout.addWidget(btn_expand_all)

        btn_collapse_all = QPushButton("全部折叠")
        btn_collapse_all.clicked.connect(lambda: self.tree_view.collapseAll())
        tb_layout.addWidget(btn_collapse_all)

        tb_layout.addStretch()

        self.le_tree_search = QLineEdit()
        self.le_tree_search.setPlaceholderText("过滤键名或值...")
        self.le_tree_search.setMaximumWidth(200)
        self.le_tree_search.textChanged.connect(self._filter_tree)
        tb_layout.addWidget(self.le_tree_search)

        layout.addLayout(tb_layout)

        splitter = QSplitter(Qt.Horizontal)

        # 左侧：源代码输入
        left_w = QWidget()
        lw_layout = QVBoxLayout(left_w)
        lw_layout.setContentsMargins(0, 0, 0, 0)
        lw_layout.addWidget(QLabel("<b>待解析 JSON 源码:</b>"))
        self.edit_tree_source = QPlainTextEdit()
        self.edit_tree_source.setFont(QFont("Consolas", 10))
        self.edit_tree_source.setPlaceholderText("输入或粘贴合法 JSON 文本以生成结构树...")
        lw_layout.addWidget(self.edit_tree_source)
        splitter.addWidget(left_w)

        # 右侧：树形结构
        right_w = QWidget()
        rw_layout = QVBoxLayout(right_w)
        rw_layout.setContentsMargins(0, 0, 0, 0)
        rw_layout.addWidget(QLabel("<b>层级结构折叠树:</b>"))

        self.tree_view = QTreeWidget()
        self.tree_view.setHeaderLabels(["键名 / 索引 (Key)", "数据类型 (Type)", "预览值 (Value)"])
        self.tree_view.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree_view.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree_view.header().setSectionResizeMode(2, QHeaderView.Stretch)
        rw_layout.addWidget(self.tree_view)
        splitter.addWidget(right_w)

        splitter.setSizes([450, 550])
        layout.addWidget(splitter, 1)

    def _build_tree_from_text(self):
        text = self.edit_tree_source.toPlainText().strip()
        if not text:
            # 尝试回退读取左栏内容
            text = self.edit_left.toPlainText().strip()
            if text:
                self.edit_tree_source.setPlainText(text)

        if not text:
            QMessageBox.information(self, "提示", "请先输入或粘贴待解析的 JSON 文本")
            return

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "JSON 语法错误", f"无法解析为树: 第 {e.lineno} 行, 第 {e.colno} 列: {e.msg}")
            return

        self.tree_view.clear()
        root_item = QTreeWidgetItem(self.tree_view)
        root_item.setText(0, "$ (根节点)")
        root_item.setText(1, type(data).__name__)
        self._populate_tree_item(root_item, data)
        root_item.setExpanded(True)

    def _populate_tree_item(self, parent_item: QTreeWidgetItem, data: Any):
        if isinstance(data, dict):
            parent_item.setText(1, f"Object ({len(data)} 项)")
            parent_item.setForeground(1, QBrush(QColor("#38bdf8")))
            for k, v in data.items():
                child = QTreeWidgetItem(parent_item)
                child.setText(0, str(k))
                child.setText(1, type(v).__name__)
                self._populate_tree_item(child, v)
        elif isinstance(data, list):
            parent_item.setText(1, f"Array [{len(data)} 项]")
            parent_item.setForeground(1, QBrush(QColor("#f59e0b")))
            for idx, item in enumerate(data):
                child = QTreeWidgetItem(parent_item)
                child.setText(0, f"[{idx}]")
                child.setText(1, type(item).__name__)
                self._populate_tree_item(child, item)
        else:
            val_str = json.dumps(data, ensure_ascii=False) if data is not None else "null"
            parent_item.setText(2, val_str)
            if isinstance(data, str):
                parent_item.setForeground(2, QBrush(QColor("#10b981")))
            elif isinstance(data, (int, float)):
                parent_item.setForeground(2, QBrush(QColor("#ec4899")))
            elif isinstance(data, bool):
                parent_item.setForeground(2, QBrush(QColor("#8b5cf6")))

    def _filter_tree(self, text: str):
        query = text.strip().lower()

        def _check_item(item: QTreeWidgetItem) -> bool:
            match = False
            if not query or query in item.text(0).lower() or query in item.text(2).lower():
                match = True
            child_matched = False
            for i in range(item.childCount()):
                if _check_item(item.child(i)):
                    child_matched = True
            is_visible = match or child_matched
            item.setHidden(not is_visible)
            if child_matched:
                item.setExpanded(True)
            return is_visible

        for i in range(self.tree_view.topLevelItemCount()):
            _check_item(self.tree_view.topLevelItem(i))

    # =========================================================================
    # Tab 3: JSONPath 查询构建与逻辑
    # =========================================================================
    def _setup_path_tab(self):
        layout = QVBoxLayout(self.tab_path)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 查询输入行
        q_row = QHBoxLayout()
        q_row.setSpacing(8)

        q_row.addWidget(QLabel("<b>JSONPath:</b>"))
        self.le_jsonpath = QLineEdit("$..*")
        self.le_jsonpath.setPlaceholderText("例如: $.store.book[*].author 或 $..id")
        self.le_jsonpath.setFont(QFont("Consolas", 10))
        self.le_jsonpath.returnPressed.connect(self._run_jsonpath)
        q_row.addWidget(self.le_jsonpath, 1)

        self.combo_presets = QComboBox()
        self.combo_presets.addItems([
            "选择查询模板...",
            "全部匹配 ($..*)",
            "根节点直接子属性 ($.*)",
            "数组首项元素 ($[0])",
            "数组末项元素 ($[-1])",
            "递归提取所有 id ($..id)",
            "递归提取所有 name ($..name)"
        ])
        self.combo_presets.currentIndexChanged.connect(self._on_preset_selected)
        q_row.addWidget(self.combo_presets)

        self.btn_run_path = QPushButton("执行查询")
        self.btn_run_path.setObjectName("primaryBtn")
        self.btn_run_path.setIcon(get_icon("search", color="#ffffff", size=13))
        self.btn_run_path.clicked.connect(self._run_jsonpath)
        q_row.addWidget(self.btn_run_path)

        layout.addLayout(q_row)

        splitter = QSplitter(Qt.Horizontal)

        # 左：输入数据
        left_w = QWidget()
        lw_layout = QVBoxLayout(left_w)
        lw_layout.setContentsMargins(0, 0, 0, 0)
        lw_layout.addWidget(QLabel("<b>待检索 JSON 数据源:</b>"))
        self.edit_path_source = QPlainTextEdit()
        self.edit_path_source.setFont(QFont("Consolas", 10))
        self.edit_path_source.setPlaceholderText("在此输入或粘贴 JSON 数据源...")
        lw_layout.addWidget(self.edit_path_source)
        splitter.addWidget(left_w)

        # 右：输出结果
        right_w = QWidget()
        rw_layout = QVBoxLayout(right_w)
        rw_layout.setContentsMargins(0, 0, 0, 0)
        rh_layout = QHBoxLayout()
        rh_layout.addWidget(QLabel("<b>命中结果集:</b>"))
        self.lbl_path_hits = QLabel("0 项")
        self.lbl_path_hits.setStyleSheet("color: #38bdf8; font-weight: bold;")
        rh_layout.addWidget(self.lbl_path_hits)
        rh_layout.addStretch()
        btn_copy_hits = QPushButton("复制全部结果")
        btn_copy_hits.setIcon(get_icon("copy", size=12))
        btn_copy_hits.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.edit_path_result.toPlainText()))
        rh_layout.addWidget(btn_copy_hits)
        rw_layout.addLayout(rh_layout)

        self.edit_path_result = QPlainTextEdit()
        self.edit_path_result.setFont(QFont("Consolas", 10))
        self.edit_path_result.setReadOnly(True)
        self.edit_path_result.setPlaceholderText("查询结果将在此格式化输出...")
        rw_layout.addWidget(self.edit_path_result)
        splitter.addWidget(right_w)

        splitter.setSizes([450, 550])
        layout.addWidget(splitter, 1)

    def _on_preset_selected(self, idx: int):
        mapping = {
            1: "$..*",
            2: "$.*",
            3: "$[0]",
            4: "$[-1]",
            5: "$..id",
            6: "$..name"
        }
        if idx in mapping:
            self.le_jsonpath.setText(mapping[idx])
            self._run_jsonpath()

    def _run_jsonpath(self):
        text = self.edit_path_source.toPlainText().strip()
        if not text:
            text = self.edit_left.toPlainText().strip()
            if text:
                self.edit_path_source.setPlainText(text)

        if not text:
            QMessageBox.information(self, "提示", "请先输入或粘贴待查询的 JSON 数据源")
            return

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "JSON 语法错误", f"无法解析为 JSON: 第 {e.lineno} 行, 第 {e.colno} 列: {e.msg}")
            return

        query = self.le_jsonpath.text().strip()
        ok, results, msg = evaluate_jsonpath(data, query)

        self.lbl_path_hits.setText(f"{len(results)} 项匹配")
        if not ok:
            self.edit_path_result.setPlainText(f"查询错误: {msg}")
            return

        formatted_res = json.dumps(results, indent=2, ensure_ascii=False)
        self.edit_path_result.setPlainText(formatted_res)

    # =========================================================================
    # 通用接口与持久化生命周期
    # =========================================================================
    def set_input_text(self, text: str):
        """跨插件 Pipeline 数据接收通道"""
        if not self.edit_left.toPlainText().strip():
            self.edit_left.setPlainText(text)
        else:
            self.edit_right.setPlainText(text)
        self.edit_tree_source.setPlainText(text)
        self.edit_path_source.setPlainText(text)

    def load_settings(self):
        cfg = self.config_manager.get_plugin_config(self.PLUGIN_ID, {})
        sync = cfg.get("sync_scroll", True)
        self.cb_sync_scroll.setChecked(sync)

    def save_settings(self):
        cfg = {
            "sync_scroll": self.cb_sync_scroll.isChecked()
        }
        self.config_manager.set_plugin_config(self.PLUGIN_ID, cfg)

    def save_config(self):
        self.save_settings()

    def load_config(self):
        self.load_settings()

    def cleanup(self):
        pass
