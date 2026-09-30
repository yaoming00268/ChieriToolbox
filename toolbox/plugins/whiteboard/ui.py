"""
交互式白板 (希沃风) - UI 界面
提供手写画笔、荧光记号笔、橡皮擦除、几何形状绘制、底色切换、多级撤销与高清导出。
"""

import os
import time
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QButtonGroup, QComboBox, QFileDialog, QMessageBox,
    QFrame, QColorDialog
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.icons import get_icon, get_pixmap
from .canvas import WhiteboardCanvas


class WhiteboardWidget(QWidget):
    PLUGIN_ID = "whiteboard"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self.init_ui()
        self.init_shortcuts()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 16)
        main_layout.setSpacing(10)

        # 1. 顶部 Header
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("tools", color="#3b82f6", size=24))
        header.addWidget(icon_lbl)

        title_lbl = QLabel("交互式白板 (希沃极简教学风)")
        title_lbl.setStyleSheet("font-size: 17px; font-weight: bold;")
        header.addWidget(title_lbl)

        badge_lbl = QLabel("平滑笔迹 · 几何图形 · 网格背景 · 撤销重做")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header.addStretch()

        # 快捷全屏教学模式按钮
        self.btn_fullscreen = QPushButton("全屏教学模式 (F11)")
        self.btn_fullscreen.setIcon(get_icon("window", size=13))
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        header.addWidget(self.btn_fullscreen)

        main_layout.addLayout(header)

        # 2. 核心 Seewo 风格悬浮快捷工具栏 (两行响应式设计，彻底杜绝小窗口挤压)
        self.toolbar_frame = QFrame()
        self.toolbar_frame.setObjectName("whiteboardToolbar")
        self.toolbar_frame.setStyleSheet("""
            #whiteboardToolbar {
                background-color: #1e2230;
                border: 1px solid #2e3547;
                border-radius: 8px;
            }
        """)
        tb_main_layout = QVBoxLayout(self.toolbar_frame)
        tb_main_layout.setContentsMargins(8, 6, 8, 6)
        tb_main_layout.setSpacing(6)

        # 第 1 行：绘图工具与快捷选择
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        self.tool_btn_group = QButtonGroup(self)
        self.tool_btn_group.setExclusive(True)

        self.tools_def = [
            ("pen", "画笔", "pencil"),
            ("highlighter", "荧光笔", "zap"),
            ("eraser", "橡皮擦", "clear"),
            ("line", "直线", "chevron-right"),
            ("arrow", "箭头", "arrow-left"),
            ("rect", "矩形", "square"),
            ("circle", "圆形", "circle"),
            ("text", "文本", "type")
        ]

        for tool_id, tool_name, icon_name in self.tools_def:
            btn = QPushButton(f" {tool_name}")
            btn.setCheckable(True)
            btn.setIcon(get_icon(icon_name, size=13))
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda ch, tid=tool_id: self._on_tool_selected(tid))
            self.tool_btn_group.addButton(btn)
            row1.addWidget(btn)
            if tool_id == "pen":
                btn.setChecked(True)

        row1.addStretch()
        tb_main_layout.addLayout(row1)

        # 第 2 行：颜色选取条、笔刷粗细调节、画布底色切换与操作命令 (撤销/重做/清空/导出)
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        lbl_color = QLabel("颜色:")
        lbl_color.setStyleSheet("color: #94a3b8; font-size: 12px;")
        row2.addWidget(lbl_color)

        self.colors = [
            ("#2563eb", "经典蓝"),
            ("#ef4444", "强调红"),
            ("#10b981", "翡翠绿"),
            ("#eab308", "明亮黄"),
            ("#0f172a", "暗夜黑"),
            ("#ffffff", "纯净白"),
            ("#8b5cf6", "优雅紫")
        ]
        self.color_btn_group = QButtonGroup(self)
        self.color_btn_group.setExclusive(True)

        for col_hex, col_name in self.colors:
            c_btn = QPushButton()
            c_btn.setFixedSize(20, 20)
            c_btn.setCheckable(True)
            c_btn.setToolTip(col_name)
            border_c = "#ffffff" if col_hex == "#0f172a" else "#000000"
            c_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {col_hex};
                    border: 2px solid {border_c};
                    border-radius: 10px;
                }}
                QPushButton:checked {{
                    border: 3px solid #38bdf8;
                }}
            """)
            c_btn.clicked.connect(lambda ch, c=col_hex: self._on_color_selected(c))
            self.color_btn_group.addButton(c_btn)
            row2.addWidget(c_btn)
            if col_hex == "#2563eb":
                c_btn.setChecked(True)

        btn_more_colors = QPushButton("自定义")
        btn_more_colors.setFixedHeight(24)
        btn_more_colors.clicked.connect(self._pick_custom_color)
        row2.addWidget(btn_more_colors)

        sep2 = QLabel("|")
        sep2.setStyleSheet("color: #475569;")
        row2.addWidget(sep2)

        row2.addWidget(QLabel("粗细:"))
        self.combo_size = QComboBox()
        self.combo_size.addItems(["2 px", "4 px", "8 px", "14 px", "24 px"])
        self.combo_size.setCurrentIndex(1)
        self.combo_size.setFixedWidth(75)
        self.combo_size.currentIndexChanged.connect(self._on_size_changed)
        row2.addWidget(self.combo_size)

        sep3 = QLabel("|")
        sep3.setStyleSheet("color: #475569;")
        row2.addWidget(sep3)

        row2.addWidget(QLabel("底板:"))
        self.combo_bg = QComboBox()
        self.combo_bg.addItems(["纯白白板", "墨绿黑板", "暗黑黑板", "坐标网格", "教学点阵"])
        self.combo_bg.setFixedWidth(95)
        self.combo_bg.currentIndexChanged.connect(self._on_bg_changed)
        row2.addWidget(self.combo_bg)

        row2.addStretch()

        # 历史与导出操作区
        self.btn_undo = QPushButton("撤销")
        self.btn_undo.setIcon(get_icon("undo", size=13))
        self.btn_undo.setFixedHeight(26)
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self._undo)
        row2.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("重做")
        self.btn_redo.setIcon(get_icon("redo", size=13))
        self.btn_redo.setFixedHeight(26)
        self.btn_redo.setEnabled(False)
        self.btn_redo.clicked.connect(self._redo)
        row2.addWidget(self.btn_redo)

        self.btn_clear = QPushButton("清空")
        self.btn_clear.setIcon(get_icon("trash", size=13))
        self.btn_clear.setFixedHeight(26)
        self.btn_clear.clicked.connect(self._clear_canvas)
        row2.addWidget(self.btn_clear)

        self.btn_export = QPushButton("导出图片")
        self.btn_export.setObjectName("primaryBtn")
        self.btn_export.setIcon(get_icon("save", color="#ffffff", size=13))
        self.btn_export.setFixedHeight(26)
        self.btn_export.clicked.connect(self._export_image)
        row2.addWidget(self.btn_export)

        tb_main_layout.addLayout(row2)

        main_layout.addWidget(self.toolbar_frame)

        # 3. 核心双缓冲绘图画布
        self.canvas_container = QFrame()
        self.canvas_container.setObjectName("canvasContainer")
        self.canvas_container.setStyleSheet("""
            #canvasContainer {
                border: 1px solid #334155;
                border-radius: 8px;
            }
        """)
        c_layout = QVBoxLayout(self.canvas_container)
        c_layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = WhiteboardCanvas(self.canvas_container)
        self.canvas.can_undo_changed.connect(self.btn_undo.setEnabled)
        self.canvas.can_redo_changed.connect(self.btn_redo.setEnabled)
        c_layout.addWidget(self.canvas)

        main_layout.addWidget(self.canvas_container, 1)

    def init_shortcuts(self):
        sc_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        sc_undo.activated.connect(self._undo)

        sc_redo = QShortcut(QKeySequence("Ctrl+Y"), self)
        sc_redo.activated.connect(self._redo)

        sc_f11 = QShortcut(QKeySequence("F11"), self)
        sc_f11.activated.connect(self._toggle_fullscreen)

    def _on_tool_selected(self, tool_id: str):
        self.canvas.set_tool(tool_id)
        self.save_settings()

    def _on_color_selected(self, col_hex: str):
        self.canvas.set_color(QColor(col_hex))
        self.save_settings()

    def _pick_custom_color(self):
        col = QColorDialog.getColor(self.canvas.current_color, self, "选择画笔颜色")
        if col.isValid():
            self.canvas.set_color(col)

    def _on_size_changed(self, idx: int):
        sizes = [2, 4, 8, 14, 24]
        self.canvas.set_stroke_width(sizes[idx])
        self.save_settings()

    def _on_bg_changed(self, idx: int):
        bg_keys = ["white", "green", "dark", "grid", "dots"]
        self.canvas.set_bg_style(bg_keys[idx])
        self.save_settings()

    def _undo(self):
        self.canvas.undo()

    def _redo(self):
        self.canvas.redo()

    def _clear_canvas(self):
        res = QMessageBox.question(self, "确认清空", "是否清空当前白板上的所有书写笔迹？", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            self.canvas.clear_canvas()

    def _export_image(self):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        default_name = f"Whiteboard_{timestamp}.png"
        filepath, _ = QFileDialog.getSaveFileName(self, "导出白板为图片", default_name, "PNG Image (*.png);;JPEG Image (*.jpg)")
        if filepath:
            if self.canvas.export_image(filepath):
                QMessageBox.information(self, "导出成功", f"白板画面已成功保存至:\n{filepath}")
            else:
                QMessageBox.critical(self, "导出失败", "导出图片过程发生异常，请检查文件写入权限。")

    def _toggle_fullscreen(self):
        win = self.window()
        if win.isFullScreen():
            win.showNormal()
            self.btn_fullscreen.setText("全屏教学模式 (F11)")
        else:
            win.showFullScreen()
            self.btn_fullscreen.setText("退出全屏 (F11 / Esc)")

    def load_settings(self):
        cfg = self.config_manager.get_plugin_config(self.PLUGIN_ID, {})
        tool = cfg.get("tool", "pen")
        self.canvas.set_tool(tool)
        for btn in self.tool_btn_group.buttons():
            for t_id, t_name, _ in self.tools_def:
                if t_id == tool and t_name in btn.text():
                    btn.setChecked(True)

        col = cfg.get("color", "#2563eb")
        self.canvas.set_color(QColor(col))

        size_idx = cfg.get("size_idx", 1)
        self.combo_size.setCurrentIndex(size_idx)
        sizes = [2, 4, 8, 14, 24]
        self.canvas.set_stroke_width(sizes[size_idx])

        bg_idx = cfg.get("bg_idx", 0)
        self.combo_bg.setCurrentIndex(bg_idx)
        bg_keys = ["white", "green", "dark", "grid", "dots"]
        self.canvas.set_bg_style(bg_keys[bg_idx])

    def save_settings(self):
        cfg = {
            "tool": self.canvas.current_tool,
            "color": self.canvas.current_color.name(),
            "size_idx": self.combo_size.currentIndex(),
            "bg_idx": self.combo_bg.currentIndex()
        }
        self.config_manager.set_plugin_config(self.PLUGIN_ID, cfg)
