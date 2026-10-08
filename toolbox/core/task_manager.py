"""
工具箱 (Toolbox) - 全局后台任务中心 (Global Task Manager)
提供统一并发调度、限流保护、取消控制、状态监听与内存自平衡。
避免多插件并发消耗过度 CPU/RAM 导致系统卡死。
"""

import time
import uuid
import threading
from typing import Dict, List, Optional, Callable, Any
from PySide6.QtCore import QObject, Signal, QThreadPool, QRunnable, Slot


class TaskStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskInfo:
    def __init__(self, task_id: str, title: str, plugin_id: str = "general", max_progress: int = 100):
        self.id = task_id
        self.title = title
        self.plugin_id = plugin_id
        self.status = TaskStatus.QUEUED
        self.progress = 0
        self.max_progress = max_progress
        self.message = "等待执行..."
        self.error: Optional[str] = None
        self.created_at = time.time()
        self.updated_at = time.time()
        self.is_cancelled = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "plugin_id": self.plugin_id,
            "status": self.status,
            "progress": self.progress,
            "max_progress": self.max_progress,
            "message": self.message,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_cancelled": self.is_cancelled,
        }


class ManagedTaskRunnable(QRunnable):
    """可取消并向全局任务中心回报进度的轻量 QRunnable"""
    def __init__(self, task_id: str, fn: Callable, args: tuple = (), kwargs: dict = None):
        super().__init__()
        self.task_id = task_id
        self.fn = fn
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        manager = GlobalTaskManager.instance()
        task = manager.get_task(self.task_id)
        if not task or task.is_cancelled:
            if task and task.status != TaskStatus.CANCELLED:
                manager.update_status(self.task_id, TaskStatus.CANCELLED, "任务已取消")
            return

        manager.update_status(self.task_id, TaskStatus.RUNNING, "正在执行...")

        def progress_callback(progress: int, message: str = ""):
            manager.update_progress(self.task_id, progress, message)

        def is_cancelled() -> bool:
            t = manager.get_task(self.task_id)
            return t.is_cancelled if t else True

        try:
            import inspect
            sig = inspect.signature(self.fn)
            params = sig.parameters
            supports_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        except Exception:
            params = {}
            supports_kwargs = False

        call_kwargs = dict(self.kwargs)
        if supports_kwargs or "progress_cb" in params:
            call_kwargs["progress_cb"] = progress_callback
        if supports_kwargs or "cancel_check" in params:
            call_kwargs["cancel_check"] = is_cancelled

        try:
            # 执行业务逻辑
            result = self.fn(*self.args, **call_kwargs)
            if is_cancelled():
                manager.update_status(self.task_id, TaskStatus.CANCELLED, "任务已取消")
            else:
                manager.update_status(self.task_id, TaskStatus.COMPLETED, "执行成功")
        except Exception as e:
            if is_cancelled():
                manager.update_status(self.task_id, TaskStatus.CANCELLED, "任务已取消")
            else:
                manager.set_error(self.task_id, str(e))


class GlobalTaskManager(QObject):
    """全局后台任务调度中心单例"""
    _instance: Optional["GlobalTaskManager"] = None
    _lock = threading.Lock()

    task_added = Signal(dict)
    task_updated = Signal(dict)
    task_finished = Signal(dict)
    tasks_cleared = Signal()

    def __init__(self, max_concurrency: int = 3, max_history: int = 100):
        super().__init__()
        self._max_concurrency = max_concurrency
        self._max_history = max_history
        self._tasks: Dict[str, TaskInfo] = {}
        self._tasks_lock = threading.RLock()
        self._thread_pool = QThreadPool.globalInstance()
        # 保护并发上限，防止内存跑满或死机
        if self._thread_pool.maxThreadCount() > max_concurrency:
            self._thread_pool.setMaxThreadCount(max(2, max_concurrency))

    @classmethod
    def instance(cls) -> "GlobalTaskManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """测试隔离与重置"""
        with cls._lock:
            if cls._instance:
                cls._instance._tasks.clear()
            cls._instance = None

    def submit_task(
        self,
        title: str,
        fn: Callable,
        plugin_id: str = "general",
        args: tuple = (),
        kwargs: dict = None,
        max_progress: int = 100
    ) -> str:
        """提交新的后台异步任务"""
        task_id = str(uuid.uuid4())[:8]
        task = TaskInfo(task_id, title, plugin_id=plugin_id, max_progress=max_progress)
        with self._tasks_lock:
            self._tasks[task_id] = task
            # 清理超额的旧历史记录，保持内存精简
            self._prune_history()

        self.task_added.emit(task.to_dict())

        runnable = ManagedTaskRunnable(task_id, fn, args=args, kwargs=kwargs)
        self._thread_pool.start(runnable)
        return task_id

    def register_manual_task(self, title: str, plugin_id: str = "general", max_progress: int = 100) -> str:
        """注册由调用方自行控制进度的手动任务句柄"""
        task_id = str(uuid.uuid4())[:8]
        task = TaskInfo(task_id, title, plugin_id=plugin_id, max_progress=max_progress)
        with self._tasks_lock:
            self._tasks[task_id] = task
            self._prune_history()
        self.task_added.emit(task.to_dict())
        return task_id

    def update_progress(self, task_id: str, progress: int, message: str = ""):
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.progress = max(0, min(progress, task.max_progress))
            if message:
                task.message = message
            task.updated_at = time.time()
            d = task.to_dict()
        self.task_updated.emit(d)

    def update_status(self, task_id: str, status: str, message: str = ""):
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.status = status
            if message:
                task.message = message
            task.updated_at = time.time()
            d = task.to_dict()
        self.task_updated.emit(d)
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            self.task_finished.emit(d)

    def set_error(self, task_id: str, error_msg: str):
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.status = TaskStatus.FAILED
            task.error = error_msg
            task.message = f"执行失败: {error_msg}"
            task.updated_at = time.time()
            d = task.to_dict()
        self.task_updated.emit(d)
        self.task_finished.emit(d)

    def cancel_task(self, task_id: str):
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.is_cancelled = True
            is_queued = (task.status == TaskStatus.QUEUED)
            if not is_queued:
                task.message = "正在中断取消..."
            d = task.to_dict()
        if is_queued:
            self.update_status(task_id, TaskStatus.CANCELLED, "在排队队列中取消")
        else:
            self.task_updated.emit(d)

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        with self._tasks_lock:
            return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[dict]:
        with self._tasks_lock:
            return [t.to_dict() for t in self._tasks.values()]

    def get_active_tasks_count(self) -> int:
        with self._tasks_lock:
            return sum(1 for t in self._tasks.values() if t.status in (TaskStatus.QUEUED, TaskStatus.RUNNING))

    def clear_finished_tasks(self):
        with self._tasks_lock:
            finished_ids = [k for k, t in self._tasks.items() if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)]
            for fid in finished_ids:
                self._tasks.pop(fid, None)
        self.tasks_cleared.emit()

    def _prune_history(self):
        with self._tasks_lock:
            if len(self._tasks) <= self._max_history:
                return
            # 移除最早完成的任务
            finished = [t for t in list(self._tasks.values()) if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)]
            finished.sort(key=lambda x: x.created_at)
            remove_count = len(self._tasks) - self._max_history
            for t in finished[:remove_count]:
                self._tasks.pop(t.id, None)
