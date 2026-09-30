import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLabel,
                               QLineEdit, QGroupBox, QTextEdit, QTableWidget,
                               QTableWidgetItem, QHeaderView, QHBoxLayout,
                               QStackedWidget, QFileDialog, QListWidgetItem)
from ListWidget import DragDropListWidget
from folder_manager import flatten_and_remove_parent
from rename_manager import get_rename_names_preview, execute_rename
from rename_preview import get_rename_extensions_preview
class FileManagerGUI(QWidget):
    def __init__(self, initial_paths=None):
        super().__init__()
        self.setWindowTitle("千绘莉的文件管理器喵")
        self.resize(800, 700)
        self.current_rename_list = []
        self.setup_ui()
        if initial_paths:
            self.load_initial_paths(initial_paths)
    def load_initial_paths(self, paths):
        for path in paths:
            if os.path.exists(path):
                name = os.path.basename(path) or path
                for list_widget in [self.list1, self.list2, self.list3]:
                    if path not in list_widget.get_paths():
                        item = QListWidgetItem(name)
                        item.setData(Qt.UserRole, path)
                        list_widget.addItem(item)
        self.list1.paths_changed.emit()
        self.list2.paths_changed.emit()
        self.list3.paths_changed.emit()
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        self.stack = QStackedWidget(self)
        main_layout.addWidget(self.stack)
        self.setup_menu()
        self.setup_page1()
        self.setup_page2()
        self.setup_page3()
    def setup_menu(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<h2>请主人选择需要的功能喵：</h2>"))
        b1 = QPushButton("1. 批量重命名文件名称"); b1.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        b2 = QPushButton("2. 批量重命名文件后缀"); b2.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        b3 = QPushButton("3. 提取并删除上一级文件夹"); b3.clicked.connect(lambda: self.stack.setCurrentIndex(3))
        layout.addWidget(b1); layout.addWidget(b2); layout.addWidget(b3)
        layout.addStretch()
        self.stack.addWidget(page)
    def browse_files(self, list_widget):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择文件喵")
        current_paths = list_widget.get_paths()
        added = False
        for p in paths:
            if p not in current_paths:
                item = QListWidgetItem(os.path.basename(p))
                item.setData(Qt.UserRole, p)
                list_widget.addItem(item)
                added = True
        if added:
            list_widget.paths_changed.emit()
    def browse_dirs(self, list_widget):
        path = QFileDialog.getExistingDirectory(self, "选择文件夹喵")
        if path and path not in list_widget.get_paths():
            item = QListWidgetItem(os.path.basename(path) or path)
            item.setData(Qt.UserRole, path)
            list_widget.addItem(item)
            list_widget.paths_changed.emit()
    def clear_list(self, list_widget):
        list_widget.clear()
        list_widget.paths_changed.emit()
    def setup_page1(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        btn_back = QPushButton("返回主菜单喵"); btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        layout.addWidget(btn_back)
        group = QGroupBox("名称重命名 - 支持拖入多个文件或文件夹喵")
        gl = QVBoxLayout(group)
        self.list1 = DragDropListWidget(); self.list1.paths_changed.connect(self.update_name_preview)
        gl.addWidget(self.list1)
        hl = QHBoxLayout()
        bf = QPushButton("添加文件喵"); bf.clicked.connect(lambda: self.browse_files(self.list1))
        bd = QPushButton("添加文件夹喵"); bd.clicked.connect(lambda: self.browse_dirs(self.list1))
        bc = QPushButton("清空列表喵"); bc.clicked.connect(lambda: self.clear_list(self.list1))
        hl.addWidget(bf); hl.addWidget(bd); hl.addWidget(bc)
        gl.addLayout(hl)
        layout.addWidget(group)
        self.name1 = QLineEdit(); self.name1.setPlaceholderText("新基础名称喵..."); self.name1.textChanged.connect(self.update_name_preview)
        layout.addWidget(self.name1)
        btn_exe = QPushButton("执行名称重命名喵"); btn_exe.clicked.connect(self.run_rename_names)
        layout.addWidget(btn_exe)
        self.table1 = QTableWidget(0, 2); self.table1.setHorizontalHeaderLabels(["原文件名", "新文件名"]); self.table1.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table1)
        self.log1 = QTextEdit(); self.log1.setReadOnly(True); self.log1.setMaximumHeight(80)
        layout.addWidget(self.log1)
        self.stack.addWidget(page)
    def setup_page2(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        btn_back = QPushButton("返回主菜单喵"); btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        layout.addWidget(btn_back)
        group = QGroupBox("后缀重命名 - 支持拖入多个文件或文件夹喵")
        gl = QVBoxLayout(group)
        self.list2 = DragDropListWidget(); self.list2.paths_changed.connect(self.update_ext_preview)
        gl.addWidget(self.list2)
        hl = QHBoxLayout()
        bf = QPushButton("添加文件喵"); bf.clicked.connect(lambda: self.browse_files(self.list2))
        bd = QPushButton("添加文件夹喵"); bd.clicked.connect(lambda: self.browse_dirs(self.list2))
        bc = QPushButton("清空列表喵"); bc.clicked.connect(lambda: self.clear_list(self.list2))
        hl.addWidget(bf); hl.addWidget(bd); hl.addWidget(bc)
        gl.addLayout(hl)
        layout.addWidget(group)
        self.old_ext2 = QLineEdit(); self.old_ext2.setPlaceholderText("原后缀(留空或*代表所有)喵..."); self.old_ext2.textChanged.connect(self.update_ext_preview)
        self.new_ext2 = QLineEdit(); self.new_ext2.setPlaceholderText("新后缀(如 md)喵..."); self.new_ext2.textChanged.connect(self.update_ext_preview)
        layout.addWidget(self.old_ext2); layout.addWidget(self.new_ext2)
        btn_exe = QPushButton("执行后缀重命名喵"); btn_exe.clicked.connect(self.run_rename_exts)
        layout.addWidget(btn_exe)
        self.table2 = QTableWidget(0, 2); self.table2.setHorizontalHeaderLabels(["原文件名", "新文件名"]); self.table2.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table2)
        self.log2 = QTextEdit(); self.log2.setReadOnly(True); self.log2.setMaximumHeight(80)
        layout.addWidget(self.log2)
        self.stack.addWidget(page)
    def setup_page3(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        btn_back = QPushButton("返回主菜单喵"); btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        layout.addWidget(btn_back)
        group = QGroupBox("提取并删除上一级文件夹 - 支持拖入多个根目录喵")
        gl = QVBoxLayout(group)
        self.list3 = DragDropListWidget()
        gl.addWidget(self.list3)
        hl = QHBoxLayout()
        bd = QPushButton("添加文件夹喵"); bd.clicked.connect(lambda: self.browse_dirs(self.list3))
        bc = QPushButton("清空列表喵"); bc.clicked.connect(lambda: self.clear_list(self.list3))
        hl.addWidget(bd); hl.addWidget(bc)
        gl.addLayout(hl)
        layout.addWidget(group)
        btn_exe = QPushButton("执行提取并删除喵"); btn_exe.clicked.connect(self.run_flatten)
        layout.addWidget(btn_exe)
        self.log3 = QTextEdit(); self.log3.setReadOnly(True)
        layout.addWidget(self.log3)
        self.stack.addWidget(page)
    def update_table(self, table_widget, preview_list):
        self.current_rename_list = preview_list
        table_widget.setRowCount(len(preview_list))
        for row, (_, _, old_name, new_name) in enumerate(preview_list):
            table_widget.setItem(row, 0, QTableWidgetItem(old_name))
            table_widget.setItem(row, 1, QTableWidgetItem(new_name))
    def update_name_preview(self):
        paths = self.list1.get_paths()
        name = self.name1.text().strip()
        if paths and name:
            preview = get_rename_names_preview(paths, name)
            self.update_table(self.table1, preview)
        else:
            self.update_table(self.table1, [])
    def update_ext_preview(self):
        paths = self.list2.get_paths()
        old_e = self.old_ext2.text().strip()
        new_e = self.new_ext2.text().strip()
        if paths:
            preview = get_rename_extensions_preview(paths, old_e, new_e)
            self.update_table(self.table2, preview)
        else:
            self.update_table(self.table2, [])
    def run_rename_names(self):
        if not self.current_rename_list:
            self.log1.append("没有可执行的重命名任务喵！")
            return
        count = execute_rename(self.current_rename_list)
        self.log1.append(f"成功重命名了 {count} 个文件名称喵！")
        self.update_name_preview()
    def run_rename_exts(self):
        if not self.current_rename_list:
            self.log2.append("没有可执行的重命名任务喵！")
            return
        count = execute_rename(self.current_rename_list)
        self.log2.append(f"成功重命名了 {count} 个文件后缀喵！")
        self.update_ext_preview()
    def run_flatten(self):
        paths = self.list3.get_paths()
        if not paths:
            self.log3.append("路径不能为空喵！")
            return
        if flatten_and_remove_parent(paths):
            self.log3.append("执行完毕，内部文件已保留，空文件夹已删除喵！")
        else:
            self.log3.append("操作未能完全成功，请检查路径或权限喵。")