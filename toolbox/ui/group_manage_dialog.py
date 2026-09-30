"""
千绘莉多功能工具箱 (Chieri Toolbox) - 自定义分组管理对话框 (GroupManageDialog)
支持用户自定义创建、删除及管理插件功能分组。
严格遵循无 Emoji 原则，采用矢量图标与响应式排版。
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QInputDialog,
    QMessageBox, QFrame
)
from toolbox.core.config_manager import ConfigManager
from toolbox.core.plugin_manager import PluginManager
from toolbox.ui.icons import get_icon, get_pixmap


class GroupManageDialog(QDialog):
    groups_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self.plugin_manager = PluginManager()
        self.init_ui()
        self.refresh_list()

    def init_ui(self):
        self.setWindowTitle("自定义分组管理")
        self.setWindowIcon(get_icon("layers", size=24))
        self.resize(440, 380)
        self.setMinimumSize(380, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # 顶部 Header
        header = QHBoxLayout()
        header.setSpacing(10)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("layers", color="#3b82f6", size=24))
        header.addWidget(icon_lbl)

        title_lbl = QLabel("自定义分类与分组管理")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        header.addWidget(title_lbl)
        header.addStretch()
        layout.addLayout(header)

        desc_lbl = QLabel("您可以自由创建个性化分组（如“常用工具”、“音视频精选”等），并将任意插件卡片添加至对应分组。")
        desc_lbl.setStyleSheet("color: #64748b; font-size: 12px;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # 列表控件
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #2563eb;
                color: #ffffff;
            }
        """)
        layout.addWidget(self.list_widget, 1)

        # 操作工具栏
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_add = QPushButton("新建分组")
        self.btn_add.setIcon(get_icon("plus", size=14))
        self.btn_add.clicked.connect(self._add_group)
        btn_layout.addWidget(self.btn_add)

        self.btn_delete = QPushButton("删除选中分组")
        self.btn_delete.setIcon(get_icon("trash", size=14))
        self.btn_delete.clicked.connect(self._delete_group)
        btn_layout.addWidget(self.btn_delete)

        btn_layout.addStretch()

        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def refresh_list(self):
        self.list_widget.clear()
        custom_groups = self.config_manager.get_custom_groups()
        enabled_plugins = [p for p in self.plugin_manager.get_all_plugins() if self.config_manager.is_plugin_enabled(p.id)]

        for grp in custom_groups:
            # 统计该分组内插件数量
            count = sum(1 for p in enabled_plugins if grp in self.config_manager.get_plugin_custom_groups(p.id))
            item = QListWidgetItem(f" {grp}  ({count} 个模块)")
            item.setIcon(get_icon("tag", size=15))
            item.setData(Qt.UserRole, grp)
            self.list_widget.addItem(item)

    def _add_group(self):
        text, ok = QInputDialog.getText(self, "新建自定义分组", "请输入新分组名称:")
        if ok and text.strip():
            name = text.strip()
            if name in ("全部", "最近使用"):
                QMessageBox.warning(self, "提示", "不能使用系统保留分类名称。")
                return
            if name in self.config_manager.get_custom_groups():
                QMessageBox.warning(self, "提示", f"分组「{name}」已存在。")
                return
            self.config_manager.add_custom_group(name)
            self.refresh_list()
            self.groups_changed.emit()

    def _delete_group(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请先在上方列表中选中要删除的分组。")
            return
        grp_name = item.data(Qt.UserRole)
        res = QMessageBox.question(
            self,
            "确认删除分组",
            f"确定要删除分组「{grp_name}」吗？\n\n删除后，该分组内的插件卡片仍将保留在原有默认分类中，不会被删除。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if res == QMessageBox.Yes:
            self.config_manager.delete_custom_group(grp_name)
            self.refresh_list()
            self.groups_changed.emit()
