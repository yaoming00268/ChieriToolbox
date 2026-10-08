"""
工具箱 (Toolbox) - 插件基类与接口契约
定义所有工具箱插件必须遵循的标准生命周期与元数据接口。
"""

import os
import inspect
from abc import abstractmethod
from typing import Optional
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QWidget


class PluginBase(QObject):
    """
    工具箱插件抽象基类。
    所有功能模块均应继承此基类并实现相关方法。
    """

    # 插件基础元数据
    id: str = "base_plugin"
    name: str = "基础插件"
    description: str = "插件基础描述"
    category: str = "未分类"
    icon: str = "tools"  # 矢量图标标识或路径 (如 tools, folder, image 等)
    version: str = "1.0.0"
    author: str = "Chieri"
    sort_order: int = 100  # 首页排序优先级（越小越靠前）
    is_builtin: bool = True  # 标识是否为内核预置插件 (False 为外部扩展插件)
    supported_inputs: list = []  # 支持接收的数据类型 (例如: ["image/*", "text/plain", "file/*"])
    supported_outputs: list = []  # 支持输出的数据类型 (例如: ["image/*", "text/plain"])

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widget: Optional[QWidget] = None
        self._is_active: bool = False
        self._plugin_dir: Optional[str] = None
        self.manifest: Optional[dict] = None

    @abstractmethod
    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        按需惰性构建插件的 GUI 主部件。
        在用户首次点击进入该插件时才会被调用，节约内存与启动耗时。
        """
        pass

    def get_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """获取已实例化的 GUI 部件；若尚未创建或底层 C++ 对象已被销毁则自动重新调用 create_widget()"""
        if self._widget is not None:
            try:
                # 探测底层 C++ 对象有效性 (若父级已被销毁导致子部件析构，将抛出 RuntimeError)
                _ = self._widget.parent()
            except RuntimeError:
                self._widget = None

        if self._widget is None:
            self._widget = self.create_widget(parent)
        elif parent is not None:
            try:
                if self._widget.parent() is None:
                    self._widget.setParent(parent)
            except RuntimeError:
                self._widget = self.create_widget(parent)
        return self._widget

    def on_activated(self):
        """
        生命周期钩子：当用户在首页点击进入该插件视图时触发。
        可用于恢复监听、刷新数据或启动专属计时器。
        """
        self._is_active = True
        if self._widget is not None:
            try:
                if hasattr(self._widget, "on_activated"):
                    self._widget.on_activated()
            except RuntimeError:
                self._widget = None
            except Exception as e:
                print(f"[Plugin {self.id}] on_activated 异常: {e}")

    def on_deactivated(self):
        """
        生命周期钩子：当用户点击返回首页或切换到其他插件时触发。
        可用于暂停系统监听、停止不必要的后台轮询等，并自动保存插件设置。
        """
        self._is_active = False
        if self._widget is not None:
            try:
                if hasattr(self._widget, "on_deactivated"):
                    self._widget.on_deactivated()
                if hasattr(self._widget, "save_settings"):
                    self._widget.save_settings()
                elif hasattr(self._widget, "save_config"):
                    self._widget.save_config()
            except RuntimeError:
                self._widget = None
            except Exception as e:
                print(f"[Plugin {self.id}] on_deactivated 异常: {e}")

    def is_active(self) -> bool:
        """返回当前插件是否处于前台激活状态"""
        return self._is_active

    def handle_initial_paths(self, paths: list):
        """
        处理外部传入的文件/文件夹或URL参数
        """
        try:
            widget = self.get_widget()
            if widget and hasattr(widget, "handle_initial_paths"):
                widget.handle_initial_paths(paths)
        except Exception as e:
            print(f"[Plugin {self.id}] 处理初始路径失败: {e}")

    def accept_pipeline_data(self, data_type: str, data: any) -> bool:
        """
        跨插件数据流转管道：接收其他插件送入的数据。
        data_type: MIME 类型，例如 "image/*", "text/plain", "file/*"
        data: 具体数据对象 (例如 PIL Image / QPixmap / str / list[str])
        """
        try:
            widget = self.get_widget()
            if widget and hasattr(widget, "accept_pipeline_data"):
                return bool(widget.accept_pipeline_data(data_type, data))
            # 兼容性回退：若传入的是文件路径或路径列表，回退调用 handle_initial_paths
            if data_type.startswith("file") or isinstance(data, (list, tuple)) or (isinstance(data, str) and os.path.exists(data)):
                paths = data if isinstance(data, list) else [data]
                self.handle_initial_paths(paths)
                return True
        except Exception as e:
            print(f"[Plugin {self.id}] 管道数据接收失败: {e}")
        return False

    def cleanup(self):
        """
        生命周期钩子：当工具箱退出或插件被卸载时调用，用于释放持久句柄与资源。
        """
        self._is_active = False
        if self._widget is not None:
            if hasattr(self._widget, "save_settings"):
                try:
                    self._widget.save_settings()
                except Exception:
                    pass
            elif hasattr(self._widget, "save_config"):
                try:
                    self._widget.save_config()
                except Exception:
                    pass
            if hasattr(self._widget, "cleanup"):
                try:
                    self._widget.cleanup()
                except Exception:
                    pass
            # 优雅终止可能仍在执行的 QThread 子线程，杜绝 QThread: Destroyed while thread is still running 崩溃
            try:
                from PySide6.QtCore import QThread
                for th in self._widget.findChildren(QThread):
                    try:
                        if th.isRunning():
                            th.quit()
                            if not th.wait(300):
                                th.terminate()
                                th.wait(100)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                self._widget.setParent(None)
                self._widget.deleteLater()
            except (RuntimeError, Exception):
                pass
            self._widget = None

    def teardown(self):
        """
        生命周期钩子：当插件被动态热卸载、停用或物理删除时安全释放资源。
        释放 UI 控件、断开 Qt 信号槽、终止工作线程。
        """
        self.cleanup()

    def get_file_size(self) -> int:
        """计算插件所在的目录磁盘占用总大小 (字节数)"""
        p_dir = self.get_plugin_dir()
        if not p_dir or not os.path.exists(p_dir):
            return 0
        total_size = 0
        try:
            for root, _, files in os.walk(p_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    if os.path.isfile(fp):
                        total_size += os.path.getsize(fp)
        except Exception:
            pass
        return total_size

    def get_manifest(self) -> dict:
        """获取或生成插件标准 manifest 元数据字典"""
        if self.manifest and isinstance(self.manifest, dict):
            return dict(self.manifest)
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "category": self.category,
            "description": self.description,
            "icon": self.icon,
            "sort_order": self.sort_order,
            "is_builtin": self.is_builtin,
            "size_bytes": self.get_file_size(),
        }

    def load_config(self) -> dict:
        """从全局配置管理器读取该插件专属配置参数"""
        from toolbox.core.config_manager import ConfigManager
        return ConfigManager().get_plugin_config(self.id, {})

    def save_config(self, config: dict):
        """将该插件专属配置参数保存至全局配置"""
        from toolbox.core.config_manager import ConfigManager
        ConfigManager().set_plugin_config(self.id, config)

    def get_quick_actions(self, window=None) -> list:
        """
        返回系统托盘快捷栏调用的动作定义列表。
        每个元素为字典:
        {
            "id": str,
            "title": str,
            "icon": str,
            "callback": Callable[[], None]
        }
        子类插件可重载此方法提供专属快捷操作。
        """
        return []

    def get_plugin_dir(self) -> str:
        """获取当前插件所在的根目录"""
        if getattr(self, "_plugin_dir", None) and os.path.isdir(self._plugin_dir):
            return self._plugin_dir
        mod = inspect.getmodule(self.__class__)
        if mod and hasattr(mod, "__file__") and mod.__file__:
            return os.path.dirname(os.path.abspath(mod.__file__))
        from toolbox.core.paths import get_app_root
        return os.path.join(get_app_root(), "toolbox", "plugins", self.id)

    def get_icon_path(self) -> str:
        """获取该插件专属的独立图标绝对路径 (优先返回 PNG，兼容 SVG/ICO)"""
        p_dir = self.get_plugin_dir()
        p_png = os.path.join(p_dir, "icon.png")
        if os.path.isfile(p_png):
            return p_png
        for ext in ("icon.svg", "icon.ico"):
            candidate = os.path.join(p_dir, ext)
            if os.path.isfile(candidate):
                return candidate
        from toolbox.ui.icons import ensure_plugin_icons
        ensure_plugin_icons(self.id, p_dir)
        if os.path.isfile(p_png):
            return p_png
        from toolbox.core.paths import get_app_root
        return os.path.join(get_app_root(), "app_icon.png")

    def get_ico_path(self) -> str:
        """获取该插件专属的独立多尺寸 ICO 图标绝对路径 (含 16x16 至 256x256 mipmaps)"""
        p = os.path.join(self.get_plugin_dir(), "icon.ico")
        if os.path.isfile(p):
            return p
        from toolbox.ui.icons import ensure_plugin_icons
        ensure_plugin_icons(self.id, self.get_plugin_dir())
        if os.path.isfile(p):
            return p
        from toolbox.core.paths import get_app_root
        return os.path.join(get_app_root(), "app_icon.ico")

    def get_icon(self, size: int = 24):
        """获取该插件专属的 QIcon 图标"""
        from toolbox.ui.icons import get_plugin_icon
        return get_plugin_icon(self.id, size=size, plugin_dir=self.get_plugin_dir())



