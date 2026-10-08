"""
工具箱 (Toolbox) - 插件动态管理器 (PluginManager)
负责插件全生命周期托管：解耦式多目录扫描、动态热加载、启停切换、安全热卸载、
物理删除释放磁盘空间、离线包 (.cpk/.zip) 安全导入安装与 ZipSlip 路径穿越防御。
"""

import gc
import importlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import sys
import traceback
import types
import zipfile
from typing import Dict, List, Optional, Any
from PySide6.QtCore import QObject, Signal

from .plugin_base import PluginBase


class PluginManager(QObject):
    _instance = None

    # 生命周期信号
    plugin_loaded = Signal(object)          # 插件成功加载到内存 (PluginBase)
    plugin_unloaded = Signal(str)           # 插件从内存热卸载 (plugin_id)
    plugin_enabled = Signal(object)         # 插件被用户启用 (PluginBase)
    plugin_disabled = Signal(str)           # 插件被用户停用 (plugin_id)
    plugin_installed = Signal(object)       # 新插件包导入安装成功 (PluginBase)
    plugin_uninstalled = Signal(str)        # 插件被卸载物理删除 (plugin_id)
    plugin_error = Signal(str, str)         # 发生异常 (plugin_id_or_folder, error_message)

    # 22 个核心内置插件模块列表
    BUILTIN_PLUGIN_IDS = [
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
        "quick_launcher",
        "clipboard_manager",
        "port_network_sentinel",
        "watermark_studio",
        "json_diff_studio",
        "env_var_switcher",
    ]

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """重置单例状态（主要用于单元测试完全隔离）"""
        if cls._instance:
            try:
                cls._instance.cleanup_all()
            except Exception:
                pass
            cls._instance = None

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        super().__init__()
        # 内存中已加载的活动插件实例: plugin_id -> PluginBase
        self._plugins: Dict[str, PluginBase] = {}
        # 磁盘上已探测到的所有插件元数据登记: plugin_id -> dict
        self._available_plugins: Dict[str, Dict[str, Any]] = {}
        # 外部独立插件加载的 module 命名空间映射: plugin_id -> [module_name, ...]
        self._plugin_module_names: Dict[str, List[str]] = {}
        # 错误日志登记: item -> error_detail
        self._plugin_errors: Dict[str, str] = {}
        self._active_plugin_id: Optional[str] = None

    def discover_and_load(
        self,
        plugins_package_dir: Optional[str] = None,
        force_reload: bool = False,
        load_disabled: bool = False
    ):
        """
        全量扫描插件目录并动态加载合规插件。
        兼容内置插件目录与外部扩展插件目录（便携版 plugins_data 与安装版 %APPDATA%/ChieriToolbox/plugins）。
        """
        from toolbox.core.paths import get_plugins_search_dirs, get_bundle_dir, get_app_root
        from toolbox.core.config_manager import ConfigManager

        bundle_dir = get_bundle_dir()
        if bundle_dir not in sys.path:
            sys.path.insert(0, bundle_dir)
        app_root = get_app_root()
        if app_root not in sys.path:
            sys.path.insert(0, app_root)

        search_dirs = [plugins_package_dir] if plugins_package_dir else get_plugins_search_dirs()
        cfg = ConfigManager()
        disabled_set = set(cfg.get_disabled_plugins())

        print(f"[PluginManager] 开始在 {search_dirs} 扫描插件...")

        # 1. 扫描所有目录下的插件文件夹
        candidate_entries = []  # list of (item_name, full_folder_path, is_builtin)

        for p_dir in search_dirs:
            if not p_dir or not os.path.exists(p_dir):
                continue
            try:
                sub_items = sorted(os.listdir(p_dir))
            except Exception as e:
                print(f"[PluginManager] 读取插件目录 [{p_dir}] 失败: {e}")
                continue

            for item in sub_items:
                plugin_folder = os.path.join(p_dir, item)
                if not os.path.isdir(plugin_folder) or item.startswith("__") or item.startswith("."):
                    continue

                # 识别是否包含插件入口文件或 manifest
                has_manifest = (
                    os.path.isfile(os.path.join(plugin_folder, "manifest.json"))
                    or os.path.isfile(os.path.join(plugin_folder, "plugin.json"))
                )
                has_code = (
                    os.path.isfile(os.path.join(plugin_folder, "plugin.py"))
                    or os.path.isfile(os.path.join(plugin_folder, "plugin.pyc"))
                    or os.path.isfile(os.path.join(plugin_folder, "main.py"))
                    or os.path.isfile(os.path.join(plugin_folder, "__init__.py"))
                )

                if has_manifest or has_code:
                    # 判断是否属于内置插件
                    builtin_roots = [
                        os.path.normpath(os.path.join(get_bundle_dir(), "toolbox", "plugins")),
                        os.path.normpath(os.path.join(get_app_root(), "toolbox", "plugins")),
                        os.path.normpath(os.path.join(get_bundle_dir(), "_internal", "toolbox", "plugins")),
                        os.path.normpath(os.path.join(get_app_root(), "_internal", "toolbox", "plugins")),
                    ]
                    norm_folder = os.path.normpath(plugin_folder)
                    is_in_builtin = any(
                        norm_folder.startswith(b_root + os.sep) or norm_folder == b_root
                        for b_root in builtin_roots
                    )
                    is_builtin = item in self.BUILTIN_PLUGIN_IDS and is_in_builtin
                    # 避免重复登记
                    if not any(entry[0] == item for entry in candidate_entries):
                        candidate_entries.append((item, plugin_folder, is_builtin))

        # 2. 打包环境双重兜底保险：若目录未遍历到某些内置插件（例如被打入 PYZ），补充载入
        from toolbox.core.paths import is_frozen
        for b_id in self.BUILTIN_PLUGIN_IDS:
            if not any(entry[0] == b_id for entry in candidate_entries):
                if is_frozen() or any(os.path.isdir(os.path.join(d, b_id)) for d in search_dirs if d):
                    candidate_entries.append((b_id, "", True))

        # 3. 遍历候选插件并执行注册与条件加载
        for item, folder, is_builtin in candidate_entries:
            # 读取 manifest 元数据 (若有)
            manifest = self._read_manifest(folder) if folder else {}
            plugin_id = manifest.get("id", item)
            size_bytes = self._calc_folder_size(folder) if folder else 0

            # 记录到所有可用插件索引字典
            self._available_plugins[plugin_id] = {
                "id": plugin_id,
                "name": manifest.get("name", item),
                "version": manifest.get("version", "1.0.0"),
                "author": manifest.get("author", "Chieri"),
                "category": manifest.get("category", "未分类"),
                "description": manifest.get("description", ""),
                "icon": manifest.get("icon", "tools"),
                "sort_order": manifest.get("sort_order", 100),
                "dir": folder,
                "is_builtin": is_builtin,
                "size_bytes": size_bytes,
                "manifest": manifest,
            }

            # 启停状态检查：如果被禁用且不需要强制全量加载，则保持未装载状态，不常驻内存
            is_enabled = plugin_id not in disabled_set
            if not is_enabled and not load_disabled:
                # 处于禁用状态，跳过加载
                continue

            # 执行动态加载
            if is_builtin:
                self._load_builtin_plugin(item, folder, force_reload=force_reload)
            else:
                self._load_external_plugin_dir(folder, force_reload=force_reload)

    def _read_manifest(self, folder: str) -> dict:
        """从插件目录读取 manifest.json 或 plugin.json 元数据"""
        if not folder or not os.path.isdir(folder):
            return {}
        for fname in ("manifest.json", "plugin.json"):
            fpath = os.path.join(folder, fname)
            if os.path.isfile(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    print(f"[PluginManager] 解析 {fpath} 失败: {e}")
        return {}

    def _calc_folder_size(self, folder: str) -> int:
        """计算插件文件夹的磁盘占用字节数"""
        if not folder or not os.path.isdir(folder):
            return 0
        total = 0
        try:
            for root, _, files in os.walk(folder):
                for f in files:
                    fp = os.path.join(root, f)
                    if os.path.isfile(fp):
                        total += os.path.getsize(fp)
        except Exception:
            pass
        return total

    def _load_builtin_plugin(self, item: str, folder: str = "", force_reload: bool = False) -> Optional[PluginBase]:
        """加载工程内置核心插件（保留原生包路径契约，不预导入 ui.py）"""
        module_name = f"toolbox.plugins.{item}.plugin"
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
                plugin_instance.is_builtin = True
                if folder:
                    plugin_instance._plugin_dir = folder
                self._plugins[plugin_instance.id] = plugin_instance
                self._plugin_module_names[plugin_instance.id] = [module_name]

                # 同步更新可用列表元数据
                if plugin_instance.id in self._available_plugins:
                    self._available_plugins[plugin_instance.id].update({
                        "name": plugin_instance.name,
                        "version": plugin_instance.version,
                        "category": plugin_instance.category,
                        "description": plugin_instance.description,
                        "sort_order": plugin_instance.sort_order,
                    })
                else:
                    self._available_plugins[plugin_instance.id] = {
                        "id": plugin_instance.id,
                        "name": plugin_instance.name,
                        "version": plugin_instance.version,
                        "author": plugin_instance.author,
                        "category": plugin_instance.category,
                        "description": plugin_instance.description,
                        "icon": plugin_instance.icon,
                        "sort_order": plugin_instance.sort_order,
                        "dir": folder or plugin_instance.get_plugin_dir(),
                        "is_builtin": True,
                        "size_bytes": self._calc_folder_size(folder) if folder else 0,
                        "manifest": self._read_manifest(folder) if folder else {},
                    }

                self.plugin_loaded.emit(plugin_instance)
                return plugin_instance
            else:
                err = f"未在模块 [{module_name}] 中发现继承自 PluginBase 的有效类"
                self._plugin_errors[item] = err
                self.plugin_error.emit(item, err)
        except Exception as e:
            err_detail = traceback.format_exc()
            self._plugin_errors[item] = err_detail
            print(f"[PluginManager] 加载内置插件 [{item}] 出错: {e}\n{err_detail}")
            self.plugin_error.emit(item, str(e))
        return None

    def _load_external_plugin_dir(self, folder: str, force_reload: bool = False) -> Optional[PluginBase]:
        """
        通过 importlib.util.spec_from_file_location 动态热加载外部解耦插件包。
        建立独立隔离命名空间 chieri_plugin_<id>，注入 sys.modules。
        """
        if not folder or not os.path.isdir(folder):
            return None

        manifest = self._read_manifest(folder)
        plugin_id = manifest.get("id") or os.path.basename(folder)

        # 确定入口代码文件并严格校验路径穿越防御
        entry_candidates = []
        if manifest.get("entry_point"):
            entry_candidates.append(manifest["entry_point"])
        entry_candidates.extend(["plugin.py", "main.py", "__init__.py"])

        entry_path = None
        folder_real = os.path.realpath(folder)
        for cand in entry_candidates:
            p = os.path.join(folder, cand)
            p_real = os.path.realpath(p)
            # 安全防线：禁止通过 manifest.json entry_point 穿越逃逸出插件目录
            if not (p_real.startswith(folder_real + os.sep) or p_real == folder_real):
                continue
            if os.path.isfile(p_real):
                entry_path = p_real
                break

        if not entry_path:
            err = f"插件目录 [{folder}] 未包含有效的入口执行文件 (plugin.py / main.py)"
            self._plugin_errors[plugin_id] = err
            self.plugin_error.emit(plugin_id, err)
            return None

        pkg_name = f"chieri_plugin_{plugin_id}"
        entry_mod_name = f"{pkg_name}.main_entry"

        # 确保 folder 处于 sys.path 中以支持插件自身模块的绝对与相对导入
        if folder not in sys.path:
            sys.path.insert(0, folder)

        try:
            # 1. 建立虚拟包模块，允许外部插件内部执行相对引用 (from .ui import ...)
            if pkg_name not in sys.modules or force_reload:
                pkg_mod = types.ModuleType(pkg_name)
                pkg_mod.__path__ = [folder]
                init_p = os.path.join(folder, "__init__.py")
                pkg_mod.__file__ = init_p if os.path.isfile(init_p) else entry_path
                sys.modules[pkg_name] = pkg_mod

            # 2. 动态载入入口执行模块
            spec = importlib.util.spec_from_file_location(entry_mod_name, entry_path)
            if not spec or not spec.loader:
                raise ImportError(f"无法为入口脚本 [{entry_path}] 创建加载规范 (Spec)")

            mod = importlib.util.module_from_spec(spec)
            mod.__package__ = pkg_name
            sys.modules[entry_mod_name] = mod

            # 执行模块载入
            spec.loader.exec_module(mod)

            # 3. 寻找继承自 PluginBase 的类
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
                plugin_instance.is_builtin = False
                plugin_instance._plugin_dir = folder
                plugin_instance.manifest = manifest

                # 若 manifest 中覆盖了元数据，以 manifest 声明为准
                if manifest:
                    for k in ("name", "version", "author", "category", "description", "icon", "sort_order"):
                        if k in manifest:
                            setattr(plugin_instance, k, manifest[k])

                self._plugins[plugin_instance.id] = plugin_instance
                self._plugin_module_names[plugin_instance.id] = [pkg_name, entry_mod_name]

                # 登记到可用列表中
                self._available_plugins[plugin_instance.id] = {
                    "id": plugin_instance.id,
                    "name": plugin_instance.name,
                    "version": plugin_instance.version,
                    "author": plugin_instance.author,
                    "category": plugin_instance.category,
                    "description": plugin_instance.description,
                    "icon": plugin_instance.icon,
                    "sort_order": plugin_instance.sort_order,
                    "dir": folder,
                    "is_builtin": False,
                    "size_bytes": self._calc_folder_size(folder),
                    "manifest": manifest,
                }

                print(f"[PluginManager] 动态成功载入外部插件: [{plugin_instance.name}] (ID: {plugin_instance.id})")
                self.plugin_loaded.emit(plugin_instance)
                return plugin_instance
            else:
                # 模块未包含有效类时，清退残留污染命名空间
                for mod_k in [k for k in list(sys.modules.keys()) if k == pkg_name or k.startswith(f"{pkg_name}.")]:
                    sys.modules.pop(mod_k, None)
                err = f"未在外部插件入口 [{entry_path}] 中发现继承自 PluginBase 的有效类"
                self._plugin_errors[plugin_id] = err
                self.plugin_error.emit(plugin_id, err)
        except Exception as e:
            # 异常时完全清理该插件的模块命名空间，杜绝污染
            for mod_k in [k for k in list(sys.modules.keys()) if k == pkg_name or k.startswith(f"{pkg_name}.")]:
                sys.modules.pop(mod_k, None)
            err_detail = traceback.format_exc()
            self._plugin_errors[plugin_id] = err_detail
            print(f"[PluginManager] 动态加载外部插件 [{plugin_id}] 发生异常: {e}\n{err_detail}")
            self.plugin_error.emit(plugin_id, str(e))
        return None

    def load_external_plugin(self, plugin_dir: str, force_reload: bool = False) -> Optional[PluginBase]:
        """公开接口：动态热载入指定外部目录的插件包"""
        return self._load_external_plugin_dir(plugin_dir, force_reload=force_reload)

    def load_single_plugin(self, plugin_id: str, force_reload: bool = False) -> Optional[PluginBase]:
        """单插件精准加载，专用于独立插件启动引擎或按需激活"""
        if plugin_id in self._plugins and not force_reload:
            return self._plugins[plugin_id]

        # 检查是否为外部插件
        if plugin_id in self._available_plugins:
            record = self._available_plugins[plugin_id]
            if not record.get("is_builtin") and record.get("dir"):
                return self._load_external_plugin_dir(record["dir"], force_reload=force_reload)

        # 尝试作为内置插件加载
        from toolbox.core.paths import get_bundle_dir, get_app_root
        bundle_dir = get_bundle_dir()
        if bundle_dir not in sys.path:
            sys.path.insert(0, bundle_dir)
        app_root = get_app_root()
        if app_root not in sys.path:
            sys.path.insert(0, app_root)

        folder = ""
        from toolbox.core.paths import get_plugins_search_dirs
        for d in get_plugins_search_dirs():
            cand = os.path.join(d, plugin_id)
            if os.path.isdir(cand):
                folder = cand
                break

        return self._load_builtin_plugin(plugin_id, folder=folder, force_reload=force_reload)

    def enable_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """
        动态启用插件：
        1. 在配置持久化中标记为已启用；
        2. 若尚未载入内存，动态将其载入并建立 UI 与路由；
        3. 触发 plugin_enabled 信号。
        """
        from toolbox.core.config_manager import ConfigManager
        ConfigManager().set_plugin_enabled(plugin_id, True)

        plugin = self.get_plugin(plugin_id)
        if not plugin:
            plugin = self.load_single_plugin(plugin_id)

        if plugin:
            self.plugin_enabled.emit(plugin)
        return plugin

    def disable_plugin(self, plugin_id: str) -> bool:
        """
        动态停用插件：
        1. 在配置持久化中标记为已停用；
        2. 执行热卸载 (teardown、断开引用、清理内存、从 sys.modules 移除)；
        3. 触发 plugin_disabled 信号，通知主界面隐藏并移除路由。
        """
        from toolbox.core.config_manager import ConfigManager
        ConfigManager().set_plugin_enabled(plugin_id, False)

        if plugin_id in self._plugins:
            self.unload_plugin(plugin_id)

        self.plugin_disabled.emit(plugin_id)
        return True

    def unload_plugin(self, plugin_id: str) -> bool:
        """
        动态安全热卸载插件：
        1. 断开激活与托盘；
        2. 调用 plugin.teardown() 销毁 UI 控件与线程句柄；
        3. 清除 sys.modules 中该插件所有命名空间引用；
        4. 执行垃圾回收以彻底释放内存。
        """
        if self._active_plugin_id == plugin_id:
            self.deactivate_current_plugin()

        plugin = self._plugins.pop(plugin_id, None)
        if plugin:
            try:
                plugin.teardown()
            except Exception as e:
                print(f"[PluginManager] 卸载插件 [{plugin_id}] 调用 teardown 异常: {e}")

        # 清除 sys.modules 命名空间引用
        b_prefix = f"toolbox.plugins.{plugin_id}"
        e_prefix = f"chieri_plugin_{plugin_id}"
        to_remove = [
            k for k in list(sys.modules.keys())
            if k == b_prefix or k.startswith(f"{b_prefix}.")
            or k == e_prefix or k.startswith(f"{e_prefix}.")
        ]
        for mod_k in to_remove:
            sys.modules.pop(mod_k, None)

        self._plugin_module_names.pop(plugin_id, None)

        # 主动触发垃圾回收
        gc.collect()

        print(f"[PluginManager] 插件 [{plugin_id}] 已成功热卸载并清理命名空间")
        self.plugin_unloaded.emit(plugin_id)
        return True

    def uninstall_plugin(self, plugin_id: str) -> bool:
        """
        物理卸载并彻底释放磁盘空间：
        1. 先执行热卸载；
        2. 对外部扩展插件安全物理删除文件夹 (shutil.rmtree)；
        3. 对核心预置插件标记永久停用；
        4. 从持久化配置中彻底清除该插件专属参数；
        5. 触发 plugin_uninstalled 信号。
        """
        # 1. 确保已热卸载
        if plugin_id in self._plugins:
            self.unload_plugin(plugin_id)

        # 2. 定位插件物理目录
        record = self._available_plugins.get(plugin_id, {})
        folder = record.get("dir", "")
        if not folder:
            from toolbox.core.paths import get_plugins_search_dirs
            for d in get_plugins_search_dirs():
                cand = os.path.join(d, plugin_id)
                if os.path.isdir(cand):
                    folder = cand
                    break

        is_builtin = record.get("is_builtin", plugin_id in self.BUILTIN_PLUGIN_IDS)

        # 3. 物理删除文件或核心保护停用
        if is_builtin:
            # 核心内置插件受保护，仅作停用
            self.disable_plugin(plugin_id)
        else:
            if folder and os.path.isdir(folder):
                import stat
                def _force_rm(func, path, exc_info_or_exc):
                    try:
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    except Exception:
                        pass

                try:
                    if sys.version_info >= (3, 12):
                        shutil.rmtree(folder, onexc=_force_rm)
                    else:
                        shutil.rmtree(folder, onerror=_force_rm)
                except Exception:
                    # Windows 文件句柄竞争延迟重试
                    import time
                    time.sleep(0.08)
                    try:
                        shutil.rmtree(folder, ignore_errors=True)
                    except Exception:
                        pass
            self._available_plugins.pop(plugin_id, None)

        # 4. 清理全局配置中的从属信息
        from toolbox.core.config_manager import ConfigManager
        cfg = ConfigManager()
        cfg.delete_plugin_config(plugin_id)

        print(f"[PluginManager] 插件 [{plugin_id}] 物理卸载完成，磁盘空间已彻底释放")
        self.plugin_uninstalled.emit(plugin_id)
        return True

    def install_plugin_package(self, archive_path: str, target_dir: Optional[str] = None) -> PluginBase:
        """
        离线包导入安装 (.cpk / .zip)：
        一键解压并动态载入注册，内置严苛的 ZipSlip 路径穿越安全防御。
        """
        if not os.path.isfile(archive_path):
            raise FileNotFoundError(f"插件包文件不存在: {archive_path}")

        if not zipfile.is_zipfile(archive_path):
            raise ValueError(f"指定的插件包不是合法的 ZIP/CPK 归档: {archive_path}")

        from toolbox.core.paths import get_external_plugins_dir
        dest_root = target_dir or get_external_plugins_dir()
        os.makedirs(dest_root, exist_ok=True)
        dest_root_real = os.path.realpath(dest_root)

        with zipfile.ZipFile(archive_path, "r") as zf:
            infolist = zf.infolist()

            # 1. ZipSlip 路径穿越防御安全自检 (Windows 反斜杠与正斜杠全量统一校验)
            for info in infolist:
                fn = info.filename.replace("\\", "/")
                if "\0" in fn:
                    raise ValueError("检测到非法空字符文件名 (Null-byte injection)")
                if os.path.isabs(fn) or fn.startswith("/"):
                    raise ValueError(f"ZipSlip 安全防御拦截：禁止包含绝对路径 [{fn}]")
                if len(fn) >= 2 and fn[1] == ":":
                    raise ValueError(f"ZipSlip 安全防御拦截：禁止包含驱动器盘符 [{fn}]")
                parts = fn.split("/")
                if ".." in parts:
                    raise ValueError(f"ZipSlip 安全防御拦截：禁止包含路径穿越符号 '..' [{fn}]")

            # 2. 预先读取 manifest.json / plugin.json
            manifest_info = None
            for info in infolist:
                base = os.path.basename(info.filename.replace("\\", "/"))
                if base in ("manifest.json", "plugin.json"):
                    manifest_info = info
                    break

            manifest_data = {}
            if manifest_info:
                try:
                    manifest_data = json.loads(zf.read(manifest_info).decode("utf-8"))
                except Exception as e:
                    raise ValueError(f"解析插件 manifest.json 格式失败: {e}")

            plugin_id = manifest_data.get("id")
            if not plugin_id:
                # 尝试从包文件名推断
                plugin_id = os.path.splitext(os.path.basename(archive_path))[0]
                if "-" in plugin_id:
                    plugin_id = plugin_id.split("-")[0]

            # 校验 plugin_id 合法性
            if not re.match(r"^[a-zA-Z0-9_]+$", plugin_id):
                raise ValueError(f"非法的插件 ID 标识: {plugin_id}")

            target_plugin_dir = os.path.join(dest_root, plugin_id)
            target_real = os.path.realpath(target_plugin_dir)
            if not (target_real.startswith(dest_root_real + os.sep) or target_real == dest_root_real):
                raise ValueError("ZipSlip 安全防御拦截：目标解压目录超出允许的插件根路径")

            # 若旧版本已存在，先热卸载旧版本并安全覆盖
            if plugin_id in self._plugins:
                self.unload_plugin(plugin_id)
            if os.path.isdir(target_plugin_dir):
                shutil.rmtree(target_plugin_dir, ignore_errors=True)
            os.makedirs(target_plugin_dir, exist_ok=True)

            install_success = False
            try:
                # 3. 检查是否有统一的顶层目录前缀，解压时自动平铺
                top_parts = [
                    i.filename.replace("\\", "/").split("/")[0]
                    for i in infolist
                    if "/" in i.filename.replace("\\", "/")
                ]
                has_single_root = bool(top_parts) and len(set(top_parts)) == 1 and all(
                    i.filename.replace("\\", "/").startswith(top_parts[0] + "/") for i in infolist
                )
                root_prefix = (top_parts[0] + "/") if has_single_root else ""

                # 4. 执行文件解压
                for info in infolist:
                    norm_fn = info.filename.replace("\\", "/")
                    rel_name = norm_fn[len(root_prefix):] if root_prefix and norm_fn.startswith(root_prefix) else norm_fn
                    if not rel_name or rel_name.endswith("/"):
                        continue

                    out_path = os.path.realpath(os.path.join(target_plugin_dir, rel_name))
                    if not (out_path.startswith(target_real + os.sep) or out_path == target_real):
                        raise ValueError(f"ZipSlip 安全防御拦截：解压文件路径越界 [{rel_name}]")

                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with zf.open(info) as src, open(out_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)

                # 5. 确保存在 manifest.json 文件
                manifest_path = os.path.join(target_plugin_dir, "manifest.json")
                if not os.path.isfile(manifest_path) and manifest_data:
                    try:
                        with open(manifest_path, "w", encoding="utf-8") as f:
                            json.dump(manifest_data, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass

                # 6. 动态热载入并设为启用
                plugin = self.load_external_plugin(target_plugin_dir, force_reload=True)
                if not plugin:
                    raise RuntimeError(f"插件解压成功但动态热加载失败: {plugin_id}")

                from toolbox.core.config_manager import ConfigManager
                ConfigManager().set_plugin_enabled(plugin_id, True)

                print(f"[PluginManager] 离线插件包 [{plugin.name}] 导入并热加载成功！")
                self.plugin_installed.emit(plugin)
                install_success = True
                return plugin
            finally:
                # 异常安全屏障：若导入过程失败，立即回滚清理解压目录，杜绝破损死目录残留
                if not install_success and os.path.isdir(target_plugin_dir):
                    try:
                        shutil.rmtree(target_plugin_dir, ignore_errors=True)
                    except Exception:
                        pass

    def export_plugin_cpk(self, plugin_id: str, output_path_or_dir: str) -> str:
        """
        将任意插件（包含 22 个内置插件及外部插件）导出为符合标准规范的 .cpk 独立便携插件包。
        归档内包含 manifest.json、图标、源码及相关算法资源。
        """
        # 1. 获取插件实例或目录
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            plugin = self.load_single_plugin(plugin_id)

        folder = ""
        if plugin:
            folder = plugin.get_plugin_dir()
        elif plugin_id in self._available_plugins:
            folder = self._available_plugins[plugin_id].get("dir", "")

        if not folder or not os.path.isdir(folder):
            from toolbox.core.paths import get_plugins_search_dirs
            for d in get_plugins_search_dirs():
                cand = os.path.join(d, plugin_id)
                if os.path.isdir(cand):
                    folder = cand
                    break

        if not folder or not os.path.isdir(folder):
            raise FileNotFoundError(f"未找到插件 [{plugin_id}] 对应的磁盘文件目录")

        version = plugin.version if plugin else "1.0.0"
        pkg_filename = f"{plugin_id}-{version}.cpk"

        if os.path.isdir(output_path_or_dir):
            out_file = os.path.join(output_path_or_dir, pkg_filename)
        else:
            out_file = output_path_or_dir
            if not out_file.lower().endswith(".cpk") and not out_file.lower().endswith(".zip"):
                out_file += ".cpk"

        os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)

        # 2. 准备 manifest 数据
        manifest_data = plugin.get_manifest() if plugin else self._read_manifest(folder)
        if not manifest_data:
            manifest_data = {
                "id": plugin_id,
                "name": plugin_id,
                "version": version,
                "author": "Chieri",
                "category": "实用工具",
                "description": "",
                "icon": "icon.png",
                "entry_point": "plugin.py",
                "sort_order": 100
            }

        # 3. 打包生成 .cpk (标准 ZIP)
        with zipfile.ZipFile(out_file, "w", zipfile.ZIP_DEFLATED) as zf:
            # 写入 manifest.json
            zf.writestr("manifest.json", json.dumps(manifest_data, ensure_ascii=False, indent=2))

            out_file_abs = os.path.abspath(out_file)
            # 遍历插件目录中除 pycache 外的所有文件
            for root, dirs, files in os.walk(folder):
                # 排除 __pycache__ 和临时文件
                dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
                for f in files:
                    abs_p = os.path.join(root, f)
                    if os.path.abspath(abs_p) == out_file_abs:
                        continue
                    if f.endswith((".pyc", ".pyo", ".tmp")) or f.startswith("."):
                        continue
                    if f == "manifest.json" and os.path.normpath(root) == os.path.normpath(folder):  # 避免覆盖顶层已构造的
                        continue
                    rel_p = os.path.relpath(abs_p, folder).replace("\\", "/")
                    zf.write(abs_p, rel_p)

        print(f"[PluginManager] 成功导出插件包: {out_file}")
        return os.path.normpath(out_file)

    def get_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """根据 ID 获取已加载的插件实例"""
        return self._plugins.get(plugin_id)

    def get_all_plugins(self) -> List[PluginBase]:
        """获取所有当前已加载的活动插件，按 sort_order 升序排序"""
        return sorted(self._plugins.values(), key=lambda p: p.sort_order)

    def get_all_plugin_records(self) -> List[Dict[str, Any]]:
        """
        获取所有已发现插件的完整信息列表（包含已启用与已禁用、内置核心与外部扩展），
        专供“插件工坊 / 插件管理器”卡片化展示与管理。
        """
        from toolbox.core.config_manager import ConfigManager
        cfg = ConfigManager()
        records = []

        all_pids = list(dict.fromkeys(list(self._plugins.keys()) + list(self._available_plugins.keys())))
        for pid in all_pids:
            p = self._plugins.get(pid)
            avail = self._available_plugins.get(pid, {})
            is_enabled = cfg.is_plugin_enabled(pid)
            is_loaded = p is not None

            name = p.name if p else avail.get("name", pid)
            version = p.version if p else avail.get("version", "1.0.0")
            category = p.category if p else avail.get("category", "未分类")
            description = p.description if p else avail.get("description", "")
            author = p.author if p else avail.get("author", "Chieri")
            is_builtin = p.is_builtin if p else avail.get("is_builtin", True)
            size_bytes = p.get_file_size() if p else avail.get("size_bytes", 0)
            sort_order = p.sort_order if p else avail.get("sort_order", 100)
            p_dir = p.get_plugin_dir() if p else avail.get("dir", "")

            records.append({
                "id": pid,
                "name": name,
                "version": version,
                "category": category,
                "description": description,
                "author": author,
                "is_builtin": is_builtin,
                "is_enabled": is_enabled,
                "is_loaded": is_loaded,
                "size_bytes": size_bytes,
                "sort_order": sort_order,
                "dir": p_dir,
                "plugin": p,
            })

        records.sort(key=lambda r: (not r["is_enabled"], r["sort_order"]))
        return records

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
        for p in list(self._plugins.values()):
            try:
                p.cleanup()
            except Exception as e:
                print(f"[PluginManager] 清理插件 [{p.id}] 出错: {e}")
        self._plugins.clear()

    def is_plugin_enabled(self, plugin_id: str) -> bool:
        """检查插件是否处于启用状态"""
        from toolbox.core.config_manager import ConfigManager
        return ConfigManager().is_plugin_enabled(plugin_id)

    def get_plugins_accepting(self, data_type: str) -> List[PluginBase]:
        """
        获取支持接收指定 MIME 数据类型的所有可用插件列表
        """
        matched = []
        dt_lower = data_type.lower()
        for p in self._plugins.values():
            if not self.is_plugin_enabled(p.id):
                continue
            inputs = getattr(p, "supported_inputs", [])
            for inp in inputs:
                inp_lower = inp.lower()
                if inp_lower == "*/*" or inp_lower == dt_lower:
                    matched.append(p)
                    break
                if "/" in inp_lower and "/" in dt_lower:
                    inp_main, inp_sub = inp_lower.split("/", 1)
                    dt_main, dt_sub = dt_lower.split("/", 1)
                    if inp_main == dt_main and (inp_sub == "*" or inp_sub == dt_sub):
                        matched.append(p)
                        break
        return matched

    def pipe_data(self, source_id: str, target_id: str, data_type: str, data: any) -> bool:
        """
        跨插件管道数据流转调用 (支持目标插件按需惰性加载)
        """
        target = self.get_plugin(target_id)
        if not target:
            target = self.load_single_plugin(target_id)
        if not target:
            return False
        return target.accept_pipeline_data(data_type, data)
