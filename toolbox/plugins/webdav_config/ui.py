"""
WebDAV 配置工具 - UI 界面
集成 OpenList / AList 内核标准的 WebDAV 客户端与存储配置，支持多配置管理、连通性探测、
远程文件浏览交互与 Windows 本地网络驱动器一键挂载映射。
"""

import os
from typing import Optional, Dict, Any, List
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QGroupBox, QMessageBox, QFileDialog, QInputDialog,
    QSplitter
)
import pyperclip

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.icons import get_icon, get_pixmap
from .client import (
    WebDAVClient, format_bytes, get_windows_mount_cmd,
    mount_webdav_as_drive, unmount_webdav_drive
)


class WebDAVConfigWidget(QWidget):
    PLUGIN_ID = "webdav_config"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self.current_remote_path = "/"
        self.client: Optional[WebDAVClient] = None
        self.profiles: Dict[str, Dict[str, Any]] = {}
        self.active_profile_name = "OpenList 默认服务"

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 18, 24, 20)
        main_layout.setSpacing(12)

        # 1. 顶部 Header
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("globe", color="#3b82f6", size=26))
        header.addWidget(icon_lbl)

        title_lbl = QLabel("WebDAV 配置管理器 (OpenList / AList 内核)")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title_lbl)

        badge_lbl = QLabel("RFC 4918 存储网关")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header.addStretch()
        main_layout.addLayout(header)

        # 2. 分割器：左侧连接配置与挂载，右侧远程文件浏览器
        splitter = QSplitter(Qt.Horizontal)

        # --- 左侧面板：配置与挂载 ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(10)

        # 配置方案选择
        profile_group = QGroupBox("WebDAV 配置方案")
        p_layout = QVBoxLayout(profile_group)
        p_layout.setSpacing(8)

        row_p = QHBoxLayout()
        self.combo_profiles = QComboBox()
        self.combo_profiles.currentTextChanged.connect(self._on_profile_selected)
        row_p.addWidget(self.combo_profiles, 1)

        btn_new_p = QPushButton("新建")
        btn_new_p.clicked.connect(self._create_new_profile)
        row_p.addWidget(btn_new_p)

        btn_del_p = QPushButton("删除")
        btn_del_p.clicked.connect(self._delete_current_profile)
        row_p.addWidget(btn_del_p)
        p_layout.addLayout(row_p)

        # 连接字段
        form_layout = QVBoxLayout()
        form_layout.setSpacing(6)

        form_layout.addWidget(QLabel("服务端 WebDAV URL 地址:"))
        self.le_url = QLineEdit()
        self.le_url.setPlaceholderText("http://127.0.0.1:5244/dav/")
        form_layout.addWidget(self.le_url)

        # 快速填充预设芯片
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        btn_pre_openlist = QPushButton("OpenList")
        btn_pre_openlist.setFixedHeight(22)
        btn_pre_openlist.clicked.connect(lambda: self.le_url.setText("http://127.0.0.1:5244/dav/"))
        preset_row.addWidget(btn_pre_openlist)

        btn_pre_alist = QPushButton("AList")
        btn_pre_alist.setFixedHeight(22)
        btn_pre_alist.clicked.connect(lambda: self.le_url.setText("http://127.0.0.1:5244/dav/"))
        preset_row.addWidget(btn_pre_alist)

        btn_pre_nextcloud = QPushButton("Nextcloud")
        btn_pre_nextcloud.setFixedHeight(22)
        btn_pre_nextcloud.clicked.connect(lambda: self.le_url.setText("https://your-domain/remote.php/dav/files/user/"))
        preset_row.addWidget(btn_pre_nextcloud)
        preset_row.addStretch()
        form_layout.addLayout(preset_row)

        row_auth = QHBoxLayout()
        v_user = QVBoxLayout()
        v_user.addWidget(QLabel("用户名:"))
        self.le_username = QLineEdit()
        v_user.addWidget(self.le_username)
        row_auth.addLayout(v_user)

        v_pwd = QVBoxLayout()
        v_pwd.addWidget(QLabel("访问密码 / Token:"))
        self.le_password = QLineEdit()
        self.le_password.setEchoMode(QLineEdit.Password)
        v_pwd.addWidget(self.le_password)
        row_auth.addLayout(v_pwd)
        form_layout.addLayout(row_auth)

        p_layout.addLayout(form_layout)

        # 连通测试与保存按钮
        btn_row = QHBoxLayout()
        self.btn_test = QPushButton("测试连通性")
        self.btn_test.setIcon(get_icon("refresh", size=14))
        self.btn_test.clicked.connect(self._test_connection)
        btn_row.addWidget(self.btn_test)

        self.btn_save_profile = QPushButton("保存配置")
        self.btn_save_profile.setObjectName("primaryBtn")
        self.btn_save_profile.setIcon(get_icon("save", size=14))
        self.btn_save_profile.clicked.connect(self._save_active_profile)
        btn_row.addWidget(self.btn_save_profile)
        p_layout.addLayout(btn_row)

        self.lbl_conn_status = QLabel("就绪 · 等待连接测试")
        self.lbl_conn_status.setStyleSheet("color: #64748b; font-size: 12px;")
        self.lbl_conn_status.setWordWrap(True)
        p_layout.addWidget(self.lbl_conn_status)

        left_layout.addWidget(profile_group)

        # Windows 网络驱动器映射助手组
        mount_group = QGroupBox("Windows 驱动器映射助手")
        m_layout = QVBoxLayout(mount_group)
        m_layout.setSpacing(8)

        row_m1 = QHBoxLayout()
        row_m1.addWidget(QLabel("选择本地盘符:"))
        self.combo_drive = QComboBox()
        self.combo_drive.addItems(["Z:", "Y:", "X:", "W:", "V:", "U:", "T:", "S:"])
        row_m1.addWidget(self.combo_drive)
        row_m1.addStretch()
        m_layout.addLayout(row_m1)

        row_m2 = QHBoxLayout()
        self.btn_mount = QPushButton("挂载为网络盘")
        self.btn_mount.setIcon(get_icon("network", size=14))
        self.btn_mount.clicked.connect(self._mount_network_drive)
        row_m2.addWidget(self.btn_mount)

        self.btn_unmount = QPushButton("断开挂载")
        self.btn_unmount.clicked.connect(self._unmount_network_drive)
        row_m2.addWidget(self.btn_unmount)

        self.btn_copy_cmd = QPushButton("复制命令")
        self.btn_copy_cmd.setIcon(get_icon("copy", size=14))
        self.btn_copy_cmd.clicked.connect(self._copy_mount_cmd)
        row_m2.addWidget(self.btn_copy_cmd)
        m_layout.addLayout(row_m2)

        m_hint = QLabel("通过 net use 将 WebDAV 映射为资源管理器本地驱动器盘符。")
        m_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        m_layout.addWidget(m_hint)

        left_layout.addWidget(mount_group)
        left_layout.addStretch()
        splitter.addWidget(left_widget)

        # --- 右侧面板：远程文件浏览器 ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        # 导航工具栏
        nav_box = QHBoxLayout()
        nav_box.setSpacing(6)

        self.btn_up_dir = QPushButton("返回上级")
        self.btn_up_dir.setIcon(get_icon("arrow-left", size=14))
        self.btn_up_dir.clicked.connect(self._go_up_dir)
        nav_box.addWidget(self.btn_up_dir)

        self.lbl_path = QLabel("/")
        self.lbl_path.setStyleSheet("font-weight: 600; padding: 0 4px;")
        nav_box.addWidget(self.lbl_path, 1)

        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setIcon(get_icon("refresh", size=14))
        self.btn_refresh.clicked.connect(self._refresh_dir)
        nav_box.addWidget(self.btn_refresh)

        self.btn_mkdir = QPushButton("新建文件夹")
        self.btn_mkdir.setIcon(get_icon("folder-plus", size=14))
        self.btn_mkdir.clicked.connect(self._create_remote_dir)
        nav_box.addWidget(self.btn_mkdir)

        self.btn_upload = QPushButton("上传文件")
        self.btn_upload.setIcon(get_icon("file-plus", size=14))
        self.btn_upload.clicked.connect(self._upload_local_file)
        nav_box.addWidget(self.btn_upload)

        self.btn_download = QPushButton("下载所选")
        self.btn_download.setIcon(get_icon("download", size=14))
        self.btn_download.clicked.connect(self._download_selected_file)
        nav_box.addWidget(self.btn_download)

        right_layout.addLayout(nav_box)

        # 远程文件表格
        self.table_files = QTableWidget()
        self.table_files.setColumnCount(4)
        self.table_files.setHorizontalHeaderLabels(["名称", "类型", "文件大小", "修改时间"])
        self.table_files.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_files.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_files.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_files.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_files.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_files.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_files.cellDoubleClicked.connect(self._on_table_double_clicked)
        right_layout.addWidget(self.table_files, 1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)

        main_layout.addWidget(splitter, 1)

    def _get_active_client(self) -> WebDAVClient:
        url = self.le_url.text().strip()
        user = self.le_username.text().strip()
        pwd = self.le_password.text()
        return WebDAVClient(url, user, pwd)

    def _test_connection(self):
        client = self._get_active_client()
        ok, msg, headers = client.test_connection()
        if ok:
            self.lbl_conn_status.setText(msg)
            self.lbl_conn_status.setStyleSheet("color: #10b981; font-size: 12px; font-weight: bold;")
            self.client = client
            self._refresh_dir()
        else:
            self.lbl_conn_status.setText(msg)
            self.lbl_conn_status.setStyleSheet("color: #ef4444; font-size: 12px;")

    def _refresh_dir(self):
        if not self.client:
            self.client = self._get_active_client()

        ok, msg, items = self.client.list_dir(self.current_remote_path)
        if not ok:
            self.lbl_conn_status.setText(msg)
            return

        self.lbl_path.setText(self.current_remote_path)
        self.table_files.setRowCount(0)

        for row_idx, item in enumerate(items):
            self.table_files.insertRow(row_idx)

            # 名称项带对应矢量图标
            name_item = QTableWidgetItem(item["name"])
            icon_name = "folder" if item["is_dir"] else "tools"
            name_item.setIcon(get_icon(icon_name, size=16))
            name_item.setData(Qt.UserRole, item)
            self.table_files.setItem(row_idx, 0, name_item)

            type_str = "文件夹" if item["is_dir"] else "文件"
            self.table_files.setItem(row_idx, 1, QTableWidgetItem(type_str))

            sz_str = "-" if item["is_dir"] else format_bytes(item["size"])
            self.table_files.setItem(row_idx, 2, QTableWidgetItem(sz_str))

            self.table_files.setItem(row_idx, 3, QTableWidgetItem(item.get("modified", "")))

    def _on_table_double_clicked(self, row: int, col: int):
        name_item = self.table_files.item(row, 0)
        if not name_item:
            return
        item_data = name_item.data(Qt.UserRole)
        if item_data and item_data.get("is_dir"):
            # 进入子目录
            name = item_data["name"]
            if self.current_remote_path.endswith("/"):
                self.current_remote_path += name
            else:
                self.current_remote_path += f"/{name}"
            self._refresh_dir()

    def _go_up_dir(self):
        if self.current_remote_path in ("/", ""):
            return
        parts = self.current_remote_path.rstrip("/").split("/")
        parts.pop()
        new_path = "/".join(parts)
        self.current_remote_path = new_path if new_path else "/"
        self._refresh_dir()

    def _create_remote_dir(self):
        if not self.client:
            self.client = self._get_active_client()

        name, ok = QInputDialog.getText(self, "新建远端文件夹", "请输入文件夹名称:")
        if ok and name.strip():
            target = f"{self.current_remote_path.rstrip('/')}/{name.strip()}"
            suc, err = self.client.create_directory(target)
            if suc:
                self._refresh_dir()
            else:
                QMessageBox.warning(self, "创建失败", err)

    def _upload_local_file(self):
        if not self.client:
            self.client = self._get_active_client()

        f_path, _ = QFileDialog.getOpenFileName(self, "选择上传的本地文件")
        if f_path and os.path.isfile(f_path):
            base = os.path.basename(f_path)
            target = f"{self.current_remote_path.rstrip('/')}/{base}"
            suc, err = self.client.upload_file(f_path, target)
            if suc:
                self._refresh_dir()
                QMessageBox.information(self, "上传成功", f"文件 [{base}] 已上传至 WebDAV 服务端。")
            else:
                QMessageBox.warning(self, "上传失败", err)

    def _download_selected_file(self):
        rows = self.table_files.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "请先在列表中选中需要下载的文件。")
            return

        name_item = self.table_files.item(rows[0].row(), 0)
        item_data = name_item.data(Qt.UserRole)
        if not item_data or item_data.get("is_dir"):
            QMessageBox.information(self, "提示", "暂不支持直接下载整个文件夹，请进入后选择文件。")
            return

        name = item_data["name"]
        save_p, _ = QFileDialog.getSaveFileName(self, "保存文件到本地", name)
        if save_p:
            target = f"{self.current_remote_path.rstrip('/')}/{name}"
            suc, err = self.client.download_file(target, save_p)
            if suc:
                QMessageBox.information(self, "下载完成", f"文件已成功保存至:\n{save_p}")
            else:
                QMessageBox.warning(self, "下载失败", err)

    def _mount_network_drive(self):
        dl = self.combo_drive.currentText()
        url = self.le_url.text().strip()
        user = self.le_username.text().strip()
        pwd = self.le_password.text()

        ok, msg = mount_webdav_as_drive(dl, url, user, pwd)
        if ok:
            QMessageBox.information(self, "挂载成功", msg)
        else:
            QMessageBox.critical(self, "挂载失败", msg)

    def _unmount_network_drive(self):
        dl = self.combo_drive.currentText()
        ok, msg = unmount_webdav_drive(dl)
        if ok:
            QMessageBox.information(self, "卸载成功", msg)
        else:
            QMessageBox.warning(self, "断开异常", msg)

    def _copy_mount_cmd(self):
        dl = self.combo_drive.currentText()
        url = self.le_url.text().strip()
        user = self.le_username.text().strip()
        pwd = self.le_password.text()
        cmd = get_windows_mount_cmd(dl, url, user, pwd)
        pyperclip.copy(cmd)
        QMessageBox.information(self, "已复制命令", f"已复制 Windows net use 命令行指令:\n\n{cmd}")

    def _create_new_profile(self):
        name, ok = QInputDialog.getText(self, "新建配置方案", "请输入新方案名称:")
        if ok and name.strip():
            p_name = name.strip()
            self.profiles[p_name] = {
                "url": "http://127.0.0.1:5244/dav/",
                "username": "",
                "password": ""
            }
            self.combo_profiles.addItem(p_name)
            self.combo_profiles.setCurrentText(p_name)
            self.save_settings()

    def _delete_current_profile(self):
        if len(self.profiles) <= 1:
            QMessageBox.information(self, "提示", "至少保留一个配置方案。")
            return
        curr = self.combo_profiles.currentText()
        if curr in self.profiles:
            del self.profiles[curr]
            idx = self.combo_profiles.findText(curr)
            if idx >= 0:
                self.combo_profiles.removeItem(idx)
            self.save_settings()

    def _on_profile_selected(self, name: str):
        if not name or name not in self.profiles:
            return
        self.active_profile_name = name
        data = self.profiles[name]
        self.le_url.setText(data.get("url", "http://127.0.0.1:5244/dav/"))
        self.le_username.setText(data.get("username", ""))
        self.le_password.setText(data.get("password", ""))

    def _save_active_profile(self):
        curr = self.combo_profiles.currentText()
        if not curr:
            curr = "默认节点"
        self.profiles[curr] = {
            "url": self.le_url.text().strip(),
            "username": self.le_username.text().strip(),
            "password": self.le_password.text()
        }
        self.save_settings()
        QMessageBox.information(self, "已保存", f"配置方案 [{curr}] 已成功保存！")

    def load_settings(self):
        cfg = self.config_manager.get_plugin_config(self.PLUGIN_ID, {})
        saved_profiles = cfg.get("profiles", {})
        if saved_profiles:
            self.profiles = saved_profiles
        else:
            self.profiles = {
                "OpenList 默认服务": {
                    "url": "http://127.0.0.1:5244/dav/",
                    "username": "admin",
                    "password": ""
                },
                "AList 本地服务": {
                    "url": "http://127.0.0.1:5244/dav/",
                    "username": "admin",
                    "password": ""
                }
            }

        self.combo_profiles.clear()
        for p_name in self.profiles:
            self.combo_profiles.addItem(p_name)

        active = cfg.get("active_profile", "OpenList 默认服务")
        if active in self.profiles:
            self.combo_profiles.setCurrentText(active)
            self._on_profile_selected(active)
        else:
            first_key = list(self.profiles.keys())[0]
            self.combo_profiles.setCurrentText(first_key)
            self._on_profile_selected(first_key)

    def save_settings(self):
        curr = self.combo_profiles.currentText()
        if curr and curr in self.profiles:
            self.profiles[curr] = {
                "url": self.le_url.text().strip(),
                "username": self.le_username.text().strip(),
                "password": self.le_password.text()
            }
        cfg = {
            "profiles": self.profiles,
            "active_profile": curr
        }
        self.config_manager.set_plugin_config(self.PLUGIN_ID, cfg)
