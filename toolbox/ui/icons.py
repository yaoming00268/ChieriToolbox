"""
工具箱 (Toolbox) - 现代矢量图标系统 (Vector Icons)
采用极简无衬线 Lucide/Feather 规范的高清矢量 SVG 渲染引擎。
拒绝丑陋 Emoji，提供原生深浅主题自适应着色与高分屏无损缩放。
"""

import io
import os
from typing import Dict, Optional, Tuple, Any, List
from PySide6.QtCore import QByteArray, Qt, QRectF, QBuffer
from PySide6.QtGui import QIcon, QPainter, QPixmap, QImage, QColor, QBrush, QPen, QLinearGradient
from PySide6.QtSvg import QSvgRenderer
from PIL import Image

# 核心矢量 SVG 路径定义库 (基于 24x24 视口)
SVG_PATHS: Dict[str, str] = {
    # 应用程序主品牌 Logo (现代几何立体工具箱)
    "app_logo": (
        '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>'
        '<polyline points="3.27 6.96 12 12.01 20.73 6.96"/>'
        '<line x1="12" y1="22.08" x2="12" y2="12"/>'
    ),
    "toolbox": (
        '<rect width="20" height="14" x="2" y="7" rx="2" ry="2"/>'
        '<path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>'
    ),
    # 插件分类与专属图标 (替换原有 Emoji)
    "folder": (
        '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 8 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>'
    ),
    "image": (
        '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>'
        '<circle cx="9" cy="9" r="2"/>'
        '<path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>'
    ),
    "keyboard": (
        '<rect width="20" height="16" x="2" y="4" rx="2"/>'
        '<path d="M6 8h.01"/>'
        '<path d="M10 8h.01"/>'
        '<path d="M14 8h.01"/>'
        '<path d="M18 8h.01"/>'
        '<path d="M6 12h.01"/>'
        '<path d="M18 12h.01"/>'
        '<path d="M10 16h4"/>'
    ),
    "video": (
        '<path d="m22 8-6 4 6 4V8Z"/>'
        '<rect width="14" height="12" x="2" y="6" rx="2" ry="2"/>'
    ),
    "music": (
        '<path d="M9 18V5l12-2v13"/>'
        '<circle cx="6" cy="18" r="3"/>'
        '<circle cx="18" cy="16" r="3"/>'
    ),
    "system": (
        '<rect width="16" height="16" x="4" y="4" rx="2"/>'
        '<rect width="6" height="6" x="9" y="9" rx="1"/>'
        '<path d="M15 2v2"/>'
        '<path d="M15 20v2"/>'
        '<path d="M2 15h2"/>'
        '<path d="M2 9h2"/>'
        '<path d="M20 15h2"/>'
        '<path d="M20 9h2"/>'
        '<path d="M9 2v2"/>'
        '<path d="M9 20v2"/>'
    ),
    "tools": (
        '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>'
    ),
    # 交互操作与导航图标
    "search": (
        '<circle cx="11" cy="11" r="8"/>'
        '<path d="m21 21-4.3-4.3"/>'
    ),
    "clear": (
        '<path d="M18 6 6 18"/>'
        '<path d="m6 6 12 12"/>'
    ),
    "arrow-left": (
        '<path d="m12 19-7-7 7-7"/>'
        '<path d="M19 12H5"/>'
    ),
    "chevron-right": (
        '<path d="m9 18 6-6-6-6"/>'
    ),
    "chevron-left": (
        '<path d="m15 18-6-6 6-6"/>'
    ),
    "home": (
        '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
        '<polyline points="9 22 9 12 15 12 15 22"/>'
    ),
    # 深浅模式与系统跟随
    "sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2"/>'
        '<path d="M12 20v2"/>'
        '<path d="m4.93 4.93 1.41 1.41"/>'
        '<path d="m17.66 17.66 1.41 1.41"/>'
        '<path d="M2 12h2"/>'
        '<path d="M20 12h2"/>'
        '<path d="m6.34 17.66-1.41 1.41"/>'
        '<path d="m19.07 4.93-1.41 1.41"/>'
    ),
    "moon": (
        '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>'
    ),
    "monitor": (
        '<rect width="20" height="14" x="2" y="3" rx="2"/>'
        '<line x1="8" x2="16" y1="21" y2="21"/>'
        '<line x1="12" x2="12" y1="17" y2="21"/>'
    ),
    # 常用功能控件按钮图标
    "file-plus": (
        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
        '<path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
        '<path d="M9 15h6"/>'
        '<path d="M12 12v6"/>'
    ),
    "folder-plus": (
        '<path d="M12 10v6"/>'
        '<path d="M9 13h6"/>'
        '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 8 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>'
    ),
    "trash": (
        '<path d="M3 6h18"/>'
        '<path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>'
        '<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>'
    ),
    "play": (
        '<polygon points="6 3 20 12 6 21 6 3"/>'
    ),
    "download": (
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="7 10 12 15 17 10"/>'
        '<line x1="12" x2="12" y1="15" y2="3"/>'
    ),
    "refresh": (
        '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>'
        '<path d="M21 3v5h-5"/>'
        '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>'
        '<path d="M8 16H3v5"/>'
    ),
    "save": (
        '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
        '<path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/>'
        '<path d="M7 3v4a1 1 0 0 0 1 1h7"/>'
    ),
    "check": (
        '<polyline points="20 6 9 17 4 12"/>'
    ),
    "settings": (
        '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    "sparkles": (
        '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>'
    ),
    "youtube": (
        '<path d="M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17"/>'
        '<polygon points="10 15 15 12 10 9 10 15"/>'
    ),
    "scissors": (
        '<circle cx="6" cy="6" r="3"/>'
        '<path d="M8.12 8.12 12 12"/>'
        '<path d="M20 4 8.12 15.88"/>'
        '<circle cx="6" cy="18" r="3"/>'
        '<path d="M14.8 14.8 20 20"/>'
    ),
    "archive": (
        '<rect width="20" height="5" x="2" y="3" rx="1"/>'
        '<path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/>'
        '<path d="M10 12h4"/>'
    ),
    "shield": (
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'
    ),
    "globe": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/>'
        '<path d="M2 12h20"/>'
    ),
    "languages": (
        '<path d="m5 8 6 6"/>'
        '<path d="m4 14 6-6 2-3"/>'
        '<path d="M2 5h12"/>'
        '<path d="M7 2h1"/>'
        '<path d="m22 22-5-10-5 10"/>'
        '<path d="M14 18h6"/>'
    ),
    "lock": (
        '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/>'
        '<path d="M7 11V7a5 5 0 0 1 10 0v4"/>'
    ),
    "unlock": (
        '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/>'
        '<path d="M7 11V7a5 5 0 0 1 9.9-1"/>'
    ),
    "network": (
        '<rect width="6" height="6" x="9" y="2" rx="1"/>'
        '<path d="M12 8v4"/>'
        '<rect width="6" height="6" x="2" y="16" rx="1"/>'
        '<rect width="6" height="6" x="16" y="16" rx="1"/>'
        '<path d="M5 16v-2a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v2"/>'
    ),
    "zap": (
        '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'
    ),
    "copy": (
        '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>'
        '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>'
    ),
    "mic": (
        '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>'
        '<path d="M19 10v2a7 7 0 0 1-14 0v-2"/>'
        '<line x1="12" x2="12" y1="19" y2="22"/>'
    ),
    "camera": (
        '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/>'
        '<circle cx="12" cy="13" r="3"/>'
    ),
    "pause": (
        '<rect x="6" y="4" width="4" height="16"/>'
        '<rect x="14" y="4" width="4" height="16"/>'
    ),
    "stop": (
        '<rect width="16" height="16" x="4" y="4" rx="2"/>'
    ),
    "pencil": (
        '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>'
    ),
    "undo": (
        '<path d="M3 7v6h6"/>'
        '<path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>'
    ),
    "redo": (
        '<path d="M21 7v6h-6"/>'
        '<path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3L21 13"/>'
    ),
    "square": (
        '<rect width="18" height="18" x="3" y="3" rx="2"/>'
    ),
    "circle": (
        '<circle cx="12" cy="12" r="10"/>'
    ),
    "type": (
        '<polyline points="4 7 4 4 20 4 20 7"/>'
        '<line x1="9" x2="15" y1="20" y2="20"/>'
        '<line x1="12" x2="12" y1="4" y2="20"/>'
    ),
    "window": (
        '<rect width="20" height="16" x="2" y="4" rx="2"/>'
        '<path d="M2 8h20"/>'
    ),
    "clock": (
        '<circle cx="12" cy="12" r="10"/>'
        '<polyline points="12 6 12 12 16 14"/>'
    ),
    "external-link": (
        '<path d="M15 3h6v6"/>'
        '<path d="M10 14 21 3"/>'
        '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
    ),
    "package": (
        '<path d="m7.5 4.27 9 5.15"/>'
        '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>'
        '<path d="m3.3 7 8.7 5 8.7-5"/>'
        '<path d="M12 22V12"/>'
    ),
    "box": (
        '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>'
        '<path d="m3.3 7 8.7 5 8.7-5"/>'
        '<path d="M12 22V12"/>'
    ),
    "layers": (
        '<polygon points="12 2 2 7 12 12 22 7 12 2"/>'
        '<polyline points="2 17 12 22 22 17"/>'
        '<polyline points="2 12 12 17 22 12"/>'
    ),
    "tag": (
        '<path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z"/>'
        '<path d="M7 7h.01"/>'
    ),
    "plus": (
        '<path d="M5 12h14"/>'
        '<path d="M12 5v14"/>'
    ),
    "minus": (
        '<path d="M5 12h14"/>'
    ),
    "power": (
        '<path d="M18.36 6.64a9 9 0 1 1-12.73 0"/>'
        '<line x1="12" y1="2" x2="12" y2="12"/>'
    ),
    "puzzle": (
        '<path d="M19.439 7.85c0 0-1.439.15-2.439-1s0-2.85 0-2.85h-3s-.15 1.44-1.15 2.44-2.85 0-2.85 0v-3h-4v4s1.44.15 2.44 1.15 0 2.85 0 2.85h-3v4s1.44.15 2.44 1.15 0 2.85 0 2.85h4v-3s.15-1.44 1.15-2.44 2.85 0 2.85 0v3h3s.15-1.44 1.15-2.44 2.85 0 2.85 0v-4h-3s-1.44-.15-2.44-1.15 0-2.85 0-2.85z"/>'
    ),
    "clipboard": (
        '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/>'
        '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'
    ),
    "git-compare": (
        '<circle cx="18" cy="18" r="3"/>'
        '<circle cx="6" cy="6" r="3"/>'
        '<path d="M13 6h3a2 2 0 0 1 2 2v7"/>'
        '<path d="M11 18H8a2 2 0 0 1-2-2V9"/>'
    ),
    "sliders": (
        '<line x1="4" x2="4" y1="21" y2="14"/>'
        '<line x1="4" x2="4" y1="10" y2="3"/>'
        '<line x1="12" x2="12" y1="21" y2="12"/>'
        '<line x1="12" x2="12" y1="8" y2="3"/>'
        '<line x1="20" x2="20" y1="21" y2="16"/>'
        '<line x1="20" x2="20" y1="12" y2="3"/>'
        '<line x1="1" x2="7" y1="14" y2="14"/>'
        '<line x1="9" x2="15" y1="8" y2="8"/>'
        '<line x1="17" x2="23" y1="16" y2="16"/>'
    ),
    "code": (
        '<polyline points="16 18 22 12 16 6"/>'
        '<polyline points="8 6 2 12 8 18"/>'
    ),
}

# 缓存已生成的 QPixmap 和 QIcon
_PIXMAP_CACHE: Dict[Tuple[str, str, int, float], QPixmap] = {}
_ICON_CACHE: Dict[Tuple[str, str, int, float], QIcon] = {}


def build_svg_xml(name: str, color: str = "#3b82f6", stroke_width: float = 2.0) -> str:
    """生成标准化 SVG XML 字符串"""
    path_data = SVG_PATHS.get(name, SVG_PATHS["tools"])
    fill_mode = "none"
    if name in ("play", "zap", "stop"):
        fill_mode = color
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
        f'fill="{fill_mode}" stroke="{color}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'{path_data}'
        f'</svg>'
    )


def get_pixmap(name: str, color: Optional[str] = None, size: int = 24, stroke_width: float = 2.0) -> QPixmap:
    """按指定名称、着色与尺寸获取清晰的矢量 QPixmap"""
    effective_color = color or "#3b82f6"
    cache_key = (name, effective_color, size, stroke_width)
    if cache_key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[cache_key]

    svg_str = build_svg_xml(name, effective_color, stroke_width)
    renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()

    _PIXMAP_CACHE[cache_key] = pixmap
    return pixmap


def get_icon(name: str, color: Optional[str] = None, size: int = 24, stroke_width: float = 2.0) -> QIcon:
    """按指定名称、着色与尺寸获取 QIcon"""
    effective_color = color or "#3b82f6"
    cache_key = (name, effective_color, size, stroke_width)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

    pixmap = get_pixmap(name, effective_color, size, stroke_width)
    icon = QIcon(pixmap)
    _ICON_CACHE[cache_key] = icon
    return icon


# ========================================================
# 22 个功能模块专属独立图标视觉规范字典 (Plugin Icon Config)
# 为每个插件定制专属的矢量符号、主题渐变色板与高对比度渲染参数
# ========================================================
PLUGIN_ICON_CONFIG: Dict[str, Dict[str, Any]] = {
    "file_suite": {
        "symbol": "folder",
        "color_start": "#3b82f6",
        "color_end": "#1d4ed8",
        "accent": "#3b82f6",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "archive_manager": {
        "symbol": "archive",
        "color_start": "#f59e0b",
        "color_end": "#b45309",
        "accent": "#f59e0b",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "image_master": {
        "symbol": "image",
        "color_start": "#10b981",
        "color_end": "#047857",
        "accent": "#10b981",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "screen_capture": {
        "symbol": "camera",
        "color_start": "#0284c7",
        "color_end": "#0369a1",
        "accent": "#0284c7",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "media_compressor": {
        "symbol": "zap",
        "color_start": "#f97316",
        "color_end": "#c2410c",
        "accent": "#f97316",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "frame_extractor": {
        "symbol": "layers",
        "color_start": "#6366f1",
        "color_end": "#4338ca",
        "accent": "#6366f1",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "screen_recorder": {
        "symbol": "monitor",
        "color_start": "#e11d48",
        "color_end": "#9f1239",
        "accent": "#e11d48",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "auto_input": {
        "symbol": "keyboard",
        "color_start": "#8b5cf6",
        "color_end": "#6d28d9",
        "accent": "#8b5cf6",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "video_to_audio": {
        "symbol": "music",
        "color_start": "#a855f7",
        "color_end": "#7e22ce",
        "accent": "#a855f7",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "audio_converter": {
        "symbol": "refresh",
        "color_start": "#06b6d4",
        "color_end": "#0e7490",
        "accent": "#06b6d4",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "audio_recorder": {
        "symbol": "mic",
        "color_start": "#ef4444",
        "color_end": "#b91c1c",
        "accent": "#ef4444",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "ncm_decryptor": {
        "symbol": "unlock",
        "color_start": "#d946ef",
        "color_end": "#a21caf",
        "accent": "#d946ef",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "audio_cutter": {
        "symbol": "scissors",
        "color_start": "#ec4899",
        "color_end": "#be185d",
        "accent": "#ec4899",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "media_downloader": {
        "symbol": "video",
        "color_start": "#0ea5e9",
        "color_end": "#0369a1",
        "accent": "#0ea5e9",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "webdav_config": {
        "symbol": "globe",
        "color_start": "#0891b2",
        "color_end": "#155e75",
        "accent": "#0891b2",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "youtube_downloader": {
        "symbol": "youtube",
        "color_start": "#dc2626",
        "color_end": "#991b1b",
        "accent": "#dc2626",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "osu_skin_studio": {
        "symbol": "sparkles",
        "color_start": "#f43f5e",
        "color_end": "#be123c",
        "accent": "#f43f5e",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "translator": {
        "symbol": "languages",
        "color_start": "#4f46e5",
        "color_end": "#3730a3",
        "accent": "#4f46e5",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "whiteboard": {
        "symbol": "pencil",
        "color_start": "#14b8a6",
        "color_end": "#0f766e",
        "accent": "#14b8a6",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "system_integrator": {
        "symbol": "system",
        "color_start": "#64748b",
        "color_end": "#334155",
        "accent": "#64748b",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "force_killer": {
        "symbol": "shield",
        "color_start": "#e11d48",
        "color_end": "#881337",
        "accent": "#e11d48",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "proxy_configurator": {
        "symbol": "network",
        "color_start": "#10b981",
        "color_end": "#065f46",
        "accent": "#10b981",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "quick_launcher": {
        "symbol": "search",
        "color_start": "#8b5cf6",
        "color_end": "#6d28d9",
        "accent": "#8b5cf6",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "clipboard_manager": {
        "symbol": "clipboard",
        "color_start": "#0ea5e9",
        "color_end": "#0284c7",
        "accent": "#0ea5e9",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "port_network_sentinel": {
        "symbol": "shield",
        "color_start": "#10b981",
        "color_end": "#047857",
        "accent": "#10b981",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
    "watermark_studio": {
        "symbol": "image",
        "color_start": "#06b6d4",
        "color_end": "#0891b2",
        "accent": "#06b6d4",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0,
    },
}

_PLUGIN_BADGE_CACHE: Dict[Tuple[str, int], QPixmap] = {}
_PLUGIN_ICON_CACHE: Dict[Tuple[str, int], QIcon] = {}


def render_plugin_badge_qimage(plugin_id: str, size: int = 256) -> QImage:
    """
    渲染指定插件的高保真圆角渐变微章 QImage (基准 256x256)
    包含精致内光晕边框与高对比度居中矢量符号。
    """
    cfg = PLUGIN_ICON_CONFIG.get(plugin_id, {
        "symbol": "tools",
        "color_start": "#3b82f6",
        "color_end": "#1d4ed8",
        "accent": "#3b82f6",
        "stroke_color": "#ffffff",
        "stroke_width": 2.0
    })

    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)

    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    # 1. 绘制带有圆角矩形的高对比渐变底板
    pad = size * 0.04
    rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    radius = size * 0.22

    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor(cfg["color_start"]))
    gradient.setColorAt(1.0, QColor(cfg["color_end"]))

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawRoundedRect(rect, radius, radius)

    # 2. 绘制微妙的内高光半透明边框 (增强微质感)
    border_pen = QPen(QColor(255, 255, 255, 70), max(1.0, size * 0.015))
    painter.setPen(border_pen)
    painter.setBrush(Qt.NoBrush)
    inner_rect = QRectF(rect.x() + 0.5, rect.y() + 0.5, rect.width() - 1.0, rect.height() - 1.0)
    painter.drawRoundedRect(inner_rect, radius, radius)

    # 3. 居中渲染高对比度白色矢量符号
    symbol_name = cfg.get("symbol", "tools")
    stroke_w = cfg.get("stroke_width", 2.0)
    stroke_col = cfg.get("stroke_color", "#ffffff")
    svg_str = build_svg_xml(symbol_name, color=stroke_col, stroke_width=stroke_w)
    renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))

    sym_pad = size * 0.24
    sym_rect = QRectF(sym_pad, sym_pad, size - 2 * sym_pad, size - 2 * sym_pad)
    renderer.render(painter, sym_rect)

    painter.end()
    return img


def get_plugin_badge_pixmap(plugin_id: str, size: int = 32) -> QPixmap:
    """获取指定插件的独立徽章 QPixmap (带缓存)"""
    cache_key = (plugin_id, size)
    if cache_key in _PLUGIN_BADGE_CACHE:
        return _PLUGIN_BADGE_CACHE[cache_key]

    qimg = render_plugin_badge_qimage(plugin_id, size=max(128, size * 2))
    pix = QPixmap.fromImage(qimg).scaled(
        size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )
    _PLUGIN_BADGE_CACHE[cache_key] = pix
    return pix


def get_plugin_pixmap(plugin_id: str, color: Optional[str] = None, size: int = 24) -> QPixmap:
    """获取指定插件的高对比矢量符号 QPixmap"""
    cfg = PLUGIN_ICON_CONFIG.get(plugin_id, {})
    sym = cfg.get("symbol", "tools")
    eff_color = color or cfg.get("accent", "#3b82f6")
    return get_pixmap(sym, color=eff_color, size=size)


def get_plugin_icon(plugin_id: str, size: int = 24, plugin_dir: Optional[str] = None) -> QIcon:
    """
    获取指定插件的独立 QIcon。
    若插件目录下已存在 icon.svg/icon.ico/icon.png 则直接载入并缓存，否则由徽章渲染器生成。
    """
    cache_key = (plugin_id, size, plugin_dir or "")
    if cache_key in _PLUGIN_ICON_CACHE:
        return _PLUGIN_ICON_CACHE[cache_key]

    if plugin_dir and os.path.isdir(plugin_dir):
        for candidate_name in ("icon.svg", "icon.ico", "icon.png"):
            cand = os.path.join(plugin_dir, candidate_name)
            if os.path.isfile(cand):
                if candidate_name.endswith(".svg"):
                    renderer = QSvgRenderer(cand)
                    if renderer.isValid():
                        pix = QPixmap(size, size)
                        pix.fill(Qt.transparent)
                        painter = QPainter(pix)
                        renderer.render(painter)
                        painter.end()
                        icon = QIcon(pix)
                        _PLUGIN_ICON_CACHE[cache_key] = icon
                        return icon
                else:
                    icon = QIcon(cand)
                    if not icon.isNull():
                        _PLUGIN_ICON_CACHE[cache_key] = icon
                        return icon

    from toolbox.core.paths import get_app_root
    cand_ico = os.path.join(get_app_root(), "toolbox", "plugins", plugin_id, "icon.ico")
    if os.path.isfile(cand_ico):
        icon = QIcon(cand_ico)
        if not icon.isNull():
            _PLUGIN_ICON_CACHE[cache_key] = icon
            return icon

    # 使用多分辨率徽章构建 QIcon
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        pix = get_plugin_badge_pixmap(plugin_id, size=s)
        icon.addPixmap(pix)

    _PLUGIN_ICON_CACHE[cache_key] = icon
    return icon


def generate_plugin_ico_and_png(plugin_id: str, target_dir: str) -> Tuple[str, str]:
    """
    在指定目录下生成该插件的高清 PNG (256x256) 与全尺寸 ICO 文件 (包含 16, 32, 48, 64, 128, 256 全部 mipmaps)。
    返回 (ico_path, png_path)。
    """
    os.makedirs(target_dir, exist_ok=True)
    ico_path = os.path.join(target_dir, "icon.ico")
    png_path = os.path.join(target_dir, "icon.png")

    qimg = render_plugin_badge_qimage(plugin_id, size=256)

    qba = QByteArray()
    qbuf = QBuffer(qba)
    qbuf.open(QBuffer.WriteOnly)
    qimg.save(qbuf, "PNG")

    pil_img = Image.open(io.BytesIO(bytes(qba)))

    # 保存 256x256 高清 PNG
    pil_img.save(png_path, format="PNG")

    # 保存包含全量 Windows 规格 mipmaps 的 ICO
    mipmap_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    pil_img.save(ico_path, format="ICO", sizes=mipmap_sizes)

    return ico_path, png_path


def ensure_plugin_icons(plugin_id: str, plugin_dir: Optional[str] = None) -> Tuple[str, str]:
    """
    确保指定插件目录下具备合法的独立 icon.ico 与 icon.png 图标文件。
    若不存在或为空，则立即自动生成。
    """
    if not plugin_dir:
        from toolbox.core.paths import get_app_root
        plugin_dir = os.path.join(get_app_root(), "toolbox", "plugins", plugin_id)

    ico_path = os.path.join(plugin_dir, "icon.ico")
    png_path = os.path.join(plugin_dir, "icon.png")

    need_gen = False
    if not os.path.isfile(ico_path) or os.path.getsize(ico_path) == 0:
        need_gen = True
    if not os.path.isfile(png_path) or os.path.getsize(png_path) == 0:
        need_gen = True

    if need_gen:
        try:
            return generate_plugin_ico_and_png(plugin_id, plugin_dir)
        except Exception as e:
            print(f"[Icons] 为插件 {plugin_id} 生成独立图标失败: {e}")

    return ico_path, png_path


def ensure_all_plugin_icons() -> Dict[str, Tuple[str, str]]:
    """
    检查并为全部 22 个插件生成并持久化独立的 icon.ico 与 icon.png。
    """
    from toolbox.core.paths import get_app_root
    plugins_dir = os.path.join(get_app_root(), "toolbox", "plugins")
    results = {}
    for pid in PLUGIN_ICON_CONFIG:
        p_dir = os.path.join(plugins_dir, pid)
        if os.path.isdir(p_dir):
            results[pid] = ensure_plugin_icons(pid, p_dir)
    return results
