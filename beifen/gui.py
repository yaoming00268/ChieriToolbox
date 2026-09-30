import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QStackedWidget
from gui_pages import PageRenameNames, PageRenameExtensions, PageFlattenFolders
class FileManagerGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("千绘莉的文件管理器喵")
        self.resize(800, 700)
        self.setup_ui()
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        self.stack = QStackedWidget(self)
        main_layout.addWidget(self.stack)
        self.setup_menu()
        self.page1 = PageRenameNames(self.stack)
        self.page2 = PageRenameExtensions(self.stack)
        self.page3 = PageFlattenFolders(self.stack)
        self.stack.addWidget(self.page1)
        self.stack.addWidget(self.page2)
        self.stack.addWidget(self.page3)
    def setup_menu(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<h2>请主人选择需要的功能喵：</h2>"))
        b1 = QPushButton("1. 批量重命名文件名称"); b1.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        b2 = QPushButton("2. 批量重命名文件后缀"); b2.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        b3 = QPushButton("3. 提取并删除该级文件夹保留子文件"); b3.clicked.connect(lambda: self.stack.setCurrentIndex(3))
        layout.addWidget(b1); layout.addWidget(b2); layout.addWidget(b3)
        layout.addStretch()
        self.stack.addWidget(page)