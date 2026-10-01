"""
工具箱 (Toolbox) - 现代化设置中心 (SettingsDialog)
提供插件显隐调节、开机自启多选调度、多开模式切换、UI透明度与毛玻璃级别微调及运行环境自检。
严格遵循无 Emoji 原则，采用矢量图标与现代化深浅响应式排版。
"""

from typing import List, Dict, Optional
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QCheckBox, QSlider, QScrollArea,
    QGroupBox, QListWidget, QListWidgetItem, QFrame, QMessageBox,
    QLineEdit, QGridLayout, QComboBox, QFileDialog
)

import os
import winreg
from toolbox.core.config_manager import ConfigManager
from toolbox.core.plugin_manager import PluginManager
from toolbox.core.plugin_exporter import PluginExporter
from toolbox.core.event_bus import EventBus
from toolbox.core.theme import ThemeManager
from toolbox.core.window_effects import apply_window_opacity, apply_dual_opacity, apply_acrylic_effect
from toolbox.ui.icons import get_icon, get_pixmap, get_plugin_badge_pixmap
from toolbox.plugins.system_integrator.registry_ops import (
    set_autostart, is_autostart_enabled, run_system_health_check, get_toolbox_main_command
)


class SettingsDialog(QDialog):
    settings_saved = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self.plugin_manager = PluginManager()
        if not self.plugin_manager.get_all_plugins():
            self.plugin_manager.discover_and_load()
        self.theme_manager = ThemeManager()
        self.event_bus = EventBus()

        from toolbox.core.tray_manager import PluginTrayManager
        self.tray_manager = PluginTrayManager()
        self.tray_manager.tray_changed.connect(self._sync_tray_ui_state)

        self._plugin_checkboxes: Dict[str, QCheckBox] = {}
        self._autostart_checkboxes: Dict[str, QCheckBox] = {}
        self._tray_checkboxes: Dict[str, QCheckBox] = {}
        self._plugin_tray_checkboxes: Dict[str, QCheckBox] = {}
        self._tray_status_labels: Dict[str, QLabel] = {}

        self._card_preview_timer = QTimer(self)
        self._card_preview_timer.setSingleShot(True)
        self._card_preview_timer.setInterval(40)
        self._card_preview_timer.timeout.connect(self._do_preview_card_layout)

        self._opacity_preview_timer = QTimer(self)
        self._opacity_preview_timer.setSingleShot(True)
        self._opacity_preview_timer.setInterval(40)
        self._opacity_preview_timer.timeout.connect(self._do_preview_opacity)

        self._blur_preview_timer = QTimer(self)
        self._blur_preview_timer.setSingleShot(True)
        self._blur_preview_timer.setInterval(40)
        self._blur_preview_timer.timeout.connect(self._do_preview_blur)

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        self.setWindowTitle("工具箱设置中心")
        self.setWindowIcon(get_icon("settings", size=24))
        self.resize(760, 580)
        self.setMinimumSize(660, 480)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 18)
        main_layout.setSpacing(14)

        # 顶部标题栏
        top_bar = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("settings", color="#3b82f6", size=26))
        top_bar.addWidget(icon_lbl)

        title_lbl = QLabel("全局参数与功能偏好设置")
        title_lbl.setStyleSheet("font-size: 17px; font-weight: bold;")
        top_bar.addWidget(title_lbl)
        top_bar.addStretch()
        main_layout.addLayout(top_bar)

        # 选项卡控件
        self.tabs = QTabWidget()
        self.tabs.setObjectName("settingsTab")

        # 选项卡 1: 功能模块管理
        self.tab_plugins = self._build_plugins_tab()
        self.tabs.addTab(self.tab_plugins, "功能模块管理")

        # 选项卡 2: 独立系统托盘常驻管理
        self.tab_tray = self._build_tray_tab()
        self.tabs.addTab(self.tab_tray, "系统托盘常驻")

        # 选项卡 3: 启动与多开设置
        self.tab_boot = self._build_boot_tab()
        self.tabs.addTab(self.tab_boot, "启动与多开行为")

        # 选项卡 3: 视觉与特效设置
        self.tab_visual = self._build_visual_tab()
        self.tabs.addTab(self.tab_visual, "界面视觉与特效")

        # 选项卡 4: 独立应用导出
        self.tab_export = self._build_export_tab()
        self.tabs.addTab(self.tab_export, "独立应用导出")

        main_layout.addWidget(self.tabs, 1)

        # 底部操作按钮
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)
        bottom_layout.addStretch()

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)

        self.btn_apply = QPushButton("应用")
        self.btn_apply.clicked.connect(self._apply_settings_action)
        bottom_layout.addWidget(self.btn_apply)

        self.btn_save = QPushButton("确定")
        self.btn_save.setObjectName("primaryBtn")
        self.btn_save.setIcon(get_icon("check", color="#ffffff", size=14))
        self.btn_save.clicked.connect(self._save_and_close_action)
        bottom_layout.addWidget(self.btn_save)

        main_layout.addLayout(bottom_layout)

    def _build_plugins_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        desc_lbl = QLabel("可在此处按需启用或关闭特定的插件功能。关闭后该功能将不会出现在首页及最近使用中。")
        desc_lbl.setStyleSheet("color: #64748b; font-size: 12px;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # 工具栏：搜索与快捷操作
        tool_bar = QHBoxLayout()
        self.le_plugin_filter = QLineEdit()
        self.le_plugin_filter.setPlaceholderText("过滤功能模块...")
        self.le_plugin_filter.setMinimumHeight(28)
        self.le_plugin_filter.textChanged.connect(self._filter_plugins_list)
        tool_bar.addWidget(self.le_plugin_filter, 1)

        btn_select_all = QPushButton("全部启用")
        btn_select_all.clicked.connect(lambda: self._set_all_plugins(True))
        tool_bar.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("全部关闭")
        btn_deselect_all.clicked.connect(lambda: self._set_all_plugins(False))
        tool_bar.addWidget(btn_deselect_all)

        layout.addLayout(tool_bar)

        # 滚动列表承载各插件项
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #2e3547; border-radius: 6px; }")

        self.plugin_list_container = QWidget()
        self.plugin_list_layout = QVBoxLayout(self.plugin_list_container)
        self.plugin_list_layout.setContentsMargins(8, 8, 8, 8)
        self.plugin_list_layout.setSpacing(6)

        scroll.setWidget(self.plugin_list_container)
        layout.addWidget(scroll, 1)

        return widget

    def _build_tray_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        desc_lbl = QLabel(
            "独立系统托盘常驻管理：\n"
            "在此选择需要独立常驻在 Windows 任务栏系统托盘的功能模块。勾选后，插件专属独立图标将即时常驻右下角通知区域，"
            "右键即可呼出专属快捷功能栏、设置与退出选项，无需打开工具箱主窗口即可随时随地调用。"
        )
        desc_lbl.setStyleSheet("color: #64748b; font-size: 12px; line-height: 1.4;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # 工具栏：搜索与快捷操作
        tool_bar = QHBoxLayout()
        self.le_tray_filter = QLineEdit()
        self.le_tray_filter.setPlaceholderText("过滤托盘插件...")
        self.le_tray_filter.setMinimumHeight(28)
        self.le_tray_filter.textChanged.connect(self._filter_tray_list)
        tool_bar.addWidget(self.le_tray_filter, 1)

        btn_select_all = QPushButton("全部常驻")
        btn_select_all.clicked.connect(lambda: self._set_all_tray_plugins(True))
        tool_bar.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("全部取消")
        btn_deselect_all.clicked.connect(lambda: self._set_all_tray_plugins(False))
        tool_bar.addWidget(btn_deselect_all)

        layout.addLayout(tool_bar)

        # 滚动列表承载各托盘项
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #2e3547; border-radius: 6px; }")

        self.tray_list_container = QWidget()
        self.tray_list_layout = QVBoxLayout(self.tray_list_container)
        self.tray_list_layout.setContentsMargins(8, 8, 8, 8)
        self.tray_list_layout.setSpacing(6)

        scroll.setWidget(self.tray_list_container)
        layout.addWidget(scroll, 1)

        return widget

    def _get_main_window(self):
        from toolbox.ui.main_window import MainWindow
        parent = self.parentWidget()
        if isinstance(parent, MainWindow):
            return parent
        for top in QApplication.topLevelWidgets():
            if isinstance(top, MainWindow):
                return top
        return None

    def _filter_tray_list(self, text: str):
        kw = text.strip().lower()
        for p in self.plugin_manager.get_all_plugins():
            cb = self._tray_checkboxes.get(p.id)
            if not cb:
                continue
            parent_frame = cb.parentWidget()
            if not parent_frame:
                continue
            visible = (not kw) or (kw in p.name.lower()) or (kw in p.description.lower()) or (kw in p.category.lower()) or (kw in p.id.lower())
            parent_frame.setVisible(visible)

    def _set_all_tray_plugins(self, enable: bool):
        for pid, cb in list(self._tray_checkboxes.items()):
            if enable and not cb.isEnabled():
                continue
            if cb.isChecked() != enable:
                cb.setChecked(enable)

    def _sync_tray_ui_state(self, plugin_id: str, checked: bool):
        if plugin_id in self._tray_checkboxes:
            cb = self._tray_checkboxes[plugin_id]
            try:
                if cb.isChecked() != checked:
                    cb.blockSignals(True)
                    cb.setChecked(checked)
                    cb.blockSignals(False)
            except RuntimeError:
                pass

        if plugin_id in self._plugin_tray_checkboxes:
            cb = self._plugin_tray_checkboxes[plugin_id]
            try:
                if cb.isChecked() != checked:
                    cb.blockSignals(True)
                    cb.setChecked(checked)
                    cb.blockSignals(False)
            except RuntimeError:
                pass

        if plugin_id in self._tray_status_labels:
            lbl = self._tray_status_labels[plugin_id]
            try:
                if checked:
                    lbl.setText("常驻中")
                    lbl.setStyleSheet("color: #10b981; font-size: 11px; font-weight: bold; background: #064e3b; padding: 2px 6px; border-radius: 4px;")
                else:
                    lbl.setText("未常驻")
                    lbl.setStyleSheet("color: #64748b; font-size: 11px; background: #1e293b; padding: 2px 6px; border-radius: 4px;")
            except RuntimeError:
                pass

    def _on_plugin_enabled_toggled(self, plugin_id: str, enabled: bool):
        """当插件启用状态变化时，联动控制系统托盘勾选项"""
        if plugin_id in self._plugin_tray_checkboxes:
            cb_fast = self._plugin_tray_checkboxes[plugin_id]
            try:
                cb_fast.setEnabled(enabled)
                cb_fast.setToolTip("显示在系统托盘" if enabled else "需先启用此插件才能常驻系统托盘")
                if not enabled and cb_fast.isChecked():
                    cb_fast.setChecked(False)
            except RuntimeError:
                pass

        if plugin_id in self._tray_checkboxes:
            cb_tray = self._tray_checkboxes[plugin_id]
            try:
                cb_tray.setEnabled(enabled)
                cb_tray.setToolTip("" if enabled else "需先在「功能模块管理」中启用此插件才能常驻系统托盘")
                if not enabled and cb_tray.isChecked():
                    cb_tray.setChecked(False)
            except RuntimeError:
                pass

    def _on_tray_plugin_toggled(self, plugin_id: str, checked: bool):
        self._sync_tray_ui_state(plugin_id, checked)
        self.config_manager.set_tray_plugin(plugin_id, checked)

        p = self.plugin_manager.get_plugin(plugin_id)
        if not p:
            return

        if checked:
            self.tray_manager.add_tray_icon(p)
        else:
            self.tray_manager.remove_tray_icon(plugin_id)

    def _build_boot_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        # 1. 开机自启组
        autostart_group = QGroupBox("开机自启动与功能直达")
        as_layout = QVBoxLayout(autostart_group)
        as_layout.setSpacing(8)

        self.cb_autostart_enabled = QCheckBox("开启 Windows 系统开机自启")
        self.cb_autostart_enabled.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.cb_autostart_enabled.toggled.connect(self._on_autostart_toggled)
        as_layout.addWidget(self.cb_autostart_enabled)

        as_hint = QLabel("勾选后，工具箱将在 Windows 启动时自启动。您可以多选需要自启时直接调度打开的功能：")
        as_hint.setStyleSheet("color: #64748b; font-size: 12px;")
        as_hint.setWordWrap(True)
        as_layout.addWidget(as_hint)

        # 自启动功能多选列表
        self.autostart_scroll = QScrollArea()
        self.autostart_scroll.setFixedHeight(150)
        self.autostart_scroll.setWidgetResizable(True)
        self.autostart_scroll.setStyleSheet("QScrollArea { border: 1px solid #2e3547; border-radius: 6px; }")

        self.autostart_container = QWidget()
        self.autostart_layout = QVBoxLayout(self.autostart_container)
        self.autostart_layout.setContentsMargins(6, 6, 6, 6)
        self.autostart_layout.setSpacing(4)
        self.autostart_scroll.setWidget(self.autostart_container)

        as_layout.addWidget(self.autostart_scroll)
        layout.addWidget(autostart_group)

        # 2. 多开功能组
        multi_win_group = QGroupBox("多开模式 (独立窗口运行)")
        mw_layout = QVBoxLayout(multi_win_group)
        mw_layout.setSpacing(8)

        self.cb_multi_window = QCheckBox("开启多开功能 (打开插件时不使用页面切换，而是新建独立窗口并保留首页)")
        self.cb_multi_window.setStyleSheet("font-weight: 600; font-size: 13px;")
        mw_layout.addWidget(self.cb_multi_window)

        mw_hint = QLabel(
            "开启此功能后，点击任意功能卡片都会在其独立的顶级窗口中启动，主首页窗口保持常驻。"
            "您可以同时开启多个不同的工具进行并行操作。每个独立窗口均可单独记忆其窗口大小与屏幕位置。"
        )
        mw_hint.setStyleSheet("color: #64748b; font-size: 12px;")
        mw_hint.setWordWrap(True)
        mw_layout.addWidget(mw_hint)

        layout.addWidget(multi_win_group)

        # 3. 首页打开默认展示分组
        startup_group_box = QGroupBox("首页启动与默认展示项")
        sg_layout = QVBoxLayout(startup_group_box)
        sg_layout.setSpacing(8)

        row_sg = QHBoxLayout()
        row_sg.addWidget(QLabel("打开工具箱时默认展示的分组:"))
        self.combo_default_group = QComboBox()
        self.combo_default_group.setMinimumHeight(28)
        row_sg.addWidget(self.combo_default_group, 1)
        sg_layout.addLayout(row_sg)

        sg_hint = QLabel("选择每次打开工具箱时默认选中的功能分组（支持全部、最近使用、默认类别或自定义分组）。")
        sg_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        sg_hint.setWordWrap(True)
        sg_layout.addWidget(sg_hint)

        layout.addWidget(startup_group_box)
        layout.addStretch()

        return widget

    def _build_visual_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        # 1. 窗口与组件双层透明度调节
        opacity_group = QGroupBox("UI 窗口与组件透明度调节 (双层独立调节)")
        op_layout = QVBoxLayout(opacity_group)
        op_layout.setSpacing(10)

        # 1.1 背景透光度
        row_bg = QHBoxLayout()
        lbl_bg_title = QLabel("窗口背景透光度:")
        lbl_bg_title.setFixedWidth(120)
        row_bg.addWidget(lbl_bg_title)

        self.slider_bg_opacity = QSlider(Qt.Horizontal)
        self.slider_bg_opacity.setRange(30, 100)
        self.slider_bg_opacity.setValue(100)
        self.slider_bg_opacity.valueChanged.connect(self._on_bg_opacity_slider_changed)
        row_bg.addWidget(self.slider_bg_opacity, 1)

        self.lbl_bg_opacity_val = QLabel("100%")
        self.lbl_bg_opacity_val.setFixedWidth(50)
        self.lbl_bg_opacity_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_bg.addWidget(self.lbl_bg_opacity_val)
        op_layout.addLayout(row_bg)

        bg_hint = QLabel("调节窗口整体底板的透光度（30% - 100%）。调低后可使桌面壁纸或亚克力磨砂质感穿透底板。")
        bg_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        op_layout.addWidget(bg_hint)

        # 1.2 组件透明度
        row_comp = QHBoxLayout()
        lbl_comp_title = QLabel("交互组件透明度:")
        lbl_comp_title.setFixedWidth(120)
        row_comp.addWidget(lbl_comp_title)

        self.slider_comp_opacity = QSlider(Qt.Horizontal)
        self.slider_comp_opacity.setRange(40, 100)
        self.slider_comp_opacity.setValue(100)
        self.slider_comp_opacity.valueChanged.connect(self._on_comp_opacity_slider_changed)
        row_comp.addWidget(self.slider_comp_opacity, 1)

        self.lbl_comp_opacity_val = QLabel("100%")
        self.lbl_comp_opacity_val.setFixedWidth(50)
        self.lbl_comp_opacity_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_comp.addWidget(self.lbl_comp_opacity_val)
        op_layout.addLayout(row_comp)

        comp_hint = QLabel("调节前景卡片、输入框、文字与按钮的透明度（40% - 100%），保持文字与组件清晰可读。")
        comp_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        op_layout.addWidget(comp_hint)

        layout.addWidget(opacity_group)

        # 2. 毛玻璃特效
        blur_group = QGroupBox("Windows 亚克力与毛玻璃特效 (Acrylic Blur)")
        blur_layout = QVBoxLayout(blur_group)
        blur_layout.setSpacing(8)

        self.cb_acrylic = QCheckBox("启用 Windows 亚克力 / 毛玻璃背景特效")
        self.cb_acrylic.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.cb_acrylic.toggled.connect(self._on_acrylic_toggled)
        blur_layout.addWidget(self.cb_acrylic)

        row_blur = QHBoxLayout()
        row_blur.addWidget(QLabel("毛玻璃强度级别:"))
        self.slider_blur = QSlider(Qt.Horizontal)
        self.slider_blur.setRange(0, 100)
        self.slider_blur.setValue(50)
        self.slider_blur.valueChanged.connect(self._on_blur_slider_changed)
        row_blur.addWidget(self.slider_blur, 1)

        self.lbl_blur_val = QLabel("50")
        self.lbl_blur_val.setFixedWidth(45)
        self.lbl_blur_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_blur.addWidget(self.lbl_blur_val)
        blur_layout.addLayout(row_blur)

        blur_hint = QLabel("在 Windows 10/11 系统下呈现现代玻璃磨砂质感。若系统环境或显卡驱动不支持则安全降级。")
        blur_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        blur_layout.addWidget(blur_hint)
        layout.addWidget(blur_group)

        # 3. 插件卡片尺寸与排版间距
        card_group = QGroupBox("首页插件卡片尺寸与排版间距调节")
        card_layout = QVBoxLayout(card_group)
        card_layout.setSpacing(10)

        # 卡片宽度
        row_cw = QHBoxLayout()
        lbl_cw = QLabel("卡片宽度:")
        lbl_cw.setFixedWidth(80)
        row_cw.addWidget(lbl_cw)
        self.slider_card_w = QSlider(Qt.Horizontal)
        self.slider_card_w.setRange(220, 420)
        self.slider_card_w.setValue(280)
        self.slider_card_w.valueChanged.connect(self._on_card_w_changed)
        row_cw.addWidget(self.slider_card_w, 1)
        self.lbl_card_w_val = QLabel("280 px")
        self.lbl_card_w_val.setFixedWidth(60)
        self.lbl_card_w_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_cw.addWidget(self.lbl_card_w_val)
        card_layout.addLayout(row_cw)

        # 卡片高度
        row_ch = QHBoxLayout()
        lbl_ch = QLabel("卡片高度:")
        lbl_ch.setFixedWidth(80)
        row_ch.addWidget(lbl_ch)
        self.slider_card_h = QSlider(Qt.Horizontal)
        self.slider_card_h.setRange(130, 240)
        self.slider_card_h.setValue(165)
        self.slider_card_h.valueChanged.connect(self._on_card_h_changed)
        row_ch.addWidget(self.slider_card_h, 1)
        self.lbl_card_h_val = QLabel("165 px")
        self.lbl_card_h_val.setFixedWidth(60)
        self.lbl_card_h_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_ch.addWidget(self.lbl_card_h_val)
        card_layout.addLayout(row_ch)

        # 网格间距
        row_cs = QHBoxLayout()
        lbl_cs = QLabel("网格间距:")
        lbl_cs.setFixedWidth(80)
        row_cs.addWidget(lbl_cs)
        self.slider_card_spacing = QSlider(Qt.Horizontal)
        self.slider_card_spacing.setRange(8, 40)
        self.slider_card_spacing.setValue(18)
        self.slider_card_spacing.valueChanged.connect(self._on_card_spacing_changed)
        row_cs.addWidget(self.slider_card_spacing, 1)
        self.lbl_card_spacing_val = QLabel("18 px")
        self.lbl_card_spacing_val.setFixedWidth(60)
        self.lbl_card_spacing_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_cs.addWidget(self.lbl_card_spacing_val)
        card_layout.addLayout(row_cs)

        btn_reset_card = QPushButton("恢复默认尺寸与间距 (280x165, 间距18)")
        btn_reset_card.setFixedWidth(260)
        btn_reset_card.clicked.connect(self._reset_card_dimensions)
        card_layout.addWidget(btn_reset_card)

        card_hint = QLabel("滑动时即时生效预览。窗口较大时卡片将自适应排布更多列，填满界面留白。")
        card_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        card_layout.addWidget(card_hint)

        layout.addWidget(card_group)

        # 4. 系统健康检查与诊断
        health_group = QGroupBox("本地环境引擎诊断")
        h_layout = QVBoxLayout(health_group)
        self.lbl_health_info = QLabel("正在检测系统环境...")
        self.lbl_health_info.setStyleSheet("font-size: 12px; color: #64748b;")
        h_layout.addWidget(self.lbl_health_info)
        layout.addWidget(health_group)

        layout.addStretch()
        scroll.setWidget(widget)
        return scroll

    def _build_export_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        desc_lbl = QLabel(
            "您可以将工具箱中的任意功能模块导出为独立的 Windows 应用程序或 Setup 安装包。\n"
            "独立导出的插件具备独立的设置面板（支持开机自启、独立托盘快捷栏及双层UI透明度调节），完全脱离工具箱主程序独立运行。"
        )
        desc_lbl.setStyleSheet("color: #64748b; font-size: 12px;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # 插件选择
        plugin_grp = QGroupBox("选择要导出的插件")
        p_layout = QVBoxLayout(plugin_grp)
        p_layout.setSpacing(8)

        self.export_combo_plugin = QComboBox()
        self.export_combo_plugin.setMinimumHeight(32)
        plugins = self.plugin_manager.get_all_plugins()
        for p in plugins:
            self.export_combo_plugin.addItem(p.get_icon(size=16), f"{p.name} ({p.category})", p.id)
        p_layout.addWidget(self.export_combo_plugin)
        layout.addWidget(plugin_grp)

        # 导出参数选项
        opt_grp = QGroupBox("安装包与打包参数")
        opt_layout = QVBoxLayout(opt_grp)
        opt_layout.setSpacing(8)

        self.export_cb_setup = QCheckBox("生成独立 Setup 一键安装程序 (含安装向导、桌面快捷方式与卸载脚本)")
        self.export_cb_setup.setChecked(True)
        self.export_cb_setup.setStyleSheet("font-weight: 600;")
        opt_layout.addWidget(self.export_cb_setup)

        self.export_cb_desktop = QCheckBox("默认生成桌面与开始菜单快捷方式")
        self.export_cb_desktop.setChecked(True)
        opt_layout.addWidget(self.export_cb_desktop)

        self.export_cb_autostart = QCheckBox("默认配置开机自动启动")
        self.export_cb_autostart.setChecked(False)
        opt_layout.addWidget(self.export_cb_autostart)

        self.export_cb_zip = QCheckBox("同时打包为 ZIP 自动化压缩包")
        self.export_cb_zip.setChecked(True)
        opt_layout.addWidget(self.export_cb_zip)

        self.export_cb_spec = QCheckBox("生成 PyInstaller 单文件编译规范 (.spec & .bat)")
        self.export_cb_spec.setChecked(True)
        opt_layout.addWidget(self.export_cb_spec)

        layout.addWidget(opt_grp)

        # 导出目录
        dir_grp = QGroupBox("导出保存路径")
        d_layout = QHBoxLayout(dir_grp)
        d_layout.setSpacing(8)

        from toolbox.core.paths import get_app_root
        default_dir = os.path.join(get_app_root(), "dist", "standalone_plugins")
        self.export_le_dir = QLineEdit(default_dir)
        self.export_le_dir.setMinimumHeight(28)
        d_layout.addWidget(self.export_le_dir, 1)

        btn_browse = QPushButton("浏览...")
        btn_browse.setIcon(get_icon("folder", size=14))
        btn_browse.clicked.connect(self._browse_export_dir)
        d_layout.addWidget(btn_browse)
        layout.addWidget(dir_grp)

        # 导出动作栏
        action_layout = QHBoxLayout()
        self.lbl_export_status = QLabel("就绪 · 可随时开始导出")
        self.lbl_export_status.setStyleSheet("color: #64748b; font-size: 12px;")
        action_layout.addWidget(self.lbl_export_status, 1)

        self.btn_export_open_folder = QPushButton("打开导出目录")
        self.btn_export_open_folder.setIcon(get_icon("folder", size=14))
        self.btn_export_open_folder.setVisible(False)
        self.btn_export_open_folder.clicked.connect(self._open_export_dir)
        action_layout.addWidget(self.btn_export_open_folder)

        self.btn_do_export = QPushButton("立即导出独立安装包")
        self.btn_do_export.setObjectName("primaryBtn")
        self.btn_do_export.setIcon(get_icon("package", color="#ffffff", size=14))
        self.btn_do_export.setFixedHeight(34)
        self.btn_do_export.clicked.connect(self._do_tab_export)
        action_layout.addWidget(self.btn_do_export)

        layout.addLayout(action_layout)
        layout.addStretch()

        return widget

    def _browse_export_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择导出保存目录", self.export_le_dir.text())
        if d:
            self.export_le_dir.setText(d)

    def _open_export_dir(self):
        target = getattr(self, "_last_exported_dir", self.export_le_dir.text())
        if os.path.exists(target):
            os.startfile(target)

    def _do_tab_export(self):
        pid = self.export_combo_plugin.currentData()
        out_dir = self.export_le_dir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "提示", "请选择有效的导出保存目录。")
            return

        self.btn_do_export.setEnabled(False)
        self.lbl_export_status.setText("正在打包独立应用与 Setup 安装程序...")

        res = PluginExporter.export_plugin(
            plugin_id=pid,
            output_dir=out_dir,
            package_type="setup" if self.export_cb_setup.isChecked() else "portable",
            create_shortcuts=self.export_cb_desktop.isChecked(),
            autostart_default=self.export_cb_autostart.isChecked(),
            create_archive=self.export_cb_zip.isChecked(),
            generate_pyinstaller_spec=self.export_cb_spec.isChecked(),
        )

        self.btn_do_export.setEnabled(True)
        if res.get("success"):
            target_p = res.get("output_dir")
            archive_p = res.get("archive_path")
            self._last_exported_dir = target_p
            msg = f"插件「{res.get('plugin_name')}」已成功导出！\n\n应用目录: {target_p}"
            if archive_p:
                msg += f"\n压缩安装包: {archive_p}"
            self.lbl_export_status.setText("导出成功！您可以点击左侧按钮打开目录查看。")
            self.lbl_export_status.setStyleSheet("color: #10b981; font-weight: bold; font-size: 12px;")
            self.btn_export_open_folder.setVisible(True)
            QMessageBox.information(self, "导出成功", msg)
        else:
            err = res.get("error", "未知错误")
            self.lbl_export_status.setText(f"导出失败: {err}")
            self.lbl_export_status.setStyleSheet("color: #ef4444; font-size: 12px;")
            QMessageBox.critical(self, "导出失败", f"导出过程发生异常:\n{err}")


    def load_settings(self):
        """载入当前配置并绑定控件状态"""
        # 1. 载入插件列表与托盘常驻管理列表
        all_plugins = self.plugin_manager.get_all_plugins()
        disabled_plugins = set(self.config_manager.get_disabled_plugins())
        tray_plugins = set(self.config_manager.get_tray_plugins())

        # 清空已有插件项
        for cb in self._plugin_checkboxes.values():
            parent_frame = cb.parentWidget()
            if parent_frame:
                parent_frame.hide()
                parent_frame.setParent(None)
                parent_frame.deleteLater()
            else:
                cb.hide()
                cb.setParent(None)
                cb.deleteLater()
        self._plugin_checkboxes.clear()
        self._plugin_tray_checkboxes.clear()

        # 清空托盘管理列表项
        for cb in self._tray_checkboxes.values():
            parent_frame = cb.parentWidget()
            if parent_frame:
                parent_frame.hide()
                parent_frame.setParent(None)
                parent_frame.deleteLater()
            else:
                cb.hide()
                cb.setParent(None)
                cb.deleteLater()
        self._tray_checkboxes.clear()
        self._tray_status_labels.clear()

        for cb in self._autostart_checkboxes.values():
            cb.hide()
            cb.setParent(None)
            cb.deleteLater()
        self._autostart_checkboxes.clear()

        # 获取开机自启配置
        autostart_cfg = self.config_manager.get_autostart_config()
        autostart_enabled = autostart_cfg.get("enabled", False) or is_autostart_enabled()
        autostart_plugins = set(autostart_cfg.get("plugins", []))

        for p in all_plugins:
            is_enabled = p.id not in disabled_plugins

            # 1.1 插件启用开关项 (集成显示在系统托盘勾选项)
            item_frame = QFrame(self.plugin_list_container)
            item_frame.setObjectName("pluginRow")
            row_layout = QHBoxLayout(item_frame)
            row_layout.setContentsMargins(4, 2, 4, 2)
            row_layout.setSpacing(10)

            icon_lbl = QLabel(item_frame)
            icon_lbl.setPixmap(get_plugin_badge_pixmap(p.id, size=20))
            row_layout.addWidget(icon_lbl)

            cb = QCheckBox(f"{p.name} [{p.category}]", item_frame)
            cb.setChecked(is_enabled)
            cb.setToolTip(p.description)
            cb.toggled.connect(lambda checked, pid=p.id: self._on_plugin_enabled_toggled(pid, checked))
            row_layout.addWidget(cb, 1)

            cb_tray_fast = QCheckBox("显示在系统托盘", item_frame)
            cb_tray_fast.setChecked(is_enabled and (p.id in tray_plugins))
            cb_tray_fast.setEnabled(is_enabled)
            cb_tray_fast.setToolTip("显示在系统托盘" if is_enabled else "需先启用此插件才能常驻系统托盘")
            cb_tray_fast.setStyleSheet("font-size: 11px; color: #38bdf8;")
            cb_tray_fast.toggled.connect(lambda checked, pid=p.id: self._on_tray_plugin_toggled(pid, checked))
            row_layout.addWidget(cb_tray_fast)
            self._plugin_tray_checkboxes[p.id] = cb_tray_fast

            lbl_desc = QLabel(p.description, item_frame)
            lbl_desc.setStyleSheet("color: #64748b; font-size: 11px;")
            lbl_desc.setMaximumWidth(260)
            row_layout.addWidget(lbl_desc)

            self.plugin_list_layout.addWidget(item_frame)
            self._plugin_checkboxes[p.id] = cb

            # 1.2 独立系统托盘常驻管理行
            t_frame = QFrame(self.tray_list_container)
            t_frame.setObjectName("trayRow")
            t_layout = QHBoxLayout(t_frame)
            t_layout.setContentsMargins(6, 4, 6, 4)
            t_layout.setSpacing(10)

            t_icon_lbl = QLabel(t_frame)
            t_icon_lbl.setPixmap(get_plugin_badge_pixmap(p.id, size=22))
            t_layout.addWidget(t_icon_lbl)

            t_cb = QCheckBox(f"{p.name} [{p.category}]", t_frame)
            t_cb.setStyleSheet("font-weight: 600;")
            t_cb.setChecked(is_enabled and (p.id in tray_plugins))
            t_cb.setEnabled(is_enabled)
            t_cb.setToolTip("勾选后独立显示在系统托盘通知区" if is_enabled else "需先在「功能模块管理」中启用此插件才能常驻系统托盘")
            t_cb.toggled.connect(lambda checked, pid=p.id: self._on_tray_plugin_toggled(pid, checked))
            t_layout.addWidget(t_cb, 1)

            t_desc = QLabel(p.description, t_frame)
            t_desc.setStyleSheet("color: #64748b; font-size: 11px;")
            t_desc.setMaximumWidth(280)
            t_layout.addWidget(t_desc)

            in_tray_active = is_enabled and (p.id in tray_plugins)
            t_status = QLabel("常驻中" if in_tray_active else "未常驻", t_frame)
            if in_tray_active:
                t_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: bold; background: #064e3b; padding: 2px 6px; border-radius: 4px;")
            else:
                t_status.setStyleSheet("color: #64748b; font-size: 11px; background: #1e293b; padding: 2px 6px; border-radius: 4px;")
            t_layout.addWidget(t_status)

            self.tray_list_layout.addWidget(t_frame)
            self._tray_checkboxes[p.id] = t_cb
            self._tray_status_labels[p.id] = t_status

            # 1.3 自启动多选功能项
            as_cb = QCheckBox(f"{p.name} ({p.id})", self.autostart_container)
            as_cb.setChecked(p.id in autostart_plugins)
            self.autostart_layout.addWidget(as_cb)
            self._autostart_checkboxes[p.id] = as_cb

        self.plugin_list_layout.addStretch()
        self.tray_list_layout.addStretch()
        self.autostart_layout.addStretch()

        # 2. 开机自启
        self.cb_autostart_enabled.setChecked(autostart_enabled)
        self.autostart_scroll.setEnabled(autostart_enabled)

        # 3. 多开功能与默认启动分组
        self.cb_multi_window.setChecked(self.config_manager.get_multi_window_mode())

        self.combo_default_group.clear()
        default_groups = ["全部", "最近使用"]
        built_in_cats = sorted(list({p.category for p in all_plugins if p.category}))
        custom_groups = self.config_manager.get_custom_groups()
        all_group_options = default_groups + [c for c in built_in_cats if c not in default_groups]
        for cg in custom_groups:
            if cg not in all_group_options:
                all_group_options.append(cg)
        self.combo_default_group.addItems(all_group_options)

        cur_def = self.config_manager.get_default_startup_group()
        cur_idx = self.combo_default_group.findText(cur_def)
        if cur_idx >= 0:
            self.combo_default_group.setCurrentIndex(cur_idx)
        else:
            self.combo_default_group.setCurrentIndex(0)

        # 4. 双层透明度
        bg_op = self.config_manager.get_bg_opacity()
        comp_op = self.config_manager.get_component_opacity()
        bg_val = int(round(bg_op * 100))
        comp_val = int(round(comp_op * 100))
        self.slider_bg_opacity.setValue(bg_val)
        self.lbl_bg_opacity_val.setText(f"{bg_val}%")
        self.slider_comp_opacity.setValue(comp_val)
        self.lbl_comp_opacity_val.setText(f"{comp_val}%")

        # 5. 毛玻璃
        acrylic = self.config_manager.get_acrylic_enabled()
        self.cb_acrylic.setChecked(acrylic)
        blur_lvl = self.config_manager.get_blur_level()
        self.slider_blur.setValue(blur_lvl)
        self.lbl_blur_val.setText(str(blur_lvl))
        self.slider_blur.setEnabled(acrylic)

        # 6. 卡片尺寸与排版间距
        cw = self.config_manager.get_card_width()
        ch = self.config_manager.get_card_height()
        cs = self.config_manager.get_card_spacing()
        self.slider_card_w.setValue(cw)
        self.lbl_card_w_val.setText(f"{cw} px")
        self.slider_card_h.setValue(ch)
        self.lbl_card_h_val.setText(f"{ch} px")
        self.slider_card_spacing.setValue(cs)
        self.lbl_card_spacing_val.setText(f"{cs} px")

        # 7. 环境诊断
        from toolbox.plugins.archive_manager.engine import find_7z_executable
        p7z = find_7z_executable()
        diag = run_system_health_check()
        self.lbl_health_info.setText(
            f"Python: {diag.get('python_version', '未知')} | "
            f"FFmpeg: {diag.get('ffmpeg_status', '未知')} | "
            f"7-Zip: {'已就绪' if p7z else '未检测到'} | "
            f"已载入插件: {len(all_plugins)} 个"
        )

    def _filter_plugins_list(self, text: str):
        kw = text.strip().lower()
        for p in self.plugin_manager.get_all_plugins():
            cb = self._plugin_checkboxes.get(p.id)
            if not cb:
                continue
            parent_frame = cb.parentWidget()
            if not parent_frame:
                continue
            visible = (not kw) or (kw in p.name.lower()) or (kw in p.description.lower()) or (kw in p.category.lower()) or (kw in p.id.lower())
            parent_frame.setVisible(visible)

    def _set_all_plugins(self, enable: bool):
        for cb in self._plugin_checkboxes.values():
            cb.setChecked(enable)

    def _on_autostart_toggled(self, checked: bool):
        self.autostart_scroll.setEnabled(checked)

    def _on_bg_opacity_slider_changed(self, value: int):
        self.lbl_bg_opacity_val.setText(f"{value}%")
        self._opacity_preview_timer.start()

    def _on_comp_opacity_slider_changed(self, value: int):
        self.lbl_comp_opacity_val.setText(f"{value}%")
        self._opacity_preview_timer.start()

    def _do_preview_opacity(self):
        bg_op = self.slider_bg_opacity.value() / 100.0
        comp_op = self.slider_comp_opacity.value() / 100.0
        parent = self.parentWidget()
        if parent:
            apply_dual_opacity(parent, bg_opacity=bg_op, component_opacity=comp_op)

    def _on_card_w_changed(self, value: int):
        self.lbl_card_w_val.setText(f"{value} px")
        self._preview_card_layout()

    def _on_card_h_changed(self, value: int):
        self.lbl_card_h_val.setText(f"{value} px")
        self._preview_card_layout()

    def _on_card_spacing_changed(self, value: int):
        self.lbl_card_spacing_val.setText(f"{value} px")
        self._preview_card_layout()

    def _preview_card_layout(self):
        self._card_preview_timer.start()

    def _do_preview_card_layout(self):
        self.config_manager.set_card_width(self.slider_card_w.value(), auto_save=False)
        self.config_manager.set_card_height(self.slider_card_h.value(), auto_save=False)
        self.config_manager.set_card_spacing(self.slider_card_spacing.value(), auto_save=False)
        self.event_bus.settings_changed.emit()

    def _reset_card_dimensions(self):
        self.slider_card_w.setValue(280)
        self.slider_card_h.setValue(165)
        self.slider_card_spacing.setValue(18)
        self.lbl_card_w_val.setText("280 px")
        self.lbl_card_h_val.setText("165 px")
        self.lbl_card_spacing_val.setText("18 px")
        self._do_preview_card_layout()

    def _on_acrylic_toggled(self, checked: bool):
        self.slider_blur.setEnabled(checked)
        parent = self.parentWidget()
        if parent:
            apply_acrylic_effect(parent, enabled=checked, blur_level=self.slider_blur.value(), is_dark=self.theme_manager.is_dark())

    def _on_blur_slider_changed(self, value: int):
        self.lbl_blur_val.setText(str(value))
        if self.cb_acrylic.isChecked():
            self._blur_preview_timer.start()

    def _do_preview_blur(self):
        if self.cb_acrylic.isChecked():
            parent = self.parentWidget()
            if parent:
                apply_acrylic_effect(parent, enabled=True, blur_level=self.slider_blur.value(), is_dark=self.theme_manager.is_dark())

    def _apply_settings_action(self):
        """执行保存并应用"""
        # 1. 保存插件启用/禁用状态
        disabled = []
        for p_id, cb in self._plugin_checkboxes.items():
            if not cb.isChecked():
                disabled.append(p_id)
        self.config_manager.set("disabled_plugins", disabled, auto_save=False)

        # 1.1 保存独立系统托盘常驻配置
        for p_id, cb in self._tray_checkboxes.items():
            self.config_manager.set_tray_plugin(p_id, cb.isChecked(), auto_save=False)

        # 2. 保存开机自启动配置
        autostart_enabled = self.cb_autostart_enabled.isChecked()
        autostart_plugins = [p_id for p_id, cb in self._autostart_checkboxes.items() if cb.isChecked()]
        self.config_manager.set_autostart_config(autostart_enabled, autostart_plugins, auto_save=False)

        # 写入注册表自启动
        try:
            if autostart_enabled:
                run_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key_path, 0, winreg.KEY_ALL_ACCESS)
                cmd = f"{get_toolbox_main_command()} --autostart"
                winreg.SetValueEx(key, "ChieriToolbox", 0, winreg.REG_SZ, cmd)
                winreg.CloseKey(key)
            else:
                set_autostart(False)
        except Exception as e:
            print(f"[SettingsDialog] 注册表自启操作提示: {e}")

        # 3. 多开模式与默认启动分组
        self.config_manager.set_multi_window_mode(self.cb_multi_window.isChecked(), auto_save=False)
        self.config_manager.set_default_startup_group(self.combo_default_group.currentText(), auto_save=False)

        # 4. 双层透明度与毛玻璃
        bg_op = self.slider_bg_opacity.value() / 100.0
        comp_op = self.slider_comp_opacity.value() / 100.0
        self.config_manager.set_bg_opacity(bg_op, auto_save=False)
        self.config_manager.set_component_opacity(comp_op, auto_save=False)
        self.config_manager.set_window_opacity(bg_op, auto_save=False)
        self.config_manager.set_acrylic_enabled(self.cb_acrylic.isChecked(), auto_save=False)
        self.config_manager.set_blur_level(self.slider_blur.value(), auto_save=False)

        # 5. 卡片尺寸与排版间距
        self.config_manager.set_card_width(self.slider_card_w.value(), auto_save=False)
        self.config_manager.set_card_height(self.slider_card_h.value(), auto_save=False)
        self.config_manager.set_card_spacing(self.slider_card_spacing.value(), auto_save=False)

        # 统一写入磁盘
        self.config_manager.save()

        # 广播通知
        self.event_bus.settings_changed.emit()
        self.settings_saved.emit()

    def _save_and_close_action(self):
        self._apply_settings_action()
        self.accept()

    def reject(self):
        """取消时重新从磁盘加载配置，还原所有预览改动"""
        self.config_manager.reload()
        parent = self.parentWidget()
        if parent and hasattr(parent, "apply_visual_settings"):
            parent.apply_visual_settings()
        self.event_bus.settings_changed.emit()
        super().reject()
