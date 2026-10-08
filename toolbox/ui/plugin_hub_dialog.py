"""
工具箱 (Toolbox) - 插件工坊与插件管理器 (PluginHubDialog / PluginHubWidget)
提供全量插件（包含 22 个内置核心与外部独立扩展）的卡片化生命周期管理：
- 实时启停切换 (Enable / Disable)
- 安全热卸载 (Hot Unload)
- 物理删除与磁盘空间释放 (Uninstall)
- 离线包导入安装 (.cpk / .zip，带 ZipSlip 路径穿越防御)
- 独立便携包导出 (.cpk)
"""

import os
from typing import Optional, List, Dict, Any
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QScrollArea, QFrame, QMessageBox,
    QFileDialog, QButtonGroup
)
from PySide6.QtGui import QIcon

from toolbox.core.plugin_manager import PluginManager
from toolbox.core.config_manager import ConfigManager
from toolbox.core.theme import ThemeManager
from toolbox.core.paths import get_external_plugins_dir, is_portable_mode
from toolbox.ui.icons import get_icon, get_pixmap, get_plugin_icon, get_plugin_badge_pixmap


def _format_size(size_bytes: int) -> str:
    """人性化格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


class PluginHubWidget(QWidget):
    """插件工坊主控件，可独立嵌入或作为对话框展示"""

    plugin_state_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.pm = PluginManager()
        self.cfg = ConfigManager()
        self.tm = ThemeManager()
        self.current_filter_category = "all"
        self.search_keyword = ""
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(100)
        self._search_timer.timeout.connect(self.refresh_plugins_list)

        self.init_ui()
        self.refresh_plugins_list()

        # 监听插件管理器全局生命周期信号以实现无缝自响应
        self.pm.plugin_loaded.connect(self._on_lifecycle_event)
        self.pm.plugin_unloaded.connect(self._on_lifecycle_event)
        self.pm.plugin_enabled.connect(self._on_lifecycle_event)
        self.pm.plugin_disabled.connect(self._on_lifecycle_event)
        self.pm.plugin_installed.connect(self._on_lifecycle_event)
        self.pm.plugin_uninstalled.connect(self._on_lifecycle_event)
        self.destroyed.connect(self.cleanup)

    def cleanup(self, *args):
        """断开与全局插件管理器的所有信号连接，防止内存泄露与失效调用"""
        if getattr(self, "_is_cleaned_up", False):
            return
        self._is_cleaned_up = True
        for sig in (
            self.pm.plugin_loaded, self.pm.plugin_unloaded,
            self.pm.plugin_enabled, self.pm.plugin_disabled,
            self.pm.plugin_installed, self.pm.plugin_uninstalled
        ):
            try:
                sig.disconnect(self._on_lifecycle_event)
            except Exception:
                pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def _on_lifecycle_event(self, *args):
        # 延迟微防抖刷新
        QTimer.singleShot(20, self.refresh_plugins_list)
        self.plugin_state_changed.emit()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 14)
        main_layout.setSpacing(12)

        # 1. 顶部 Header 与全局动作
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("puzzle", color="#3b82f6", size=26))
        header_layout.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        lbl_title = QLabel("插件工坊与模块管理 (Plugin Hub)")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_vbox.addWidget(lbl_title)

        lbl_sub = QLabel("微内核架构 · 模块随删随装 · 动态热加载 · 离线包导入导出")
        lbl_sub.setStyleSheet("font-size: 11px; color: #94a3b8;")
        title_vbox.addWidget(lbl_sub)
        header_layout.addLayout(title_vbox, 1)

        # 动作按钮：导入安装与刷新
        self.btn_import = QPushButton("本地安装插件 (.cpk/.zip)")
        self.btn_import.setObjectName("primaryBtn")
        self.btn_import.setIcon(get_icon("download", color="#ffffff", size=14))
        self.btn_import.clicked.connect(self._action_import_package)
        header_layout.addWidget(self.btn_import)

        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setIcon(get_icon("refresh", size=14))
        self.btn_refresh.clicked.connect(self._action_refresh_scan)
        header_layout.addWidget(self.btn_refresh)

        main_layout.addLayout(header_layout)

        # 2. 搜索框与过滤器标签胶囊
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        self.search_le = QLineEdit()
        self.search_le.setPlaceholderText("搜索插件名称、描述、分类或 ID...")
        self.search_le.setMinimumHeight(28)
        self.search_le.textChanged.connect(self._on_search_text_changed)
        filter_bar.addWidget(self.search_le, 1)

        # 过滤分类芯片按钮组
        self.filter_btn_group = QButtonGroup(self)
        self.filter_btn_group.setExclusive(True)

        filters = [
            ("all", "全部"),
            ("enabled", "已启用"),
            ("disabled", "已停用"),
            ("builtin", "核心内置"),
            ("external", "外部扩展"),
        ]
        for f_key, f_label in filters:
            btn = QPushButton(f_label)
            btn.setCheckable(True)
            if f_key == "all":
                btn.setChecked(True)
            btn.setStyleSheet(self._get_chip_style())
            btn.clicked.connect(lambda checked, k=f_key: self._on_filter_chip_clicked(k))
            self.filter_btn_group.addButton(btn)
            filter_bar.addWidget(btn)

        main_layout.addLayout(filter_bar)

        # 3. 插件卡片展示滚动区
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #2e3547; border-radius: 6px; }")

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(10, 10, 10, 10)
        self.cards_layout.setSpacing(8)

        self.scroll_area.setWidget(self.cards_container)
        main_layout.addWidget(self.scroll_area, 1)

        # 4. 底部状态摘要与插件目录直达
        footer_layout = QHBoxLayout()
        self.lbl_stats = QLabel("统计信息加载中...")
        self.lbl_stats.setStyleSheet("color: #64748b; font-size: 11px;")
        footer_layout.addWidget(self.lbl_stats, 1)

        self.btn_open_folder = QPushButton("打开扩展插件目录")
        self.btn_open_folder.setIcon(get_icon("folder", size=13))
        self.btn_open_folder.clicked.connect(self._action_open_external_dir)
        footer_layout.addWidget(self.btn_open_folder)

        main_layout.addLayout(footer_layout)

    def _get_chip_style(self) -> str:
        is_dark = self.tm.is_dark()
        bg = "#1e293b" if is_dark else "#f1f5f9"
        border = "#334155" if is_dark else "#cbd5e1"
        text = "#94a3b8" if is_dark else "#475569"
        return f"""
            QPushButton {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 3px 10px;
                font-size: 11px;
                color: {text};
            }}
            QPushButton:hover {{
                border-color: #3b82f6;
                color: #3b82f6;
            }}
            QPushButton:checked {{
                background-color: #2563eb;
                border-color: #2563eb;
                color: #ffffff;
                font-weight: bold;
            }}
        """

    def _on_search_text_changed(self, text: str):
        self.search_keyword = text.strip().lower()
        self._search_timer.start()

    def _on_filter_chip_clicked(self, filter_key: str):
        self.current_filter_category = filter_key
        self.refresh_plugins_list()

    def refresh_plugins_list(self):
        """刷新并渲染所有插件卡片"""
        # 清空现有卡片
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        records = self.pm.get_all_plugin_records()

        # 统计数据计算
        total_count = len(records)
        enabled_count = sum(1 for r in records if r["is_enabled"])
        disabled_count = total_count - enabled_count
        external_count = sum(1 for r in records if not r["is_builtin"])

        storage_mode = "绿色便携目录" if is_portable_mode() else "用户 AppData"
        self.lbl_stats.setText(
            f"共 {total_count} 个功能模块 | 已启用: {enabled_count} | "
            f"已停用: {disabled_count} | 外部扩展: {external_count} ({storage_mode})"
        )

        # 过滤展示列表
        filtered = []
        for r in records:
            # 状态过滤
            if self.current_filter_category == "enabled" and not r["is_enabled"]:
                continue
            if self.current_filter_category == "disabled" and r["is_enabled"]:
                continue
            if self.current_filter_category == "builtin" and not r["is_builtin"]:
                continue
            if self.current_filter_category == "external" and r["is_builtin"]:
                continue

            # 关键词过滤
            if self.search_keyword:
                kw = self.search_keyword
                in_name = kw in r["name"].lower()
                in_desc = kw in r["description"].lower()
                in_id = kw in r["id"].lower()
                in_cat = kw in r["category"].lower()
                if not (in_name or in_desc or in_id or in_cat):
                    continue

            filtered.append(r)

        # 构建卡片
        is_dark = self.tm.is_dark()
        card_bg = "#1e293b" if is_dark else "#f8fafc"
        card_border = "#334155" if is_dark else "#e2e8f0"

        for r in filtered:
            card = self._build_plugin_card(r, card_bg, card_border)
            self.cards_layout.addWidget(card)

        if not filtered:
            empty_lbl = QLabel("未找到匹配的功能模块")
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet("color: #64748b; font-size: 13px; margin: 30px 0;")
            self.cards_layout.addWidget(empty_lbl)

        self.cards_layout.addStretch()

    def _build_plugin_card(self, r: Dict[str, Any], bg: str, border: str) -> QFrame:
        card = QFrame()
        card.setObjectName("pluginHubCard")
        card.setStyleSheet(f"""
            QFrame#pluginHubCard {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # 1. 图标展示 (36x36)
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(36, 36)
        p_dir = r.get("dir", "")
        pix = get_plugin_badge_pixmap(r["id"], size=36)
        icon_lbl.setPixmap(pix)
        layout.addWidget(icon_lbl)

        # 2. 中间信息区
        info_vbox = QVBoxLayout()
        info_vbox.setSpacing(4)

        # 标题栏：名称、版本号、核心/扩展徽章、类别徽章
        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        name_lbl = QLabel(r["name"])
        name_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        title_row.addWidget(name_lbl)

        ver_lbl = QLabel(f"v{r['version']}")
        ver_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; background: rgba(56, 189, 248, 0.15); padding: 1px 6px; border-radius: 4px;")
        title_row.addWidget(ver_lbl)

        type_text = "核心内置" if r["is_builtin"] else "外部扩展"
        type_color = "#10b981" if r["is_builtin"] else "#f59e0b"
        type_lbl = QLabel(type_text)
        type_lbl.setStyleSheet(f"color: {type_color}; font-size: 10px; background: rgba(16, 185, 129, 0.1); padding: 1px 5px; border-radius: 4px;")
        title_row.addWidget(type_lbl)

        cat_lbl = QLabel(r["category"])
        cat_lbl.setStyleSheet("color: #94a3b8; font-size: 10px; background: rgba(148, 163, 184, 0.1); padding: 1px 5px; border-radius: 4px;")
        title_row.addWidget(cat_lbl)

        title_row.addStretch()
        info_vbox.addLayout(title_row)

        # 描述
        desc_text = r["description"] or "暂无插件描述"
        desc_lbl = QLabel(desc_text)
        desc_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        desc_lbl.setWordWrap(True)
        info_vbox.addWidget(desc_lbl)

        # 底部细节：ID, 大小, 作者
        detail_row = QHBoxLayout()
        detail_row.setSpacing(12)
        id_lbl = QLabel(f"ID: {r['id']}")
        id_lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
        detail_row.addWidget(id_lbl)

        sz_lbl = QLabel(f"大小: {_format_size(r['size_bytes'])}")
        sz_lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
        detail_row.addWidget(sz_lbl)

        author_lbl = QLabel(f"作者: {r['author']}")
        author_lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
        detail_row.addWidget(author_lbl)

        detail_row.addStretch()
        info_vbox.addLayout(detail_row)

        layout.addLayout(info_vbox, 1)

        # 3. 右侧操作动作区
        action_vbox = QVBoxLayout()
        action_vbox.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        action_vbox.setSpacing(6)

        # 状态指示
        status_row = QHBoxLayout()
        status_row.setSpacing(4)
        status_dot = QLabel("●" if r["is_enabled"] else "○")
        status_dot.setStyleSheet("color: #22c55e;" if r["is_enabled"] else "color: #94a3b8;")
        status_lbl = QLabel("运行中" if r["is_enabled"] else "已停用")
        status_lbl.setStyleSheet("color: #22c55e; font-size: 11px; font-weight: bold;" if r["is_enabled"] else "color: #94a3b8; font-size: 11px;")
        status_row.addWidget(status_dot)
        status_row.addWidget(status_lbl)
        action_vbox.addLayout(status_row)

        # 操作按钮排
        btns_row = QHBoxLayout()
        btns_row.setSpacing(6)

        # 启停切换开关
        btn_toggle = QPushButton("停用" if r["is_enabled"] else "启用")
        btn_toggle.setFixedSize(54, 26)
        if r["is_enabled"]:
            btn_toggle.setStyleSheet("background-color: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 4px; font-size: 11px;")
        else:
            btn_toggle.setStyleSheet("background-color: #0284c7; color: #ffffff; border: none; border-radius: 4px; font-size: 11px; font-weight: bold;")
        btn_toggle.clicked.connect(lambda checked, pid=r["id"], en=r["is_enabled"]: self._action_toggle_plugin(pid, not en))
        btns_row.addWidget(btn_toggle)

        # 导出便携包按钮
        btn_export = QPushButton("导出包")
        btn_export.setFixedSize(56, 26)
        btn_export.setToolTip("将该插件导出为标准的独立 .cpk 便携分发包")
        btn_export.setStyleSheet("font-size: 11px;")
        btn_export.clicked.connect(lambda checked, pid=r["id"]: self._action_export_plugin(pid))
        btns_row.addWidget(btn_export)

        # 卸载 / 移除按钮
        btn_del = QPushButton("卸载")
        btn_del.setFixedSize(46, 26)
        btn_del.setToolTip("卸载并彻底释放磁盘空间" if not r["is_builtin"] else "核心插件不可物理删除，将执行停用")
        btn_del.setStyleSheet("font-size: 11px; color: #64748b;")
        btn_del.clicked.connect(lambda checked, pid=r["id"], is_b=r["is_builtin"]: self._action_uninstall_plugin(pid, is_b))
        btns_row.addWidget(btn_del)

        action_vbox.addLayout(btns_row)
        layout.addLayout(action_vbox)

        return card

    def _action_toggle_plugin(self, plugin_id: str, enable: bool):
        """启停切换插件（生命周期事件将自动驱动统一单次防抖刷新）"""
        if enable:
            self.pm.enable_plugin(plugin_id)
        else:
            self.pm.disable_plugin(plugin_id)

    def _action_export_plugin(self, plugin_id: str):
        """导出 .cpk 插件包"""
        out_dir = QFileDialog.getExistingDirectory(self, "选择插件包导出目录")
        if not out_dir:
            return
        try:
            exported_path = self.pm.export_plugin_cpk(plugin_id, out_dir)
            QMessageBox.information(
                self,
                "导出成功",
                f"插件包已成功导出为标准 .cpk 文件：\n{exported_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出插件包发生异常: {e}")

    def _action_uninstall_plugin(self, plugin_id: str, is_builtin: bool):
        """卸载并清理插件"""
        if is_builtin:
            reply = QMessageBox.question(
                self,
                "提示",
                f"插件 [{plugin_id}] 为工具箱内置核心功能，无法物理删除核心文件。\n是否将其停用？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.pm.disable_plugin(plugin_id)
                self.plugin_state_changed.emit()
                self.refresh_plugins_list()
            return

        reply = QMessageBox.warning(
            self,
            "确认卸载删除",
            f"确定要彻底卸载插件 [{plugin_id}] 吗？\n该操作将永久物理删除该插件对应的磁盘文件并释放空间！",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.pm.uninstall_plugin(plugin_id)
                self.plugin_state_changed.emit()
                self.refresh_plugins_list()
                QMessageBox.information(self, "卸载成功", f"插件 [{plugin_id}] 已完全卸载，空间已回收。")
            except Exception as e:
                QMessageBox.critical(self, "卸载异常", f"卸载过程发生异常: {e}")

    def _action_import_package(self):
        """离线包导入安装"""
        fpath, _ = QFileDialog.getOpenFileName(
            self,
            "选择离线插件包",
            "",
            "千绘莉插件包 (*.cpk *.zip);;所有文件 (*.*)"
        )
        if not fpath:
            return

        try:
            plugin = self.pm.install_plugin_package(fpath)
            self.plugin_state_changed.emit()
            self.refresh_plugins_list()
            QMessageBox.information(
                self,
                "安装成功",
                f"插件「{plugin.name}」已成功安装并动态热加载生效！\n无需重启应用即可随时使用。"
            )
        except Exception as e:
            QMessageBox.critical(self, "安装失败", f"导入插件包失败:\n{e}")

    def _action_refresh_scan(self):
        """重新扫描插件目录"""
        self.pm.discover_and_load(load_disabled=False)
        self.refresh_plugins_list()
        self.plugin_state_changed.emit()

    def _action_open_external_dir(self):
        """在文件管理器中打开外部扩展插件目录"""
        ext_dir = get_external_plugins_dir()
        os.makedirs(ext_dir, exist_ok=True)
        try:
            os.startfile(ext_dir)
        except Exception as e:
            QMessageBox.warning(self, "提示", f"无法打开目录: {e}")


class PluginHubDialog(QDialog):
    """插件工坊独立模态对话框封装"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("千绘莉插件工坊 (Plugin Hub)")
        self.setWindowIcon(get_icon("puzzle", size=24))
        self.resize(780, 560)
        self.setMinimumSize(680, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.hub_widget = PluginHubWidget(self)
        layout.addWidget(self.hub_widget)

    def closeEvent(self, event):
        if hasattr(self, "hub_widget") and self.hub_widget:
            self.hub_widget.cleanup()
        super().closeEvent(event)
