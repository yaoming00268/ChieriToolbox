"""
工具箱 (Toolbox) - 现代化文件拖拽列表组件 (ModernDragDropListWidget)
支持文件与文件夹原生拖拽、双击直接打开/系统资源管理器定位、路径复制、
多选删除、一键清空与实时状态反馈。
"""

import os
import subprocess
from typing import List
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QFileDialog, QMenu, QApplication
)
from PySide6.QtGui import QAction, QPainter, QColor

from toolbox.ui.icons import get_icon


class DropListWidget(QListWidget):
    """支持居中空状态提示绘制的专用拖拽列表"""
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QColor("#94a3b8"))
            font = painter.font()
            font.setPointSize(10)
            painter.setFont(font)
            rect = self.viewport().rect()
            text = "拖入文件或文件夹，或点击上方按钮添加"
            painter.drawText(rect, Qt.AlignCenter, text)
            painter.end()


class ModernFileListWidget(QWidget):
    paths_changed = Signal(list)  # 当文件列表变化时触发，传出当前所有路径列表

    def __init__(self, title: str = "文件列表", hint: str = "可将文件或文件夹直接拖拽至此处", parent=None):
        super().__init__(parent)
        self.title = title
        self.hint = hint
        self._is_drag_active = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 顶部工具条
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.lbl_title = QLabel(f"<b>{self.title}</b>")
        self.lbl_title.setStyleSheet("font-size: 13px; font-weight: 600;")
        top_bar.addWidget(self.lbl_title)

        self.lbl_badge = QLabel("0 项")
        self.lbl_badge.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border-radius: 9px; "
            "padding: 1px 7px; font-size: 11px; font-weight: bold;"
        )
        top_bar.addWidget(self.lbl_badge)
        top_bar.addStretch()

        self.btn_add_files = QPushButton("添加文件")
        self.btn_add_files.setIcon(get_icon("file-plus", size=16))
        self.btn_add_files.setToolTip("选择一个或多个文件加入列表")
        self.btn_add_files.clicked.connect(self._browse_files)
        top_bar.addWidget(self.btn_add_files)

        self.btn_add_folder = QPushButton("添加目录")
        self.btn_add_folder.setIcon(get_icon("folder-plus", size=16))
        self.btn_add_folder.setToolTip("选择文件夹并将其内文件扫描加入列表")
        self.btn_add_folder.clicked.connect(self._browse_folder)
        top_bar.addWidget(self.btn_add_folder)

        self.btn_clear = QPushButton("清空")
        self.btn_clear.setIcon(get_icon("trash", size=16))
        self.btn_clear.setToolTip("清空当前所有文件列表")
        self.btn_clear.clicked.connect(self.clear)
        top_bar.addWidget(self.btn_clear)

        layout.addLayout(top_bar)

        # 核心 ListWidget
        self.list_widget = DropListWidget()
        self.list_widget.setAcceptDrops(True)
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)

        # 挂载拖拽事件拦截
        self.list_widget.dragEnterEvent = self._drag_enter
        self.list_widget.dragMoveEvent = self._drag_move
        self.list_widget.dragLeaveEvent = self._drag_leave
        self.list_widget.dropEvent = self._drop_event

        layout.addWidget(self.list_widget)

    def _drag_enter(self, event):
        if event.mimeData().hasUrls():
            self._is_drag_active = True
            self.list_widget.setProperty("dragActive", "true")
            self.list_widget.style().unpolish(self.list_widget)
            self.list_widget.style().polish(self.list_widget)
            event.acceptProposedAction()

    def _drag_move(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _drag_leave(self, event):
        self._is_drag_active = False
        self.list_widget.setProperty("dragActive", "false")
        self.list_widget.style().unpolish(self.list_widget)
        self.list_widget.style().polish(self.list_widget)
        event.accept()

    def _drop_event(self, event):
        self._is_drag_active = False
        self.list_widget.setProperty("dragActive", "false")
        self.list_widget.style().unpolish(self.list_widget)
        self.list_widget.style().polish(self.list_widget)
        urls = event.mimeData().urls()
        if urls:
            paths = [url.toLocalFile() for url in urls if url.toLocalFile()]
            self.add_paths(paths)
            event.acceptProposedAction()

    def _browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        if files:
            self.add_paths(files)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self.add_paths([folder])

    def add_paths(self, paths: List[str]):
        """批量加入路径，自动规范化与去重"""
        current_set = set(self.get_paths())
        added = False
        for p in paths:
            norm_p = os.path.normpath(p)
            if norm_p not in current_set and os.path.exists(norm_p):
                current_set.add(norm_p)
                name = os.path.basename(norm_p) or norm_p
                item = QListWidgetItem(name)
                # 根据是文件还是目录设置小图标
                icon_type = "folder" if os.path.isdir(norm_p) else "file-plus"
                item.setIcon(get_icon(icon_type, size=16))
                item.setToolTip(f"{norm_p}\n(双击直接打开，右键查看更多)")
                item.setData(Qt.UserRole, norm_p)
                self.list_widget.addItem(item)
                added = True
        if added:
            self._update_count()
            self.paths_changed.emit(self.get_paths())

    def get_paths(self) -> List[str]:
        """获取当前列表内所有文件的绝对路径"""
        return [self.list_widget.item(i).data(Qt.UserRole) for i in range(self.list_widget.count())]

    def clear(self):
        self.list_widget.clear()
        self._update_count()
        self.paths_changed.emit([])

    def set_paths(self, paths: List[str]):
        """清空并重新设置路径列表"""
        self.clear()
        self.add_paths(paths)

    def _update_count(self):
        count = self.list_widget.count()
        self.lbl_badge.setText(f"{count} 项")

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """双击项：在系统中调用默认打开"""
        path = item.data(Qt.UserRole)
        if path and os.path.exists(path):
            try:
                os.startfile(path)
            except Exception:
                pass

    def _show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        menu = QMenu(self)

        if item:
            path = item.data(Qt.UserRole)

            act_open = QAction("打开文件/目录", self)
            act_open.setIcon(get_icon("play", size=14))
            act_open.triggered.connect(lambda: self._open_path(path))
            menu.addAction(act_open)

            act_reveal = QAction("在资源管理器中定位", self)
            act_reveal.setIcon(get_icon("folder", size=14))
            act_reveal.triggered.connect(lambda: self._reveal_in_explorer(path))
            menu.addAction(act_reveal)

            act_copy = QAction("复制完整路径", self)
            act_copy.setIcon(get_icon("tools", size=14))
            act_copy.triggered.connect(lambda: QApplication.clipboard().setText(path))
            menu.addAction(act_copy)

            menu.addSeparator()

        act_del = QAction("从列表中移除", self)
        act_del.setIcon(get_icon("clear", size=14))
        act_del.triggered.connect(self._remove_selected)
        menu.addAction(act_del)

        act_clear = QAction("清空所有", self)
        act_clear.setIcon(get_icon("trash", size=14))
        act_clear.triggered.connect(self.clear)
        menu.addAction(act_clear)

        menu.exec(self.list_widget.mapToGlobal(pos))

    def _open_path(self, path: str):
        if path and os.path.exists(path):
            try:
                os.startfile(path)
            except Exception:
                pass

    def _reveal_in_explorer(self, path: str):
        if path and os.path.exists(path):
            try:
                norm_p = os.path.normpath(path)
                subprocess.Popen(f'explorer /select,"{norm_p}"')
            except Exception:
                pass

    def _remove_selected(self):
        selected_items = self.list_widget.selectedItems()
        for item in selected_items:
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
        self._update_count()
        self.paths_changed.emit(self.get_paths())
