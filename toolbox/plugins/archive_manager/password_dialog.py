"""
ACG 密码本管理对话框 (AcgPasswordDialog)
支持查看、搜索、添加、删除、导入、导出二次元社区常用解压密码与个人历史记忆。
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFileDialog, QWidget
)

from toolbox.ui.icons import get_icon, get_pixmap
from .password_book import AcgPasswordBook, DEFAULT_ACG_PASSWORDS


class AcgPasswordDialog(QDialog):
    """ACG 密码本管理对话框"""
    password_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("ACG 社区解压密码本")
        self.resize(520, 500)
        self.book = AcgPasswordBook()
        self.init_ui()
        self.refresh_table()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # 1. 顶部标题
        header = QHBoxLayout()
        header.setSpacing(10)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("archive", color="#eab308", size=24))
        header.addWidget(icon_lbl)

        title_lbl = QLabel("ACG 社区解压密码本 & 历史记忆")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(title_lbl)
        header.addStretch()

        layout.addLayout(header)

        # 2. 搜索过滤与新增栏
        filter_row = QHBoxLayout()
        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText("搜索密码...")
        self.le_search.textChanged.connect(self._filter_table)
        filter_row.addWidget(self.le_search, 1)

        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setIcon(get_icon("refresh", size=14))
        self.btn_refresh.clicked.connect(self.refresh_table)
        filter_row.addWidget(self.btn_refresh)
        layout.addLayout(filter_row)

        # 3. 密码表格
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["解压密码", "类型来源"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.doubleClicked.connect(self._use_selected_password)
        layout.addWidget(self.table, 1)

        # 4. 新增密码栏
        add_row = QHBoxLayout()
        self.le_new_pwd = QLineEdit()
        self.le_new_pwd.setPlaceholderText("输入新的解压密码添加至记忆本...")
        self.le_new_pwd.returnPressed.connect(self._add_password)
        add_row.addWidget(self.le_new_pwd, 1)

        self.btn_add = QPushButton("添加记录")
        self.btn_add.setIcon(get_icon("play", size=14))
        self.btn_add.clicked.connect(self._add_password)
        add_row.addWidget(self.btn_add)
        layout.addLayout(add_row)

        # 5. 底部操作按键 (导入 / 导出 / 删除 / 选用)
        action_row = QHBoxLayout()
        self.btn_import = QPushButton("导入 TXT...")
        self.btn_import.clicked.connect(self._import_txt)
        action_row.addWidget(self.btn_import)

        self.btn_export = QPushButton("导出 TXT...")
        self.btn_export.clicked.connect(self._export_txt)
        action_row.addWidget(self.btn_export)

        self.btn_del = QPushButton("删除记录")
        self.btn_del.clicked.connect(self._del_password)
        action_row.addWidget(self.btn_del)

        action_row.addStretch()

        self.btn_use = QPushButton("填入此密码")
        self.btn_use.setObjectName("primaryBtn")
        self.btn_use.setIcon(get_icon("check", size=14))
        self.btn_use.clicked.connect(self._use_selected_password)
        action_row.addWidget(self.btn_use)

        layout.addLayout(action_row)

    def refresh_table(self):
        query = self.le_search.text().strip().lower()
        customs = set(self.book.get_custom_passwords())
        all_pwds = self.book.get_all_passwords()

        filtered = []
        for p in all_pwds:
            if not query or query in p.lower():
                is_custom = p in customs
                source = "用户记忆" if is_custom else "社区预设"
                filtered.append((p, source, is_custom))

        self.table.setRowCount(len(filtered))
        for row, (p, src, is_cust) in enumerate(filtered):
            item_p = QTableWidgetItem(p)
            item_s = QTableWidgetItem(src)
            if is_cust:
                item_s.setForeground(Qt.darkGreen)
            else:
                item_s.setForeground(Qt.gray)
            self.table.setItem(row, 0, item_p)
            self.table.setItem(row, 1, item_s)

    def _filter_table(self):
        self.refresh_table()

    def _add_password(self):
        txt = self.le_new_pwd.text().strip()
        if not txt:
            return
        if self.book.add_password(txt):
            self.le_new_pwd.clear()
            self.refresh_table()

    def _del_password(self):
        row = self.table.currentRow()
        if row < 0:
            return
        pwd_item = self.table.item(row, 0)
        src_item = self.table.item(row, 1)
        if not pwd_item or not src_item:
            return

        pwd = pwd_item.text()
        if src_item.text() != "用户记忆":
            QMessageBox.information(self, "提示", "预设的社区密码不可删除。")
            return

        self.book.remove_password(pwd)
        self.refresh_table()

    def _use_selected_password(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item:
            pwd = item.text()
            self.password_selected.emit(pwd)
            self.accept()

    def _import_txt(self):
        f, _ = QFileDialog.getOpenFileName(self, "导入密码文件", "", "文本文件 (*.txt);;所有文件 (*.*)")
        if f:
            cnt = self.book.import_passwords(f)
            QMessageBox.information(self, "导入完成", f"已成功导入 {cnt} 条密码记录。")
            self.refresh_table()

    def _export_txt(self):
        f, _ = QFileDialog.getSaveFileName(self, "导出密码本", "acg_passwords.txt", "文本文件 (*.txt)")
        if f:
            if self.book.export_passwords(f):
                QMessageBox.information(self, "导出完成", f"密码本已保存至:\n{f}")
            else:
                QMessageBox.warning(self, "导出失败", "写入文件失败。")
