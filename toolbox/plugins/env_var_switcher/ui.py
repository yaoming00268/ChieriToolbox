"""
环境变量切换管家 (Environment Variable Switcher) - UI 界面
提供 Windows 用户/系统环境变量可视化、PATH 幽灵路径体检清理、一键备份还原与方案快速切换。
"""

import os
import sys
import json
from typing import Optional, Dict, List, Tuple, Any
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QTabWidget, QDialog, QComboBox, QPlainTextEdit, QMessageBox,
    QFileDialog, QFrame, QGroupBox
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.icons import get_icon, get_pixmap
from .engine import (
    is_admin, get_user_variables, get_system_variables,
    set_variable, delete_variable, broadcast_environment_change,
    parse_path_entries, clean_path_entries, create_env_backup,
    restore_env_backup
)


class EditVarDialog(QDialog):
    """环境变量新建/编辑对话框"""
    def __init__(self, name: str = "", value: str = "", scope: str = "user", reg_type: int = 1, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑环境变量" if name else "新建环境变量")
        self.resize(520, 360)
        self.scope = scope
        self.reg_type = reg_type

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # 作用域与类型
        row_scope = QHBoxLayout()
        row_scope.addWidget(QLabel("作用域:"))
        self.combo_scope = QComboBox()
        self.combo_scope.addItems(["用户级 (User)", "系统级 (System)"])
        self.combo_scope.setCurrentIndex(1 if scope.lower() == "system" else 0)
        row_scope.addWidget(self.combo_scope)

        row_scope.addWidget(QLabel("类型:"))
        self.combo_type = QComboBox()
        self.combo_type.addItems(["REG_SZ (标准字符串)", "REG_EXPAND_SZ (可扩展环境变量)"])
        self.combo_type.setCurrentIndex(1 if reg_type == 2 else 0)
        row_scope.addWidget(self.combo_type)
        row_scope.addStretch()
        layout.addLayout(row_scope)

        # 变量名
        layout.addWidget(QLabel("变量名称 (Variable Name):"))
        self.le_name = QLineEdit(name)
        self.le_name.setPlaceholderText("例如: JAVA_HOME, PYTHON_PATH")
        if name:
            self.le_name.setReadOnly(True)  # 修改已存在变量时不可改名
        layout.addWidget(self.le_name)

        # 变量值
        layout.addWidget(QLabel("变量值 (Variable Value):"))
        self.edit_val = QPlainTextEdit()
        self.edit_val.setPlainText(value)
        self.edit_val.setPlaceholderText("输入或粘贴变量值，多个路径用分号 (;) 分隔...")
        layout.addWidget(self.edit_val, 1)

        # 便捷选路工具按钮
        row_tools = QHBoxLayout()
        btn_pick_dir = QPushButton("浏览目录...")
        btn_pick_dir.setIcon(get_icon("folder", size=13))
        btn_pick_dir.clicked.connect(self._pick_dir)
        row_tools.addWidget(btn_pick_dir)

        btn_pick_file = QPushButton("浏览文件...")
        btn_pick_file.setIcon(get_icon("file-plus", size=13))
        btn_pick_file.clicked.connect(self._pick_file)
        row_tools.addWidget(btn_pick_file)
        row_tools.addStretch()
        layout.addLayout(row_tools)

        # 底部按钮
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_ok = QPushButton("保存生效")
        btn_ok.setObjectName("primaryBtn")
        btn_ok.clicked.connect(self.accept)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择目录")
        if d:
            curr = self.edit_val.toPlainText().strip()
            if curr:
                self.edit_val.setPlainText(curr + ";" + d)
            else:
                self.edit_val.setPlainText(d)

    def _pick_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择文件")
        if f:
            curr = self.edit_val.toPlainText().strip()
            if curr:
                self.edit_val.setPlainText(curr + ";" + f)
            else:
                self.edit_val.setPlainText(f)

    def get_data(self) -> Tuple[str, str, str, int]:
        name = self.le_name.text().strip()
        val = self.edit_val.toPlainText().strip()
        scope = "system" if self.combo_scope.currentIndex() == 1 else "user"
        rtype = 2 if self.combo_type.currentIndex() == 1 else 1
        return name, val, scope, rtype


class EnvVarSwitcherWidget(QWidget):
    PLUGIN_ID = "env_var_switcher"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self.cached_user_vars: Dict[str, Tuple[str, int]] = {}
        self.cached_sys_vars: Dict[str, Tuple[str, int]] = {}
        self.profiles: List[Dict[str, Any]] = []

        self.init_ui()
        self.load_settings()
        self._refresh_all()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 14, 18, 14)
        root_layout.setSpacing(10)

        # 1. 顶部 Header
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("sliders", color="#3b82f6", size=26))
        header.addWidget(icon_lbl)

        title_lbl = QLabel("环境变量切换管家")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title_lbl)

        admin_badge = QLabel("管理员模式 (完全读写)" if is_admin() else "普通权限 (系统变量只读)")
        admin_badge.setFixedHeight(22)
        admin_style = (
            "background-color: #10b981; color: #ffffff;" if is_admin()
            else "background-color: #f59e0b; color: #ffffff;"
        )
        admin_badge.setStyleSheet(f"{admin_style} border-radius: 9px; padding: 2px 8px; font-size: 11px; font-weight: bold;")
        header.addWidget(admin_badge, 0, Qt.AlignVCenter)

        header.addStretch()
        root_layout.addLayout(header)

        # 2. 快捷操作工具条
        tb_layout = QHBoxLayout()
        tb_layout.setSpacing(8)

        self.btn_new = QPushButton("新建变量...")
        self.btn_new.setObjectName("primaryBtn")
        self.btn_new.setIcon(get_icon("plus", color="#ffffff", size=13))
        self.btn_new.clicked.connect(self._create_new_var)
        tb_layout.addWidget(self.btn_new)

        self.btn_edit = QPushButton("编辑选中")
        self.btn_edit.setIcon(get_icon("pencil", size=13))
        self.btn_edit.clicked.connect(self._edit_selected_var)
        tb_layout.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("删除选中")
        self.btn_delete.setIcon(get_icon("trash", size=13))
        self.btn_delete.clicked.connect(self._delete_selected_var)
        tb_layout.addWidget(self.btn_delete)

        self.btn_backup = QPushButton("一键备份")
        self.btn_backup.setIcon(get_icon("save", size=13))
        self.btn_backup.clicked.connect(self._do_backup)
        tb_layout.addWidget(self.btn_backup)

        self.btn_restore = QPushButton("还原快照...")
        self.btn_restore.setIcon(get_icon("refresh", size=13))
        self.btn_restore.clicked.connect(self._do_restore)
        tb_layout.addWidget(self.btn_restore)

        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setIcon(get_icon("refresh", size=13))
        self.btn_refresh.clicked.connect(self._refresh_all)
        tb_layout.addWidget(self.btn_refresh)

        tb_layout.addStretch()

        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText("过滤变量名或值...")
        self.le_search.setMaximumWidth(220)
        self.le_search.textChanged.connect(self._filter_tables)
        tb_layout.addWidget(self.le_search)

        root_layout.addLayout(tb_layout)

        # 3. 标签页
        self.tabs = QTabWidget()
        root_layout.addWidget(self.tabs, 1)

        # Tab 1: 用户环境变量
        self.tab_user = QWidget()
        self._setup_user_tab()
        self.tabs.addTab(self.tab_user, get_icon("tools", size=14), "用户环境变量")

        # Tab 2: 系统环境变量
        self.tab_sys = QWidget()
        self._setup_sys_tab()
        self.tabs.addTab(self.tab_sys, get_icon("system", size=14), "系统环境变量")

        # Tab 3: PATH 专线深度体检
        self.tab_path = QWidget()
        self._setup_path_tab()
        self.tabs.addTab(self.tab_path, get_icon("sparkles", size=14), "PATH 专线体检与优化")

        # Tab 4: 方案切换
        self.tab_profiles = QWidget()
        self._setup_profiles_tab()
        self.tabs.addTab(self.tab_profiles, get_icon("sliders", size=14), "环境预设方案切换")

    # =========================================================================
    # Tab 1: 用户环境变量
    # =========================================================================
    def _setup_user_tab(self):
        layout = QVBoxLayout(self.tab_user)
        layout.setContentsMargins(6, 6, 6, 6)
        self.table_user = self._create_var_table()
        self.table_user.doubleClicked.connect(lambda: self._edit_var_from_table(self.table_user, "user"))
        layout.addWidget(self.table_user)

    # =========================================================================
    # Tab 2: 系统环境变量
    # =========================================================================
    def _setup_sys_tab(self):
        layout = QVBoxLayout(self.tab_sys)
        layout.setContentsMargins(6, 6, 6, 6)
        self.table_sys = self._create_var_table()
        self.table_sys.doubleClicked.connect(lambda: self._edit_var_from_table(self.table_sys, "system"))
        layout.addWidget(self.table_sys)

    def _create_var_table(self) -> QTableWidget:
        tbl = QTableWidget()
        tbl.setColumnCount(3)
        tbl.setHorizontalHeaderLabels(["变量名称", "变量值", "注册表类型"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        return tbl

    # =========================================================================
    # Tab 3: PATH 专线体检与优化
    # =========================================================================
    def _setup_path_tab(self):
        layout = QVBoxLayout(self.tab_path)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 顶部操作行
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("<b>PATH 作用域:</b>"))
        self.combo_path_scope = QComboBox()
        self.combo_path_scope.addItems(["用户 PATH (User)", "系统 PATH (System)"])
        self.combo_path_scope.currentIndexChanged.connect(self._load_path_table)
        top_row.addWidget(self.combo_path_scope)

        self.btn_add_path_entry = QPushButton("添加路径...")
        self.btn_add_path_entry.setIcon(get_icon("plus", size=13))
        self.btn_add_path_entry.clicked.connect(self._add_path_item)
        top_row.addWidget(self.btn_add_path_entry)

        self.btn_path_up = QPushButton("上移")
        self.btn_path_up.setIcon(get_icon("arrow-left", size=13))
        self.btn_path_up.clicked.connect(lambda: self._move_path_item(-1))
        top_row.addWidget(self.btn_path_up)

        self.btn_path_down = QPushButton("下移")
        self.btn_path_down.setIcon(get_icon("chevron-right", size=13))
        self.btn_path_down.clicked.connect(lambda: self._move_path_item(1))
        top_row.addWidget(self.btn_path_down)

        self.btn_delete_path_entry = QPushButton("移除选中")
        self.btn_delete_path_entry.setIcon(get_icon("trash", size=13))
        self.btn_delete_path_entry.clicked.connect(self._delete_path_item)
        top_row.addWidget(self.btn_delete_path_entry)

        self.btn_clean_path = QPushButton("一键清理失效与冗余")
        self.btn_clean_path.setObjectName("primaryBtn")
        self.btn_clean_path.setIcon(get_icon("sparkles", color="#ffffff", size=13))
        self.btn_clean_path.clicked.connect(self._clean_path_action)
        top_row.addWidget(self.btn_clean_path)

        self.btn_save_path = QPushButton("保存生效 PATH")
        self.btn_save_path.setIcon(get_icon("save", size=13))
        self.btn_save_path.clicked.connect(self._save_path_action)
        top_row.addWidget(self.btn_save_path)

        top_row.addStretch()
        layout.addLayout(top_row)

        # 表格
        self.table_path = QTableWidget()
        self.table_path.setColumnCount(4)
        self.table_path.setHorizontalHeaderLabels(["序号", "物理目录路径", "状态诊断", "识别环境"])
        self.table_path.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_path.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_path.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_path.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_path.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_path.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table_path, 1)

    # =========================================================================
    # Tab 4: 方案快速切换
    # =========================================================================
    def _setup_profiles_tab(self):
        layout = QVBoxLayout(self.tab_profiles)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        tip_lbl = QLabel(
            "<b>多套开发环境一键瞬间切换</b><br>"
            "<span style='color:#64748b; font-size:12px;'>"
            "快速在 Python 3.10 / 3.12、Node.js 18 / 20、Java 17 或 C++ 工具链之间自由切换，"
            "自动更新用户变量并全局广播生效。"
            "</span>"
        )
        layout.addWidget(tip_lbl)

        p_row = QHBoxLayout()
        self.combo_profiles = QComboBox()
        self.combo_profiles.setMinimumWidth(260)
        p_row.addWidget(self.combo_profiles)

        btn_apply = QPushButton("一键激活此方案")
        btn_apply.setObjectName("primaryBtn")
        btn_apply.setIcon(get_icon("check", color="#ffffff", size=13))
        btn_apply.clicked.connect(self._apply_current_profile)
        p_row.addWidget(btn_apply)

        btn_save_current_as = QPushButton("保存当前环境为新方案...")
        btn_save_current_as.setIcon(get_icon("save", size=13))
        btn_save_current_as.clicked.connect(self._save_profile_dialog)
        p_row.addWidget(btn_save_current_as)

        btn_del_profile = QPushButton("删除方案")
        btn_del_profile.setIcon(get_icon("trash", size=13))
        btn_del_profile.clicked.connect(self._delete_profile)
        p_row.addWidget(btn_del_profile)

        p_row.addStretch()
        layout.addLayout(p_row)

        grp_details = QGroupBox("方案配置预览")
        g_layout = QVBoxLayout(grp_details)
        self.edit_profile_preview = QPlainTextEdit()
        self.edit_profile_preview.setReadOnly(True)
        g_layout.addWidget(self.edit_profile_preview)
        layout.addWidget(grp_details, 1)

        self.combo_profiles.currentIndexChanged.connect(self._update_profile_preview)

    # =========================================================================
    # 核心数据刷新与渲染
    # =========================================================================
    def _refresh_all(self):
        self.cached_user_vars = get_user_variables()
        self.cached_sys_vars = get_system_variables()
        self._populate_table(self.table_user, self.cached_user_vars)
        self._populate_table(self.table_sys, self.cached_sys_vars)
        self._load_path_table()

    def _populate_table(self, table: QTableWidget, var_dict: Dict[str, Tuple[str, int]]):
        table.setRowCount(0)
        query = self.le_search.text().strip().lower()

        for name in sorted(var_dict.keys(), key=lambda x: x.upper()):
            val, rtype = var_dict[name]
            if query and query not in name.lower() and query not in val.lower():
                continue

            r = table.rowCount()
            table.insertRow(r)
            item_name = QTableWidgetItem(name)
            item_name.setFont(QFont("Segoe UI", 9, QFont.Bold))
            table.setItem(r, 0, item_name)

            item_val = QTableWidgetItem(val)
            item_val.setToolTip(val)
            table.setItem(r, 1, item_val)

            type_name = "REG_EXPAND_SZ" if rtype == 2 else "REG_SZ"
            item_type = QTableWidgetItem(type_name)
            table.setItem(r, 2, item_type)

    def _filter_tables(self):
        self._populate_table(self.table_user, self.cached_user_vars)
        self._populate_table(self.table_sys, self.cached_sys_vars)

    # =========================================================================
    # 增删改操作
    # =========================================================================
    def _create_new_var(self):
        active_tab = self.tabs.currentIndex()
        default_scope = "system" if active_tab == 1 else "user"
        dlg = EditVarDialog(scope=default_scope, parent=self)
        if dlg.exec() == QDialog.Accepted:
            name, val, scope, rtype = dlg.get_data()
            if name:
                ok, msg = set_variable(name, val, scope=scope, reg_type=rtype)
                if ok:
                    QMessageBox.information(self, "成功", msg)
                    self._refresh_all()
                else:
                    QMessageBox.warning(self, "设置失败", msg)

    def _edit_selected_var(self):
        active_tab = self.tabs.currentIndex()
        if active_tab == 0:
            self._edit_var_from_table(self.table_user, "user")
        elif active_tab == 1:
            self._edit_var_from_table(self.table_sys, "system")

    def _edit_var_from_table(self, table: QTableWidget, scope: str):
        row = table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一行变量")
            return
        name = table.item(row, 0).text()
        val = table.item(row, 1).text()
        rtype_str = table.item(row, 2).text()
        rtype = 2 if "EXPAND" in rtype_str else 1

        dlg = EditVarDialog(name=name, value=val, scope=scope, reg_type=rtype, parent=self)
        if dlg.exec() == QDialog.Accepted:
            _, new_val, new_scope, new_rtype = dlg.get_data()
            ok, msg = set_variable(name, new_val, scope=new_scope, reg_type=new_rtype)
            if ok:
                QMessageBox.information(self, "成功", msg)
                self._refresh_all()
            else:
                QMessageBox.warning(self, "保存失败", msg)

    def _delete_selected_var(self):
        active_tab = self.tabs.currentIndex()
        table = self.table_sys if active_tab == 1 else self.table_user
        scope = "system" if active_tab == 1 else "user"

        row = table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中要删除的环境变量")
            return

        name = table.item(row, 0).text()
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要永久删除 [{scope.upper()}] 环境变量 【{name}】 吗？\n此操作不可逆！",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            ok, msg = delete_variable(name, scope=scope)
            if ok:
                QMessageBox.information(self, "成功", msg)
                self._refresh_all()
            else:
                QMessageBox.warning(self, "删除失败", msg)

    # =========================================================================
    # PATH 专题体检逻辑
    # =========================================================================
    def _load_path_table(self):
        is_sys = self.combo_path_scope.currentIndex() == 1
        var_dict = self.cached_sys_vars if is_sys else self.cached_user_vars
        path_str = ""
        for k in ("Path", "PATH", "path"):
            if k in var_dict:
                path_str = var_dict[k][0]
                break

        entries = parse_path_entries(path_str)
        self.table_path.setRowCount(0)

        for e in entries:
            r = self.table_path.rowCount()
            self.table_path.insertRow(r)

            # 序号
            self.table_path.setItem(r, 0, QTableWidgetItem(str(e["index"])))

            # 物理目录
            item_raw = QTableWidgetItem(e["raw"])
            item_raw.setToolTip(f"展开路径: {e['expanded']}")
            self.table_path.setItem(r, 1, item_raw)

            # 状态诊断
            item_status = QTableWidgetItem(e["status"])
            if not e["is_valid"]:
                item_status.setForeground(QBrush(QColor("#ef4444")))
            elif e["is_duplicate"]:
                item_status.setForeground(QBrush(QColor("#f59e0b")))
            else:
                item_status.setForeground(QBrush(QColor("#10b981")))
            self.table_path.setItem(r, 2, item_status)

            # 工具标签
            tag_item = QTableWidgetItem(e["tool_tag"] or "-")
            if e["tool_tag"]:
                tag_item.setForeground(QBrush(QColor("#38bdf8")))
            self.table_path.setItem(r, 3, tag_item)

    def _move_path_item(self, direction: int):
        row = self.table_path.currentRow()
        if row < 0:
            return
        target = row + direction
        if 0 <= target < self.table_path.rowCount():
            # 交换数据行
            raw1 = self.table_path.item(row, 1).text()
            raw2 = self.table_path.item(target, 1).text()
            self.table_path.item(row, 1).setText(raw2)
            self.table_path.item(target, 1).setText(raw1)
            self.table_path.selectRow(target)

    def _add_path_item(self):
        d = QFileDialog.getExistingDirectory(self, "选择要添加到 PATH 的目录")
        if d:
            r = self.table_path.rowCount()
            self.table_path.insertRow(r)
            self.table_path.setItem(r, 0, QTableWidgetItem(str(r + 1)))
            self.table_path.setItem(r, 1, QTableWidgetItem(d))
            self.table_path.setItem(r, 2, QTableWidgetItem("正常 (新增)"))
            self.table_path.setItem(r, 3, QTableWidgetItem("-"))

    def _delete_path_item(self):
        row = self.table_path.currentRow()
        if row >= 0:
            self.table_path.removeRow(row)

    def _clean_path_action(self):
        entries = [self.table_path.item(r, 1).text() for r in range(self.table_path.rowCount())]
        cleaned, stats = clean_path_entries(entries, remove_dead=True, remove_duplicates=True)
        # 刷新表格
        path_str = ";".join(cleaned)
        self.combo_path_scope.blockSignals(True)
        entries_data = parse_path_entries(path_str)
        self.table_path.setRowCount(0)
        for e in entries_data:
            r = self.table_path.rowCount()
            self.table_path.insertRow(r)
            self.table_path.setItem(r, 0, QTableWidgetItem(str(e["index"])))
            self.table_path.setItem(r, 1, QTableWidgetItem(e["raw"]))
            item_st = QTableWidgetItem(e["status"])
            item_st.setForeground(QBrush(QColor("#10b981")))
            self.table_path.setItem(r, 2, item_st)
            self.table_path.setItem(r, 3, QTableWidgetItem(e["tool_tag"] or "-"))
        self.combo_path_scope.blockSignals(False)

        QMessageBox.information(
            self, "体检清理完成",
            f"已清除 {stats['removed_dead']} 个失效幽灵路径，消除 {stats['removed_duplicates']} 个重复冗余项！\n"
            "请确认无误后点击【保存生效 PATH】写入系统。"
        )

    def _save_path_action(self):
        is_sys = self.combo_path_scope.currentIndex() == 1
        scope = "system" if is_sys else "user"
        entries = [self.table_path.item(r, 1).text() for r in range(self.table_path.rowCount())]
        new_path_str = ";".join(entries)

        # 找到原本使用的 PATH 变量名称大小写
        var_dict = self.cached_sys_vars if is_sys else self.cached_user_vars
        target_name = "Path"
        for k in ("Path", "PATH", "path"):
            if k in var_dict:
                target_name = k
                break

        ok, msg = set_variable(target_name, new_path_str, scope=scope, reg_type=2)
        if ok:
            QMessageBox.information(self, "成功", f"[{scope.upper()}] PATH 已更新并广播生效！")
            self._refresh_all()
        else:
            QMessageBox.warning(self, "保存失败", msg)

    # =========================================================================
    # 快照备份与还原
    # =========================================================================
    def _do_backup(self):
        ok, path, payload = create_env_backup()
        if ok:
            QMessageBox.information(
                self, "备份成功",
                f"已完整备份当前系统与用户环境变量快照！\n保存位置:\n{path}"
            )
        else:
            QMessageBox.warning(self, "备份失败", f"无法创建备份快照: {path}")

    def _do_restore(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择要还原的环境快照文件",
            os.path.join(os.path.expanduser("~"), ".chieri_toolbox", "env_backups"),
            "快照文件 (*.json);;所有文件 (*.*)"
        )
        if path and os.path.isfile(path):
            ok, msg = restore_env_backup(path, restore_user=True, restore_system=is_admin())
            if ok:
                QMessageBox.information(self, "还原结果", msg)
                self._refresh_all()
            else:
                QMessageBox.warning(self, "还原失败", msg)

    # =========================================================================
    # 方案切换
    # =========================================================================
    def _load_default_profiles(self):
        self.profiles = [
            {
                "id": "default",
                "name": "标准默认开发方案",
                "description": "保持当前 Windows 用户与系统的标准默认环境",
                "variables": {}
            },
            {
                "id": "python_fast",
                "name": "Python 高性能运行方案",
                "description": "设置 PYTHONUNBUFFERED=1, PYTHONDONTWRITEBYTECODE=0, PIP_DISABLE_PIP_VERSION_CHECK=1",
                "variables": {
                    "PYTHONUNBUFFERED": "1",
                    "PIP_DISABLE_PIP_VERSION_CHECK": "1"
                }
            },
            {
                "id": "node_dev",
                "name": "Node.js 全栈方案",
                "description": "设置 NODE_ENV=development, CHOKIDAR_USEPOLLING=0",
                "variables": {
                    "NODE_ENV": "development",
                    "CHOKIDAR_USEPOLLING": "0"
                }
            }
        ]

    def _update_profiles_combo(self):
        self.combo_profiles.blockSignals(True)
        self.combo_profiles.clear()
        for p in self.profiles:
            self.combo_profiles.addItem(p["name"], p)
        self.combo_profiles.blockSignals(False)
        self._update_profile_preview()

    def _update_profile_preview(self):
        idx = self.combo_profiles.currentIndex()
        if idx >= 0 and idx < len(self.profiles):
            p = self.profiles[idx]
            self.edit_profile_preview.setPlainText(json.dumps(p, indent=2, ensure_ascii=False))

    def _apply_current_profile(self):
        idx = self.combo_profiles.currentIndex()
        if idx < 0:
            return
        p = self.profiles[idx]
        applied = 0
        for k, v in p.get("variables", {}).items():
            ok, _ = set_variable(k, str(v), scope="user", broadcast=False)
            if ok:
                applied += 1
        broadcast_environment_change()
        QMessageBox.information(self, "方案激活成功", f"方案【{p['name']}】已成功激活，生效 {applied} 项定制变量！")
        self._refresh_all()

    def _save_profile_dialog(self):
        name, ok = QFileDialog.getSaveFileName(self, "选择方案存储文件", "my_env_profile.json", "JSON (*.json)")
        if name and ok:
            p_data = {
                "id": f"profile_{len(self.profiles)+1}",
                "name": os.path.basename(name).replace(".json", ""),
                "description": "自定义环境方案快照",
                "variables": {k: v[0] for k, v in self.cached_user_vars.items()}
            }
            try:
                with open(name, "w", encoding="utf-8") as f:
                    json.dump(p_data, f, indent=2, ensure_ascii=False)
                self.profiles.append(p_data)
                self._update_profiles_combo()
                self.save_settings()
                QMessageBox.information(self, "成功", f"方案已保存至 {name}")
            except Exception as e:
                QMessageBox.warning(self, "保存失败", f"异常: {e}")

    def _delete_profile(self):
        idx = self.combo_profiles.currentIndex()
        if idx > 0 and idx < len(self.profiles):
            del self.profiles[idx]
            self._update_profiles_combo()
            self.save_settings()

    # =========================================================================
    # 持久化生命周期
    # =========================================================================
    def load_settings(self):
        cfg = self.config_manager.get_plugin_config(self.PLUGIN_ID, {})
        saved_profiles = cfg.get("profiles")
        if saved_profiles and isinstance(saved_profiles, list):
            self.profiles = saved_profiles
        else:
            self._load_default_profiles()
        self._update_profiles_combo()

    def save_settings(self):
        cfg = {
            "profiles": self.profiles
        }
        self.config_manager.set_plugin_config(self.PLUGIN_ID, cfg)

    def save_config(self):
        self.save_settings()

    def load_config(self):
        self.load_settings()

    def cleanup(self):
        pass
