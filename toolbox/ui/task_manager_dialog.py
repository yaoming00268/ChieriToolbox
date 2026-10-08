"""
工具箱 (Toolbox) - 全局后台任务中心面板 (TaskManagerDialog)
现代化卡片式任务列表，实时跟踪与管理转码、下载、批量压缩等后台长耗时作业。
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QScrollArea, QWidget, QFrame
)
from toolbox.core.task_manager import GlobalTaskManager, TaskStatus


class TaskItemWidget(QFrame):
    """单个后台任务的可视化卡片"""
    def __init__(self, task_dict: dict, on_cancel: callable, parent=None):
        super().__init__(parent)
        self.task_id = task_dict["id"]
        self.on_cancel = on_cancel
        self.setObjectName("TaskCard")
        self.setStyleSheet("""
            #TaskCard {
                background: rgba(128, 128, 128, 0.08);
                border: 1px solid rgba(128, 128, 128, 0.18);
                border-radius: 8px;
                padding: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Header: Title + Plugin ID + Status + Cancel Btn
        top_row = QHBoxLayout()
        self.lbl_title = QLabel(task_dict["title"])
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 13px;")

        self.lbl_plugin = QLabel(f"[{task_dict['plugin_id']}]")
        self.lbl_plugin.setStyleSheet("color: #888888; font-size: 11px;")

        self.lbl_status = QLabel(task_dict["status"])
        self.lbl_status.setStyleSheet("font-size: 11px; padding: 2px 6px; border-radius: 4px;")
        self._update_status_style(task_dict["status"])

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setFixedSize(50, 24)
        self.btn_cancel.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.btn_cancel.clicked.connect(lambda: self.on_cancel(self.task_id))

        top_row.addWidget(self.lbl_title)
        top_row.addWidget(self.lbl_plugin)
        top_row.addStretch()
        top_row.addWidget(self.lbl_status)
        top_row.addWidget(self.btn_cancel)
        layout.addLayout(top_row)

        # Progress bar
        self.pbar = QProgressBar()
        self.pbar.setRange(0, task_dict.get("max_progress", 100))
        self.pbar.setValue(task_dict.get("progress", 0))
        self.pbar.setFixedHeight(8)
        self.pbar.setTextVisible(False)
        layout.addWidget(self.pbar)

        # Message
        self.lbl_msg = QLabel(task_dict.get("message", ""))
        self.lbl_msg.setStyleSheet("color: #777777; font-size: 11px;")
        layout.addWidget(self.lbl_msg)

        if task_dict["status"] in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            self.btn_cancel.setEnabled(False)

    def _update_status_style(self, status: str):
        colors = {
            TaskStatus.RUNNING: "background: #2563eb; color: white;",
            TaskStatus.QUEUED: "background: #d97706; color: white;",
            TaskStatus.COMPLETED: "background: #16a34a; color: white;",
            TaskStatus.FAILED: "background: #dc2626; color: white;",
            TaskStatus.CANCELLED: "background: #6b7280; color: white;",
        }
        self.lbl_status.setText(status.upper())
        self.lbl_status.setStyleSheet(f"font-size: 11px; padding: 2px 6px; border-radius: 4px; font-weight: bold; {colors.get(status, '')}")

    def update_data(self, task_dict: dict):
        status = task_dict.get("status", TaskStatus.QUEUED)
        self._update_status_style(status)
        self.pbar.setValue(task_dict.get("progress", 0))
        self.lbl_msg.setText(task_dict.get("message", ""))
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            self.btn_cancel.setEnabled(False)


class TaskManagerDialog(QDialog):
    """全局任务管理器窗口"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("全局后台任务中心")
        self.resize(520, 480)
        self.manager = GlobalTaskManager.instance()
        self.item_widgets = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        # Top Bar
        header = QHBoxLayout()
        self.lbl_summary = QLabel("当前后台任务: 0 活跃")
        self.lbl_summary.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.btn_clear = QPushButton("清空已结束")
        self.btn_clear.clicked.connect(self._clear_finished)

        header.addWidget(self.lbl_summary)
        header.addStretch()
        header.addWidget(self.btn_clear)
        main_layout.addLayout(header)

        # Scroll Area for Task Items
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.tasks_layout = QVBoxLayout(self.scroll_content)
        self.tasks_layout.setContentsMargins(4, 4, 4, 4)
        self.tasks_layout.setSpacing(8)
        self.tasks_layout.addStretch()
        self.scroll.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll)

        # Connect signals
        self.manager.task_added.connect(self._on_task_added)
        self.manager.task_updated.connect(self._on_task_updated)
        self.manager.task_finished.connect(self._on_task_updated)
        self.manager.tasks_cleared.connect(self._refresh_all)

        self._refresh_all()

    def _refresh_all(self):
        # Clear layout
        for w in self.item_widgets.values():
            w.setParent(None)
            w.deleteLater()
        self.item_widgets.clear()

        tasks = self.manager.get_all_tasks()
        # Sort so running/queued are on top
        tasks.sort(key=lambda x: (x["status"] in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED), -x["created_at"]))

        for t in tasks:
            self._add_task_item(t)
        self._update_summary()

    def _add_task_item(self, t: dict):
        item = TaskItemWidget(t, on_cancel=self.manager.cancel_task, parent=self.scroll_content)
        self.tasks_layout.insertWidget(self.tasks_layout.count() - 1, item)
        self.item_widgets[t["id"]] = item

    def _on_task_added(self, t: dict):
        if t["id"] not in self.item_widgets:
            item = TaskItemWidget(t, on_cancel=self.manager.cancel_task, parent=self.scroll_content)
            self.tasks_layout.insertWidget(0, item)
            self.item_widgets[t["id"]] = item
        self._update_summary()

    def _on_task_updated(self, t: dict):
        item = self.item_widgets.get(t["id"])
        if item:
            item.update_data(t)
        self._update_summary()

    def _update_summary(self):
        active = self.manager.get_active_tasks_count()
        total = len(self.manager.get_all_tasks())
        self.lbl_summary.setText(f"后台任务: {active} 进行中 / 共 {total} 项")

    def _clear_finished(self):
        self.manager.clear_finished_tasks()

    def cleanup(self):
        try:
            self.manager.task_added.disconnect(self._on_task_added)
        except Exception:
            pass
        try:
            self.manager.task_updated.disconnect(self._on_task_updated)
        except Exception:
            pass
        try:
            self.manager.task_finished.disconnect(self._on_task_updated)
        except Exception:
            pass
        try:
            self.manager.tasks_cleared.disconnect(self._refresh_all)
        except Exception:
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def reject(self):
        self.cleanup()
        super().reject()
