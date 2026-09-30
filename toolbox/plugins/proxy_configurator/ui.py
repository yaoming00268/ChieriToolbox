"""
应用代理配置工具 - UI 界面
提供 Windows 系统代理、环境变量代理、Git 全局代理与 pip 镜像代理的一键开启、关闭与网络延迟检测；
支持注册表已安装应用扫描与外部程序导入，提供单独软件进程代理注入启动；
支持网站/域名独立代理路由，以根网址为基准，所有子网址与子路由自适应生效，支持已有网址查看与任一网址删除。
"""

import os
from typing import Optional, List, Dict, Any
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QComboBox, QTextEdit,
    QGridLayout, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QDialog, QSizePolicy, QTabWidget,
    QFileDialog, QScrollArea
)

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.icons import get_icon, get_pixmap
from .engine import (
    get_system_proxy_status, set_system_proxy,
    get_env_proxy_status, set_env_proxy,
    get_git_proxy_status, set_git_proxy,
    get_pip_status, set_pip_proxy, set_pip_mirror,
    PIP_MIRRORS, test_proxy_latency,
    extract_root_domain, matches_root_domain,
    scan_registry_installed_apps, launch_app_with_proxy,
    generate_pac_script, export_pac_file,
    get_pac_proxy_status, set_pac_proxy
)


class LatencyTestWorker(QThread):
    finished = Signal(bool, float, str)

    def __init__(self, proxy_addr: str, test_url: str):
        super().__init__()
        self.proxy_addr = proxy_addr
        self.test_url = test_url

    def run(self):
        ok, elapsed, msg = test_proxy_latency(self.proxy_addr, self.test_url)
        self.finished.emit(ok, elapsed, msg)


class RegistryAppScanWorker(QThread):
    finished = Signal(list)

    def run(self):
        apps = scan_registry_installed_apps()
        self.finished.emit(apps)


class RegistryAppSelectDialog(QDialog):
    """扫描并选择注册表已安装软件对话框"""
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("扫描注册表已安装应用")
        self.resize(750, 480)
        self.selected_app: Optional[Dict[str, str]] = None
        self._all_apps: List[Dict[str, str]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # 搜索过滤栏
        search_row = QHBoxLayout()
        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText("过滤已安装应用名称、发布者或安装目录...")
        self.le_search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.le_search.textChanged.connect(self._filter_apps)
        search_row.addWidget(self.le_search, 1)

        self.lbl_status = QLabel("正在扫描注册表...")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 12px;")
        search_row.addWidget(self.lbl_status)
        layout.addLayout(search_row)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["软件名称", "版本", "主执行程序 / 路径", "发布商"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_confirm)
        layout.addWidget(self.table, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton("确认选择并导入")
        self.btn_ok.setObjectName("primaryBtn")
        self.btn_ok.setIcon(get_icon("check", size=14))
        self.btn_ok.clicked.connect(self._on_confirm)
        btn_row.addWidget(self.btn_ok)
        layout.addLayout(btn_row)

        # 启动扫描后台线程
        self.worker = RegistryAppScanWorker(self)
        self.worker.finished.connect(self._on_scan_finished)
        self.worker.start()

    def _on_scan_finished(self, apps: List[Dict[str, str]]):
        self._all_apps = apps
        self.lbl_status.setText(f"共发现 {len(apps)} 个已安装应用")
        self._render_table(apps)

    def _filter_apps(self, kw: str):
        kw = kw.strip().lower()
        if not kw:
            self._render_table(self._all_apps)
            return
        filtered = [
            a for a in self._all_apps
            if kw in a.get("name", "").lower() or kw in a.get("publisher", "").lower() or kw in a.get("exe_path", "").lower() or kw in a.get("install_location", "").lower()
        ]
        self._render_table(filtered)

    def _render_table(self, apps: List[Dict[str, str]]):
        self.table.setRowCount(0)
        for r_idx, a in enumerate(apps):
            self.table.insertRow(r_idx)
            item_name = QTableWidgetItem(a.get("name", ""))
            item_name.setIcon(get_icon("system", size=13))
            item_name.setData(Qt.UserRole, a)
            self.table.setItem(r_idx, 0, item_name)
            self.table.setItem(r_idx, 1, QTableWidgetItem(a.get("version", "")))
            self.table.setItem(r_idx, 2, QTableWidgetItem(a.get("exe_path", "") or a.get("install_location", "")))
            self.table.setItem(r_idx, 3, QTableWidgetItem(a.get("publisher", "")))

    def _on_confirm(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "请先在列表中选中一个应用程序。")
            return
        self.selected_app = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        self.accept()


class ProxyConfiguratorWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.latency_worker: Optional[LatencyTestWorker] = None
        self.configured_urls: List[str] = []
        self.configured_apps: List[Dict[str, str]] = []

        self.init_ui()
        self.load_settings()
        self.refresh_all_statuses()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(10)
        self.scroll_area.setWidget(container)
        root_layout.addWidget(self.scroll_area)

        # 1. 顶部标题栏
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("network", color="#06b6d4", size=26))
        header_layout.addWidget(icon_lbl)

        title_lbl = QLabel("应用代理配置工具 (Proxy Configurator)")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_lbl)

        badge_lbl = QLabel("全局代理 · 单独软件注入 · 根网址智能路由")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #0891b2; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header_layout.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header_layout.addStretch()

        btn_refresh = QPushButton("刷新状态")
        btn_refresh.setIcon(get_icon("refresh", size=14))
        btn_refresh.clicked.connect(self.refresh_all_statuses)
        header_layout.addWidget(btn_refresh)

        layout.addLayout(header_layout)

        # 2. 全局代理地址与预设卡片 (两行响应式排版，避免挤压溢出)
        preset_group = QGroupBox("代理服务器与端口预设")
        preset_layout = QVBoxLayout(preset_group)
        preset_layout.setContentsMargins(14, 12, 14, 12)
        preset_layout.setSpacing(10)

        # 代理地址行
        addr_row = QHBoxLayout()
        addr_row.setSpacing(10)

        addr_row.addWidget(QLabel("代理主机与端口:"))
        self.le_host = QLineEdit("127.0.0.1")
        self.le_host.setMinimumWidth(120)
        self.le_host.setMaximumWidth(220)
        addr_row.addWidget(self.le_host)

        addr_row.addWidget(QLabel(":"))
        self.le_port = QLineEdit("7890")
        self.le_port.setMinimumWidth(70)
        self.le_port.setMaximumWidth(100)
        addr_row.addWidget(self.le_port)

        addr_row.addSpacing(12)
        addr_row.addWidget(QLabel("快捷预设:"))
        btn_p1 = QPushButton("Clash (7890)")
        btn_p1.clicked.connect(lambda: self.le_port.setText("7890"))
        addr_row.addWidget(btn_p1)

        btn_p2 = QPushButton("v2rayN (10809)")
        btn_p2.clicked.connect(lambda: self.le_port.setText("10809"))
        addr_row.addWidget(btn_p2)

        btn_p3 = QPushButton("SS (1080)")
        btn_p3.clicked.connect(lambda: self.le_port.setText("1080"))
        addr_row.addWidget(btn_p3)

        btn_p4 = QPushButton("Sing-box (2080)")
        btn_p4.clicked.connect(lambda: self.le_port.setText("2080"))
        addr_row.addWidget(btn_p4)

        addr_row.addStretch()
        preset_layout.addLayout(addr_row)

        # 全局控制按钮
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(10)

        self.btn_enable_all = QPushButton("一键开启全部代理")
        self.btn_enable_all.setToolTip("一键同时开启 Windows 系统代理、用户环境变量、Git 全局及 Pip 镜像代理")
        self.btn_enable_all.setObjectName("primaryBtn")
        self.btn_enable_all.setIcon(get_icon("check", size=15))
        self.btn_enable_all.setFixedHeight(34)
        self.btn_enable_all.clicked.connect(self._enable_all_proxies)
        ctrl_row.addWidget(self.btn_enable_all)

        self.btn_disable_all = QPushButton("一键停用全部代理")
        self.btn_disable_all.setObjectName("dangerBtn")
        self.btn_disable_all.setIcon(get_icon("clear", size=15))
        self.btn_disable_all.setFixedHeight(34)
        self.btn_disable_all.clicked.connect(self._disable_all_proxies)
        ctrl_row.addWidget(self.btn_disable_all)

        self.btn_test_latency = QPushButton("网络连通性测速")
        self.btn_test_latency.setIcon(get_icon("refresh", size=14))
        self.btn_test_latency.setFixedHeight(34)
        self.btn_test_latency.clicked.connect(self._test_latency)
        ctrl_row.addWidget(self.btn_test_latency)

        self.lbl_latency_badge = QLabel("未测速")
        self.lbl_latency_badge.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 500; padding: 0 4px;")
        ctrl_row.addWidget(self.lbl_latency_badge)
        ctrl_row.addStretch()

        preset_layout.addLayout(ctrl_row)
        layout.addWidget(preset_group)

        # 3. 独立选项卡：分别展示【全局系统与环境代理】与【单独软件与网站代理】
        self.routing_tabs = QTabWidget()

        # Tab A: 独立网站代理路由 (根网址为基准，子网址全适应)
        tab_sites = QWidget()
        ts_layout = QVBoxLayout(tab_sites)
        ts_layout.setContentsMargins(12, 12, 12, 12)
        ts_layout.setSpacing(10)

        site_input_row = QHBoxLayout()
        site_input_row.addWidget(QLabel("添加代理网址/域名:"))
        self.le_url_input = QLineEdit()
        self.le_url_input.setPlaceholderText("输入根域名或完整 URL (如 github.com 或 https://huggingface.co/models)...")
        self.le_url_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.le_url_input.returnPressed.connect(self._add_url_rule)
        site_input_row.addWidget(self.le_url_input, 1)

        self.btn_add_url = QPushButton("添加代理网址")
        self.btn_add_url.setObjectName("primaryBtn")
        self.btn_add_url.setIcon(get_icon("check", size=13))
        self.btn_add_url.clicked.connect(self._add_url_rule)
        site_input_row.addWidget(self.btn_add_url)
        ts_layout.addLayout(site_input_row)

        lbl_site_hint = QLabel("规则说明：输入任意 URL 或域名后将自动提取根网址，该根网址旗下的所有子域名 (*.root) 及子网页路径 (root/*) 均自适应走该代理通道。")
        lbl_site_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        ts_layout.addWidget(lbl_site_hint)

        self.table_urls = QTableWidget()
        self.table_urls.setColumnCount(4)
        self.table_urls.setHorizontalHeaderLabels(["根网址 (Root Domain)", "自适应规则覆盖", "代理地址", "操作"])
        self.table_urls.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_urls.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_urls.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_urls.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_urls.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_urls.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_urls.setMinimumHeight(120)
        ts_layout.addWidget(self.table_urls, 1)

        # 网址自适应规则测试栏
        test_row = QHBoxLayout()
        test_row.addWidget(QLabel("测试网址自适应匹配:"))
        self.le_test_url = QLineEdit()
        self.le_test_url.setPlaceholderText("输入待测 URL (如 https://api.github.com/v1 或 sub.huggingface.co)...")
        self.le_test_url.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.le_test_url.returnPressed.connect(self._test_url_matching)
        test_row.addWidget(self.le_test_url, 1)

        self.btn_test_match = QPushButton("测试匹配")
        self.btn_test_match.setIcon(get_icon("search", size=13))
        self.btn_test_match.clicked.connect(self._test_url_matching)
        test_row.addWidget(self.btn_test_match)
        ts_layout.addLayout(test_row)

        self.lbl_match_result = QLabel("输入 URL 并点击测试，验证是否归属于已配置的根网址代理通道。")
        self.lbl_match_result.setStyleSheet("color: #64748b; font-size: 11px;")
        ts_layout.addWidget(self.lbl_match_result)

        # PAC 智能分流与脚本导出
        pac_row = QHBoxLayout()
        self.btn_enable_pac = QPushButton("应用为系统 PAC 智能分流 (仅匹配网址走代理)")
        self.btn_enable_pac.setObjectName("primaryBtn")
        self.btn_enable_pac.setIcon(get_icon("check", size=13))
        self.btn_enable_pac.clicked.connect(self._apply_pac_to_system)
        pac_row.addWidget(self.btn_enable_pac)

        self.btn_disable_pac = QPushButton("停用 PAC 分流")
        self.btn_disable_pac.setIcon(get_icon("clear", size=13))
        self.btn_disable_pac.clicked.connect(self._disable_pac_proxy)
        pac_row.addWidget(self.btn_disable_pac)

        self.btn_export_pac = QPushButton("导出 PAC 脚本...")
        self.btn_export_pac.setIcon(get_icon("save", size=13))
        self.btn_export_pac.clicked.connect(self._export_pac_script)
        pac_row.addWidget(self.btn_export_pac)

        self.lbl_pac_status = QLabel("PAC 状态: 检查中...")
        self.lbl_pac_status.setStyleSheet("color: #64748b; font-size: 11px;")
        pac_row.addWidget(self.lbl_pac_status)
        pac_row.addStretch()
        ts_layout.addLayout(pac_row)

        self.routing_tabs.addTab(tab_sites, "单独网站/域名代理路由")

        # Tab B: 独立应用程序代理 (注册表扫描与外部导入)
        tab_apps = QWidget()
        ta_layout = QVBoxLayout(tab_apps)
        ta_layout.setContentsMargins(12, 12, 12, 12)
        ta_layout.setSpacing(10)

        app_tool_row = QHBoxLayout()
        self.btn_scan_reg_apps = QPushButton("从注册表扫描已安装软件")
        self.btn_scan_reg_apps.setIcon(get_icon("search", size=14))
        self.btn_scan_reg_apps.clicked.connect(self._open_registry_scan_dialog)
        app_tool_row.addWidget(self.btn_scan_reg_apps)

        self.btn_import_external_app = QPushButton("从外部导入应用程序 (.exe)")
        self.btn_import_external_app.setIcon(get_icon("folder", size=14))
        self.btn_import_external_app.clicked.connect(self._import_external_exe)
        app_tool_row.addWidget(self.btn_import_external_app)
        app_tool_row.addStretch()
        ta_layout.addLayout(app_tool_row)

        lbl_app_hint = QLabel("可选择特定软件独立注入代理环境启动，不影响其他软件正常网络连接。")
        lbl_app_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        ta_layout.addWidget(lbl_app_hint)

        self.table_apps = QTableWidget()
        self.table_apps.setColumnCount(4)
        self.table_apps.setHorizontalHeaderLabels(["应用名称", "程序执行文件路径 (.exe)", "代理状态", "操作"])
        self.table_apps.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_apps.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_apps.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_apps.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_apps.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_apps.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_apps.setMinimumHeight(130)
        ta_layout.addWidget(self.table_apps, 1)

        self.routing_tabs.addTab(tab_apps, "单独软件/进程代理管理")

        # Tab C: 全局模块化代理 (Windows 系统、环境变量、Git、Pip)
        tab_global = QWidget()
        grid_layout = QGridLayout(tab_global)
        grid_layout.setContentsMargins(12, 12, 12, 12)
        grid_layout.setSpacing(12)

        # 卡片 1: Windows 系统代理
        c1 = self._build_card_frame("Windows 系统代理", "浏览器 (Edge/Chrome) 与绝大多数现代应用生效")
        c1_layout = QVBoxLayout(c1)
        self.lbl_sys_status = QLabel("状态: 检查中...")
        self.lbl_sys_status.setStyleSheet("font-weight: 500;")
        c1_layout.addWidget(self.lbl_sys_status)

        c1_btns = QHBoxLayout()
        btn_c1_on = QPushButton("开启系统代理")
        btn_c1_on.clicked.connect(self._enable_sys_proxy)
        c1_btns.addWidget(btn_c1_on)
        btn_c1_off = QPushButton("停用")
        btn_c1_off.clicked.connect(self._disable_sys_proxy)
        c1_btns.addWidget(btn_c1_off)
        c1_layout.addLayout(c1_btns)
        grid_layout.addWidget(c1, 0, 0)

        # 卡片 2: 用户环境变量
        c2 = self._build_card_frame("用户环境变量代理", "终端、curl、Python requests 及多数命令行工具生效")
        c2_layout = QVBoxLayout(c2)
        self.lbl_env_status = QLabel("状态: 检查中...")
        self.lbl_env_status.setStyleSheet("font-weight: 500;")
        c2_layout.addWidget(self.lbl_env_status)

        c2_btns = QHBoxLayout()
        btn_c2_on = QPushButton("设置环境变量")
        btn_c2_on.clicked.connect(self._enable_env_proxy)
        c2_btns.addWidget(btn_c2_on)
        btn_c2_off = QPushButton("清除")
        btn_c2_off.clicked.connect(self._disable_env_proxy)
        c2_btns.addWidget(btn_c2_off)
        c2_layout.addLayout(c2_btns)
        grid_layout.addWidget(c2, 0, 1)

        # 卡片 3: Git 全局代理
        c3 = self._build_card_frame("Git 全局代理", "克隆与推送 GitHub / GitLab 仓库时加速")
        c3_layout = QVBoxLayout(c3)
        self.lbl_git_status = QLabel("状态: 检查中...")
        self.lbl_git_status.setStyleSheet("font-weight: 500;")
        c3_layout.addWidget(self.lbl_git_status)

        c3_btns = QHBoxLayout()
        btn_c3_on = QPushButton("开启 Git 代理")
        btn_c3_on.clicked.connect(self._enable_git_proxy)
        c3_btns.addWidget(btn_c3_on)
        btn_c3_off = QPushButton("取消 Git 代理")
        btn_c3_off.clicked.connect(self._disable_git_proxy)
        c3_btns.addWidget(btn_c3_off)
        c3_layout.addLayout(c3_btns)
        grid_layout.addWidget(c3, 1, 0)

        # 卡片 4: Pip 代理与镜像源
        c4 = self._build_card_frame("Pip 代理与国内镜像", "Python pip 安装依赖加速与镜像切换")
        c4_layout = QVBoxLayout(c4)
        self.lbl_pip_status = QLabel("状态: 检查中...")
        self.lbl_pip_status.setStyleSheet("font-weight: 500;")
        c4_layout.addWidget(self.lbl_pip_status)

        pip_m_row = QHBoxLayout()
        self.combo_pip_mirror = QComboBox()
        self.combo_pip_mirror.addItems(list(PIP_MIRRORS.keys()))
        pip_m_row.addWidget(self.combo_pip_mirror, 1)
        btn_apply_mirror = QPushButton("设为镜像")
        btn_apply_mirror.clicked.connect(self._apply_pip_mirror)
        pip_m_row.addWidget(btn_apply_mirror)
        c4_layout.addLayout(pip_m_row)

        c4_btns = QHBoxLayout()
        btn_c4_on = QPushButton("开启 Pip 代理")
        btn_c4_on.clicked.connect(self._enable_pip_proxy)
        c4_btns.addWidget(btn_c4_on)
        btn_c4_off = QPushButton("清除 Pip 代理")
        btn_c4_off.clicked.connect(self._disable_pip_proxy)
        c4_btns.addWidget(btn_c4_off)
        c4_layout.addLayout(c4_btns)
        grid_layout.addWidget(c4, 1, 1)

        self.routing_tabs.addTab(tab_global, "系统与全局开发代理 (Git / Pip / Env)")
        layout.addWidget(self.routing_tabs, 1)

        # 4. 日志控制台
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMinimumHeight(45)
        self.log_console.setMaximumHeight(80)
        self.log_console.setPlaceholderText("代理配置与测试日志...")
        layout.addWidget(self.log_console)

    def _build_card_frame(self, title: str, subtitle: str) -> QFrame:
        card = QFrame()
        card.setObjectName("pluginCard")
        l = QVBoxLayout(card)
        l.setContentsMargins(14, 12, 14, 12)
        l.setSpacing(6)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        l.addWidget(t_lbl)

        st_lbl = QLabel(subtitle)
        st_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        l.addWidget(st_lbl)
        return card

    def _get_current_proxy_addr(self) -> str:
        host = self.le_host.text().strip() or "127.0.0.1"
        port = self.le_port.text().strip() or "7890"
        return f"{host}:{port}"

    # ---------------- 独立网址表操作 ----------------
    def _add_url_rule(self):
        raw = self.le_url_input.text().strip()
        if not raw:
            QMessageBox.information(self, "提示", "请输入网址或域名。")
            return
        root = extract_root_domain(raw)
        if not root:
            QMessageBox.warning(self, "格式错误", "无法从输入的网址解析出有效的根网址。")
            return

        if root in self.configured_urls:
            QMessageBox.information(self, "提示", f"根网址 [{root}] 已存在于代理规则表中。")
            return

        self.configured_urls.append(root)
        self.le_url_input.clear()
        self._render_urls_table()
        self.save_settings()
        self.log_console.append(f"[网址代理] 已添加根网址规则: {root} (全子域名与子网页均已生效)")

    def _remove_url_rule(self, root: str):
        if root in self.configured_urls:
            self.configured_urls.remove(root)
            self._render_urls_table()
            self.save_settings()
            self.log_console.append(f"[网址代理] 已删除网址代理规则: {root}")

    def _render_urls_table(self):
        self.table_urls.setRowCount(0)
        proxy_addr = self._get_current_proxy_addr()
        for idx, root in enumerate(self.configured_urls):
            self.table_urls.insertRow(idx)
            item_root = QTableWidgetItem(root)
            item_root.setIcon(get_icon("network", size=13))
            self.table_urls.setItem(idx, 0, item_root)

            item_rule = QTableWidgetItem(f"所有子域名与子网页自适应 (*.{root}/*)")
            self.table_urls.setItem(idx, 1, item_rule)

            item_proxy = QTableWidgetItem(proxy_addr)
            self.table_urls.setItem(idx, 2, item_proxy)

            btn_del = QPushButton("删除")
            btn_del.setObjectName("dangerBtn")
            btn_del.setIcon(get_icon("trash", size=12))
            btn_del.setFixedSize(65, 26)
            btn_del.clicked.connect(lambda checked=False, r=root: self._remove_url_rule(r))
            self.table_urls.setCellWidget(idx, 3, btn_del)

    def _test_url_matching(self):
        url = self.le_test_url.text().strip()
        if not url:
            self.lbl_match_result.setText("请输入待测试的 URL。")
            self.lbl_match_result.setStyleSheet("color: #ef4444; font-size: 11px;")
            return

        proxy_addr = self._get_current_proxy_addr()
        matched_rd = None
        for rd in self.configured_urls:
            if matches_root_domain(url, rd):
                matched_rd = rd
                break

        if matched_rd:
            self.lbl_match_result.setText(f"[成功] 匹配成功！该网址归属于根网址 [{matched_rd}]，自适应走代理: {proxy_addr}")
            self.lbl_match_result.setStyleSheet("color: #10b981; font-size: 11px; font-weight: bold;")
            self.log_console.append(f"[网址路由匹配] 测试 URL: {url} -> 匹配根网址 [{matched_rd}] -> 代理 {proxy_addr}")
        else:
            self.lbl_match_result.setText("[未匹配] 未匹配任何规则：该网址不归属于已配置的根网址，将直连访问 (DIRECT)")
            self.lbl_match_result.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: bold;")
            self.log_console.append(f"[网址路由匹配] 测试 URL: {url} -> 无匹配根网址 -> 直连 (DIRECT)")

    def _apply_pac_to_system(self):
        if not self.configured_urls:
            QMessageBox.information(self, "提示", "请先在上方表格中添加至少一个根网址代理规则。")
            return
        proxy_addr = self._get_current_proxy_addr()
        from toolbox.core.paths import get_app_data_dir
        pac_path = os.path.join(get_app_data_dir(), "proxy_rules.pac")
        ok, msg = export_pac_file(pac_path, proxy_addr, self.configured_urls)
        if not ok:
            QMessageBox.critical(self, "生成失败", msg)
            return
        s_ok, s_msg = set_pac_proxy(True, pac_path)
        if s_ok:
            self.log_console.append(f"[PAC 代理] {s_msg}")
            QMessageBox.information(self, "PAC 已生效", f"系统 PAC 智能分流已成功开启！\n\n规则文件：{pac_path}\n当前生效根网址：{len(self.configured_urls)} 个\n代理通道：{proxy_addr}")
        else:
            self.log_console.append(f"[PAC 代理失败] {s_msg}")
            QMessageBox.warning(self, "配置失败", s_msg)
        self.refresh_all_statuses()

    def _disable_pac_proxy(self):
        ok, msg = set_pac_proxy(False)
        self.log_console.append(f"[PAC 代理] {msg}")
        self.refresh_all_statuses()

    def _export_pac_script(self):
        proxy_addr = self._get_current_proxy_addr()
        p, _ = QFileDialog.getSaveFileName(self, "导出 PAC 脚本文件", "proxy.pac", "PAC 脚本 (*.pac *.js)")
        if p:
            ok, msg = export_pac_file(p, proxy_addr, self.configured_urls)
            if ok:
                QMessageBox.information(self, "导出成功", msg)
            else:
                QMessageBox.warning(self, "导出失败", msg)
            self.log_console.append(f"[PAC 导出] {msg}")


    # ---------------- 独立应用表操作 ----------------
    def _open_registry_scan_dialog(self):
        dlg = RegistryAppSelectDialog(self)
        if dlg.exec() and dlg.selected_app:
            app = dlg.selected_app
            exe = app.get("exe_path", "") or app.get("install_location", "")
            name = app.get("name", "未命名应用")
            self._add_app_to_list(name, exe)

    def _import_external_exe(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择可执行程序 (.exe)", "", "执行程序 (*.exe)")
        if p and os.path.isfile(p):
            name = os.path.splitext(os.path.basename(p))[0]
            self._add_app_to_list(name, os.path.normpath(p))

    def _add_app_to_list(self, name: str, exe_path: str):
        if not exe_path:
            QMessageBox.warning(self, "未检测到执行文件", "该软件未检测到有效的主执行文件路径。")
            return

        for a in self.configured_apps:
            if a.get("exe_path") == exe_path:
                QMessageBox.information(self, "提示", f"应用 [{name}] 已在列表中。")
                return

        self.configured_apps.append({
            "name": name,
            "exe_path": exe_path
        })
        self._render_apps_table()
        self.save_settings()
        self.log_console.append(f"[应用代理] 已加入受控应用列表: {name} ({exe_path})")

    def _remove_app_from_list(self, exe_path: str):
        self.configured_apps = [a for a in self.configured_apps if a.get("exe_path") != exe_path]
        self._render_apps_table()
        self.save_settings()
        self.log_console.append(f"[应用代理] 已移除受控应用: {exe_path}")

    def _launch_app_proxy(self, exe_path: str):
        proxy_addr = self._get_current_proxy_addr()
        ok, msg = launch_app_with_proxy(exe_path, proxy_addr)
        if ok:
            self.log_console.append(f"[应用启动成功] {msg} (代理通道: {proxy_addr})")
        else:
            self.log_console.append(f"[应用启动失败] {msg}")
            QMessageBox.warning(self, "启动失败", msg)

    def _render_apps_table(self):
        self.table_apps.setRowCount(0)
        proxy_addr = self._get_current_proxy_addr()
        for idx, app in enumerate(self.configured_apps):
            self.table_apps.insertRow(idx)
            item_name = QTableWidgetItem(app.get("name", ""))
            item_name.setIcon(get_icon("system", size=13))
            self.table_apps.setItem(idx, 0, item_name)

            exe_p = app.get("exe_path", "")
            self.table_apps.setItem(idx, 1, QTableWidgetItem(exe_p))
            self.table_apps.setItem(idx, 2, QTableWidgetItem(f"通道: {proxy_addr}"))

            act_widget = QWidget()
            act_layout = QHBoxLayout(act_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(6)

            btn_run = QPushButton("带代理运行")
            btn_run.setObjectName("primaryBtn")
            btn_run.setIcon(get_icon("play", size=12))
            btn_run.clicked.connect(lambda checked=False, p=exe_p: self._launch_app_proxy(p))
            act_layout.addWidget(btn_run)

            btn_del = QPushButton("移除")
            btn_del.setIcon(get_icon("trash", size=12))
            btn_del.clicked.connect(lambda checked=False, p=exe_p: self._remove_app_from_list(p))
            act_layout.addWidget(btn_del)

            self.table_apps.setCellWidget(idx, 3, act_widget)

    # ---------------- 原有状态刷新与开关 ----------------
    def refresh_all_statuses(self):
        # 1. 系统代理
        sys_st = get_system_proxy_status()
        if sys_st.get("enabled"):
            self.lbl_sys_status.setText(f"已开启: {sys_st.get('server', '')}")
            self.lbl_sys_status.setStyleSheet("color: #10b981; font-weight: bold;")
        else:
            self.lbl_sys_status.setText("已停用")
            self.lbl_sys_status.setStyleSheet("color: #64748b; font-weight: 500;")

        # 2. 环境变量
        env_st = get_env_proxy_status()
        if env_st.get("enabled"):
            self.lbl_env_status.setText(f"已配置: {env_st.get('http') or env_st.get('all')}")
            self.lbl_env_status.setStyleSheet("color: #10b981; font-weight: bold;")
        else:
            self.lbl_env_status.setText("未设置")
            self.lbl_env_status.setStyleSheet("color: #64748b; font-weight: 500;")

        # 3. Git 全局代理
        git_st = get_git_proxy_status()
        if not git_st.get("installed"):
            self.lbl_git_status.setText("未安装 Git")
            self.lbl_git_status.setStyleSheet("color: #ef4444; font-weight: 500;")
        elif git_st.get("enabled"):
            self.lbl_git_status.setText(f"已开启: {git_st.get('http', '')}")
            self.lbl_git_status.setStyleSheet("color: #10b981; font-weight: bold;")
        else:
            self.lbl_git_status.setText("已停用")
            self.lbl_git_status.setStyleSheet("color: #64748b; font-weight: 500;")

        # 4. Pip 代理
        pip_st = get_pip_status()
        if pip_st.get("enabled"):
            self.lbl_pip_status.setText(f"代理开启: {pip_st.get('proxy', '')}")
            self.lbl_pip_status.setStyleSheet("color: #10b981; font-weight: bold;")
        else:
            self.lbl_pip_status.setText("代理未设置")
            self.lbl_pip_status.setStyleSheet("color: #64748b; font-weight: 500;")

        # 5. PAC 智能分流
        pac_st = get_pac_proxy_status()
        if pac_st.get("enabled"):
            self.lbl_pac_status.setText("PAC 已生效 (匹配网址走代理)")
            self.lbl_pac_status.setStyleSheet("color: #10b981; font-weight: bold;")
        else:
            self.lbl_pac_status.setText("PAC 未启用")
            self.lbl_pac_status.setStyleSheet("color: #64748b; font-weight: 500;")

        self._render_urls_table()
        self._render_apps_table()

    def _enable_sys_proxy(self):
        addr = self._get_current_proxy_addr()
        ok, msg = set_system_proxy(True, addr)
        self.log_console.append(f"[系统代理] {msg}")
        self.refresh_all_statuses()

    def _disable_sys_proxy(self):
        ok, msg = set_system_proxy(False)
        self.log_console.append(f"[系统代理] {msg}")
        self.refresh_all_statuses()

    def _enable_env_proxy(self):
        addr = self._get_current_proxy_addr()
        ok, msg = set_env_proxy(True, addr)
        self.log_console.append(f"[环境变量] {msg}")
        self.refresh_all_statuses()

    def _disable_env_proxy(self):
        ok, msg = set_env_proxy(False)
        self.log_console.append(f"[环境变量] {msg}")
        self.refresh_all_statuses()

    def _enable_git_proxy(self):
        addr = self._get_current_proxy_addr()
        ok, msg = set_git_proxy(True, addr)
        self.log_console.append(f"[Git代理] {msg}")
        self.refresh_all_statuses()

    def _disable_git_proxy(self):
        ok, msg = set_git_proxy(False)
        self.log_console.append(f"[Git代理] {msg}")
        self.refresh_all_statuses()

    def _enable_pip_proxy(self):
        addr = self._get_current_proxy_addr()
        ok, msg = set_pip_proxy(True, addr)
        self.log_console.append(f"[Pip代理] {msg}")
        self.refresh_all_statuses()

    def _disable_pip_proxy(self):
        ok, msg = set_pip_proxy(False)
        self.log_console.append(f"[Pip代理] {msg}")
        self.refresh_all_statuses()

    def _apply_pip_mirror(self):
        key = self.combo_pip_mirror.currentText()
        url = PIP_MIRRORS.get(key, "")
        if url:
            ok, msg = set_pip_mirror(url)
            self.log_console.append(f"[Pip镜像] {msg}")
            self.refresh_all_statuses()

    def _enable_all_proxies(self):
        addr = self._get_current_proxy_addr()
        set_system_proxy(True, addr)
        set_env_proxy(True, addr)
        set_git_proxy(True, addr)
        set_pip_proxy(True, addr)
        self.log_console.append(f"[一键配置] 已全部开启代理通道 ({addr})！")
        self.refresh_all_statuses()

    def _disable_all_proxies(self):
        set_system_proxy(False)
        set_env_proxy(False)
        set_git_proxy(False)
        set_pip_proxy(False)
        self.log_console.append("[一键配置] 已彻底清空并停用所有应用代理！")
        self.refresh_all_statuses()

    def _test_latency(self):
        addr = self._get_current_proxy_addr()
        self.btn_test_latency.setEnabled(False)
        self.lbl_latency_badge.setText("测速中...")
        self.log_console.append(f"[测速] 正在通过 {addr} 连接 https://github.com 测试延时...")

        self.latency_worker = LatencyTestWorker(addr, "https://github.com")
        self.latency_worker.finished.connect(self._on_latency_finished)
        self.latency_worker.start()

    def _on_latency_finished(self, success: bool, elapsed: float, msg: str):
        self.btn_test_latency.setEnabled(True)
        if success:
            self.lbl_latency_badge.setText(f"{elapsed:.0f} ms (良好)")
            self.lbl_latency_badge.setStyleSheet("color: #10b981; font-weight: bold;")
            self.log_console.append(f"[测速成功] 延时: {elapsed:.1f}ms - {msg}")
        else:
            self.lbl_latency_badge.setText("连接失败")
            self.lbl_latency_badge.setStyleSheet("color: #ef4444; font-weight: bold;")
            self.log_console.append(f"[测速失败] {msg}")

    def load_settings(self):
        cfg = self.config.get_plugin_config("proxy_configurator", {})
        if "host" in cfg and hasattr(self, "le_host"):
            self.le_host.setText(cfg["host"])
        if "port" in cfg and hasattr(self, "le_port"):
            self.le_port.setText(cfg["port"])
        self.configured_urls = cfg.get("configured_urls", ["github.com", "huggingface.co"])
        self.configured_apps = cfg.get("configured_apps", [])
        self._render_urls_table()
        self._render_apps_table()

    def save_settings(self):
        cfg = {
            "host": self.le_host.text() if hasattr(self, "le_host") else "127.0.0.1",
            "port": self.le_port.text() if hasattr(self, "le_port") else "7890",
            "configured_urls": self.configured_urls,
            "configured_apps": self.configured_apps
        }
        self.config.set_plugin_config("proxy_configurator", cfg)
