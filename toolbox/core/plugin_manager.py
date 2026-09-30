"""
工具箱 (Toolbox) - 插件动态管理器 (PluginManager)
负责扫描 plugins 目录、动态加载、生命周期托管与异常沙箱隔离。
"""

import importlib
import inspect
import os
import sys
import traceback
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, Signal

from .plugin_base import PluginBase


class PluginManager(QObject):
    _instance = None

    plugin_loaded = Signal(object)      # 当成功载入一个插件时
    plugin_error = Signal(str, str)     # (plugin_dir, error_message)

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        super().__init__()
        self._plugins: Dict[str, PluginBase] = {}
        self._plugin_errors: Dict[str, str] = {}
        self._active_plugin_id: Optional[str] = None

    def discover_and_load(self, plugins_package_dir: Optional[str] = None, force_reload: bool = False):
        """扫描插件目录并动态加载所有合规插件，全面适配源码运行与打包冻结运行环境"""
        from toolbox.core.paths import get_plugins_search_dirs, get_bundle_dir, get_app_root

        # 确保打包资源目录及应用程序根目录均在 sys.path 中
        bundle_dir = get_bundle_dir()
        if bundle_dir not in sys.path:
            sys.path.insert(0, bundle_dir)
        app_root = get_app_root()
        if app_root not in sys.path:
            sys.path.insert(0, app_root)

        search_dirs = [plugins_package_dir] if plugins_package_dir else get_plugins_search_dirs()

        print(f"[PluginManager] 开始在 {search_dirs} 扫描插件...")

        # 22 个核心内置插件模块列表，作为打包或动态发现时的兜底对照表
        builtin_plugin_ids = [
            "archive_manager",
            "audio_converter",
            "audio_cutter",
            "audio_recorder",
            "auto_input",
            "file_suite",
            "force_killer",
            "frame_extractor",
            "image_master",
            "media_compressor",
            "media_downloader",
            "ncm_decryptor",
            "osu_skin_studio",
            "proxy_configurator",
            "screen_capture",
            "screen_recorder",
            "system_integrator",
            "translator",
            "video_to_audio",
            "webdav_config",
            "whiteboard",
            "youtube_downloader",
        ]

        candidate_items = []
        for p_dir in search_dirs:
            if not p_dir or not os.path.exists(p_dir):
                continue
            for item in sorted(os.listdir(p_dir)):
                plugin_folder = os.path.join(p_dir, item)
                if not os.path.isdir(plugin_folder) or item.startswith("__") or item.startswith("."):
                    continue

                # 兼容源码 (.py)、预编译字节码 (.pyc) 以及纯包目录
                has_plugin = (
                    os.path.exists(os.path.join(plugin_folder, "plugin.py"))
                    or os.path.exists(os.path.join(plugin_folder, "plugin.pyc"))
                    or os.path.exists(os.path.join(plugin_folder, "__init__.py"))
                )
                if has_plugin and item not in candidate_items:
                    candidate_items.append(item)

        # 打包环境双重保险：若目录未遍历到某些内置插件（例如被打入 PYZ 单文件），将其补充载入
        from toolbox.core.paths import is_frozen
        for b_id in builtin_plugin_ids:
            if b_id not in candidate_items:
                if is_frozen() or any(os.path.isdir(os.path.join(d, b_id)) for d in search_dirs if d):
                    candidate_items.append(b_id)

        for item in candidate_items:
            module_name = f"toolbox.plugins.{item}.plugin"
            try:
                # 动态加载模块 (非显式重载时不重复 reload，保护已注册的 Qt 对象)
                if module_name in sys.modules and force_reload:
                    mod = importlib.reload(sys.modules[module_name])
                elif module_name in sys.modules:
                    mod = sys.modules[module_name]
                else:
                    mod = importlib.import_module(module_name)

                # 寻找继承自 PluginBase 的类
                found_cls = None
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (inspect.isclass(attr) and 
                            issubclass(attr, PluginBase) and 
                            attr is not PluginBase):
                        found_cls = attr
                        break

                if found_cls:
                    plugin_instance = found_cls()
                    self._plugins[plugin_instance.id] = plugin_instance
                    print(f"[PluginManager] 成功加载插件: [{plugin_instance.name}] (ID: {plugin_instance.id})")
                    self.plugin_loaded.emit(plugin_instance)
                else:
                    err = f"未在模块 [{module_name}] 中发现继承自 PluginBase 的有效类"
                    self._plugin_errors[item] = err
                    print(f"[PluginManager] 警告: {err}")
                    self.plugin_error.emit(item, err)

            except Exception as e:
                err_detail = traceback.format_exc()
                self._plugin_errors[item] = err_detail
                print(f"[PluginManager] 加载插件 [{item}] 出错: {e}\n{err_detail}")
                self.plugin_error.emit(item, str(e))

    def load_single_plugin(self, plugin_id: str, force_reload: bool = False) -> Optional[PluginBase]:
        """单插件精准加载，专用于独立插件启动引擎，跳过全量扫描与外部无关联插件探查"""
        if plugin_id in self._plugins and not force_reload:
            return self._plugins[plugin_id]

        from toolbox.core.paths import get_bundle_dir, get_app_root
        bundle_dir = get_bundle_dir()
        if bundle_dir not in sys.path:
            sys.path.insert(0, bundle_dir)
        app_root = get_app_root()
        if app_root not in sys.path:
            sys.path.insert(0, app_root)

        module_name = f"toolbox.plugins.{plugin_id}.plugin"
        try:
            if module_name in sys.modules and force_reload:
                mod = importlib.reload(sys.modules[module_name])
            elif module_name in sys.modules:
                mod = sys.modules[module_name]
            else:
                mod = importlib.import_module(module_name)

            found_cls = None
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (inspect.isclass(attr) and 
                        issubclass(attr, PluginBase) and 
                        attr is not PluginBase):
                    found_cls = attr
                    break

            if found_cls:
                plugin_instance = found_cls()
                self._plugins[plugin_instance.id] = plugin_instance
                self.plugin_loaded.emit(plugin_instance)
                return plugin_instance
        except Exception as e:
            err_detail = traceback.format_exc()
            self._plugin_errors[plugin_id] = err_detail
            print(f"[PluginManager] 加载独立插件 [{plugin_id}] 异常: {e}\n{err_detail}")
        return None

    def get_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """根据 ID 获取插件实例"""
        return self._plugins.get(plugin_id)

    def get_all_plugins(self) -> List[PluginBase]:
        """获取所有已成功加载的插件，按 sort_order 升序排序"""
        return sorted(self._plugins.values(), key=lambda p: p.sort_order)

    def get_categories(self) -> List[str]:
        """获取所有已加载插件的分类标签列表"""
        cats = set()
        for p in self._plugins.values():
            cats.add(p.category)
        return sorted(list(cats))

    def activate_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """激活指定插件，触发前一个插件的 on_deactivated 及新插件的 on_activated"""
        if self._active_plugin_id and self._active_plugin_id in self._plugins:
            try:
                self._plugins[self._active_plugin_id].on_deactivated()
            except Exception as e:
                print(f"[PluginManager] 停用插件 [{self._active_plugin_id}] 出错: {e}")

        plugin = self.get_plugin(plugin_id)
        if plugin:
            try:
                plugin.on_activated()
                self._active_plugin_id = plugin_id
            except Exception as e:
                print(f"[PluginManager] 激活插件 [{plugin_id}] 出错: {e}")
        return plugin

    def deactivate_current_plugin(self):
        """停用当前正在运行的前台插件并恢复为空闲"""
        if self._active_plugin_id and self._active_plugin_id in self._plugins:
            try:
                self._plugins[self._active_plugin_id].on_deactivated()
            except Exception as e:
                print(f"[PluginManager] 停用插件出错: {e}")
        self._active_plugin_id = None

    def get_active_plugin_id(self) -> Optional[str]:
        return self._active_plugin_id

    def cleanup_all(self):
        """清理所有插件资源"""
        self.deactivate_current_plugin()
        for p in self._plugins.values():
            try:
                p.cleanup()
            except Exception as e:
                print(f"[PluginManager] 清理插件 [{p.id}] 出错: {e}")
        self._plugins.clear()
