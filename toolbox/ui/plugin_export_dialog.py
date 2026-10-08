"""
千绘莉多功能工具箱 (Chieri Toolbox) - 独立应用与 Setup 安装包导出向导 (PluginExportDialog)
提供 28 个插件的一键独立应用打包、Setup 安装器生成、快捷方式配置与目录导航。
严格遵循无 Emoji 原则，采用矢量图标与统一排版。
"""

import os
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QCheckBox, QLineEdit, QFileDialog,
    QGroupBox, QMessageBox, QFrame
)
from toolbox.core.plugin_manager import PluginManager
from toolbox.core.paths import get_app_root
from toolbox.core.plugin_exporter import PluginExporter
from toolbox.ui.icons import get_icon, get_pixmap


class PluginExportDialog(QDialog):
    def __init__(self, target_plugin_id: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.plugin_manager = PluginManager()
        self.plugin_manager.discover_and_load()
        self.target_plugin_id = target_plugin_id

        self.init_ui()
        if target_plugin_id:
            idx = self.combo_plugin.findData(target_plugin_id)
            if idx != -1:
                self.combo_plugin.setCurrentIndex(idx)

    def init_ui(self):
        self.setWindowTitle("导出插件为独立 Setup 安装包")
        self.setWindowIcon(get_icon("package", size=24))
        self.resize(580, 520)
        self.setMinimumSize(500, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        # 1. 顶部 Header
        header = QHBoxLayout()
        header.setSpacing(10)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("package", color="#3b82f6", size=26))
        header.addWidget(icon_lbl)

        title_lbl = QLabel("独立应用与 Setup 安装包导出向导")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(title_lbl)
        header.addStretch()
        layout.addLayout(header)

        desc_lbl = QLabel("可将工具箱中任意功能模块打包为完全独立的 Windows 应用程序或安装包，自带开机自启、独立设置与系统托盘。")
        desc_lbl.setStyleSheet("color: #64748b; font-size: 12px;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # 2. 插件选择
        plugin_group = QGroupBox("选择目标功能模块")
        p_layout = QVBoxLayout(plugin_group)
        p_layout.setSpacing(8)

        self.combo_plugin = QComboBox()
        self.combo_plugin.setMinimumHeight(32)
        plugins = self.plugin_manager.get_all_plugins()
        for p in plugins:
            self.combo_plugin.addItem(p.get_icon(size=16), f"{p.name} ({p.category})", p.id)
        self.combo_plugin.currentIndexChanged.connect(self._on_plugin_changed)
        p_layout.addWidget(self.combo_plugin)

        self.lbl_plugin_desc = QLabel()
        self.lbl_plugin_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.lbl_plugin_desc.setWordWrap(True)
        p_layout.addWidget(self.lbl_plugin_desc)
        layout.addWidget(plugin_group)

        # 3. 导出选项
        opt_group = QGroupBox("安装包与打包参数")
        opt_layout = QVBoxLayout(opt_group)
        opt_layout.setSpacing(8)

        self.cb_inno_setup = QCheckBox("使用 Inno Setup 编译独立原生 EXE 安装包 (Setup_<id>.exe)")
        self.cb_inno_setup.setChecked(True)
        self.cb_inno_setup.setStyleSheet("font-weight: 600; color: #0284c7;")
        opt_layout.addWidget(self.cb_inno_setup)

        iscc_path = PluginExporter.find_iscc_executable()
        self.lbl_iscc_status = QLabel()
        if iscc_path:
            is_embedded = "bin" in iscc_path.lower() and "innosetup" in iscc_path.lower()
            tag = "已就绪项目内置 Inno Setup 编译器" if is_embedded else "已检测到系统 Inno Setup 编译器"
            self.lbl_iscc_status.setText(f"{tag}: {iscc_path}")
            self.lbl_iscc_status.setStyleSheet("color: #10b981; font-size: 11px;")
        else:
            self.lbl_iscc_status.setText("未检测到 Inno Setup 编译器，将生成 .iss 脚本与一键编译批处理")
            self.lbl_iscc_status.setStyleSheet("color: #f59e0b; font-size: 11px;")
        opt_layout.addWidget(self.lbl_iscc_status)

        self.cb_create_setup = QCheckBox("生成独立 Setup 一键安装程序 (含安装向导与卸载脚本)")
        self.cb_create_setup.setChecked(True)
        self.cb_create_setup.setStyleSheet("font-weight: 500;")
        opt_layout.addWidget(self.cb_create_setup)

        self.cb_desktop_shortcut = QCheckBox("默认生成桌面与开始菜单快捷方式")
        self.cb_desktop_shortcut.setChecked(True)
        opt_layout.addWidget(self.cb_desktop_shortcut)

        self.cb_default_autostart = QCheckBox("默认开启 Windows 开机自启动与独立托盘常驻")
        self.cb_default_autostart.setChecked(False)
        opt_layout.addWidget(self.cb_default_autostart)

        self.cb_pyinstaller_spec = QCheckBox("生成 PyInstaller 单文件编译规范 (.spec & .bat)")
        self.cb_pyinstaller_spec.setChecked(True)
        opt_layout.addWidget(self.cb_pyinstaller_spec)

        self.cb_zip_archive = QCheckBox("同时打包为 ZIP 自动化压缩包")
        self.cb_zip_archive.setChecked(True)
        opt_layout.addWidget(self.cb_zip_archive)

        layout.addWidget(opt_group)

        # 4. 导出路径
        path_group = QGroupBox("导出保存目录")
        path_layout = QHBoxLayout(path_group)
        path_layout.setSpacing(8)

        default_out = os.path.join(get_app_root(), "dist", "standalone_plugins")
        self.le_output_dir = QLineEdit(default_out)
        self.le_output_dir.setMinimumHeight(28)
        path_layout.addWidget(self.le_output_dir, 1)

        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.setIcon(get_icon("folder", size=14))
        self.btn_browse.clicked.connect(self._browse_output_dir)
        path_layout.addWidget(self.btn_browse)

        layout.addWidget(path_group)

        # 状态展示
        self.lbl_status = QLabel("就绪 · 点击下方按钮开始导出")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(self.lbl_status)

        layout.addStretch()

        # 底部操作栏
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        self.btn_open_folder = QPushButton("打开导出目录")
        self.btn_open_folder.setIcon(get_icon("folder", size=14))
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self._open_output_folder)
        bottom_layout.addWidget(self.btn_open_folder)

        bottom_layout.addStretch()

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)

        self.btn_export = QPushButton("立即开始导出")
        self.btn_export.setObjectName("primaryBtn")
        self.btn_export.setIcon(get_icon("package", color="#ffffff", size=14))
        self.btn_export.setFixedHeight(34)
        self.btn_export.clicked.connect(self._do_export)
        bottom_layout.addWidget(self.btn_export)

        layout.addLayout(bottom_layout)
        self._on_plugin_changed(self.combo_plugin.currentIndex())

    def _on_plugin_changed(self, index: int):
        pid = self.combo_plugin.currentData()
        p = self.plugin_manager.get_plugin(pid)
        if p:
            self.lbl_plugin_desc.setText(f"功能简述: {p.description}")

    def _browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择导出目录", self.le_output_dir.text())
        if d:
            self.le_output_dir.setText(d)

    def _do_export(self):
        pid = self.combo_plugin.currentData()
        out_dir = self.le_output_dir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "提示", "请选择有效的导出保存目录。")
            return

        self.btn_export.setEnabled(False)
        self.lbl_status.setText("正在打包生成独立应用与 Setup 安装程序...")

        res = PluginExporter.export_plugin(
            plugin_id=pid,
            output_dir=out_dir,
            package_type="setup" if self.cb_create_setup.isChecked() else "portable",
            create_shortcuts=self.cb_desktop_shortcut.isChecked(),
            autostart_default=self.cb_default_autostart.isChecked(),
            create_archive=self.cb_zip_archive.isChecked(),
            generate_pyinstaller_spec=self.cb_pyinstaller_spec.isChecked(),
            compile_inno_setup=self.cb_inno_setup.isChecked(),
        )

        self.btn_export.setEnabled(True)
        if res.get("success"):
            target_p = res.get("output_dir")
            archive_p = res.get("archive_path")
            installer_exe = res.get("installer_exe")
            iss_p = res.get("iss_path")

            msg = f"插件「{res.get('plugin_name')}」已成功导出！\n"
            if installer_exe:
                msg += f"\n原生 EXE 安装包: {installer_exe}"
            if target_p:
                msg += f"\n应用解压目录: {target_p}"
            if archive_p:
                msg += f"\n便携压缩安装包: {archive_p}"
            if iss_p:
                msg += f"\nInno Setup 工程脚本: {iss_p}"
            if res.get("compile_error") and not installer_exe:
                msg += f"\n\n注意: {res.get('compile_error')}"

            self.lbl_status.setText("导出成功！原生 EXE 安装包已就绪。")
            self.lbl_status.setStyleSheet("color: #10b981; font-weight: bold; font-size: 12px;")
            self.btn_open_folder.setVisible(True)
            self._last_exported_dir = out_dir
            QMessageBox.information(self, "导出成功", msg)
        else:
            err = res.get("error", "未知错误")
            self.lbl_status.setText(f"导出失败: {err}")
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 12px;")
            QMessageBox.critical(self, "导出失败", f"导出过程发生异常:\n{err}")

    def _open_output_folder(self):
        path_to_open = getattr(self, "_last_exported_dir", self.le_output_dir.text())
        if os.path.exists(path_to_open):
            os.startfile(path_to_open)
