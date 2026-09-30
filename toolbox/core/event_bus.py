"""
工具箱 (Toolbox) - 事件总线 (EventBus)
支持跨组件、跨插件的轻量级发布/订阅机制。
"""

import inspect
import weakref
from typing import Callable, Dict, List, Any
from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    _instance = None

    # 定义常用通用信号
    navigate_home = Signal()                        # 触发返回首页
    navigate_to_plugin = Signal(str)               # 触发导航至特定插件 (plugin_id)
    show_toast = Signal(str, str)                  # 显示通知 (level: info/success/warning/error, message)
    theme_changed = Signal(str)                    # 主题切换 (dark/light)
    status_message = Signal(str)                   # 状态栏文本变化
    settings_changed = Signal()                    # 全局设置项变更通知 (显隐、透明度、多开等)

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        super().__init__()
        self._custom_listeners: Dict[str, List[Any]] = {}

    def subscribe(self, event_name: str, callback: Callable):
        """订阅自定义事件（支持 WeakMethod 弱引用自动注销防内存滞留）"""
        if inspect.ismethod(callback):
            ref = weakref.WeakMethod(callback)
        else:
            try:
                ref = weakref.ref(callback)
            except TypeError:
                ref = lambda cb=callback: cb

        listeners = self._custom_listeners.setdefault(event_name, [])
        for existing in listeners:
            if existing() == callback:
                return
        listeners.append(ref)

    def unsubscribe(self, event_name: str, callback: Callable):
        """取消订阅自定义事件"""
        if event_name in self._custom_listeners:
            self._custom_listeners[event_name] = [
                ref for ref in self._custom_listeners[event_name]
                if ref() is not None and ref() != callback
            ]

    def publish(self, event_name: str, *args, **kwargs):
        """发布自定义事件（自动清理已失效的弱引用）"""
        listeners = self._custom_listeners.get(event_name, [])
        active_listeners = []
        for ref in listeners:
            cb = ref()
            if cb is not None:
                active_listeners.append(ref)
                try:
                    cb(*args, **kwargs)
                except Exception as e:
                    print(f"[EventBus] 事件处理异常 [{event_name}]: {e}")
        self._custom_listeners[event_name] = active_listeners
