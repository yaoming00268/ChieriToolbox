"""
端口网络哨兵 (Port Network Sentinel) - UI 界面
提供毫秒级侦测本地处于 LISTENING 状态端口、占用进程逆向定位、一键终结与 Hosts 切换。
"""

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QTabWidget, QTextEdit, QFrame
)

from toolbox.ui.icons import get_icon
from .engine import scan_listening_ports, kill_process_by_pid, read_hosts_file, save_hosts_file, flush_dns_cache


class PortScanWorker(QThread):
    """异步后台端口扫描线程，杜绝主界面卡死"""
    scan_finished = Signal(list)

    def run(self):
        results = scan_listening_ports()
        self.scan_finished.emit(results)


class PortNetworkSentinelWidget(QWidget):
    """端口网络哨兵主面板部件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ports_data = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # 顶部导言
        top_bar = QHBoxLayout()
        tip = QLabel("<b>本地端口雷达与网络哨兵</b><br><span style='color:#64748b; font-size:12px;'>毫秒级侦测本地侦听端口、解决 8080/3000 端口占用报错、一键终结占用进程与管理 Hosts。</span>")
        tip.setWordWrap(True)
        top_bar.addWidget(tip, 1)

        self.btn_refresh = QPushButton("刷新扫描")
        self.btn_refresh.setObjectName("primaryBtn")
        self.btn_refresh.setIcon(get_icon("refresh", color="#ffffff", size=14))
        self.btn_refresh.clicked.connect(self._start_scan)
        top_bar.addWidget(self.btn_refresh)
        layout.addLayout(top_bar)

        self.worker = None

        # 选项卡
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_ports_page(), get_icon("shield", size=14), "本地端口雷达")
        self.tabs.addTab(self._build_hosts_page(), get_icon("globe", size=14), "Hosts 与 DNS 哨兵")
        layout.addWidget(self.tabs, 1)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.ports_data and (self.worker is None or not self.worker.isRunning()):
            self._start_scan()

    def _build_ports_page(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 8, 8, 8)
        l.setSpacing(8)

        # 过滤筛选行
        filter_row = QHBoxLayout()
        self.le_filter = QLineEdit()
        self.le_filter.setPlaceholderText("过滤端口号、进程名或 PID (如 8080, python, node)...")
        self.le_filter.textChanged.connect(self._render_ports_table)
        filter_row.addWidget(self.le_filter, 1)

        self.combo_proto = QComboBox()
        self.combo_proto.addItems(["全部协议", "TCP", "UDP"])
        self.combo_proto.currentIndexChanged.connect(self._render_ports_table)
        filter_row.addWidget(self.combo_proto)

        self.lbl_stats = QLabel("共 0 个侦听端口")
        self.lbl_stats.setStyleSheet("color: #64748b; font-size: 12px; margin-left: 8px;")
        filter_row.addWidget(self.lbl_stats)

        l.addLayout(filter_row)

        # 端口数据表格
        self.table_ports = QTableWidget()
        self.table_ports.setColumnCount(7)
        self.table_ports.setHorizontalHeaderLabels(["协议", "绑定地址", "端口号", "状态", "PID", "占用进程名", "快速操作"])
        self.table_ports.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_ports.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_ports.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_ports.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_ports.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table_ports.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_ports.setAlternatingRowColors(True)
        l.addWidget(self.table_ports, 1)

        return w

    def _build_hosts_page(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 8, 8, 8)
        l.setSpacing(8)

        # 顶部操作栏
        act_row = QHBoxLayout()
        act_row.addWidget(QLabel("<b>Windows 系统 Hosts 规则配置</b>"))
        act_row.addStretch()

        btn_reload = QPushButton("重新载入")
        btn_reload.clicked.connect(self._load_hosts)
        act_row.addWidget(btn_reload)

        btn_save = QPushButton("保存 Hosts")
        btn_save.setObjectName("primaryBtn")
        btn_save.setIcon(get_icon("save", color="#ffffff", size=13))
        btn_save.clicked.connect(self._save_hosts)
        act_row.addWidget(btn_save)

        btn_flush = QPushButton("刷新系统 DNS 缓存")
        btn_flush.setIcon(get_icon("refresh", size=13))
        btn_flush.clicked.connect(self._flush_dns)
        act_row.addWidget(btn_flush)

        l.addLayout(act_row)

        self.txt_hosts = QTextEdit()
        self.txt_hosts.setStyleSheet("font-family: Consolas, monospace; font-size: 13px; line-height: 1.4;")
        self._load_hosts()
        l.addWidget(self.txt_hosts, 1)

        return w

    def _start_scan(self):
        if self.worker is not None and self.worker.isRunning():
            return
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("扫描中...")
        self.worker = PortScanWorker(self)
        self.worker.scan_finished.connect(self._on_scan_finished)
        self.worker.start()

    def _on_scan_finished(self, results: list):
        self.ports_data = results
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("刷新扫描")
        self._render_ports_table()

    def _render_ports_table(self):
        q = self.le_filter.text().strip().lower()
        proto_filter = self.combo_proto.currentText()

        filtered = []
        for row in self.ports_data:
            if proto_filter != "全部协议" and row["proto"] != proto_filter:
                continue
            if q:
                match = (
                    q in str(row["port"]) or
                    q in str(row["pid"]) or
                    q in row["process_name"].lower() or
                    q in row["ip"].lower()
                )
                if not match:
                    continue
            filtered.append(row)

        self.table_ports.setRowCount(len(filtered))
        for r_idx, row in enumerate(filtered):
            self.table_ports.setItem(r_idx, 0, QTableWidgetItem(row["proto"]))
            self.table_ports.setItem(r_idx, 1, QTableWidgetItem(row["ip"]))
            
            p_item = QTableWidgetItem(str(row["port"]))
            p_item.setFont(self.font())
            p_item.setTextAlignment(Qt.AlignCenter)
            self.table_ports.setItem(r_idx, 2, p_item)

            self.table_ports.setItem(r_idx, 3, QTableWidgetItem(row["state"]))
            self.table_ports.setItem(r_idx, 4, QTableWidgetItem(str(row["pid"])))
            
            pname_item = QTableWidgetItem(row["process_name"])
            pname_item.setToolTip(f"进程: {row['process_name']} (PID: {row['pid']})")
            self.table_ports.setItem(r_idx, 5, pname_item)

            btn_kill = QPushButton("终结进程")
            btn_kill.setFixedHeight(26)
            btn_kill.setStyleSheet("font-size: 11px; padding: 2px 8px; background: rgba(220, 38, 38, 0.1); color: #dc2626; border: 1px solid rgba(220, 38, 38, 0.3);")
            pid = row["pid"]
            btn_kill.clicked.connect(lambda checked=False, p=pid, n=row["process_name"]: self._kill_port_process(p, n))
            if pid <= 4:
                btn_kill.setEnabled(False)
                btn_kill.setText("系统内核")
            self.table_ports.setCellWidget(r_idx, 6, btn_kill)

        self.lbl_stats.setText(f"共 {len(filtered)} / {len(self.ports_data)} 个侦听端口")

    def _kill_port_process(self, pid: int, proc_name: str):
        reply = QMessageBox.question(
            self,
            "确认终止进程",
            f"确定要强行结束占用端口的进程吗？\n\n进程名: {proc_name}\nPID: {pid}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            ok, msg = kill_process_by_pid(pid)
            if ok:
                QMessageBox.information(self, "操作成功", msg)
                self._start_scan()
            else:
                QMessageBox.warning(self, "操作失败", msg)

    def _load_hosts(self):
        content = read_hosts_file()
        self.txt_hosts.setPlainText(content)

    def _save_hosts(self):
        content = self.txt_hosts.toPlainText()
        ok, msg = save_hosts_file(content)
        if ok:
            QMessageBox.information(self, "保存成功", msg)
        else:
            QMessageBox.warning(self, "保存失败", msg)

    def _flush_dns(self):
        ok, msg = flush_dns_cache()
        if ok:
            QMessageBox.information(self, "DNS 刷新", msg)
        else:
            QMessageBox.warning(self, "DNS 刷新失败", msg)

    def cleanup(self):
        """退出或销毁部件时优雅终结后台探测线程，防止 QThread 异常崩溃"""
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.quit()
            self.worker.wait(1500)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def load_settings(self):
        from toolbox.core.config_manager import ConfigManager
        cfg = ConfigManager().get_plugin_config("port_network_sentinel")
        proto = cfg.get("proto", "全部协议")
        if hasattr(self, "combo_proto"):
            idx = self.combo_proto.findText(proto)
            if idx >= 0:
                self.combo_proto.setCurrentIndex(idx)

    def save_settings(self):
        from toolbox.core.config_manager import ConfigManager
        proto = self.combo_proto.currentText() if hasattr(self, "combo_proto") else "全部协议"
        ConfigManager().set_plugin_config("port_network_sentinel", {"proto": proto})
