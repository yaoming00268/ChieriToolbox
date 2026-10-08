"""
工具箱 (Toolbox) - 现代化插件卡片组件 (CardWidget)
展示插件矢量图标、标题、分类徽章、功能简述与启动按钮。
全量支持深色与浅色自适应主题样式与微交互动效。
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGraphicsDropShadowEffect
)
from PySide6.QtGui import QColor, QCursor

from toolbox.core.plugin_base import PluginBase
from toolbox.core.event_bus import EventBus
from toolbox.core.theme import ThemeManager
from toolbox.ui.icons import get_pixmap, get_icon


class PluginCardWidget(QFrame):
    clicked = Signal(str)  # 传递 plugin_id
    card_context_menu_requested = Signal(str, object)  # (plugin_id, global_pos)

    def __init__(
        self,
        plugin: PluginBase,
        card_width: Optional[int] = None,
        card_height: Optional[int] = None,
        parent=None
    ):
        self._pending_visible = False
        super().__init__(parent)
        self.setWindowFlags(Qt.Widget)
        self.plugin = plugin
        self.plugin_id = plugin.id
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.theme_manager = ThemeManager()
        self.event_bus = EventBus()

        from toolbox.core.config_manager import ConfigManager
        cfg = ConfigManager()
        self.card_width = int(card_width or cfg.get_card_width())
        self.card_height = int(card_height or cfg.get_card_height())

        self.init_ui()
        self.event_bus.theme_changed.connect(self._on_theme_changed)
        self.destroyed.connect(self.cleanup)

    def cleanup(self):
        if getattr(self, "_is_cleaned_up", False):
            return
        self._is_cleaned_up = True
        try:
            self.event_bus.theme_changed.disconnect(self._on_theme_changed)
        except Exception:
            pass

    def setVisible(self, visible: bool):
        # 绝不允许作为无父级的独立顶级窗口显示，避免在挂载前被 Win32 提升为独立桌面窗口
        if visible and self.parentWidget() is None:
            self._pending_visible = True
            return
        self._pending_visible = False
        super().setVisible(visible)

    def changeEvent(self, event):
        if event.type() == QEvent.ParentChange:
            if getattr(self, "_pending_visible", False) and self.parentWidget() is not None:
                self._pending_visible = False
                self.setVisible(True)
        super().changeEvent(event)

    def update_card_size(self, width: int, height: int):
        """动态更新卡片物理尺寸"""
        self.card_width = width
        self.card_height = height
        self.setFixedWidth(width)
        self.setFixedHeight(self.card_height)
        if hasattr(self, "desc_label"):
            self.desc_label.setMaximumHeight(max(36, self.card_height - 112))
        self.updateGeometry()

    def init_ui(self):
        self.setObjectName("pluginCard")
        self.setFixedWidth(self.card_width)
        self.setFixedHeight(self.card_height)

        # 动态阴影效果
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(16)
        self.shadow.setOffset(0, 3)
        self._update_shadow_color()
        self.setGraphicsEffect(self.shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        # 1. 顶部：图标容器 + 标题 + 分类徽章
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)

        # 矢量图标容器 (圆角几何 Squircle)
        self.icon_box = QFrame()
        self.icon_box.setFixedSize(42, 42)
        box_layout = QVBoxLayout(self.icon_box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.setAlignment(Qt.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self._render_icon()
        box_layout.addWidget(self.icon_label)
        top_layout.addWidget(self.icon_box)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(3)
        title_label = QLabel(self.plugin.name)
        title_label.setObjectName("cardTitle")

        cat_hbox = QHBoxLayout()
        cat_label = QLabel(self.plugin.category)
        cat_label.setObjectName("cardCategory")
        cat_hbox.addWidget(cat_label)
        cat_hbox.addStretch()

        title_vbox.addWidget(title_label)
        title_vbox.addLayout(cat_hbox)
        top_layout.addLayout(title_vbox, 1)

        layout.addLayout(top_layout)

        # 2. 中部：功能简述 (自动多行自适应折行，设定高度保护防止挤压底部操作栏)
        self.desc_label = QLabel(self.plugin.description)
        self.desc_label.setObjectName("cardDesc")
        self.desc_label.setWordWrap(True)
        self.desc_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.desc_label.setMaximumHeight(max(36, self.card_height - 112))
        layout.addWidget(self.desc_label, 1)

        # 3. 底部：版本标识 + 启动按钮
        bottom_layout = QHBoxLayout()
        ver_label = QLabel(f"v{self.plugin.version}")
        ver_label.setObjectName("cardVersion")
        bottom_layout.addWidget(ver_label)
        bottom_layout.addStretch()

        self.btn_open = QPushButton("进入功能")
        self.btn_open.setObjectName("btnOpen")
        self.btn_open.setIcon(get_icon("chevron-right", color="#ffffff", size=14))
        self.btn_open.setLayoutDirection(Qt.RightToLeft)  # 箭头靠右展示
        self.btn_open.clicked.connect(self._on_card_click)
        bottom_layout.addWidget(self.btn_open)

        layout.addLayout(bottom_layout)
        self._update_container_style()

    def _render_icon(self):
        from toolbox.ui.icons import get_plugin_badge_pixmap
        # 使用插件专属高保真圆角渐变微章 (36x36 完美契合 42x42 视口)
        pix = get_plugin_badge_pixmap(self.plugin.id, size=36)
        if pix and not pix.isNull():
            self.icon_label.setPixmap(pix)
        else:
            is_dark = self.theme_manager.is_dark()
            accent = "#38bdf8" if is_dark else "#2563eb"
            pix = get_pixmap(self.plugin.icon, color=accent, size=24)
            self.icon_label.setPixmap(pix)

    def _update_shadow_color(self):
        if self.theme_manager.is_dark():
            self.shadow.setColor(QColor(0, 0, 0, 80))
        else:
            self.shadow.setColor(QColor(15, 23, 42, 20))

    def _update_container_style(self):
        # 容器底色透明，由内部专属独立徽章呈现现代圆角 Squircle 视觉
        self.icon_box.setStyleSheet("background-color: transparent; border: none;")

    def _on_theme_changed(self, theme_name: str):
        self._render_icon()
        self._update_shadow_color()
        self._update_container_style()

    def enterEvent(self, event):
        if self.theme_manager.is_dark():
            self.shadow.setBlurRadius(24)
            self.shadow.setOffset(0, 5)
            self.shadow.setColor(QColor(0, 0, 0, 130))
        else:
            self.shadow.setBlurRadius(24)
            self.shadow.setOffset(0, 5)
            self.shadow.setColor(QColor(15, 23, 42, 35))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._update_shadow_color()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._on_card_click()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        self.card_context_menu_requested.emit(self.plugin_id, event.globalPos())
        event.accept()

    def _on_card_click(self):
        self.clicked.emit(self.plugin_id)

