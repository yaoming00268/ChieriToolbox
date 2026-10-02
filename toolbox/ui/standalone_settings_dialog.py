"""
工具箱 (Toolbox) - 独立插件专属设置对话框 (StandalonePluginSettingsDialog)
提供独立插件运行模式下的开机自启切换、系统托盘管理、窗口透明度与毛玻璃UI参数微调。
严格遵守无 Emoji 规范，使用矢量图标与响应式排版。
"""

import os
import sys
import winreg
from typing import Optional, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QSlider, QGroupBox, QComboBox,
    QMessageBox
)

from toolbox.core.plugin_base import PluginBase
from toolbox.core.config_manager import ConfigManager
from toolbox.core.theme import ThemeManager, THEME_LIGHT, THEME_DARK, THEME_SYSTEM
from toolbox.ui.icons import get_icon, get_pixmap, get_plugin_badge_pixmap


def get_plugin_autostart_cmd(plugin_id: str) -> str:
    """获取独立插件的开机自启动命令行"""
    from toolbox.core.paths import is_frozen, get_app_root
    if is_frozen():
        exe_path = os.path.normpath(sys.executable)
        return f'"{exe_path}" --plugin {plugin_id} --autostart'

    base_dir = get_app_root()
    # 若作为独立导出的安装包运行，优先使用自身的 launch.bat
    launch_bat = os.path.join(base_dir, "launch.bat")
    if os.path.isfile(launch_bat):
        return f'"{launch_bat}" --autostart'

    venv_pythonw = os.path.join(base_dir, ".venv", "Scripts", "pythonw.exe")
    venv_python = os.path.join(base_dir, ".venv", "Scripts", "python.exe")
    if os.path.isfile(venv_pythonw):
        py_exe = venv_pythonw
    elif os.path.isfile(venv_python):
        py_exe = venv_python
    else:
        py_exe = sys.executable

    runner = os.path.join(base_dir, "toolbox", "standalone_runner.py")
    if not os.path.isfile(runner):
        runner = os.path.join(base_dir, "main.py")
    return f'"{py_exe}" "{runner}" --plugin {plugin_id} --autostart'


def is_plugin_autostart_registered(plugin_id: str) -> bool:
    """检查独立插件是否已加入注册表开机自启"""
    reg_key = f"ChieriPlugin_{plugin_id}"
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ
        )
        val, _ = winreg.QueryValueEx(key, reg_key)
        winreg.CloseKey(key)
        return bool(val)
    except Exception:
        return False


def set_plugin_autostart_registry(plugin_id: str, enable: bool, custom_cmd: Optional[str] = None) -> Tuple[bool, str]:
    """向当前用户注册表写入或注销独立插件的开机自启项"""
    reg_key = f"ChieriPlugin_{plugin_id}"
    run_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_path, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            cmd = custom_cmd or get_plugin_autostart_cmd(plugin_id)
            winreg.SetValueEx(key, reg_key, 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(key)
            return True, "已成功开启开机自启！"
        else:
            try:
                winreg.DeleteValue(key, reg_key)
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
            return True, "已取消开机自启动。"
    except Exception as e:
        return False, f"修改开机自启失败: {e}"


class StandalonePluginSettingsDialog(QDialog):
    settings_applied = Signal()

    def __init__(self, plugin: PluginBase, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.plugin = plugin
        self.config_manager = ConfigManager()
        self.theme_manager = ThemeManager()

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        self.setWindowTitle(f"{self.plugin.name} - 独立应用设置")
        self.setWindowIcon(self.plugin.get_icon(size=24))
        self.resize(520, 500)
        self.setMinimumSize(460, 420)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 18, 20, 18)
        main_layout.setSpacing(14)

        # 顶部标题栏
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_plugin_badge_pixmap(self.plugin.id, size=24))
        top_bar.addWidget(icon_lbl)

        title_lbl = QLabel(f"「{self.plugin.name}」独立设置")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        top_bar.addWidget(title_lbl)
        top_bar.addStretch()
        main_layout.addLayout(top_bar)

        # 1. 开机自启组
        as_group = QGroupBox("系统开机自启选项")
        as_layout = QVBoxLayout(as_group)
        as_layout.setSpacing(8)

        self.cb_autostart = QCheckBox("跟随 Windows 系统开机自动启动")
        self.cb_autostart.setStyleSheet("font-weight: 600; font-size: 13px;")
        as_layout.addWidget(self.cb_autostart)

        as_hint = QLabel("启用后，计算机开机时将独立启动该插件应用，无需手动打开工具箱。")
        as_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        as_hint.setWordWrap(True)
        as_layout.addWidget(as_hint)

        self.cb_start_minimized = QCheckBox("开机自启时静默最小化到系统托盘")
        as_layout.addWidget(self.cb_start_minimized)

        main_layout.addWidget(as_group)

        # 2. 系统托盘行为
        tray_group = QGroupBox("系统托盘与窗口关闭行为")
        tray_layout = QVBoxLayout(tray_group)
        tray_layout.setSpacing(8)

        self.cb_enable_tray = QCheckBox("在 Windows 系统托盘常驻显示图标")
        self.cb_enable_tray.setChecked(True)
        tray_layout.addWidget(self.cb_enable_tray)

        self.cb_close_to_tray = QCheckBox("点击窗口关闭按钮时最小化到系统托盘 (而不是直接退出)")
        tray_layout.addWidget(self.cb_close_to_tray)

        main_layout.addWidget(tray_group)

        # 3. 界面视觉与UI参数微调
        ui_group = QGroupBox("界面视觉与 UI 参数调节")
        ui_layout = QVBoxLayout(ui_group)
        ui_layout.setSpacing(10)

        # 主题选择
        row_theme = QHBoxLayout()
        row_theme.addWidget(QLabel("外观主题模式:"))
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["跟随系统 (System)", "浅色模式 (Light)", "深色模式 (Dark)"])
        row_theme.addWidget(self.combo_theme, 1)
        ui_layout.addLayout(row_theme)

        # 背景透明度
        row_bg = QHBoxLayout()
        lbl_bg = QLabel("窗口背景透光度:")
        lbl_bg.setFixedWidth(110)
        row_bg.addWidget(lbl_bg)
        self.slider_bg = QSlider(Qt.Horizontal)
        self.slider_bg.setRange(30, 100)
        self.slider_bg.setValue(100)
        self.slider_bg.valueChanged.connect(lambda v: self.lbl_bg_val.setText(f"{v}%"))
        row_bg.addWidget(self.slider_bg, 1)
        self.lbl_bg_val = QLabel("100%")
        self.lbl_bg_val.setFixedWidth(45)
        self.lbl_bg_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_bg.addWidget(self.lbl_bg_val)
        ui_layout.addLayout(row_bg)

        # 组件透明度
        row_comp = QHBoxLayout()
        lbl_comp = QLabel("交互组件透明度:")
        lbl_comp.setFixedWidth(110)
        row_comp.addWidget(lbl_comp)
        self.slider_comp = QSlider(Qt.Horizontal)
        self.slider_comp.setRange(40, 100)
        self.slider_comp.setValue(100)
        self.slider_comp.valueChanged.connect(lambda v: self.lbl_comp_val.setText(f"{v}%"))
        row_comp.addWidget(self.slider_comp, 1)
        self.lbl_comp_val = QLabel("100%")
        self.lbl_comp_val.setFixedWidth(45)
        self.lbl_comp_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_comp.addWidget(self.lbl_comp_val)
        ui_layout.addLayout(row_comp)

        # 亚克力毛玻璃
        self.cb_acrylic = QCheckBox("启用 Windows 亚克力 / 毛玻璃质感特效")
        ui_layout.addWidget(self.cb_acrylic)

        row_blur = QHBoxLayout()
        row_blur.addWidget(QLabel("毛玻璃强度级别:"))
        self.slider_blur = QSlider(Qt.Horizontal)
        self.slider_blur.setRange(0, 100)
        self.slider_blur.setValue(50)
        self.slider_blur.valueChanged.connect(lambda v: self.lbl_blur_val.setText(f"{v}"))
        row_blur.addWidget(self.slider_blur, 1)
        self.lbl_blur_val = QLabel("50")
        self.lbl_blur_val.setFixedWidth(45)
        self.lbl_blur_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_blur.addWidget(self.lbl_blur_val)
        ui_layout.addLayout(row_blur)

        main_layout.addWidget(ui_group)
        main_layout.addStretch()

        # 底部操作按钮
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("确定")
        self.btn_save.setObjectName("primaryBtn")
        self.btn_save.setIcon(get_icon("check", color="#ffffff", size=14))
        self.btn_save.clicked.connect(self._save_settings)
        bottom_layout.addWidget(self.btn_save)

        main_layout.addLayout(bottom_layout)

    def load_settings(self):
        """加载该插件的专属配置与系统状态"""
        cfg_key = f"standalone_{self.plugin.id}"
        cfg = self.config_manager.get(cfg_key, {})

        # 自启动状态 (优先从注册表探测实际状态)
        reg_autostart = is_plugin_autostart_registered(self.plugin.id)
        self.cb_autostart.setChecked(reg_autostart or cfg.get("autostart", False))
        self.cb_start_minimized.setChecked(cfg.get("start_minimized", False))

        self.cb_enable_tray.setChecked(cfg.get("enable_tray", True))
        self.cb_close_to_tray.setChecked(cfg.get("close_to_tray", False))

        # 主题
        t_mode = cfg.get("theme", self.theme_manager.get_mode())
        if t_mode == THEME_LIGHT:
            self.combo_theme.setCurrentIndex(1)
        elif t_mode == THEME_DARK:
            self.combo_theme.setCurrentIndex(2)
        else:
            self.combo_theme.setCurrentIndex(0)

        # 透明度与毛玻璃
        bg_op = int(cfg.get("bg_opacity", self.config_manager.get_bg_opacity()) * 100)
        comp_op = int(cfg.get("component_opacity", self.config_manager.get_component_opacity()) * 100)
        self.slider_bg.setValue(max(30, min(100, bg_op)))
        self.slider_comp.setValue(max(40, min(100, comp_op)))
        self.lbl_bg_val.setText(f"{self.slider_bg.value()}%")
        self.lbl_comp_val.setText(f"{self.slider_comp.value()}%")

        self.cb_acrylic.setChecked(cfg.get("acrylic_enabled", self.config_manager.get_acrylic_enabled()))
        blur = int(cfg.get("blur_level", self.config_manager.get_blur_level()))
        self.slider_blur.setValue(max(0, min(100, blur)))
        self.lbl_blur_val.setText(f"{self.slider_blur.value()}")

    def _save_settings(self):
        """保存配置并应用开机自启与UI参数"""
        cfg_key = f"standalone_{self.plugin.id}"
        cfg = self.config_manager.get(cfg_key, {})

        autostart_val = self.cb_autostart.isChecked()
        start_minimized = self.cb_start_minimized.isChecked()
        enable_tray = self.cb_enable_tray.isChecked()
        close_to_tray = self.cb_close_to_tray.isChecked()

        t_idx = self.combo_theme.currentIndex()
        theme_val = THEME_LIGHT if t_idx == 1 else (THEME_DARK if t_idx == 2 else THEME_SYSTEM)

        bg_op = self.slider_bg.value() / 100.0
        comp_op = self.slider_comp.value() / 100.0
        acrylic = self.cb_acrylic.isChecked()
        blur = self.slider_blur.value()

        cfg.update({
            "autostart": autostart_val,
            "start_minimized": start_minimized,
            "enable_tray": enable_tray,
            "close_to_tray": close_to_tray,
            "theme": theme_val,
            "bg_opacity": bg_op,
            "component_opacity": comp_op,
            "acrylic_enabled": acrylic,
            "blur_level": blur
        })
        self.config_manager.set(cfg_key, cfg)

        # 写入注册表自启动
        ok, msg = set_plugin_autostart_registry(self.plugin.id, autostart_val)
        if not ok:
            print(f"[StandaloneSettings] 设置自启动异常: {msg}")

        # 应用主题与参数 (隔离全局配置)
        self.theme_manager.set_mode(theme_val, save_config=False)
        self.settings_applied.emit()
        self.accept()
