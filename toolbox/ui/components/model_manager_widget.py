"""
千绘莉工具箱 (Chieri Toolbox) - AI 模型轻量化管理与按需下载组件 (ModelManagerWidget & Dialog)
现代深浅响应式排版，直观展示模型体积、就绪状态、镜像源切换与流式下载进度条。
"""

import os
from typing import Optional
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QComboBox, QScrollArea, QFrame, QDialog,
    QMessageBox
)
from toolbox.core.model_manager import ModelManager, AVAILABLE_MIRRORS
from toolbox.ui.icons import get_pixmap, get_icon


class ModelItemCard(QFrame):
    download_requested = Signal(str, str)  # (model_id, mirror)
    delete_requested = Signal(str)        # (model_id)

    def __init__(self, model_info: dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.model_info = model_info
        self.model_id = model_info["id"]
        self.init_ui()

    def init_ui(self):
        self.setObjectName("modelItemCard")
        self.setStyleSheet("""
            QFrame#modelItemCard {
                background-color: var(--bg-card, rgba(30, 41, 59, 0.45));
                border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
                border-radius: 8px;
                padding: 10px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # 顶部：名称 + 分类徽章 + 就绪状态徽章
        header = QHBoxLayout()
        header.setSpacing(8)

        name_lbl = QLabel(self.model_info["name"])
        name_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: var(--text-main, #f8fafc);")
        header.addWidget(name_lbl)

        cat_badge = QLabel("超分辨率" if self.model_info["category"] == "super_resolution" else "AI音频")
        cat_badge.setStyleSheet("""
            background-color: #3b82f6; color: #ffffff;
            border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: bold;
        """)
        header.addWidget(cat_badge)

        header.addStretch()

        self.status_badge = QLabel()
        self.status_badge.setFixedHeight(20)
        header.addWidget(self.status_badge)

        layout.addLayout(header)

        # 中部：模型描述与体积
        desc_lbl = QLabel(self.model_info["description"])
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: var(--text-muted, #94a3b8); font-size: 11px;")
        layout.addWidget(desc_lbl)

        size_mb = self.model_info["size_bytes"] / (1024 * 1024)
        size_lbl = QLabel(f"预估体积: ~{size_mb:.2f} MB | 本地文件名: {self.model_info['filename']}")
        size_lbl.setStyleSheet("color: var(--text-subtle, #64748b); font-size: 10px;")
        layout.addWidget(size_lbl)

        # 进度条
        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(8)
        self.pbar.setTextVisible(False)
        self.pbar.setVisible(False)
        layout.addWidget(self.pbar)

        self.speed_lbl = QLabel()
        self.speed_lbl.setStyleSheet("font-size: 10px; color: #38bdf8;")
        self.speed_lbl.setVisible(False)
        layout.addWidget(self.speed_lbl)

        # 底部操作栏
        footer = QHBoxLayout()
        footer.setSpacing(8)

        footer.addWidget(QLabel("下载镜像:"))
        self.cb_mirror = QComboBox()
        for m_key, m_name in AVAILABLE_MIRRORS:
            self.cb_mirror.addItem(m_name, m_key)
        footer.addWidget(self.cb_mirror)

        footer.addStretch()

        self.btn_download = QPushButton("按需一键下载")
        self.btn_download.setFixedHeight(28)
        self.btn_download.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: white; border-radius: 5px;
                padding: 4px 12px; font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        self.btn_download.clicked.connect(self._on_download_clicked)
        footer.addWidget(self.btn_download)

        self.btn_delete = QPushButton("删除本地权重")
        self.btn_delete.setFixedHeight(28)
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3);
                border-radius: 5px; padding: 4px 10px; font-size: 11px;
            }
            QPushButton:hover { background-color: rgba(239, 68, 68, 0.3); }
        """)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        footer.addWidget(self.btn_delete)

        layout.addLayout(footer)
        self.update_state()

    def update_state(self):
        mm = ModelManager()
        is_ready = mm.is_model_ready(self.model_id)
        if is_ready:
            self.status_badge.setText("已就绪 (Ready)")
            self.status_badge.setStyleSheet("""
                background-color: rgba(34, 197, 94, 0.15); color: #22c55e;
                border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 4px;
                padding: 2px 8px; font-size: 10px; font-weight: bold;
            """)
            self.btn_download.setText("重新下载")
            self.btn_delete.setEnabled(True)
        else:
            self.status_badge.setText("未下载 (Not Installed)")
            self.status_badge.setStyleSheet("""
                background-color: rgba(148, 163, 184, 0.15); color: #94a3b8;
                border: 1px solid rgba(148, 163, 184, 0.3); border-radius: 4px;
                padding: 2px 8px; font-size: 10px;
            """)
            self.btn_download.setText("按需一键下载")
            self.btn_delete.setEnabled(False)

    def _on_download_clicked(self):
        mirror = self.cb_mirror.currentData()
        self.download_requested.emit(self.model_id, mirror)

    def _on_delete_clicked(self):
        self.delete_requested.emit(self.model_id)

    def set_download_progress(self, dl_bytes: int, total_bytes: int, speed: float, pct: int):
        self.pbar.setVisible(True)
        self.pbar.setValue(pct)
        self.speed_lbl.setVisible(True)
        sp_kb = speed / 1024
        dl_mb = dl_bytes / (1024 * 1024)
        tot_mb = total_bytes / (1024 * 1024)
        self.speed_lbl.setText(f"下载中: {pct}% ({dl_mb:.2f} MB / {tot_mb:.2f} MB) | 速度: {sp_kb:.1f} KB/s")
        if pct >= 100:
            self.pbar.setVisible(False)
            self.speed_lbl.setVisible(False)
            self.update_state()


class ModelManagerWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None, category_filter: Optional[str] = None):
        super().__init__(parent)
        self.category_filter = category_filter
        self.mm = ModelManager()
        self.item_cards: dict = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # 顶部提示与说明
        info_banner = QFrame()
        info_banner.setStyleSheet("""
            background-color: rgba(14, 165, 233, 0.1); border-left: 4px solid #0ea5e9;
            border-radius: 6px; padding: 10px;
        """)
        ib_layout = QVBoxLayout(info_banner)
        ib_layout.setContentsMargins(10, 8, 10, 8)
        ib_layout.setSpacing(4)

        t_lbl = QLabel("轻量化按需模型分发机制")
        t_lbl.setStyleSheet("font-weight: bold; color: #0284c7; font-size: 12px;")
        ib_layout.addWidget(t_lbl)

        d_lbl = QLabel(
            "为防止工具箱体积过度膨胀，超分与AI音频等大体量模型权重均默认不强塞入安装包。"
            "您可在此按需挑选需要的模型一键快速下载并持久化至本地。"
        )
        d_lbl.setStyleSheet("color: var(--text-muted, #94a3b8); font-size: 11px;")
        d_lbl.setWordWrap(True)
        ib_layout.addWidget(d_lbl)

        layout.addWidget(info_banner)

        # 模型列表滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        self.list_layout = QVBoxLayout(container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(10)

        models = self.mm.list_models(self.category_filter)
        for m in models:
            card = ModelItemCard(m, self)
            card.download_requested.connect(self._handle_download)
            card.delete_requested.connect(self._handle_delete)
            self.item_cards[m["id"]] = card
            self.list_layout.addWidget(card)

        self.list_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

    def refresh_states(self):
        for card in self.item_cards.values():
            card.update_state()

    def _handle_download(self, model_id: str, mirror: str):
        card = self.item_cards.get(model_id)
        if not card:
            return

        def _prog(dl, tot, sp, pct):
            card.set_download_progress(dl, tot, sp, pct)

        def _done(ok, msg):
            card.update_state()
            if ok:
                card.speed_lbl.setVisible(True)
                card.speed_lbl.setText("下载成功，模型已就绪！")
                QTimer.singleShot(2500, lambda: card.speed_lbl.setVisible(False))
            else:
                card.speed_lbl.setVisible(True)
                card.speed_lbl.setText(f"下载失败: {msg}")

        card.speed_lbl.setVisible(True)
        card.speed_lbl.setText("正在建立高速镜像连接...")
        self.mm.download_model(model_id, mirror=mirror, progress_callback=_prog, done_callback=_done)

    def _handle_delete(self, model_id: str):
        if self.mm.delete_model(model_id):
            card = self.item_cards.get(model_id)
            if card:
                card.update_state()


class ModelManagerDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, category_filter: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("AI 深度模型管理与按需下载中心")
        self.resize(680, 520)
        self.setMinimumSize(560, 420)
        layout = QVBoxLayout(self)
        self.widget = ModelManagerWidget(self, category_filter=category_filter)
        layout.addWidget(self.widget)
