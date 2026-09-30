"""
工具箱 (Toolbox) - 现代化深浅主题系统 (Theme System)
支持深色模式 (Dark)、浅色模式 (Light) 与 Windows 系统主题自适应跟随 (System)。
无任何杂乱配色与丑陋 Emoji，保证高对比度、清晰字体排印与现代化交互质感。
"""

import sys
from typing import Optional
from PySide6.QtCore import Qt, QObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from toolbox.core.config_manager import ConfigManager
from toolbox.core.event_bus import EventBus

THEME_DARK = "dark"
THEME_LIGHT = "light"
THEME_SYSTEM = "system"


# -------------------------------------------------------------
# 深色主题 QSS 样式表 (Slate / Zinc 暗夜精粹)
# -------------------------------------------------------------
DARK_THEME_QSS = """
/* 全局基础重置与排版 */
QWidget {
    background-color: #12141a;
    color: #f1f5f9;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Microsoft YaHei", sans-serif;
    font-size: 13px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

/* 顶部全局导航栏 */
#topNavBar {
    background-color: #161923;
    border-bottom: 1px solid #262a38;
}

/* 主内容堆叠区 */
#mainStack {
    background-color: #12141a;
    border: none;
}

/* 面包屑与导航标签 */
QLabel#breadcrumbLabel {
    font-size: 14px;
    color: #94a3b8;
}

QLabel#breadcrumbActive {
    font-size: 14px;
    font-weight: 600;
    color: #f8fafc;
}

QLabel#breadcrumbSeparator {
    color: #64748b;
    font-size: 13px;
}

/* 导航栏应用品牌标题 */
QLabel#appBrandTitle {
    font-size: 15px;
    font-weight: bold;
    color: #38bdf8;
    letter-spacing: 0.3px;
}

/* 分类标签标题 */
QLabel#categoryTitle {
    font-size: 14px;
    font-weight: 600;
    color: #e2e8f0;
    padding-left: 2px;
}

/* 标准通用按钮 */
QPushButton {
    background-color: #1e2230;
    color: #e2e8f0;
    border: 1px solid #2e3547;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
    outline: none;
}

QPushButton:hover {
    background-color: #2a3043;
    border-color: #3e475e;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #161823;
    border-color: #242938;
}

QPushButton:disabled {
    background-color: #161822;
    color: #4b5563;
    border-color: #222633;
}

/* 主要突出按钮 (Primary) */
QPushButton#primaryBtn, QPushButton[primary="true"] {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #3b82f6;
    font-weight: 600;
}

QPushButton#primaryBtn:hover, QPushButton[primary="true"]:hover {
    background-color: #1d4ed8;
    border-color: #60a5fa;
}

QPushButton#primaryBtn:pressed, QPushButton[primary="true"]:pressed {
    background-color: #1e40af;
    border-color: #1d4ed8;
}

/* 快捷返回首页按钮 */
QPushButton#btnBackHome {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
}

QPushButton#btnBackHome:hover {
    background-color: #2563eb;
    border-color: #3b82f6;
    color: #ffffff;
}

QPushButton#btnBackHome:pressed {
    background-color: #1d4ed8;
}

/* 扁平文字/图标按钮 */
QPushButton#flatIconBtn {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 8px;
    color: #94a3b8;
}

QPushButton#flatIconBtn:hover {
    background-color: #1f2433;
    border-color: #2e3547;
    color: #f8fafc;
}

QPushButton#flatIconBtn:checked {
    background-color: #2563eb;
    border-color: #3b82f6;
    color: #ffffff;
}

/* 主题模式切换按钮组容器 */
#themeSwitchBox {
    background-color: #13151d;
    border: 1px solid #262a38;
    border-radius: 7px;
    padding: 2px;
}

QPushButton#themeSegmentBtn {
    background-color: transparent;
    border: none;
    border-radius: 5px;
    padding: 4px 9px;
    color: #94a3b8;
    font-size: 12px;
}

QPushButton#themeSegmentBtn:hover {
    color: #ffffff;
    background-color: #1f2331;
}

QPushButton#themeSegmentBtn:checked {
    background-color: #2563eb;
    color: #ffffff;
    font-weight: 600;
}

/* 常用输入框与文本域 */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QKeySequenceEdit {
    background-color: #151822;
    color: #f8fafc;
    border: 1px solid #2e3547;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 28px;
}

QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover, QKeySequenceEdit:hover {
    border-color: #3f4861;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QKeySequenceEdit:focus {
    border: 1px solid #3b82f6;
    background-color: #191c28;
}

QLineEdit:read-only, QTextEdit:read-only, QPlainTextEdit:read-only, QKeySequenceEdit:read-only {
    background-color: #13151e;
    color: #94a3b8;
}

/* 下拉菜单 (QComboBox) */
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border-left: 1px solid #2e3547;
}

QComboBox QAbstractItemView {
    background-color: #171a25;
    border: 1px solid #2e3547;
    border-radius: 6px;
    color: #f1f5f9;
    padding: 4px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

/* 分组框 (QGroupBox) */
QGroupBox {
    border: 1px solid #282d3d;
    border-radius: 8px;
    margin-top: 22px;
    padding-top: 14px;
    font-weight: 600;
    color: #60a5fa;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    background-color: #12141a;
}

/* 选项卡 (QTabWidget) */
QTabWidget::pane {
    border: 1px solid #282d3d;
    border-radius: 8px;
    background-color: #161922;
    top: -1px;
}

QTabBar::tab {
    background-color: #191c27;
    color: #94a3b8;
    border: 1px solid #282d3d;
    border-bottom: none;
    padding: 8px 18px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}

QTabBar::tab:selected {
    background-color: #161922;
    color: #38bdf8;
    border-color: #282d3d;
    border-bottom: 2px solid #38bdf8;
    font-weight: 600;
}

QTabBar::tab:hover:!selected {
    background-color: #222634;
    color: #e2e8f0;
}

/* 列表与表格 (QListWidget & QTableWidget) */
QListWidget, QTableWidget {
    background-color: #151822;
    border: 1px solid #282d3d;
    border-radius: 8px;
    color: #e2e8f0;
    gridline-color: #222634;
    outline: none;
}

QTableWidget QHeaderView::section {
    background-color: #1d212d;
    color: #60a5fa;
    padding: 7px 10px;
    border: none;
    border-right: 1px solid #282d3d;
    border-bottom: 1px solid #282d3d;
    font-weight: 600;
}

QListWidget::item, QTableWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
}

QListWidget::item:hover, QTableWidget::item:hover {
    background-color: #1f2433;
}

QListWidget::item:selected, QTableWidget::item:selected {
    background-color: #1e3a5f;
    color: #ffffff;
}

/* 进度条 (QProgressBar) */
QProgressBar {
    background-color: #1a1d28;
    border: 1px solid #282d3d;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: 600;
    font-size: 11px;
}

QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #38bdf8);
    border-radius: 5px;
}

/* 滚动条 (QScrollBar) */
QScrollBar:vertical {
    background-color: #12141a;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #2e3547;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background-color: #424c64;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #12141a;
    height: 8px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: #2e3547;
    border-radius: 4px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #424c64;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* 单选框与复选框 (QCheckBox & QRadioButton) */
QCheckBox, QRadioButton {
    color: #e2e8f0;
    spacing: 8px;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #475569;
    border-radius: 4px;
    background-color: #151822;
}

QRadioButton::indicator {
    border-radius: 8px;
}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #38bdf8;
}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #2563eb;
    border-color: #38bdf8;
}

/* 状态栏 (QStatusBar) */
QStatusBar {
    background-color: #141720;
    color: #94a3b8;
    border-top: 1px solid #202431;
    font-size: 12px;
}

/* 插件卡片样式 */
#pluginCard {
    background-color: #191c26;
    border: 1px solid #272c3b;
    border-radius: 12px;
}

#pluginCard:hover {
    background-color: #1f2331;
    border: 1px solid #38bdf8;
}

QLabel#cardTitle {
    font-size: 15px;
    font-weight: bold;
    color: #f8fafc;
    background: transparent;
}

QLabel#cardCategory {
    font-size: 11px;
    color: #60a5fa;
    background-color: #1e293b;
    border: 1px solid #2563eb;
    border-radius: 5px;
    padding: 2px 7px;
    font-weight: 500;
}

QLabel#cardDesc {
    font-size: 12px;
    color: #94a3b8;
    background: transparent;
    line-height: 1.4;
}

QLabel#cardVersion {
    font-size: 11px;
    color: #64748b;
    background: transparent;
}

QPushButton#btnOpen {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #3b82f6;
    border-radius: 6px;
    padding: 5px 12px;
    font-weight: 600;
    font-size: 12px;
}

QPushButton#btnOpen:hover {
    background-color: #1d4ed8;
    border-color: #60a5fa;
}

/* 视频与媒体下载器信息卡片 */
QLabel#mediaCoverBox {
    background-color: #181b26;
    border: 1px dashed #333a4d;
    border-radius: 8px;
    color: #64748b;
}

QLabel#mediaTitleLabel {
    font-weight: bold;
    color: #f1f5f9;
}

QLabel#mediaUpLabel {
    color: #38bdf8;
}

QLabel#mediaFfmpegStatus {
    font-size: 11px;
    color: #4ade80;
}

/* 音游皮肤名称 */
QLabel#skinNameLabel {
    font-weight: bold;
    color: #38bdf8;
}

/* 辅助与说明提示文本 */
QLabel#helperTipLabel {
    color: #94a3b8;
    font-size: 12px;
    line-height: 1.4;
}

/* 列表拖拽高亮态 */
QListWidget[dragActive="true"] {
    border: 2px dashed #3b82f6;
    background-color: #1e2438;
}
"""


# -------------------------------------------------------------
# 浅色主题 QSS 样式表 (Slate / Sky 优雅明眸)
# -------------------------------------------------------------
LIGHT_THEME_QSS = """
/* 全局基础重置与排版 */
QWidget {
    background-color: #f8fafc;
    color: #0f172a;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Microsoft YaHei", sans-serif;
    font-size: 13px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

/* 顶部全局导航栏 */
#topNavBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e2e8f0;
}

/* 主内容堆叠区 */
#mainStack {
    background-color: #f8fafc;
    border: none;
}

/* 面包屑与导航标签 */
QLabel#breadcrumbLabel {
    font-size: 14px;
    color: #64748b;
}

QLabel#breadcrumbActive {
    font-size: 14px;
    font-weight: 600;
    color: #0f172a;
}

QLabel#breadcrumbSeparator {
    color: #94a3b8;
    font-size: 13px;
}

/* 导航栏应用品牌标题 */
QLabel#appBrandTitle {
    font-size: 15px;
    font-weight: bold;
    color: #0284c7;
    letter-spacing: 0.3px;
}

/* 分类标签标题 */
QLabel#categoryTitle {
    font-size: 14px;
    font-weight: 600;
    color: #1e293b;
    padding-left: 2px;
}

/* 标准通用按钮 */
QPushButton {
    background-color: #ffffff;
    color: #1e293b;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
    outline: none;
}

QPushButton:hover {
    background-color: #f1f5f9;
    border-color: #94a3b8;
    color: #0f172a;
}

QPushButton:pressed {
    background-color: #e2e8f0;
    border-color: #64748b;
}

QPushButton:disabled {
    background-color: #f1f5f9;
    color: #94a3b8;
    border-color: #e2e8f0;
}

/* 主要突出按钮 (Primary) */
QPushButton#primaryBtn, QPushButton[primary="true"] {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #1d4ed8;
    font-weight: 600;
}

QPushButton#primaryBtn:hover, QPushButton[primary="true"]:hover {
    background-color: #1d4ed8;
    border-color: #1e40af;
}

QPushButton#primaryBtn:pressed, QPushButton[primary="true"]:pressed {
    background-color: #1e40af;
    border-color: #172554;
}

/* 快捷返回首页按钮 */
QPushButton#btnBackHome {
    background-color: #f1f5f9;
    color: #1e293b;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
}

QPushButton#btnBackHome:hover {
    background-color: #2563eb;
    border-color: #1d4ed8;
    color: #ffffff;
}

QPushButton#btnBackHome:pressed {
    background-color: #1e40af;
    color: #ffffff;
}

/* 扁平文字/图标按钮 */
QPushButton#flatIconBtn {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 8px;
    color: #64748b;
}

QPushButton#flatIconBtn:hover {
    background-color: #e2e8f0;
    border-color: #cbd5e1;
    color: #0f172a;
}

QPushButton#flatIconBtn:checked {
    background-color: #2563eb;
    border-color: #1d4ed8;
    color: #ffffff;
}

/* 主题模式切换按钮组容器 */
#themeSwitchBox {
    background-color: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    padding: 2px;
}

QPushButton#themeSegmentBtn {
    background-color: transparent;
    border: none;
    border-radius: 5px;
    padding: 4px 9px;
    color: #64748b;
    font-size: 12px;
}

QPushButton#themeSegmentBtn:hover {
    color: #0f172a;
    background-color: #e2e8f0;
}

QPushButton#themeSegmentBtn:checked {
    background-color: #ffffff;
    color: #2563eb;
    font-weight: 600;
    border: 1px solid #cbd5e1;
}

/* 常用输入框与文本域 */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QKeySequenceEdit {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 28px;
}

QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover, QKeySequenceEdit:hover {
    border-color: #94a3b8;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QKeySequenceEdit:focus {
    border: 1px solid #2563eb;
    background-color: #ffffff;
}

QLineEdit:read-only, QTextEdit:read-only, QPlainTextEdit:read-only, QKeySequenceEdit:read-only {
    background-color: #f8fafc;
    color: #64748b;
}

/* 下拉菜单 (QComboBox) */
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border-left: 1px solid #cbd5e1;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    color: #0f172a;
    padding: 4px;
    selection-background-color: #dbeafe;
    selection-color: #1e40af;
}

/* 分组框 (QGroupBox) */
QGroupBox {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    margin-top: 22px;
    padding-top: 14px;
    font-weight: 600;
    color: #2563eb;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    background-color: #f8fafc;
}

/* 选项卡 (QTabWidget) */
QTabWidget::pane {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    background-color: #ffffff;
    top: -1px;
}

QTabBar::tab {
    background-color: #f1f5f9;
    color: #64748b;
    border: 1px solid #e2e8f0;
    border-bottom: none;
    padding: 8px 18px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}

QTabBar::tab:selected {
    background-color: #ffffff;
    color: #2563eb;
    border-color: #e2e8f0;
    border-bottom: 2px solid #2563eb;
    font-weight: 600;
}

QTabBar::tab:hover:!selected {
    background-color: #e2e8f0;
    color: #1e293b;
}

/* 列表与表格 (QListWidget & QTableWidget) */
QListWidget, QTableWidget {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    color: #0f172a;
    gridline-color: #f1f5f9;
    outline: none;
}

QTableWidget QHeaderView::section {
    background-color: #f8fafc;
    color: #1e293b;
    padding: 7px 10px;
    border: none;
    border-right: 1px solid #e2e8f0;
    border-bottom: 1px solid #e2e8f0;
    font-weight: 600;
}

QListWidget::item, QTableWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
}

QListWidget::item:hover, QTableWidget::item:hover {
    background-color: #f1f5f9;
}

QListWidget::item:selected, QTableWidget::item:selected {
    background-color: #dbeafe;
    color: #1e40af;
}

/* 进度条 (QProgressBar) */
QProgressBar {
    background-color: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    text-align: center;
    color: #1e293b;
    font-weight: 600;
    font-size: 11px;
}

QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb);
    border-radius: 5px;
}

/* 滚动条 (QScrollBar) */
QScrollBar:vertical {
    background-color: #f8fafc;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #cbd5e1;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background-color: #94a3b8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #f8fafc;
    height: 8px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: #cbd5e1;
    border-radius: 4px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #94a3b8;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* 单选框与复选框 (QCheckBox & QRadioButton) */
QCheckBox, QRadioButton {
    color: #1e293b;
    spacing: 8px;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #94a3b8;
    border-radius: 4px;
    background-color: #ffffff;
}

QRadioButton::indicator {
    border-radius: 8px;
}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #2563eb;
}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #2563eb;
    border-color: #1d4ed8;
}

/* 状态栏 (QStatusBar) */
QStatusBar {
    background-color: #ffffff;
    color: #64748b;
    border-top: 1px solid #e2e8f0;
    font-size: 12px;
}

/* 插件卡片样式 */
#pluginCard {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}

#pluginCard:hover {
    background-color: #ffffff;
    border: 1px solid #2563eb;
}

QLabel#cardTitle {
    font-size: 15px;
    font-weight: bold;
    color: #0f172a;
    background: transparent;
}

QLabel#cardCategory {
    font-size: 11px;
    color: #2563eb;
    background-color: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 5px;
    padding: 2px 7px;
    font-weight: 500;
}

QLabel#cardDesc {
    font-size: 12px;
    color: #64748b;
    background: transparent;
    line-height: 1.4;
}

QLabel#cardVersion {
    font-size: 11px;
    color: #94a3b8;
    background: transparent;
}

QPushButton#btnOpen {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #1d4ed8;
    border-radius: 6px;
    padding: 5px 12px;
    font-weight: 600;
    font-size: 12px;
}

QPushButton#btnOpen:hover {
    background-color: #1d4ed8;
    border-color: #1e40af;
}

/* 视频与媒体下载器信息卡片 */
QLabel#mediaCoverBox {
    background-color: #f1f5f9;
    border: 1px dashed #cbd5e1;
    border-radius: 8px;
    color: #64748b;
}

QLabel#mediaTitleLabel {
    font-weight: bold;
    color: #0f172a;
}

QLabel#mediaUpLabel {
    color: #0284c7;
}

QLabel#mediaFfmpegStatus {
    font-size: 11px;
    color: #15803d;
}

/* 音游皮肤名称 */
QLabel#skinNameLabel {
    font-weight: bold;
    color: #0284c7;
}

/* 辅助与说明提示文本 */
QLabel#helperTipLabel {
    color: #475569;
    font-size: 12px;
    line-height: 1.4;
}

/* 列表拖拽高亮态 */
QListWidget[dragActive="true"] {
    border: 2px dashed #2563eb;
    background-color: #eff6ff;
}
"""


def detect_system_theme() -> str:
    """
    智能检测操作系统当前的深浅色主题设置。
    优先通过 Qt 6.5+ 的 QStyleHints 获取，Windows 下兼顾注册表检测兜底。
    """
    # 1. 尝试使用 Qt 官方 styleHints
    hints = QGuiApplication.styleHints()
    if hints and hasattr(hints, "colorScheme"):
        scheme = hints.colorScheme()
        if scheme == Qt.ColorScheme.Light:
            return THEME_LIGHT
        if scheme == Qt.ColorScheme.Dark:
            return THEME_DARK

    # 2. Windows 平台通过注册表 Personalize -> AppsUseLightTheme 查询
    if sys.platform == "win32":
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return THEME_LIGHT if val == 1 else THEME_DARK
        except Exception:
            pass

    return THEME_DARK


class ThemeManager(QObject):
    """
    工具箱全局主题管理器单例。
    负责管理当前配置模式 (system / dark / light)、解析实际生效主题并驱动应用样式表更新。
    """
    _instance: Optional["ThemeManager"] = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        super().__init__()
        self.config_manager = ConfigManager()
        self.event_bus = EventBus()

        self._current_mode: str = self.config_manager.get("theme", THEME_SYSTEM)
        if self._current_mode == THEME_SYSTEM:
            self._effective_theme = detect_system_theme()
        elif self._current_mode == THEME_LIGHT:
            self._effective_theme = THEME_LIGHT
        else:
            self._effective_theme = THEME_DARK

        self._app: Optional[QApplication] = None

        # 定时核验系统主题变动 (作为 Qt styleHints colorSchemeChanged 事件驱动的低频兜底)
        self._sys_check_timer = QTimer(self)
        self._sys_check_timer.setInterval(30000)
        self._sys_check_timer.timeout.connect(self.check_system_theme_update)
        if self._current_mode == THEME_SYSTEM:
            self._sys_check_timer.start()

    def setup(self, app: QApplication):
        """挂载应用实例并监听系统主题变更信号"""
        self._app = app
        hints = QGuiApplication.styleHints()
        if hints and hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._on_system_color_scheme_changed)

        # 初始应用
        self.apply_theme(self._current_mode)

    def _on_system_color_scheme_changed(self, scheme):
        """当操作系统在运行中切换深浅主题时触发"""
        self.check_system_theme_update()

    def check_system_theme_update(self):
        """主动核验系统主题并在检测到外部变更时平滑热切换"""
        if self._current_mode == THEME_SYSTEM:
            new_effective = detect_system_theme()
            if new_effective != self._effective_theme:
                self.apply_theme(THEME_SYSTEM)

    def get_mode(self) -> str:
        """获取当前配置的主题模式: system / dark / light"""
        return self._current_mode

    def get_effective_theme(self) -> str:
        """获取当前实际呈现的主题: dark / light"""
        return self._effective_theme

    def is_dark(self) -> bool:
        return self._effective_theme == THEME_DARK

    def set_mode(self, mode: str):
        """设置主题模式，持久化并立即渲染"""
        if mode not in (THEME_SYSTEM, THEME_DARK, THEME_LIGHT):
            mode = THEME_SYSTEM
        self._current_mode = mode
        self.config_manager.set("theme", mode)

        if mode == THEME_SYSTEM:
            if not self._sys_check_timer.isActive():
                self._sys_check_timer.start()
        else:
            self._sys_check_timer.stop()

        self.apply_theme(mode)

    def apply_theme(self, mode_or_theme: str):
        """根据主题模式或名称应用样式表"""
        if mode_or_theme == THEME_SYSTEM:
            effective = detect_system_theme()
        elif mode_or_theme == THEME_LIGHT:
            effective = THEME_LIGHT
        else:
            effective = THEME_DARK

        self._effective_theme = effective
        qss = LIGHT_THEME_QSS if effective == THEME_LIGHT else DARK_THEME_QSS

        target = self._app or QApplication.instance()
        if target:
            target.setStyleSheet(qss)

        # 广播主题变更事件
        self.event_bus.theme_changed.emit(effective)


def apply_theme(app_or_widget, theme_name: str = THEME_DARK):
    """
    兼容历史接口：应用主题至目标 widget 或 application。
    支持传入 'system', 'dark', 'light'。
    """
    effective = theme_name
    if theme_name == THEME_SYSTEM:
        effective = detect_system_theme()

    if effective == THEME_LIGHT:
        app_or_widget.setStyleSheet(LIGHT_THEME_QSS)
    else:
        app_or_widget.setStyleSheet(DARK_THEME_QSS)
