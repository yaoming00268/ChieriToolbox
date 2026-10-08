"""
极速启动器 (Quick Launcher) - Spotlight 风格悬浮面板与主操作界面
支持实时插件检索、拼音首字母过滤、即时安全数学计算、Base64/时间戳及屏幕像素拾色。
"""

import sys
from typing import Optional, List, Dict
from PySide6.QtCore import Qt, Signal, QTimer, QPoint
from PySide6.QtGui import QGuiApplication, QColor, QCursor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QFrame,
    QMessageBox, QDialog, QTabWidget, QTextEdit, QScrollArea
)

from toolbox.core.plugin_manager import PluginManager
from toolbox.ui.icons import get_icon, get_pixmap
from .engine import evaluate_math_expression, convert_base64, parse_timestamp, pinyin_initials


class ResultItemWidget(QFrame):
    """搜索结果条目卡片"""
    def __init__(self, title: str, subtitle: str, tag: str = "", icon_name: str = "tools", parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background: rgba(128, 128, 128, 0.06);
                border: 1px solid rgba(128, 128, 128, 0.12);
                border-radius: 8px;
            }
            QFrame:hover {
                background: rgba(59, 130, 246, 0.12);
                border: 1px solid #3b82f6;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        self.lbl_icon = QLabel()
        self.lbl_icon.setPixmap(get_pixmap(icon_name, size=24))
        layout.addWidget(self.lbl_icon)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        text_layout.addWidget(self.lbl_title)

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setStyleSheet("color: #64748b; font-size: 11px;")
        text_layout.addWidget(self.lbl_sub)
        layout.addLayout(text_layout, 1)

        if tag:
            lbl_tag = QLabel(tag)
            lbl_tag.setStyleSheet("background: #2563eb; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;")
            layout.addWidget(lbl_tag)


class SpotlightSearchWindow(QDialog):
    """桌面全屏居中悬浮极速呼出条 (Alt+Space 风格)"""
    def __init__(self, on_select_plugin_callback=None, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.on_select_plugin = on_select_plugin_callback

        self.setFixedSize(650, 420)
        self._center_on_screen()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)

        container = QFrame()
        container.setObjectName("spotlightContainer")
        container.setStyleSheet("""
            #spotlightContainer {
                background-color: #0f172a;
                border: 1.5px solid #3b82f6;
                border-radius: 12px;
            }
        """)
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(14, 14, 14, 14)
        c_layout.setSpacing(10)

        # 搜索输入行
        input_row = QHBoxLayout()
        icon_search = QLabel()
        icon_search.setPixmap(get_pixmap("search", color="#38bdf8", size=20))
        input_row.addWidget(icon_search)

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("键入插件名/缩写、算式 (如 1024*768)、时间戳... [Esc 退出]")
        self.input_search.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #f8fafc;
                font-size: 16px;
                font-weight: 500;
                padding: 4px;
            }
        """)
        self.input_search.textChanged.connect(self._on_search_text_changed)
        input_row.addWidget(self.input_search, 1)

        btn_close = QPushButton()
        btn_close.setIcon(get_icon("clear", color="#94a3b8", size=16))
        btn_close.setStyleSheet("background: transparent; border: none; padding: 4px;")
        btn_close.clicked.connect(self.hide)
        input_row.addWidget(btn_close)

        c_layout.addLayout(input_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: rgba(255, 255, 255, 0.1);")
        c_layout.addWidget(sep)

        # 结果列表
        self.list_results = QListWidget()
        self.list_results.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
            }
            QListWidget::item {
                border-radius: 6px;
                padding: 2px;
            }
            QListWidget::item:selected {
                background: rgba(59, 130, 246, 0.25);
            }
        """)
        self.list_results.itemDoubleClicked.connect(self._on_item_activated)
        c_layout.addWidget(self.list_results, 1)

        main_layout.addWidget(container)

        self._refresh_results("")

    def _center_on_screen(self):
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 3
            self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        self._center_on_screen()
        self.input_search.clear()
        self.input_search.setFocus()
        self._refresh_results("")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            item = self.list_results.currentItem()
            if not item and self.list_results.count() > 0:
                item = self.list_results.item(0)
            if item:
                self._on_item_activated(item)
        elif event.key() == Qt.Key_Down:
            idx = self.list_results.currentRow()
            if idx < self.list_results.count() - 1:
                self.list_results.setCurrentRow(idx + 1)
        elif event.key() == Qt.Key_Up:
            idx = self.list_results.currentRow()
            if idx > 0:
                self.list_results.setCurrentRow(idx - 1)
        else:
            super().keyPressEvent(event)

    def _on_search_text_changed(self, text: str):
        self._refresh_results(text.strip())

    def _refresh_results(self, query: str):
        self.list_results.clear()
        q_lower = query.lower()

        # 1. 优先尝试数学算式计算
        math_res = evaluate_math_expression(query)
        if math_res:
            expr, ans = math_res
            item = QListWidgetItem()
            item.setData(Qt.UserRole, {"type": "copy", "val": ans})
            card = ResultItemWidget(f"计算结果: {ans}", f"算式: {expr} · 按 Enter 复制结果", tag="计算器", icon_name="sparkles")
            item.setSizeHint(card.sizeHint())
            self.list_results.addItem(item)
            self.list_results.setItemWidget(item, card)

        # 2. 匹配 Base64
        if query.startswith("b64:") or query.startswith("base64:"):
            content = query.split(":", 1)[1].strip()
            encoded = convert_base64(content, "encode")
            decoded = convert_base64(content, "decode")

            # 解码结果卡片 (若文本可合法解码则优先展示)
            if not decoded.startswith("转换错误"):
                item_d = QListWidgetItem()
                item_d.setData(Qt.UserRole, {"type": "copy", "val": decoded})
                card_d = ResultItemWidget(f"Base64 解码: {decoded}", f"原文本: {content} · 按 Enter 复制解码文本", tag="Base64解码", icon_name="sparkles")
                item_d.setSizeHint(card_d.sizeHint())
                self.list_results.addItem(item_d)
                self.list_results.setItemWidget(item_d, card_d)

            # 编码结果卡片
            item_e = QListWidgetItem()
            item_e.setData(Qt.UserRole, {"type": "copy", "val": encoded})
            card_e = ResultItemWidget(f"Base64 编码: {encoded}", f"原文本: {content} · 按 Enter 复制编码文本", tag="Base64编码", icon_name="sparkles")
            item_e.setSizeHint(card_e.sizeHint())
            self.list_results.addItem(item_e)
            self.list_results.setItemWidget(item_e, card_e)

        # 3. 匹配时间戳
        if query.startswith("time:") or query in ("now", "time", "时间"):
            param = query.split(":", 1)[1] if ":" in query else ""
            t_info = parse_timestamp(param)

            # 时间戳数字卡片
            item_t = QListWidgetItem()
            item_t.setData(Qt.UserRole, {"type": "copy", "val": t_info["timestamp"]})
            card_t = ResultItemWidget(f"Unix 时间戳: {t_info['timestamp']}", f"对应时间: {t_info['datetime']} · 按 Enter 复制时间戳", tag="时间戳", icon_name="refresh")
            item_t.setSizeHint(card_t.sizeHint())
            self.list_results.addItem(item_t)
            self.list_results.setItemWidget(item_t, card_t)

            # 格式化日期卡片
            if t_info["datetime"] and not t_info["datetime"].startswith("请输入"):
                item_dt = QListWidgetItem()
                item_dt.setData(Qt.UserRole, {"type": "copy", "val": t_info["datetime"]})
                card_dt = ResultItemWidget(f"标准北京时间: {t_info['datetime']}", f"时间戳: {t_info['timestamp']} · 按 Enter 复制时间文本", tag="日期时间", icon_name="sparkles")
                item_dt.setSizeHint(card_dt.sizeHint())
                self.list_results.addItem(item_dt)
                self.list_results.setItemWidget(item_dt, card_dt)

        # 4. 插件全量检索 (名称、描述、分类、拼音首字母)
        pm = PluginManager()
        plugins = pm.get_all_plugins()
        matched_plugins = []
        for p in plugins:
            if not pm.is_plugin_enabled(p.id):
                continue
            if not query:
                matched_plugins.append(p)
                continue

            name_lower = p.name.lower()
            desc_lower = p.description.lower()
            cat_lower = p.category.lower()
            py_name = pinyin_initials(p.name)

            if (q_lower in name_lower or q_lower in p.id.lower() or
                q_lower in desc_lower or q_lower in cat_lower or
                q_lower in py_name):
                matched_plugins.append(p)

        for p in matched_plugins[:12]:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, {"type": "plugin", "id": p.id})
            card = ResultItemWidget(p.name, p.description, tag=p.category, icon_name=p.icon)
            item.setSizeHint(card.sizeHint())
            self.list_results.addItem(item)
            self.list_results.setItemWidget(item, card)

        if self.list_results.count() > 0:
            self.list_results.setCurrentRow(0)

    def _on_item_activated(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if not data:
            return
        if data["type"] == "copy":
            cb = QGuiApplication.clipboard()
            cb.setText(data["val"])
            self.hide()
        elif data["type"] == "plugin":
            pid = data["id"]
            self.hide()
            if self.on_select_plugin:
                self.on_select_plugin(pid)


class QuickLauncherWidget(QWidget):
    """极速启动器嵌入式主面板视图"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.spotlight_window = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # 顶部工具引导栏
        header = QHBoxLayout()
        tip = QLabel("<b>千绘莉极速启动器 (Spotlight)</b><br><span style='color:#64748b; font-size:12px;'>全天候桌面极速呼出条、拼音秒搜插件、安全算式计算与实用指令集。</span>")
        tip.setWordWrap(True)
        header.addWidget(tip, 1)

        self.btn_summon = QPushButton("立即唤起 Spotlight 悬浮条")
        self.btn_summon.setObjectName("primaryBtn")
        self.btn_summon.setIcon(get_icon("search", color="#ffffff", size=15))
        self.btn_summon.setFixedHeight(36)
        self.btn_summon.clicked.connect(self._summon_spotlight)
        header.addWidget(self.btn_summon)
        layout.addLayout(header)

        # 快捷工具小部件选项卡
        tabs = QTabWidget()
        tabs.addTab(self._build_tools_page(), get_icon("sparkles", size=14), "实用指令集")
        layout.addWidget(tabs, 1)

    def _summon_spotlight(self):
        if not self.spotlight_window:
            top_win = self.window()
            cb = top_win.switch_to_plugin if hasattr(top_win, "switch_to_plugin") else None
            self.spotlight_window = SpotlightSearchWindow(on_select_plugin_callback=cb)
        self.spotlight_window.show()
        self.spotlight_window.raise_()
        self.spotlight_window.activateWindow()

    def _build_tools_page(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(12, 12, 12, 12)
        l.setSpacing(12)

        # 1. 算式计算器
        grp_calc = QFrame()
        grp_calc.setStyleSheet("background: rgba(128, 128, 128, 0.05); border-radius: 8px; padding: 6px;")
        l_calc = QVBoxLayout(grp_calc)
        l_calc.addWidget(QLabel("<b>即时算式计算器 (安全 AST 语法树解析)</b>"))
        row_c = QHBoxLayout()
        self.le_calc_input = QLineEdit()
        self.le_calc_input.setPlaceholderText("输入如 1024 * 768 / 1024 或 sqrt(256) 或 2**10...")
        self.btn_do_calc = QPushButton("计算")
        self.lbl_calc_out = QLabel("结果: 等待输入")
        self.lbl_calc_out.setStyleSheet("font-weight: bold; color: #2563eb; min-width: 140px;")
        self.btn_do_calc.clicked.connect(self._run_calc)
        self.le_calc_input.returnPressed.connect(self._run_calc)
        row_c.addWidget(self.le_calc_input, 1)
        row_c.addWidget(self.btn_do_calc)
        row_c.addWidget(self.lbl_calc_out)
        l_calc.addLayout(row_c)
        l.addWidget(grp_calc)

        # 2. Base64 快速转换
        grp_b64 = QFrame()
        grp_b64.setStyleSheet("background: rgba(128, 128, 128, 0.05); border-radius: 8px; padding: 6px;")
        l_b64 = QVBoxLayout(grp_b64)
        l_b64.addWidget(QLabel("<b>Base64 快速编解码</b>"))
        row_b = QHBoxLayout()
        self.le_b64_in = QLineEdit()
        self.le_b64_in.setPlaceholderText("输入文本或 Base64 编码...")
        btn_enc = QPushButton("编码")
        btn_dec = QPushButton("解码")
        self.le_b64_out = QLineEdit()
        self.le_b64_out.setReadOnly(True)
        btn_enc.clicked.connect(lambda: self.le_b64_out.setText(convert_base64(self.le_b64_in.text(), "encode")))
        btn_dec.clicked.connect(lambda: self.le_b64_out.setText(convert_base64(self.le_b64_in.text(), "decode")))
        row_b.addWidget(self.le_b64_in, 1)
        row_b.addWidget(btn_enc)
        row_b.addWidget(btn_dec)
        row_b.addWidget(self.le_b64_out, 1)
        l_b64.addLayout(row_b)
        l.addWidget(grp_b64)

        # 3. 屏幕拾色器
        grp_pick = QFrame()
        grp_pick.setStyleSheet("background: rgba(128, 128, 128, 0.05); border-radius: 8px; padding: 6px;")
        l_pick = QVBoxLayout(grp_pick)
        l_pick.addWidget(QLabel("<b>屏幕全局像素吸色器</b>"))
        row_p = QHBoxLayout()
        self.btn_pick_color = QPushButton("抓取当前光标处像素颜色")
        self.lbl_color_preview = QLabel(" ")
        self.lbl_color_preview.setFixedSize(32, 24)
        self.lbl_color_preview.setStyleSheet("background: #000000; border: 1px solid #94a3b8; border-radius: 4px;")
        self.lbl_color_hex = QLabel("HEX: #000000")
        self.lbl_color_hex.setStyleSheet("font-weight: bold;")
        self.btn_pick_color.clicked.connect(self._pick_screen_color)
        row_p.addWidget(self.btn_pick_color)
        row_p.addWidget(self.lbl_color_preview)
        row_p.addWidget(self.lbl_color_hex)
        row_p.addStretch()
        l_pick.addLayout(row_p)
        l.addWidget(grp_pick)

        l.addStretch()
        return w

    def _run_calc(self):
        txt = self.le_calc_input.text().strip()
        res = evaluate_math_expression(txt)
        if res:
            self.lbl_calc_out.setText(f"结果: {res[1]}")
        else:
            self.lbl_calc_out.setText("结果: 表达式无效")

    def _pick_screen_color(self):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        pos = QCursor.pos()
        pix = screen.grabWindow(0, pos.x(), pos.y(), 1, 1)
        if not pix.isNull():
            img = pix.toImage()
            color = img.pixelColor(0, 0)
            hex_str = color.name(QColor.HexRgb).upper()
            self.lbl_color_preview.setStyleSheet(f"background: {hex_str}; border: 1px solid #94a3b8; border-radius: 4px;")
            self.lbl_color_hex.setText(f"HEX: {hex_str} (RGB: {color.red()},{color.green()},{color.blue()})")
            cb = QGuiApplication.clipboard()
            cb.setText(hex_str)

    def load_settings(self):
        from toolbox.core.config_manager import ConfigManager
        cfg = ConfigManager().get_plugin_config("quick_launcher")
        calc_in = cfg.get("calc_input", "")
        if calc_in and hasattr(self, "le_calc_input"):
            self.le_calc_input.setText(calc_in)

    def save_settings(self):
        from toolbox.core.config_manager import ConfigManager
        calc_in = self.le_calc_input.text() if hasattr(self, "le_calc_input") else ""
        ConfigManager().set_plugin_config("quick_launcher", {"calc_input": calc_in})
