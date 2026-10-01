"""
工具箱 (Toolbox) - 现代化窗口视觉特效与毛玻璃合成器 (Window Effects)
支持 Windows 10/11 亚克力 (Acrylic)、DWM 背景模糊 (Blur Behind) 及全局透明度无损融合。
"""

import sys
import ctypes
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

# Windows API 常量
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMSBT_AUTO = 0
DWMSBT_NONE = 1
DWMSBT_MAINWINDOW = 2       # Mica
DWMSBT_TRANSIENTWINDOW = 3  # Acrylic
DWMSBT_TABBEDWINDOW = 4     # Tabbed Mica

ACCENT_DISABLED = 0
ACCENT_ENABLE_GRADIENT = 1
ACCENT_ENABLE_TRANSPARENTGRADIENT = 2
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4


class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int)
    ]


class WINCOMPATTRDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t)
    ]


def is_windows() -> bool:
    return sys.platform == "win32"


def get_windows_build() -> int:
    if not is_windows():
        return 0
    try:
        return sys.getwindowsversion().build
    except Exception:
        return 0


def apply_window_opacity(widget: QWidget, opacity: float):
    """
    安全设置窗口透明度 (兼顾向后兼容)
    opacity: 0.2 ~ 1.0
    """
    if not widget:
        return
    try:
        val = max(0.2, min(1.0, float(opacity)))
        widget.setWindowOpacity(val)
    except Exception as e:
        print(f"[WindowEffects] 设置窗口透明度失败: {e}")


def apply_dual_opacity(widget: QWidget, bg_opacity: float = 1.0, component_opacity: float = 1.0):
    """
    独立控制窗口背景透明度与交互组件透明度：
    - bg_opacity: 控制窗口整体/背景透光度 (0.2 ~ 1.0)
    - component_opacity: 控制前景控件、卡片、输入框与文字透明度 (0.4 ~ 1.0)
    """
    if not widget:
        return
    try:
        bg_val = max(0.2, min(1.0, float(bg_opacity)))
        comp_val = max(0.4, min(1.0, float(component_opacity)))

        # 1. 顶层窗口保持 1.0 不透明度，杜绝全局 Alpha 通道压低子控件引发双重相乘发虚发暗
        widget.setWindowOpacity(1.0)
        if bg_val < 0.999:
            widget.setAttribute(Qt.WA_TranslucentBackground, True)
        else:
            widget.setAttribute(Qt.WA_TranslucentBackground, False)

        # 2. 交互组件透明度 (通过 centralWidget 上的 QGraphicsOpacityEffect 独立控制)
        central = getattr(widget, "centralWidget", None)
        target = central() if callable(central) and central() else widget

        from PySide6.QtWidgets import QGraphicsOpacityEffect
        effect = getattr(target, "_component_opacity_effect", None)
        if comp_val >= 0.999:
            if effect:
                target.setGraphicsEffect(None)
                target._component_opacity_effect = None
        else:
            if not effect:
                effect = QGraphicsOpacityEffect(target)
                target._component_opacity_effect = effect
                target.setGraphicsEffect(effect)
            effect.setOpacity(comp_val)
        widget.update()
    except Exception as e:
        print(f"[WindowEffects] 设置双层透明度失败: {e}")


def apply_acrylic_effect(widget: QWidget, enabled: bool = True, blur_level: int = 50, is_dark: bool = True):
    """
    安全启用或停用 Windows 毛玻璃 / 亚克力视觉滤镜
    支持 Windows 11 原生 Backdrop 与 Windows 10 SetWindowCompositionAttribute。
    若系统环境或硬件不支持，将安全降级，不会抛出致命异常。
    """
    if not is_windows() or not widget:
        return

    try:
        hwnd = int(widget.winId())
    except Exception:
        return

    build = get_windows_build()

    # 1. Windows 11 (Build 22000+) 原生 DwmSetWindowAttribute 系统毛玻璃
    if build >= 22000:
        try:
            dwmapi = ctypes.windll.dwmapi
            backdrop_type = ctypes.c_int(DWMSBT_TRANSIENTWINDOW if enabled else DWMSBT_NONE)
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_SYSTEMBACKDROP_TYPE,
                ctypes.byref(backdrop_type),
                ctypes.sizeof(backdrop_type)
            )
            return
        except Exception:
            pass

    # 2. Windows 10 (Build 17134+) SetWindowCompositionAttribute
    try:
        user32 = ctypes.windll.user32
        set_window_comp_attr = getattr(user32, "SetWindowCompositionAttribute", None)
        if not set_window_comp_attr:
            return

        policy = ACCENT_POLICY()
        if enabled:
            policy.AccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND
            policy.AccentFlags = 2  # 启用绘制边框与高质感模糊
            # 根据深浅主题和模糊级别合成 RGBA 蒙版 (0xAA BB GG RR)
            alpha = max(30, min(240, int(blur_level * 2.2)))
            if is_dark:
                color = (alpha << 24) | (0x1e << 16) | (0x19 << 8) | 0x14
            else:
                color = (alpha << 24) | (0xf5 << 16) | (0xf1 << 8) | 0xeb
            policy.GradientColor = color
        else:
            policy.AccentState = ACCENT_DISABLED
            policy.AccentFlags = 0
            policy.GradientColor = 0

        data = WINCOMPATTRDATA()
        data.Attribute = 19  # WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.byref(policy), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(policy)

        set_window_comp_attr(hwnd, ctypes.byref(data))
    except Exception as e:
        # 静默降级
        pass
