"""
工具箱 (Toolbox) - 配置持久化管理器
统一管理全局配置及各插件的独立配置。
"""

import json
import os
import sys
import threading
from typing import Any, Dict, Optional


def _deep_merge_dict(target: dict, source: dict) -> dict:
    """深度递归合并字典，source 覆盖 target 中相同键的值"""
    for k, v in source.items():
        if k in target and isinstance(target[k], dict) and isinstance(v, dict):
            _deep_merge_dict(target[k], v)
        else:
            target[k] = v
    return target


class ConfigManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """重置单例实例（用于单元测试配置隔离）"""
        with cls._lock:
            cls._instance = None

    def __init__(self, config_file: str = ""):
        # 如果已初始化，但传入了不同的有效 config_file，则切换目标文件并重新加载
        if getattr(self, "_initialized", False):
            if not config_file or config_file == self.config_file:
                return
            self.config_file = config_file
            self.data = self._load()
            return

        self._initialized = True
        
        # 默认保存于程序持久化根目录下的 toolbox_config.json
        if not config_file:
            from toolbox.core.paths import get_config_path
            config_file = get_config_path("toolbox_config.json")
        self.config_file = config_file
        self.data: Dict[str, Any] = self._load()

    def reload(self):
        """从磁盘重新加载当前配置"""
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        default_config = {
            "theme": "system",
            "recent_plugins": [],
            "window": {
                "width": 1080,
                "height": 720,
            },
            "window_opacity": 1.0,
            "bg_opacity": 1.0,
            "component_opacity": 1.0,
            "card_width": 280,
            "card_height": 165,
            "card_spacing": 18,
            "acrylic_enabled": False,
            "blur_level": 50,
            "multi_window_mode": False,
            "disabled_plugins": [],
            "custom_groups": [],
            "plugin_custom_groups": {},
            "plugin_excluded_groups": {},
            "default_startup_group": "全部",
            "tray_plugins": [],
            "autostart": {
                "enabled": False,
                "plugins": []
            },
            "ffmpeg_path": "",
            "plugins": {}
        }
        if os.path.exists(self.config_file):
            if os.path.getsize(self.config_file) == 0:
                return default_config
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        _deep_merge_dict(default_config, loaded)
            except Exception as e:
                print(f"[ConfigManager] 读取配置文件失败: {e}，将使用默认配置")
        return default_config

    def save(self):
        """原子持久化当前配置到文件，带跨进程文件锁与最新状态递归合并以防丢失更新"""
        with self._lock:
            dir_path = os.path.dirname(os.path.abspath(self.config_file))
            os.makedirs(dir_path, exist_ok=True)
            lock_path = self.config_file + ".lock"
            lock_fd = None
            locked = False
            if sys.platform == "win32":
                try:
                    import msvcrt
                    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
                    msvcrt.locking(lock_fd, msvcrt.LK_LOCK, 1)
                    locked = True
                except Exception:
                    pass

            try:
                # 重新载入磁盘上其他进程可能写入的最新配置并进行深度合并
                if os.path.exists(self.config_file) and os.path.getsize(self.config_file) > 0:
                    try:
                        with open(self.config_file, "r", encoding="utf-8") as f:
                            disk_data = json.load(f)
                            if isinstance(disk_data, dict):
                                self.data = _deep_merge_dict(disk_data, self.data)
                    except Exception:
                        pass

                tmp_file = os.path.join(dir_path, f"._tmp_cfg_{os.getpid()}_{os.path.basename(self.config_file)}")
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_file, self.config_file)
            except Exception as e:
                print(f"[ConfigManager] 保存配置文件失败: {e}")
            finally:
                if lock_fd is not None:
                    try:
                        if locked:
                            import msvcrt
                            msvcrt.locking(lock_fd, msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                    try:
                        os.close(lock_fd)
                    except Exception:
                        pass

    def get(self, key: str, default: Any = None) -> Any:
        """获取顶级配置项"""
        return self.data.get(key, default)

    def set(self, key: str, value: Any, auto_save: bool = True):
        """设置顶级配置项"""
        self.data[key] = value
        if auto_save:
            self.save()

    def get_plugin_config(self, plugin_id: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """获取指定插件的专属配置字典"""
        plugins = self.data.setdefault("plugins", {})
        return plugins.setdefault(plugin_id, default or {})

    def set_plugin_config(self, plugin_id: str, config: Dict[str, Any], auto_save: bool = True):
        """保存指定插件的专属配置字典"""
        plugins = self.data.setdefault("plugins", {})
        plugins[plugin_id] = config
        if auto_save:
            self.save()

    def record_recent_plugin(self, plugin_id: str):
        """记录最近访问的插件"""
        recents = self.data.setdefault("recent_plugins", [])
        if plugin_id in recents:
            recents.remove(plugin_id)
        recents.insert(0, plugin_id)
        self.data["recent_plugins"] = recents[:8]  # 最多保留8个
        self.save()

    def is_plugin_enabled(self, plugin_id: str) -> bool:
        """检查特定插件是否处于启用状态"""
        disabled = self.data.get("disabled_plugins", [])
        return plugin_id not in disabled

    def set_plugin_enabled(self, plugin_id: str, enabled: bool, auto_save: bool = True):
        """设置特定插件的启用状态"""
        disabled = list(self.data.get("disabled_plugins", []))
        if enabled:
            if plugin_id in disabled:
                disabled.remove(plugin_id)
        else:
            if plugin_id not in disabled:
                disabled.append(plugin_id)
        self.data["disabled_plugins"] = disabled
        if auto_save:
            self.save()

    def get_disabled_plugins(self) -> list:
        return list(self.data.get("disabled_plugins", []))

    def get_multi_window_mode(self) -> bool:
        return bool(self.data.get("multi_window_mode", False))

    def set_multi_window_mode(self, enabled: bool, auto_save: bool = True):
        self.set("multi_window_mode", enabled, auto_save=auto_save)

    def get_window_opacity(self) -> float:
        return float(self.data.get("window_opacity", 1.0))

    def set_window_opacity(self, opacity: float, auto_save: bool = True):
        val = max(0.2, min(1.0, float(opacity)))
        self.set("window_opacity", val, auto_save=auto_save)

    def get_bg_opacity(self) -> float:
        return float(self.data.get("bg_opacity", self.data.get("window_opacity", 1.0)))

    def set_bg_opacity(self, opacity: float, auto_save: bool = True):
        val = max(0.2, min(1.0, float(opacity)))
        self.set("bg_opacity", val, auto_save=auto_save)

    def get_component_opacity(self) -> float:
        return float(self.data.get("component_opacity", 1.0))

    def set_component_opacity(self, opacity: float, auto_save: bool = True):
        val = max(0.4, min(1.0, float(opacity)))
        self.set("component_opacity", val, auto_save=auto_save)

    def get_card_width(self) -> int:
        return int(self.data.get("card_width", 280))

    def set_card_width(self, width: int, auto_save: bool = True):
        val = max(200, min(420, int(width)))
        self.set("card_width", val, auto_save=auto_save)

    def get_card_height(self) -> int:
        return int(self.data.get("card_height", 165))

    def set_card_height(self, height: int, auto_save: bool = True):
        val = max(130, min(260, int(height)))
        self.set("card_height", val, auto_save=auto_save)

    def get_card_spacing(self) -> int:
        return int(self.data.get("card_spacing", 18))

    def set_card_spacing(self, spacing: int, auto_save: bool = True):
        val = max(8, min(40, int(spacing)))
        self.set("card_spacing", val, auto_save=auto_save)

    def get_acrylic_enabled(self) -> bool:
        return bool(self.data.get("acrylic_enabled", False))

    def set_acrylic_enabled(self, enabled: bool, auto_save: bool = True):
        self.set("acrylic_enabled", enabled, auto_save=auto_save)

    def get_blur_level(self) -> int:
        return int(self.data.get("blur_level", 50))

    def set_blur_level(self, level: int, auto_save: bool = True):
        self.set("blur_level", max(0, min(100, int(level))), auto_save=auto_save)

    def get_autostart_config(self) -> dict:
        return self.data.get("autostart", {"enabled": False, "plugins": []})

    def set_autostart_config(self, enabled: bool, plugins: Optional[list] = None, auto_save: bool = True):
        self.data["autostart"] = {
            "enabled": enabled,
            "plugins": plugins or []
        }
        if auto_save:
            self.save()

    def get_custom_groups(self) -> list:
        """获取所有用户自定义分组名称列表"""
        return list(self.data.get("custom_groups", []))

    def add_custom_group(self, name: str, auto_save: bool = True) -> bool:
        """添加一个新的自定义分组"""
        name = name.strip()
        if not name or name in ("全部", "最近使用"):
            return False
        groups = list(self.data.get("custom_groups", []))
        if name not in groups:
            groups.append(name)
            self.data["custom_groups"] = groups
            if auto_save:
                self.save()
            return True
        return False

    def delete_custom_group(self, name: str, auto_save: bool = True) -> bool:
        """删除一个自定义分组，并清理该分组中的插件从属映射"""
        groups = list(self.data.get("custom_groups", []))
        if name in groups:
            groups.remove(name)
            self.data["custom_groups"] = groups
            # 清理自定义映射
            mappings = dict(self.data.get("plugin_custom_groups", {}))
            changed = False
            for pid, plist in list(mappings.items()):
                if name in plist:
                    plist = [g for g in plist if g != name]
                    mappings[pid] = plist
                    changed = True
            if changed:
                self.data["plugin_custom_groups"] = mappings

            # 清理排除映射
            excl_mappings = dict(self.data.get("plugin_excluded_groups", {}))
            excl_changed = False
            for pid, elist in list(excl_mappings.items()):
                if name in elist:
                    elist = [g for g in elist if g != name]
                    excl_mappings[pid] = elist
                    excl_changed = True
            if excl_changed:
                self.data["plugin_excluded_groups"] = excl_mappings

            # 若默认启动分组恰好为被删除的分组，重置为全部
            if self.data.get("default_startup_group") == name:
                self.data["default_startup_group"] = "全部"
            if auto_save:
                self.save()
            return True
        return False

    def get_plugin_custom_groups(self, plugin_id: str) -> list:
        """获取特定插件所属的所有额外/自定义分组"""
        mappings = self.data.get("plugin_custom_groups", {})
        return list(mappings.get(plugin_id, []))

    def get_plugin_excluded_groups(self, plugin_id: str) -> list:
        """获取特定插件被显式踢出/排除的分组列表"""
        mappings = self.data.get("plugin_excluded_groups", {})
        return list(mappings.get(plugin_id, []))

    def get_plugin_groups(self, plugin_id: str, default_category: Optional[str] = None) -> list:
        """获取特定插件当前所属的所有有效分组（包含内置分类与自定义分组）"""
        groups = []
        excluded = set(self.get_plugin_excluded_groups(plugin_id))
        if default_category and default_category not in excluded:
            groups.append(default_category)
        for g in self.get_plugin_custom_groups(plugin_id):
            if g not in groups and g not in excluded:
                groups.append(g)
        return groups

    def is_plugin_in_group(self, plugin_id: str, group_name: str, default_category: Optional[str] = None) -> bool:
        """检查特定插件是否属于指定分组"""
        if not group_name or group_name == "全部":
            return True
        excluded = self.get_plugin_excluded_groups(plugin_id)
        if group_name in excluded:
            return False
        custom_list = self.get_plugin_custom_groups(plugin_id)
        if group_name in custom_list:
            return True
        if default_category and group_name == default_category:
            return True
        return False

    def add_plugin_to_group(
        self,
        plugin_id: str,
        group_name: str,
        default_category: Optional[str] = None,
        auto_save: bool = True
    ) -> bool:
        """将某插件加入分组（可加入自定义分组或恢复被移出的默认分类）"""
        group_name = group_name.strip()
        if not group_name:
            return False

        changed = False
        # 1. 若曾被排除，先解除排除
        excl_mappings = dict(self.data.get("plugin_excluded_groups", {}))
        cur_excl = list(excl_mappings.get(plugin_id, []))
        if group_name in cur_excl:
            cur_excl.remove(group_name)
            excl_mappings[plugin_id] = cur_excl
            self.data["plugin_excluded_groups"] = excl_mappings
            changed = True

        # 2. 检查是否为自定义分组
        groups = list(self.data.get("custom_groups", []))
        if group_name not in groups and group_name not in ("全部", "最近使用") and group_name != default_category:
            groups.append(group_name)
            self.data["custom_groups"] = groups
            changed = True

        # 3. 若非默认分类或属于自定义分组，加入自定义映射列表
        if group_name != default_category:
            mappings = dict(self.data.get("plugin_custom_groups", {}))
            cur_list = list(mappings.get(plugin_id, []))
            if group_name not in cur_list:
                cur_list.append(group_name)
                mappings[plugin_id] = cur_list
                self.data["plugin_custom_groups"] = mappings
                changed = True

        if changed and auto_save:
            self.save()
        return changed

    def remove_plugin_from_group(
        self,
        plugin_id: str,
        group_name: str,
        default_category: Optional[str] = None,
        auto_save: bool = True
    ) -> bool:
        """将某插件从指定分组中踢出（支持移出自定义分组及内置分类）"""
        group_name = group_name.strip()
        if not group_name:
            return False

        changed = False
        # 1. 若存在于自定义分组映射中，剔除
        mappings = dict(self.data.get("plugin_custom_groups", {}))
        cur_list = list(mappings.get(plugin_id, []))
        if group_name in cur_list:
            cur_list.remove(group_name)
            mappings[plugin_id] = cur_list
            self.data["plugin_custom_groups"] = mappings
            changed = True

        # 2. 若是其固有分类，加入排除列表
        if default_category and group_name == default_category:
            excl_mappings = dict(self.data.get("plugin_excluded_groups", {}))
            cur_excl = list(excl_mappings.get(plugin_id, []))
            if group_name not in cur_excl:
                cur_excl.append(group_name)
                excl_mappings[plugin_id] = cur_excl
                self.data["plugin_excluded_groups"] = excl_mappings
                changed = True

        if changed and auto_save:
            self.save()
        return changed

    def get_default_startup_group(self) -> str:
        """获取工具箱启动时默认展示的分组"""
        return str(self.data.get("default_startup_group", "全部"))

    def set_default_startup_group(self, group_name: str, auto_save: bool = True):
        """设置工具箱启动时默认展示的分组"""
        self.set("default_startup_group", group_name.strip() or "全部", auto_save=auto_save)

    get_default_group = get_default_startup_group
    set_default_group = set_default_startup_group


    def get_tray_plugins(self) -> list:
        """获取独立常驻托盘的插件 ID 列表"""
        return list(self.data.get("tray_plugins", []))

    def is_plugin_in_tray(self, plugin_id: str) -> bool:
        """检查特定插件是否已独立常驻系统托盘"""
        return plugin_id in self.data.get("tray_plugins", [])

    def set_tray_plugin(self, plugin_id: str, enabled: bool, auto_save: bool = True):
        """添加或移除特定插件的独立托盘图标"""
        trays = list(self.data.get("tray_plugins", []))
        if enabled:
            if plugin_id not in trays:
                trays.append(plugin_id)
        else:
            if plugin_id in trays:
                trays.remove(plugin_id)
        self.data["tray_plugins"] = trays
        if auto_save:
            self.save()

