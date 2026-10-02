"""
工具箱 (Toolbox) - 现代化首页仪表盘 (HomePage)
全矢量图标展示、类别动态计数胶囊栏、实时交互搜索与无结果友好引导。
"""

from typing import List, Optional
from PySide6.QtCore import Qt, Signal, QEvent, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QGridLayout, QFrame, QButtonGroup,
    QSizePolicy, QMenu, QInputDialog, QMessageBox
)
from toolbox.core.plugin_base import PluginBase
from toolbox.core.config_manager import ConfigManager
from toolbox.core.event_bus import EventBus
from toolbox.core.theme import ThemeManager
from toolbox.core.tray_manager import PluginTrayManager
from toolbox.ui.components.card_widget import PluginCardWidget
from toolbox.ui.icons import get_pixmap, get_icon, get_plugin_icon
from toolbox.ui.plugin_export_dialog import PluginExportDialog
from toolbox.ui.group_manage_dialog import GroupManageDialog


class HomePage(QWidget):
    open_plugin_requested = Signal(str)  # 申请打开特定 plugin_id
    open_standalone_requested = Signal(str)  # 申请以独立窗口打开特定 plugin_id

    def __init__(self, plugins: Optional[List[PluginBase]] = None, parent=None):
        super().__init__(parent)
        self.plugins: List[PluginBase] = plugins or []
        self.config_manager = ConfigManager()
        self.current_category: str = self.config_manager.get_default_startup_group()
        self._pending_startup_category: Optional[str] = self.current_category
        self.search_keyword: str = ""
        self.card_widgets: List[PluginCardWidget] = []
        self._card_pool: dict = {}
        self.theme_manager = ThemeManager()
        self.event_bus = EventBus()

        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(150)
        self._search_debounce_timer.timeout.connect(self._filter_and_render_cards)

        self.init_ui()
        self._settings_timer = QTimer(self)
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(30)
        self._settings_timer.timeout.connect(self._do_refresh_on_settings_changed)

        self.event_bus.theme_changed.connect(self._on_theme_changed)
        self.event_bus.settings_changed.connect(self._on_settings_changed)

    def set_plugins(self, plugins: List[PluginBase]):
        """更新插件列表并刷新渲染"""
        self.plugins = plugins
        self._card_pool.clear()
        if getattr(self, "_pending_startup_category", None):
            self.current_category = self._pending_startup_category
            self._pending_startup_category = None
        self._rebuild_recent_bar()
        self._rebuild_category_buttons()
        self._filter_and_render_cards()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 26, 32, 22)
        main_layout.setSpacing(18)

        # 1. 顶部 Header 欢迎区与搜索区
        header_layout = QHBoxLayout()
        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        self.logo_label = QLabel()
        self.logo_label.setFixedSize(28, 28)
        self._update_logo()
        title_row.addWidget(self.logo_label)

        title = QLabel("千绘莉的多功能工具箱")
        title.setObjectName("headerTitle")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        title_row.addWidget(title)
        title_row.addStretch()

        header_vbox.addLayout(title_row)

        subtitle = QLabel("聚合跨工作区实用工具 · 现代化深浅双模 · 随开随用 · 极速流转")
        subtitle.setStyleSheet("font-size: 13px; color: #94a3b8;")
        header_vbox.addWidget(subtitle)
        header_layout.addLayout(header_vbox, 1)

        # 搜索输入框与统计信息
        search_box = QVBoxLayout()
        search_box.setAlignment(Qt.AlignRight)

        search_input_layout = QHBoxLayout()
        search_input_layout.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索工具名称、功能或描述... (Enter 直达)")
        self.search_input.setMinimumHeight(30)
        self.search_input.setMinimumWidth(220)
        self.search_input.setMaximumWidth(580)
        self.search_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.returnPressed.connect(self._on_search_enter_pressed)
        self.search_input.installEventFilter(self)
        search_input_layout.addWidget(self.search_input, 1)

        self.btn_clear_search = QPushButton()
        self.btn_clear_search.setObjectName("flatIconBtn")
        self.btn_clear_search.setIcon(get_icon("clear", size=14))
        self.btn_clear_search.setToolTip("清空搜索")
        self.btn_clear_search.setVisible(False)
        self.btn_clear_search.setFixedSize(28, 28)
        self.btn_clear_search.clicked.connect(self._clear_search)
        search_input_layout.addWidget(self.btn_clear_search)

        search_box.addLayout(search_input_layout)

        self.lbl_count_info = QLabel("共 0 个功能模块")
        self.lbl_count_info.setStyleSheet("color: #64748b; font-size: 12px; margin-top: 2px;")
        self.lbl_count_info.setAlignment(Qt.AlignRight)
        search_box.addWidget(self.lbl_count_info)

        header_layout.addLayout(search_box)
        main_layout.addLayout(header_layout)

        # 2. 最近使用快捷标签栏 (支持自适应水平平滑滚动，杜绝小窗口文字挤压截断)
        self.recent_container = QWidget()
        recent_nav_layout = QHBoxLayout(self.recent_container)
        recent_nav_layout.setContentsMargins(0, 0, 0, 0)
        recent_nav_layout.setSpacing(8)

        lbl_tag = QLabel("最近使用:")
        lbl_tag.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        recent_nav_layout.addWidget(lbl_tag)

        self.recent_scroll = QScrollArea()
        self.recent_scroll.setWidgetResizable(True)
        self.recent_scroll.setFixedHeight(36)
        self.recent_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.recent_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.recent_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.recent_frame = QWidget()
        self.recent_frame.setObjectName("recentBar")
        self.recent_layout = QHBoxLayout(self.recent_frame)
        self.recent_layout.setContentsMargins(0, 2, 0, 2)
        self.recent_layout.setSpacing(8)

        self.recent_scroll.setWidget(self.recent_frame)
        self.recent_scroll.installEventFilter(self)
        self.recent_scroll.viewport().installEventFilter(self)
        self.recent_frame.installEventFilter(self)

        recent_nav_layout.addWidget(self.recent_scroll, 1)
        main_layout.addWidget(self.recent_container)

        # 3. 分类筛选胶囊栏 (左右微调滚动按钮与水平滚动区协同排布)
        self.cat_nav_container = QWidget()
        cat_nav_layout = QHBoxLayout(self.cat_nav_container)
        cat_nav_layout.setContentsMargins(0, 0, 0, 0)
        cat_nav_layout.setSpacing(6)

        self.btn_cat_prev = QPushButton()
        self.btn_cat_prev.setFixedSize(28, 28)
        self.btn_cat_prev.setCursor(Qt.PointingHandCursor)
        self.btn_cat_prev.setToolTip("向左浏览更多分类")
        self.btn_cat_prev.setIcon(get_icon("chevron-left", size=14))
        self.btn_cat_prev.clicked.connect(lambda: self._scroll_category(-180))
        cat_nav_layout.addWidget(self.btn_cat_prev)

        self.cat_scroll = QScrollArea()
        self.cat_scroll.setWidgetResizable(True)
        self.cat_scroll.setFixedHeight(44)
        self.cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cat_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cat_frame = QWidget()
        self.cat_frame.setObjectName("catFrame")
        self.cat_layout = QHBoxLayout(self.cat_frame)
        self.cat_layout.setContentsMargins(0, 4, 0, 4)
        self.cat_layout.setSpacing(8)
        self.cat_button_group = QButtonGroup(self)
        self.cat_button_group.setExclusive(True)

        self.cat_scroll.setWidget(self.cat_frame)
        self.cat_scroll.installEventFilter(self)
        self.cat_scroll.viewport().installEventFilter(self)
        self.cat_frame.installEventFilter(self)

        cat_nav_layout.addWidget(self.cat_scroll, 1)

        self.btn_cat_next = QPushButton()
        self.btn_cat_next.setFixedSize(28, 28)
        self.btn_cat_next.setCursor(Qt.PointingHandCursor)
        self.btn_cat_next.setToolTip("向右浏览更多分类")
        self.btn_cat_next.setIcon(get_icon("chevron-right", size=14))
        self.btn_cat_next.clicked.connect(lambda: self._scroll_category(180))
        cat_nav_layout.addWidget(self.btn_cat_next)

        main_layout.addWidget(self.cat_nav_container)

        h_bar = self.cat_scroll.horizontalScrollBar()
        h_bar.valueChanged.connect(self._update_cat_nav_buttons)
        h_bar.rangeChanged.connect(self._update_cat_nav_buttons)

        # 4. 滚动区域承载卡片网格
        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_container = QWidget()
        self.cards_container.setObjectName("cardsContainer")
        self.grid_layout = QGridLayout(self.cards_container)
        self.grid_layout.setSpacing(18)
        self.grid_layout.setContentsMargins(4, 4, 4, 24)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.cards_scroll.setWidget(self.cards_container)
        self.cards_scroll.viewport().installEventFilter(self)
        main_layout.addWidget(self.cards_scroll, 1)

        self._rebuild_recent_bar()
        self._rebuild_category_buttons()
        self._filter_and_render_cards()

    def _rebuild_recent_bar(self):
        """重新渲染最近使用的工具快捷标签栏"""
        while self.recent_layout.count():
            item = self.recent_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        recent_ids = self.config_manager.get("recent_plugins", [])
        enabled_plugins_map = {
            p.id: p for p in self.plugins if self.config_manager.is_plugin_enabled(p.id)
        }
        valid_recents = [pid for pid in recent_ids if pid in enabled_plugins_map]

        if not valid_recents:
            if hasattr(self, "recent_container"):
                self.recent_container.setVisible(False)
            self.recent_frame.setVisible(False)
            return

        if hasattr(self, "recent_container"):
            self.recent_container.setVisible(True)
        self.recent_frame.setVisible(True)

        is_dark = self.theme_manager.is_dark()
        bg_col = "#1e2230" if is_dark else "#f1f5f9"
        text_col = "#94a3b8" if is_dark else "#475569"
        border_col = "#2e3547" if is_dark else "#cbd5e1"
        hover_bg = "#2a3043" if is_dark else "#e2e8f0"
        hover_text = "#ffffff" if is_dark else "#0f172a"

        chip_style = f"""
            QPushButton {{
                background-color: {bg_col};
                color: {text_col};
                border: 1px solid {border_col};
                border-radius: 12px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                color: {hover_text};
                border-color: #3b82f6;
            }}
        """

        for pid in valid_recents[:8]:
            p = enabled_plugins_map[pid]
            btn = QPushButton(f" {p.name}", self.recent_frame)
            btn.setIcon(get_plugin_icon(p.id, size=14))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(chip_style)
            btn.clicked.connect(lambda checked=False, target_id=pid: self.open_plugin_requested.emit(target_id))
            self.recent_layout.addWidget(btn)
            btn.adjustSize()

        self.recent_layout.addStretch()

    def _update_logo(self):
        color = "#38bdf8" if self.theme_manager.is_dark() else "#0284c7"
        self.logo_label.setPixmap(get_pixmap("app_logo", color=color, size=28))

    def _rebuild_category_buttons(self):
        # 彻底从按钮组与布局中解绑并删除旧按钮，杜绝内存与视图层叠泄露
        for btn in list(self.cat_button_group.buttons()):
            self.cat_button_group.removeButton(btn)

        while self.cat_layout.count():
            item = self.cat_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        # 统计各分类数量 (仅统计已启用的插件)
        enabled_plugins = [p for p in self.plugins if self.config_manager.is_plugin_enabled(p.id)]
        recent_ids = self.config_manager.get("recent_plugins", [])
        enabled_map = {p.id: p for p in enabled_plugins}
        valid_recents = [pid for pid in recent_ids if pid in enabled_map]

        category_counts = {"全部": len(enabled_plugins)}
        if valid_recents:
            category_counts["最近使用"] = len(valid_recents)
        for p in enabled_plugins:
            groups = self.config_manager.get_plugin_groups(p.id, p.category)
            for g in groups:
                if g not in ("全部", "最近使用"):
                    category_counts[g] = category_counts.get(g, 0) + 1

        # 统计用户自定义分组（确保空的自定义分组也显示）
        custom_groups = self.config_manager.get_custom_groups()
        for grp in custom_groups:
            if grp not in category_counts:
                category_counts[grp] = 0

        # 检查当前选中的分类是否存在，若不存在则回退至“全部”
        if self.current_category not in category_counts:
            self.current_category = "全部"

        is_dark = self.theme_manager.is_dark()
        pill_style = self._get_pill_style(is_dark)

        for cat, count in category_counts.items():
            btn = QPushButton(f"{cat} ({count})", self.cat_frame)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            if cat in custom_groups:
                btn.setIcon(get_icon("tag", size=13))
                btn.setContextMenuPolicy(Qt.CustomContextMenu)
                btn.customContextMenuRequested.connect(
                    lambda pos, c=cat, b=btn: self._on_custom_cat_context_menu(c, b.mapToGlobal(pos))
                )
                btn.setToolTip("右键可快速删除此自定义分组")
            if cat == self.current_category:
                btn.setChecked(True)
            btn.setStyleSheet(pill_style)
            self.cat_button_group.addButton(btn)
            self.cat_layout.addWidget(btn)
            btn.adjustSize()
            btn.installEventFilter(self)
            btn.clicked.connect(lambda checked, c=cat, b=btn: self._on_category_clicked(c, b))

        # 胶囊栏尾部“新建分组”微按钮
        self.btn_new_group = QPushButton(self.cat_frame)
        self.btn_new_group.setFixedSize(28, 28)
        self.btn_new_group.setCursor(Qt.PointingHandCursor)
        self.btn_new_group.setIcon(get_icon("plus", size=13))
        self.btn_new_group.setToolTip("新建自定义分组...")
        self.btn_new_group.clicked.connect(self._prompt_create_new_group)
        border_c = "#2e3547" if is_dark else "#cbd5e1"
        self.btn_new_group.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px dashed {border_c};
                border-radius: 14px;
            }}
            QPushButton:hover {{
                border-color: #3b82f6;
                background-color: {"#2a3043" if is_dark else "#e2e8f0"};
            }}
        """)
        self.cat_layout.addWidget(self.btn_new_group)

        self.cat_layout.addStretch()
        self._apply_cat_nav_style()
        self._update_cat_nav_buttons()

    def _get_pill_style(self, is_dark: bool) -> str:
        if is_dark:
            return """
                QPushButton {
                    background-color: #1e2230;
                    color: #94a3b8;
                    border: 1px solid #2e3547;
                    border-radius: 14px;
                    padding: 4px 11px;
                    font-size: 12px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #2a3043;
                    color: #ffffff;
                    border-color: #3b82f6;
                }
                QPushButton:checked {
                    background-color: #2563eb;
                    color: #ffffff;
                    border-color: #3b82f6;
                    font-weight: 600;
                }
            """
        else:
            return """
                QPushButton {
                    background-color: #ffffff;
                    color: #475569;
                    border: 1px solid #cbd5e1;
                    border-radius: 14px;
                    padding: 4px 11px;
                    font-size: 12px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #f1f5f9;
                    color: #0f172a;
                    border-color: #2563eb;
                }
                QPushButton:checked {
                    background-color: #2563eb;
                    color: #ffffff;
                    border-color: #1d4ed8;
                    font-weight: 600;
                }
            """

    def _on_category_clicked(self, category: str, btn: Optional[QPushButton] = None):
        self.current_category = category
        if btn and hasattr(self, "cat_scroll"):
            self.cat_scroll.ensureWidgetVisible(btn, 24, 0)
        self._filter_and_render_cards()

    def _scroll_category(self, delta: int):
        if hasattr(self, "cat_scroll"):
            bar = self.cat_scroll.horizontalScrollBar()
            bar.setValue(bar.value() + delta)

    def _update_cat_nav_buttons(self):
        if not hasattr(self, "btn_cat_prev") or not hasattr(self, "cat_scroll"):
            return
        bar = self.cat_scroll.horizontalScrollBar()
        max_val = bar.maximum()
        val = bar.value()
        has_overflow = max_val > 0
        self.btn_cat_prev.setVisible(has_overflow)
        self.btn_cat_next.setVisible(has_overflow)
        if has_overflow:
            self.btn_cat_prev.setEnabled(val > 0)
            self.btn_cat_next.setEnabled(val < max_val)

    def _get_cat_nav_button_style(self, is_dark: bool) -> str:
        border_col = "#2e3547" if is_dark else "#cbd5e1"
        hover_bg = "#2a3043" if is_dark else "#e2e8f0"
        return f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {border_col};
                border-radius: 14px;
                color: #64748b;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                border-color: #3b82f6;
                color: #3b82f6;
            }}
            QPushButton:disabled {{
                border-color: transparent;
                background-color: transparent;
            }}
        """

    def _apply_cat_nav_style(self):
        if hasattr(self, "btn_cat_prev") and hasattr(self, "btn_cat_next"):
            is_dark = self.theme_manager.is_dark()
            st = self._get_cat_nav_button_style(is_dark)
            self.btn_cat_prev.setStyleSheet(st)
            self.btn_cat_next.setStyleSheet(st)

    def _on_search_changed(self, text: str):
        self.search_keyword = text.strip().lower()
        self.btn_clear_search.setVisible(bool(self.search_keyword))
        self._search_debounce_timer.start(150)

    def _clear_search(self):
        self._search_debounce_timer.stop()
        self.search_input.clear()
        self.search_keyword = ""
        self._filter_and_render_cards()

    def _on_search_enter_pressed(self):
        """按下 Enter 键立即完成过滤并直接进入当前首个匹配的插件模块"""
        self._search_debounce_timer.stop()
        self._filter_and_render_cards()
        if self.card_widgets:
            first_card = self.card_widgets[0]
            self.open_plugin_requested.emit(first_card.plugin_id)

    def _filter_and_render_cards(self):
        # 移除已有网格布局项（隐藏池化卡片，仅销毁非池化临时组件如空状态提示）
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setVisible(False)
                if widget not in self._card_pool.values():
                    widget.deleteLater()

        self.card_widgets.clear()

        # 筛选符合条件的插件 (仅显示已启用的插件)
        matched_plugins = []
        enabled_plugins = [p for p in self.plugins if self.config_manager.is_plugin_enabled(p.id)]
        enabled_map = {p.id: p for p in enabled_plugins}

        if self.current_category == "最近使用":
            recent_ids = self.config_manager.get("recent_plugins", [])
            for pid in recent_ids:
                if pid in enabled_map:
                    p = enabled_map[pid]
                    if self.search_keyword:
                        kw = self.search_keyword
                        if (kw not in p.name.lower() and 
                            kw not in p.description.lower() and 
                            kw not in p.id.lower() and
                            kw not in p.category.lower()):
                            continue
                    matched_plugins.append(p)
        else:
            for p in enabled_plugins:
                if self.current_category != "全部":
                    if not self.config_manager.is_plugin_in_group(p.id, self.current_category, default_category=p.category):
                        continue
                if self.search_keyword:
                    kw = self.search_keyword
                    if (kw not in p.name.lower() and 
                        kw not in p.description.lower() and 
                        kw not in p.id.lower() and
                        kw not in p.category.lower()):
                        continue
                matched_plugins.append(p)

        # 更新数量统计
        if self.search_keyword or self.current_category != "全部":
            self.lbl_count_info.setText(f"筛选出 {len(matched_plugins)} / {len(enabled_plugins)} 个模块")
        else:
            self.lbl_count_info.setText(f"共 {len(enabled_plugins)} 个功能模块")

        # 动态自适应计算列数与卡片尺寸
        columns = self._calculate_columns()
        self._current_columns = columns
        card_w = self._calculate_effective_card_width(columns)
        self._current_card_w = card_w
        _, card_h, card_spacing = self._get_card_dimensions()
        self.grid_layout.setSpacing(card_spacing)

        for idx, plugin in enumerate(matched_plugins):
            row = idx // columns
            col = idx % columns
            if plugin.id in self._card_pool:
                card = self._card_pool[plugin.id]
                card.update_card_size(card_w, card_h)
                if card.parent() is not self.cards_container:
                    card.setParent(self.cards_container)
            else:
                card = PluginCardWidget(plugin, card_width=card_w, card_height=card_h, parent=self.cards_container)
                card.clicked.connect(self.open_plugin_requested.emit)
                card.card_context_menu_requested.connect(self._on_card_context_menu)
                self._card_pool[plugin.id] = card

            self.grid_layout.addWidget(card, row, col)
            card.setVisible(True)
            self.card_widgets.append(card)

        if not matched_plugins:
            empty_widget = QWidget(self.cards_container)
            empty_layout = QVBoxLayout(empty_widget)
            empty_layout.setAlignment(Qt.AlignCenter)
            empty_layout.setSpacing(12)
            empty_layout.setContentsMargins(0, 40, 0, 0)

            icon_lbl = QLabel(empty_widget)
            icon_lbl.setAlignment(Qt.AlignCenter)
            icon_lbl.setPixmap(get_pixmap("search", color="#64748b", size=48))
            empty_layout.addWidget(icon_lbl)

            lbl_hint = QLabel("未找到匹配的功能模块", empty_widget)
            lbl_hint.setStyleSheet("color: #64748b; font-size: 15px; font-weight: 600;")
            lbl_hint.setAlignment(Qt.AlignCenter)
            empty_layout.addWidget(lbl_hint)

            btn_reset = QPushButton("清除搜索与筛选", empty_widget)
            btn_reset.setFixedWidth(140)
            btn_reset.clicked.connect(self._reset_filters)
            empty_layout.addWidget(btn_reset, 0, Qt.AlignCenter)

            self.grid_layout.addWidget(empty_widget, 0, 0, 1, columns)

    def _get_card_dimensions(self) -> tuple:
        """获取当前配置的卡片宽度、高度与网格间距"""
        w = self.config_manager.get_card_width()
        h = self.config_manager.get_card_height()
        s = self.config_manager.get_card_spacing()
        return w, h, s

    def _calculate_columns(self) -> int:
        """根据当前容器实际可用宽度动态自适应计算最佳卡片列数"""
        card_w, _, spacing = self._get_card_dimensions()
        viewport_w = 0
        if hasattr(self, "cards_scroll") and self.cards_scroll.viewport():
            viewport_w = self.cards_scroll.viewport().width()
        if viewport_w <= 100:
            viewport_w = max(300, self.width() - 64 - 16)
        avail = max(100, viewport_w - 8)
        cols = max(1, int((avail + spacing) // (card_w + spacing)))
        return cols

    def _calculate_effective_card_width(self, columns: int) -> int:
        """根据当前视口可用宽度动态均分卡片宽度，消除右侧空隙并保持视觉丰满"""
        base_w, _, spacing = self._get_card_dimensions()
        viewport_w = 0
        if hasattr(self, "cards_scroll") and self.cards_scroll.viewport():
            viewport_w = self.cards_scroll.viewport().width()
        if viewport_w <= 100:
            viewport_w = max(300, self.width() - 64 - 16)
        avail = max(100, viewport_w - 12)
        if columns <= 1:
            return base_w
        col_w = int((avail - (columns - 1) * spacing) // columns)
        return max(base_w, min(base_w + 60, col_w))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_cat_nav_buttons()
        cols = self._calculate_columns()
        card_w = self._calculate_effective_card_width(cols)
        if cols != getattr(self, "_current_columns", None) or card_w != getattr(self, "_current_card_w", None):
            self._current_columns = cols
            self._current_card_w = card_w
            self._reflow_cards()

    def _reflow_cards(self):
        """轻量级重排卡片网格，彻底重置内部排版矩阵，保证窗口缩放极致流畅无残留"""
        if not self.card_widgets:
            return
        columns = self._calculate_columns()
        self._current_columns = columns
        card_w = self._calculate_effective_card_width(columns)
        self._current_card_w = card_w
        _, card_h, spacing = self._get_card_dimensions()

        widgets = list(self.card_widgets)
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)

        self.grid_layout.setSpacing(spacing)
        for idx, card in enumerate(widgets):
            card.update_card_size(card_w, card_h)
            row = idx // columns
            col = idx % columns
            self.grid_layout.addWidget(card, row, col)

    def _reset_filters(self):
        self.search_input.clear()
        self.current_category = "全部"
        self._rebuild_category_buttons()
        self._filter_and_render_cards()

    def eventFilter(self, watched, event):
        if hasattr(self, "cards_scroll") and watched == self.cards_scroll.viewport() and event.type() == QEvent.Resize:
            cols = self._calculate_columns()
            card_w = self._calculate_effective_card_width(cols)
            if cols != getattr(self, "_current_columns", None) or card_w != getattr(self, "_current_card_w", None):
                self._current_columns = cols
                self._current_card_w = card_w
                self._reflow_cards()
        if event.type() == QEvent.Wheel:
            if (watched in (getattr(self, "cat_scroll", None),
                            getattr(self, "cat_scroll", None) and self.cat_scroll.viewport(),
                            getattr(self, "cat_frame", None)) or
                (hasattr(self, "cat_frame") and self.cat_frame.isAncestorOf(watched))):
                delta = event.angleDelta().y() or event.angleDelta().x()
                bar = self.cat_scroll.horizontalScrollBar()
                bar.setValue(bar.value() - delta)
                return True
            if (watched in (getattr(self, "recent_scroll", None),
                            getattr(self, "recent_scroll", None) and self.recent_scroll.viewport(),
                            getattr(self, "recent_frame", None)) or
                (hasattr(self, "recent_frame") and self.recent_frame.isAncestorOf(watched))):
                delta = event.angleDelta().y() or event.angleDelta().x()
                bar = self.recent_scroll.horizontalScrollBar()
                bar.setValue(bar.value() - delta)
                return True
        if watched == self.search_input and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                if self.search_input.text():
                    self.search_input.clear()
                    return True
        return super().eventFilter(watched, event)


    def _on_theme_changed(self, theme_name: str):
        self._update_logo()
        self._apply_cat_nav_style()
        self._rebuild_recent_bar()
        self._rebuild_category_buttons()
        self.update()

    def _on_settings_changed(self):
        """当全局设置变更（如插件启用/停用、卡片尺寸间距、最近访问变动）时立即刷新"""
        self._do_refresh_on_settings_changed()

    def _do_refresh_on_settings_changed(self):
        card_w, card_h, card_spacing = self._get_card_dimensions()
        self.grid_layout.setSpacing(card_spacing)
        for card in self.card_widgets:
            card.update_card_size(card_w, card_h)
        self._apply_cat_nav_style()
        self._rebuild_recent_bar()
        self._rebuild_category_buttons()
        self._filter_and_render_cards()

    def _on_card_context_menu(self, plugin_id: str, global_pos):
        """处理卡片右键菜单呼出：独立窗口打开、分组管理、系统托盘、Setup导出、删除隐藏"""
        plugin = next((p for p in self.plugins if p.id == plugin_id), None)
        if not plugin:
            return

        menu = QMenu(self)

        # 1. 以独立窗口打开
        act_standalone = menu.addAction(get_icon("window", size=15), "以独立窗口打开")
        act_standalone.triggered.connect(lambda: self.open_standalone_requested.emit(plugin_id))

        menu.addSeparator()

        # 2. 加入分组子菜单
        menu_add_group = menu.addMenu(get_icon("folder-plus", size=15), "加入分组")
        all_custom_groups = self.config_manager.get_custom_groups()
        current_groups = self.config_manager.get_plugin_groups(plugin_id, plugin.category)
        
        # 内置分类 + 自定义分组汇总候选列表
        built_in_cats = sorted(list(set(p.category for p in self.plugins if p.category)))
        all_candidate_groups = list(dict.fromkeys(built_in_cats + all_custom_groups))

        for grp in all_candidate_groups:
            is_in = self.config_manager.is_plugin_in_group(plugin_id, grp, plugin.category)
            if is_in:
                act_grp = menu_add_group.addAction(get_icon("tag", size=14), f"{grp} (已在分组)")
                act_grp.setEnabled(False)
            else:
                act_grp = menu_add_group.addAction(get_icon("tag", size=14), grp)
                act_grp.triggered.connect(lambda ch, g=grp, pid=plugin_id, def_c=plugin.category: self._add_plugin_to_group(pid, g, def_c))

        menu_add_group.addSeparator()
        act_new_grp_and_add = menu_add_group.addAction(get_icon("plus", size=14), "新建自定义分组...")
        act_new_grp_and_add.triggered.connect(lambda ch, pid=plugin_id, def_c=plugin.category: self._prompt_new_group_for_plugin(pid, def_c))

        # 3. 踢出分组（支持移出当前分组与子菜单踢出任意所属分组）
        if self.current_category not in ("全部", "最近使用"):
            if self.config_manager.is_plugin_in_group(plugin_id, self.current_category, plugin.category):
                act_rem_cur = menu.addAction(get_icon("minus", size=15), f"从当前分组「{self.current_category}」踢出")
                act_rem_cur.triggered.connect(lambda ch, pid=plugin_id, g=self.current_category, def_c=plugin.category: self._remove_plugin_from_group(pid, g, def_c))

        if current_groups:
            menu_rem_group = menu.addMenu(get_icon("minus", size=15), "踢出分组")
            for grp in current_groups:
                act_g = menu_rem_group.addAction(get_icon("tag", size=14), f"从「{grp}」踢出")
                act_g.triggered.connect(lambda ch, g=grp, pid=plugin_id, def_c=plugin.category: self._remove_plugin_from_group(pid, g, def_c))

        # 4. 新建与管理分组
        act_manage_groups = menu.addAction(get_icon("layers", size=15), "管理自定义分组...")
        act_manage_groups.triggered.connect(self._open_group_management)

        menu.addSeparator()

        # 5. 独立显示在系统托盘
        is_in_tray = self.config_manager.is_plugin_in_tray(plugin_id)
        if is_in_tray:
            act_tray = menu.addAction(get_icon("monitor", size=15), "从系统托盘移除")
            act_tray.triggered.connect(lambda ch, p=plugin: self._toggle_tray(p, False))
        else:
            act_tray = menu.addAction(get_icon("monitor", size=15), "独立显示在系统托盘")
            act_tray.triggered.connect(lambda ch, p=plugin: self._toggle_tray(p, True))

        # 6. 导出为独立 Setup 安装包
        act_export = menu.addAction(get_icon("package", size=15), "导出为独立 Setup 安装包...")
        act_export.triggered.connect(lambda ch, pid=plugin_id: self._open_export_dialog(pid))

        menu.addSeparator()

        # 7. 删除/隐藏该插件
        act_delete = menu.addAction(get_icon("trash", size=15), "删除该插件 (可从设置重新开启)")
        act_delete.triggered.connect(lambda ch, p=plugin: self._delete_plugin_from_home(plugin))

        menu.exec(global_pos)

    def _add_plugin_to_group(self, plugin_id: str, group_name: str, default_category: Optional[str] = None):
        self.config_manager.add_plugin_to_group(plugin_id, group_name, default_category)
        self._rebuild_category_buttons()
        self._filter_and_render_cards()

    def _remove_plugin_from_group(self, plugin_id: str, group_name: str, default_category: Optional[str] = None):
        self.config_manager.remove_plugin_from_group(plugin_id, group_name, default_category)
        self._rebuild_category_buttons()
        self._filter_and_render_cards()

    def _prompt_new_group_for_plugin(self, plugin_id: str, default_category: Optional[str] = None):
        text, ok = QInputDialog.getText(self, "新建自定义分组", "请输入新分组名称:")
        if ok and text.strip():
            name = text.strip()
            if name in ("全部", "最近使用"):
                QMessageBox.warning(self, "提示", "不能使用系统保留分类名称。")
                return
            self.config_manager.add_custom_group(name)
            self.config_manager.add_plugin_to_group(plugin_id, name, default_category)
            self._rebuild_category_buttons()
            self._filter_and_render_cards()

    def _prompt_create_new_group(self):
        text, ok = QInputDialog.getText(self, "新建自定义分组", "请输入新分组名称:")
        if ok and text.strip():
            name = text.strip()
            if name in ("全部", "最近使用"):
                QMessageBox.warning(self, "提示", "不能使用系统保留分类名称。")
                return
            if name in self.config_manager.get_custom_groups():
                QMessageBox.warning(self, "提示", f"分组「{name}」已存在。")
                return
            self.config_manager.add_custom_group(name)
            self._rebuild_category_buttons()
            self._filter_and_render_cards()

    def _open_group_management(self):
        dialog = GroupManageDialog(parent=self.window())
        dialog.groups_changed.connect(lambda: (
            self._rebuild_category_buttons(),
            self._filter_and_render_cards()
        ))
        dialog.exec()

    def _on_custom_cat_context_menu(self, cat: str, global_pos):
        menu = QMenu(self)
        act_del = menu.addAction(get_icon("trash", size=14), f"删除分组「{cat}」")
        act_del.triggered.connect(lambda: self._delete_group_action(cat))
        menu.exec(global_pos)

    def _delete_group_action(self, group_name: str):
        res = QMessageBox.question(
            self,
            "确认删除分组",
            f"确定要删除自定义分组「{group_name}」吗？\n\n删除后，该分组内的插件卡片仍将保留在原有默认分类中，不会被删除。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if res == QMessageBox.Yes:
            self.config_manager.delete_custom_group(group_name)
            if self.current_category == group_name:
                self.current_category = "全部"
            self._rebuild_category_buttons()
            self._filter_and_render_cards()

    def _toggle_tray(self, plugin: PluginBase, enable: bool):
        tray_mgr = PluginTrayManager()
        if enable:
            tray_mgr.add_tray_icon(
                plugin,
                on_open_callback=lambda: self.open_plugin_requested.emit(plugin.id),
                on_settings_callback=lambda p=plugin: self._open_plugin_settings(p.id),
                on_exit_callback=lambda: tray_mgr.remove_tray_icon(plugin.id),
                on_export_callback=lambda: self._open_export_dialog(plugin.id)
            )
        else:
            tray_mgr.remove_tray_icon(plugin.id)

    def _open_plugin_settings(self, plugin_id: str):
        plugin = next((p for p in self.plugins if p.id == plugin_id), None)
        if plugin:
            from toolbox.ui.standalone_settings_dialog import StandalonePluginSettingsDialog
            dialog = StandalonePluginSettingsDialog(plugin, parent=self.window())
            dialog.exec()

    def _open_export_dialog(self, plugin_id: str):
        dialog = PluginExportDialog(target_plugin_id=plugin_id, parent=self.window())
        dialog.exec()

    def _delete_plugin_from_home(self, plugin: PluginBase):
        res = QMessageBox.question(
            self,
            "确认删除插件",
            f"确定要从首页删除/隐藏「{plugin.name}」吗？\n\n删除后该功能将不会在首页及最近使用中显示。\n您随时可以在【设置中心 -> 功能模块管理】中重新勾选开启。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if res == QMessageBox.Yes:
            self.config_manager.set_plugin_enabled(plugin.id, False)
            self._rebuild_recent_bar()
            self._rebuild_category_buttons()
            self._filter_and_render_cards()
            self.event_bus.settings_changed.emit()


