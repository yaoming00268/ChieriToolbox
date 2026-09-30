"""
系统增强与右键助手 - UI 界面
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QCheckBox, QMessageBox, QTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from .registry_ops import (
    is_context_menu_registered, register_context_menu, unregister_context_menu,
    is_autostart_enabled, set_autostart, run_system_health_check
)


class SystemIntegratorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.refresh_status()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # 1. Windows 右键菜单集成卡片
        menu_group = QGroupBox("资源管理器右键快捷菜单")
        menu_layout = QVBoxLayout(menu_group)
        menu_layout.setSpacing(10)

        self.lbl_menu_status = QLabel("当前状态: 检测中...")
        self.lbl_menu_status.setStyleSheet("font-size: 14px; font-weight: bold;")
        menu_layout.addWidget(self.lbl_menu_status)

        tip1 = QLabel("开启后，在任意文件夹空白处、选中文件夹或选中文件右键，可直接呼出「千绘莉的多功能工具箱」！无需管理员权限，即开即用。")
        tip1.setObjectName("helperTipLabel")
        tip1.setWordWrap(True)
        menu_layout.addWidget(tip1)

        btn_h1 = QHBoxLayout()
        self.btn_reg_menu = QPushButton("添加右键菜单")
        self.btn_reg_menu.setObjectName("primaryBtn")
        self.btn_reg_menu.clicked.connect(self._add_menu)
        btn_h1.addWidget(self.btn_reg_menu)

        self.btn_unreg_menu = QPushButton("移除右键菜单")
        self.btn_unreg_menu.clicked.connect(self._remove_menu)
        btn_h1.addWidget(self.btn_unreg_menu)
        btn_h1.addStretch()
        menu_layout.addLayout(btn_h1)

        main_layout.addWidget(menu_group)

        # 2. 开机自启卡片
        boot_group = QGroupBox("开机自启动设置")
        boot_layout = QVBoxLayout(boot_group)
        boot_layout.setSpacing(10)

        self.cb_autostart = QCheckBox("系统开机时自动启动工具箱 (自启动至托盘/后台)")
        self.cb_autostart.toggled.connect(self._on_autostart_toggled)
        boot_layout.addWidget(self.cb_autostart)

        main_layout.addWidget(boot_group)

        # 3. 系统环境健康体检报告
        health_group = QGroupBox("工具箱运行环境自检")
        health_layout = QVBoxLayout(health_group)
        health_layout.setSpacing(10)

        self.tbl_health = QTableWidget(0, 2)
        self.tbl_health.setHorizontalHeaderLabels(["检查项", "诊断状态与路径详情"])
        self.tbl_health.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_health.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        health_layout.addWidget(self.tbl_health)

        btn_h3 = QHBoxLayout()
        btn_check = QPushButton("重新体检诊断")
        btn_check.clicked.connect(self.refresh_status)
        btn_h3.addWidget(btn_check)
        btn_h3.addStretch()
        health_layout.addLayout(btn_h3)

        main_layout.addWidget(health_group, 1)

    def refresh_status(self):
        # 刷新右键状态
        has_menu = is_context_menu_registered()
        if has_menu:
            self.lbl_menu_status.setText("当前状态: 已成功注册右键菜单")
            self.lbl_menu_status.setStyleSheet("color: #16a34a; font-size: 14px; font-weight: bold;")
            self.btn_reg_menu.setEnabled(False)
            self.btn_unreg_menu.setEnabled(True)
        else:
            self.lbl_menu_status.setText("当前状态: 未注册右键菜单")
            self.lbl_menu_status.setStyleSheet("color: #71717a; font-size: 14px; font-weight: bold;")
            self.btn_reg_menu.setEnabled(True)
            self.btn_unreg_menu.setEnabled(False)

        # 刷新自启状态
        self.cb_autostart.blockSignals(True)
        self.cb_autostart.setChecked(is_autostart_enabled())
        self.cb_autostart.blockSignals(False)

        # 刷新体检表格
        diag = run_system_health_check()
        items = [
            ("Python 运行时版本", diag["python_version"]),
            ("Python 解释器路径", diag["python_path"]),
            ("FFmpeg 混流引擎", f"{diag['ffmpeg_status']} ({diag['ffmpeg_path']})"),
            ("Windows 右键菜单", diag["context_menu"]),
            ("开机自动启动", diag["autostart"]),
        ]
        self.tbl_health.setRowCount(len(items))
        for row, (k, v) in enumerate(items):
            self.tbl_health.setItem(row, 0, QTableWidgetItem(k))
            item_val = QTableWidgetItem(v)
            if "已就绪" in v or "已成功" in v or "已开启" in v:
                item_val.setForeground(Qt.GlobalColor.darkGreen)
            self.tbl_health.setItem(row, 1, item_val)

    def _add_menu(self):
        ok, msg = register_context_menu()
        if ok:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.warning(self, "失败", msg)
        self.refresh_status()

    def _remove_menu(self):
        ok, msg = unregister_context_menu()
        if ok:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.warning(self, "失败", msg)
        self.refresh_status()

    def _on_autostart_toggled(self, checked: bool):
        ok, msg = set_autostart(checked)
        if ok:
            QMessageBox.information(self, "自启动设置", msg)
        else:
            QMessageBox.warning(self, "设置失败", msg)
        self.refresh_status()

    def load_settings(self):
        self.refresh_status()

    def save_settings(self):
        pass
