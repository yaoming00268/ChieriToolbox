"""
强力解锁与应用粉碎删除 - UI 界面
提供文件占用排查、锁死解除、文件覆写粉碎与顽固进程树一键强杀。
"""

import os
from typing import Optional, List, Dict
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QTabWidget, QTextEdit,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QMessageBox
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.icons import get_icon, get_pixmap
from .engine import (
    get_locking_processes, force_unlock_and_delete,
    kill_process, list_running_processes, kill_processes_by_name,
    scan_registry_installed_apps
)


class RegistryScanWorker(QThread):
    finished = Signal(list)

    def run(self):
        apps = scan_registry_installed_apps()
        self.finished.emit(apps)


class ForceKillerWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.config = ConfigManager()
        self._reg_apps: List[Dict[str, str]] = []
        self._scan_worker: Optional[RegistryScanWorker] = None
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(14)

        # 1. 顶部标题栏
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("shield", color="#ef4444", size=26))
        header_layout.addWidget(icon_lbl)

        title_lbl = QLabel("顽固应用与文件强力粉碎")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_lbl)

        badge_lbl = QLabel("Restart Manager 底层驱动级解锁")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #ef4444; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header_layout.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # 2. 分页标签栏 (文件粉碎 / 进程强杀)
        self.tabs = QTabWidget()

        # Tab 1: 文件/文件夹解锁粉碎
        tab_shred = QWidget()
        shred_layout = QVBoxLayout(tab_shred)
        shred_layout.setContentsMargins(12, 16, 12, 12)
        shred_layout.setSpacing(12)

        # 目标选择
        target_group = QGroupBox("选择锁死或待删除的目标")
        t_box = QHBoxLayout(target_group)
        self.le_target = QLineEdit()
        self.le_target.setPlaceholderText("可直接拖入任意无法删除的文件或文件夹...")
        self.le_target.textChanged.connect(self._on_target_changed)
        t_box.addWidget(self.le_target, 1)

        btn_browse_file = QPushButton("选择文件...")
        btn_browse_file.setIcon(get_icon("folder", size=14))
        btn_browse_file.clicked.connect(self._browse_file)
        t_box.addWidget(btn_browse_file)

        btn_browse_dir = QPushButton("选择文件夹...")
        btn_browse_dir.setIcon(get_icon("folder", size=14))
        btn_browse_dir.clicked.connect(self._browse_dir)
        t_box.addWidget(btn_browse_dir)

        shred_layout.addWidget(target_group)

        # 占用排查展示
        proc_group = QGroupBox("占用锁检测结果 (锁定当前目标的进程)")
        p_box = QVBoxLayout(proc_group)
        p_box.setSpacing(8)

        check_row = QHBoxLayout()
        btn_check_lock = QPushButton("排查占用进程")
        btn_check_lock.setIcon(get_icon("search", size=14))
        btn_check_lock.clicked.connect(self._check_locking)
        check_row.addWidget(btn_check_lock)

        self.lbl_lock_summary = QLabel("尚未排查")
        self.lbl_lock_summary.setStyleSheet("color: #64748b; font-size: 12px;")
        check_row.addWidget(self.lbl_lock_summary, 1)
        p_box.addLayout(check_row)

        self.table_locking = QTableWidget()
        self.table_locking.setColumnCount(3)
        self.table_locking.setHorizontalHeaderLabels(["PID", "锁定进程名称", "单项操作"])
        self.table_locking.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_locking.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_locking.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_locking.setFixedHeight(110)
        p_box.addWidget(self.table_locking)

        shred_layout.addWidget(proc_group)

        # 选项与操作
        opt_group = QGroupBox("粉碎安全选项")
        opt_box = QVBoxLayout(opt_group)
        opt_box.setSpacing(8)

        self.cb_auto_kill = QCheckBox("自动强制终止所有检测到的占用进程树并解除文件句柄锁定")
        self.cb_auto_kill.setChecked(True)
        opt_box.addWidget(self.cb_auto_kill)

        self.cb_zero_wipe = QCheckBox("覆写 0 字节粉碎 (防止数据恢复软件扫描还原)")
        opt_box.addWidget(self.cb_zero_wipe)

        shred_layout.addWidget(opt_group)

        self.btn_shred = QPushButton("强制解锁并粉碎删除")
        self.btn_shred.setObjectName("dangerBtn")
        self.btn_shred.setIcon(get_icon("trash", size=16))
        self.btn_shred.setFixedHeight(38)
        self.btn_shred.setStyleSheet("font-weight: bold;")
        self.btn_shred.clicked.connect(self._do_shred)
        shred_layout.addWidget(self.btn_shred)

        self.tabs.addTab(tab_shred, "文件解除占用与强力粉碎")

        # Tab 2: 顽固进程强杀
        tab_proc = QWidget()
        proc_layout = QVBoxLayout(tab_proc)
        proc_layout.setContentsMargins(12, 16, 12, 12)
        proc_layout.setSpacing(12)

        # 搜索与刷新栏
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("搜索进程 (名称/PID):"))
        self.le_proc_search = QLineEdit()
        self.le_proc_search.setPlaceholderText("输入进程名过滤 (例如 chrome, ffmpeg, node)...")
        self.le_proc_search.textChanged.connect(self._refresh_process_table)
        search_row.addWidget(self.le_proc_search, 1)

        btn_refresh_procs = QPushButton("刷新进程")
        btn_refresh_procs.setIcon(get_icon("refresh", size=14))
        btn_refresh_procs.clicked.connect(self._refresh_process_table)
        search_row.addWidget(btn_refresh_procs)

        btn_quick_clean = QPushButton("清理残留引擎 (ffmpeg/node)")
        btn_quick_clean.setObjectName("dangerBtn")
        btn_quick_clean.clicked.connect(self._kill_common_leak_procs)
        search_row.addWidget(btn_quick_clean)

        proc_layout.addLayout(search_row)

        # 进程表格
        self.table_all_procs = QTableWidget()
        self.table_all_procs.setColumnCount(4)
        self.table_all_procs.setHorizontalHeaderLabels(["PID", "进程映像名", "内存使用", "强杀操作"])
        self.table_all_procs.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_all_procs.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_all_procs.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_all_procs.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        proc_layout.addWidget(self.table_all_procs, 1)

        self.tabs.addTab(tab_proc, "系统顽固进程强杀")

        # Tab 3: 注册表已安装软件扫描与粉碎
        tab_reg = QWidget()
        reg_layout = QVBoxLayout(tab_reg)
        reg_layout.setContentsMargins(12, 16, 12, 12)
        reg_layout.setSpacing(12)

        reg_search_row = QHBoxLayout()
        reg_search_row.addWidget(QLabel("搜索已安装软件:"))
        self.le_reg_search = QLineEdit()
        self.le_reg_search.setPlaceholderText("过滤软件名称、路径或发布商...")
        self.le_reg_search.textChanged.connect(self._filter_reg_apps)
        reg_search_row.addWidget(self.le_reg_search, 1)

        self.btn_scan_registry = QPushButton("扫描已安装软件")
        self.btn_scan_registry.setIcon(get_icon("search", size=14))
        self.btn_scan_registry.clicked.connect(self.scan_registry_apps)
        reg_search_row.addWidget(self.btn_scan_registry)

        self.lbl_reg_count = QLabel("尚未扫描")
        self.lbl_reg_count.setStyleSheet("color: #64748b; font-size: 12px;")
        reg_search_row.addWidget(self.lbl_reg_count)
        reg_layout.addLayout(reg_search_row)

        self.table_reg_apps = QTableWidget()
        self.table_reg_apps.setColumnCount(5)
        self.table_reg_apps.setHorizontalHeaderLabels(["软件名称", "版本", "安装目录 / 主程序", "发布者", "操作"])
        self.table_reg_apps.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_reg_apps.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_reg_apps.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_reg_apps.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_reg_apps.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_reg_apps.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_reg_apps.setEditTriggers(QTableWidget.NoEditTriggers)
        reg_layout.addWidget(self.table_reg_apps, 1)

        self.tabs.addTab(tab_reg, "注册表已安装软件扫描与粉碎")
        layout.addWidget(self.tabs, 1)

        # 3. 底部状态与日志
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(self.lbl_status)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFixedHeight(85)
        self.log_console.setPlaceholderText("操作执行与安全审计日志...")
        layout.addWidget(self.log_console)

        self._refresh_process_table()

    def _browse_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择被占用的文件", "", "所有文件 (*.*)")
        if f:
            self.le_target.setText(f)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择被占用的文件夹", "")
        if d:
            self.le_target.setText(d)

    def _on_target_changed(self, text: str):
        if text.strip() and os.path.exists(text.strip()):
            self._check_locking()

    def _check_locking(self):
        target = self.le_target.text().strip()
        if not target or not os.path.exists(target):
            self.lbl_lock_summary.setText("目标路径不存在。")
            self.table_locking.setRowCount(0)
            return

        procs = get_locking_processes(target)
        self.table_locking.setRowCount(len(procs))
        if procs:
            self.lbl_lock_summary.setText(f"检测到 {len(procs)} 个进程正在占用此文件！")
            for row, (pid, name) in enumerate(procs):
                self.table_locking.setItem(row, 0, QTableWidgetItem(str(pid)))
                self.table_locking.setItem(row, 1, QTableWidgetItem(name))
                btn_kill = QPushButton("单独结束")
                btn_kill.setObjectName("dangerBtn")
                btn_kill.clicked.connect(lambda _, p=pid: self._kill_single_pid(p))
                self.table_locking.setCellWidget(row, 2, btn_kill)
        else:
            self.lbl_lock_summary.setText("未发现进程显式占用此文件 (可直接尝试粉碎删除)。")

    def _kill_single_pid(self, pid: int):
        ok, msg = kill_process(pid, force_tree=True)
        self.log_console.append(f"[强杀] {msg}")
        self._check_locking()

    def _do_shred(self):
        target = self.le_target.text().strip()
        if not target or not os.path.exists(target):
            self.lbl_status.setText("请先选择有效的文件或文件夹。")
            return

        # 危险防误触二次确认
        confirm = QMessageBox.question(
            self,
            "确认粉碎删除",
            f"确定要彻底粉碎删除以下目标吗？此操作无法撤销！\n\n{target}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        self.btn_shred.setEnabled(False)
        self.lbl_status.setText("正在执行强力解锁与粉碎...")
        self.log_console.append(f"[粉碎] 开始解锁并删除: {target}")

        ok, msg = force_unlock_and_delete(
            target_path=target,
            shred=self.cb_zero_wipe.isChecked(),
            auto_kill_locking_procs=self.cb_auto_kill.isChecked()
        )

        self.btn_shred.setEnabled(True)
        if ok:
            self.lbl_status.setText("粉碎删除成功！")
            self.log_console.append(f"[成功] {msg}")
            self.table_locking.setRowCount(0)
            self.lbl_lock_summary.setText("目标已彻底移除。")
        else:
            self.lbl_status.setText("删除遇到问题。")
            self.log_console.append(f"[警告] {msg}")

    def _refresh_process_table(self):
        kw = self.le_proc_search.text().strip()
        procs = list_running_processes(kw)

        self.table_all_procs.setRowCount(len(procs))
        for row, p in enumerate(procs):
            pid = p["pid"]
            self.table_all_procs.setItem(row, 0, QTableWidgetItem(str(pid)))
            self.table_all_procs.setItem(row, 1, QTableWidgetItem(p["name"]))
            self.table_all_procs.setItem(row, 2, QTableWidgetItem(p["memory"]))

            btn_kill = QPushButton("强杀进程树")
            btn_kill.setObjectName("dangerBtn")
            btn_kill.clicked.connect(lambda _, p_id=pid: self._kill_proc_tree(p_id))
            self.table_all_procs.setCellWidget(row, 3, btn_kill)

    def _kill_proc_tree(self, pid: int):
        ok, msg = kill_process(pid, force_tree=True)
        self.log_console.append(f"[进程强杀] {msg}")
        self._refresh_process_table()

    def _kill_common_leak_procs(self):
        for name in ("ffmpeg.exe", "chromedriver.exe", "node.exe"):
            kill_processes_by_name(name)
        self.log_console.append("[清理] 已批量清理常见残留开发进程。")
        self._refresh_process_table()

    def scan_registry_apps(self):
        self.btn_scan_registry.setEnabled(False)
        self.lbl_reg_count.setText("正在扫描已安装软件注册表...")
        self._scan_worker = RegistryScanWorker()
        self._scan_worker.finished.connect(self._on_scan_apps_finished)
        self._scan_worker.start()

    def _on_scan_apps_finished(self, apps: list):
        self._reg_apps = apps
        self.btn_scan_registry.setEnabled(True)
        self.lbl_reg_count.setText(f"共发现 {len(apps)} 个已安装软件")
        self._filter_reg_apps()

    def _filter_reg_apps(self):
        kw = self.le_reg_search.text().strip().lower()
        if not kw:
            matched = self._reg_apps
        else:
            matched = [
                a for a in self._reg_apps
                if kw in a.get("name", "").lower()
                or kw in a.get("install_location", "").lower()
                or kw in a.get("publisher", "").lower()
                or kw in a.get("exe_path", "").lower()
            ]
        self._render_reg_apps_table(matched)

    def _render_reg_apps_table(self, apps: list):
        self.table_reg_apps.setRowCount(len(apps))
        for row, app in enumerate(apps):
            self.table_reg_apps.setItem(row, 0, QTableWidgetItem(app.get("name", "")))
            self.table_reg_apps.setItem(row, 1, QTableWidgetItem(app.get("version", "")))

            loc = app.get("install_location") or app.get("exe_path") or ""
            self.table_reg_apps.setItem(row, 2, QTableWidgetItem(loc))
            self.table_reg_apps.setItem(row, 3, QTableWidgetItem(app.get("publisher", "")))

            action_widget = QWidget()
            h_layout = QHBoxLayout(action_widget)
            h_layout.setContentsMargins(4, 2, 4, 2)
            h_layout.setSpacing(6)

            btn_to_target = QPushButton("选为粉碎目标")
            btn_to_target.setToolTip("将此软件安装目录或主程序填入解锁粉碎页")
            btn_to_target.clicked.connect(lambda _, a=app: self._fill_reg_app_to_target(a))
            h_layout.addWidget(btn_to_target)

            btn_kill_app = QPushButton("结束相关进程")
            btn_kill_app.setObjectName("dangerBtn")
            btn_kill_app.setToolTip("尝试查杀与此软件主程序同名的所有活动进程")
            btn_kill_app.clicked.connect(lambda _, a=app: self._kill_reg_app_procs(a))
            h_layout.addWidget(btn_kill_app)

            btn_del_direct = QPushButton("强制粉碎删除")
            btn_del_direct.setObjectName("dangerBtn")
            btn_del_direct.setToolTip("直接对安装目录执行驱动级解锁与彻底粉碎")
            btn_del_direct.clicked.connect(lambda _, a=app: self._shred_reg_app_direct(a))
            h_layout.addWidget(btn_del_direct)

            self.table_reg_apps.setCellWidget(row, 4, action_widget)

    def _fill_reg_app_to_target(self, app: dict):
        path = app.get("install_location") or app.get("exe_path")
        if path:
            self.tabs.setCurrentIndex(0)
            self.le_target.setText(path)
            self.log_console.append(f"[目标] 已将软件路径导入粉碎列表: {path}")

    def _kill_reg_app_procs(self, app: dict):
        exe_path = app.get("exe_path")
        name = os.path.basename(exe_path) if exe_path else f"{app.get('name')}.exe"
        if name:
            killed = kill_processes_by_name(name)
            self.log_console.append(f"[进程] 已尝试终止软件进程 '{name}' (共清理 {killed} 个实例)")

    def _shred_reg_app_direct(self, app: dict):
        path = app.get("install_location") or app.get("exe_path")
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "路径无效", f"未找到软件的有效物理路径或该路径已不存在：\n{path}")
            return

        confirm = QMessageBox.question(
            self,
            "确认粉碎删除软件",
            f"确定要彻底粉碎删除已安装软件【{app.get('name')}】的目录或主程序吗？\n\n路径：{path}\n此操作无法撤销！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        self.lbl_status.setText(f"正在粉碎软件: {app.get('name')}...")
        self.log_console.append(f"[软件粉碎] 开始解锁并删除: {path}")

        ok, msg = force_unlock_and_delete(
            target_path=path,
            shred=self.cb_zero_wipe.isChecked(),
            auto_kill_locking_procs=self.cb_auto_kill.isChecked()
        )
        if ok:
            self.lbl_status.setText(f"软件【{app.get('name')}】粉碎删除成功！")
            self.log_console.append(f"[成功] {msg}")
            self.scan_registry_apps()
        else:
            self.lbl_status.setText("删除遇到问题。")
            self.log_console.append(f"[警告] {msg}")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                fp = urls[0].toLocalFile()
                self.tabs.setCurrentIndex(0)
                self.le_target.setText(fp)
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def handle_initial_paths(self, paths: list):
        if paths:
            self.tabs.setCurrentIndex(0)
            self.le_target.setText(str(paths[0]))

    def load_settings(self):
        cfg = self.config.get_plugin_config("force_killer", {})
        tab_idx = cfg.get("tab_idx", 0)
        if 0 <= tab_idx < self.tabs.count():
            self.tabs.setCurrentIndex(tab_idx)

    def save_settings(self):
        cfg = {
            "tab_idx": self.tabs.currentIndex()
        }
        self.config.set_plugin_config("force_killer", cfg)
