"""
osu!mania 皮肤调校工作台 - 无损 skin.ini 解析器
保留所有未知 Section、全量注释行、行内注释与原始排版布局，支持原子安全持久化。
"""

import os
from typing import Dict, List, Any, Optional


class SkinParser:
    def __init__(self):
        self.general: Dict[str, str] = {}
        self.colours: Dict[str, str] = {}
        self.fonts: Dict[str, str] = {}
        self.sections: Dict[str, Dict[str, str]] = {}
        self.mania_sections: List[Dict[str, str]] = []
        self._ast: List[Dict[str, Any]] = []

    def load(self, filepath: str):
        self.general = {}
        self.colours = {}
        self.fonts = {}
        self.sections = {}
        self.mania_sections = []
        self._ast = []

        if not os.path.exists(filepath):
            return

        current_sec: Optional[Dict[str, Any]] = None

        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                stripped = line.strip()

                # 空行或整行注释
                if not stripped or stripped.startswith('//') or stripped.startswith('#'):
                    raw_node = {"type": "raw", "text": line.rstrip('\r\n')}
                    if current_sec is not None:
                        current_sec["entries"].append(raw_node)
                    else:
                        self._ast.append(raw_node)
                    continue

                # Section 头部 [SectionName]
                if stripped.startswith('[') and ']' in stripped:
                    sec_name = stripped[1:stripped.index(']')].strip()
                    current_sec = {
                        "type": "section",
                        "name": sec_name,
                        "raw_header": line.rstrip('\r\n'),
                        "entries": [],
                        "data": {}
                    }
                    self._ast.append(current_sec)
                    self.sections[sec_name] = current_sec["data"]

                    sec_lower = sec_name.lower()
                    if sec_lower == 'general':
                        self.general = current_sec["data"]
                    elif sec_lower == 'colours':
                        self.colours = current_sec["data"]
                    elif sec_lower == 'fonts':
                        self.fonts = current_sec["data"]
                    elif sec_lower == 'mania':
                        self.mania_sections.append(current_sec["data"])
                    continue

                # 键值对行
                if ':' in line and current_sec is not None:
                    # 分离行内注释
                    inline_comment = ""
                    content_part = line
                    c_idx = -1
                    slash_idx = content_part.find('//')
                    hash_idx = content_part.find('#')
                    if slash_idx != -1 and hash_idx != -1:
                        c_idx = min(slash_idx, hash_idx)
                    elif slash_idx != -1:
                        c_idx = slash_idx
                    elif hash_idx != -1:
                        c_idx = hash_idx

                    if c_idx != -1:
                        inline_comment = " " + content_part[c_idx:].rstrip('\r\n')
                        content_part = content_part[:c_idx]

                    if ':' in content_part:
                        parts = content_part.split(':', 1)
                        raw_key = parts[0]
                        key = raw_key.strip()
                        raw_val = parts[1]
                        val = raw_val.strip()

                        sep = ": " if ": " in content_part else ":"

                        entry = {
                            "type": "kv",
                            "key": key,
                            "val": val,
                            "raw_key": raw_key.strip(),
                            "separator": sep,
                            "comment": inline_comment
                        }
                        current_sec["entries"].append(entry)
                        current_sec["data"][key] = val
                        continue

                # 其他未知行内容（作为 raw 节点保留）
                raw_node = {"type": "raw", "text": line.rstrip('\r\n')}
                if current_sec is not None:
                    current_sec["entries"].append(raw_node)
                else:
                    self._ast.append(raw_node)

    def get_section(self, section_name: str) -> Optional[Dict[str, str]]:
        """获取任意 Section 的数据字典（大小写不敏感）"""
        sec_lower = section_name.strip().lower()
        for node in self._ast:
            if node.get("type") == "section" and node.get("name", "").strip().lower() == sec_lower:
                return node.get("data")
        return None

    def get_mania_section(self, keys: str) -> Optional[Dict[str, str]]:
        for sec in self.mania_sections:
            k_val = ""
            for k, v in sec.items():
                if k.lower() == 'keys':
                    k_val = v
                    break
            if k_val.strip() == str(keys).strip():
                return sec
        return None

    def update_or_add_mania_section(self, keys: str, data: Dict[str, str]):
        target_sec = None
        for node in self._ast:
            if node.get("type") == "section" and node.get("name", "").lower() == "mania":
                for k, v in node["data"].items():
                    if k.lower() == "keys" and str(v).strip() == str(keys).strip():
                        target_sec = node
                        break
                if target_sec:
                    break

        if target_sec is not None:
            # 同步更新已存在节点（使用防御性拷贝，防止 data 即为 target_sec["data"] 时 clear 导致数据被排空）
            new_data = dict(data)
            target_sec["data"].clear()
            target_sec["data"].update(new_data)
            # 同步 entries
            existing_keys = set()
            for entry in target_sec["entries"]:
                if entry.get("type") == "kv":
                    k = entry["key"]
                    if k in new_data:
                        entry["val"] = str(new_data[k])
                        existing_keys.add(k)
                    else:
                        entry["type"] = "removed"

            target_sec["entries"] = [e for e in target_sec["entries"] if e.get("type") != "removed"]

            # 追加新键
            for k, v in new_data.items():
                if k not in existing_keys:
                    target_sec["entries"].append({
                        "type": "kv",
                        "key": k,
                        "val": str(v),
                        "raw_key": k,
                        "separator": ": ",
                        "comment": ""
                    })

            # 更新 self.mania_sections 引用
            for idx, sec in enumerate(self.mania_sections):
                k_val = ""
                for k, v in sec.items():
                    if k.lower() == 'keys':
                        k_val = v
                        break
                if k_val.strip() == str(keys).strip():
                    self.mania_sections[idx] = target_sec["data"]
                    break
        else:
            # 新增 Mania Section
            new_data = dict(data)
            new_data["Keys"] = str(keys)
            entries = []
            for k, v in new_data.items():
                entries.append({
                    "type": "kv",
                    "key": k,
                    "val": str(v),
                    "raw_key": k,
                    "separator": ": ",
                    "comment": ""
                })

            sec_node = {
                "type": "section",
                "name": "Mania",
                "raw_header": "[Mania]",
                "entries": entries,
                "data": new_data
            }
            if self._ast:
                self._ast.append({"type": "raw", "text": ""})
            self._ast.append(sec_node)
            self.mania_sections.append(new_data)

    def save(self, filepath: str):
        # 如果未从文件加载且 _ast 为空，构造基础 _ast
        if not self._ast:
            if self.general:
                self._ast.append({"type": "section", "name": "General", "raw_header": "[General]", "entries": [
                    {"type": "kv", "key": k, "val": str(v), "raw_key": k, "separator": ": ", "comment": ""} for k, v in self.general.items()
                ], "data": self.general})
            if self.colours:
                self._ast.append({"type": "raw", "text": ""})
                self._ast.append({"type": "section", "name": "Colours", "raw_header": "[Colours]", "entries": [
                    {"type": "kv", "key": k, "val": str(v), "raw_key": k, "separator": ": ", "comment": ""} for k, v in self.colours.items()
                ], "data": self.colours})
            if self.fonts:
                self._ast.append({"type": "raw", "text": ""})
                self._ast.append({"type": "section", "name": "Fonts", "raw_header": "[Fonts]", "entries": [
                    {"type": "kv", "key": k, "val": str(v), "raw_key": k, "separator": ": ", "comment": ""} for k, v in self.fonts.items()
                ], "data": self.fonts})
            for m in self.mania_sections:
                self._ast.append({"type": "raw", "text": ""})
                self._ast.append({"type": "section", "name": "Mania", "raw_header": "[Mania]", "entries": [
                    {"type": "kv", "key": k, "val": str(v), "raw_key": k, "separator": ": ", "comment": ""} for k, v in m.items()
                ], "data": m})

        # 同步字典变更至 AST
        ast_sec_names = set()
        for node in self._ast:
            if node.get("type") == "section":
                sec_name_lower = node.get("name", "").strip().lower()
                ast_sec_names.add(sec_name_lower)
                sec_data = node.get("data", {})
                existing_keys = set()
                for entry in node.get("entries", []):
                    if entry.get("type") == "kv":
                        k = entry["key"]
                        if k in sec_data:
                            entry["val"] = str(sec_data[k])
                            existing_keys.add(k)
                        else:
                            entry["type"] = "removed"
                node["entries"] = [e for e in node["entries"] if e.get("type") != "removed"]
                for k, v in sec_data.items():
                    if k not in existing_keys:
                        node["entries"].append({
                            "type": "kv",
                            "key": k,
                            "val": str(v),
                            "raw_key": k,
                            "separator": ": ",
                            "comment": ""
                        })

        # 检查 self.sections 中动态新增但未在 AST 中的 Section
        for s_name, s_data in self.sections.items():
            if s_name.strip().lower() not in ast_sec_names and s_data:
                entries = [{
                    "type": "kv",
                    "key": k,
                    "val": str(v),
                    "raw_key": k,
                    "separator": ": ",
                    "comment": ""
                } for k, v in s_data.items()]
                sec_node = {
                    "type": "section",
                    "name": s_name,
                    "raw_header": f"[{s_name}]",
                    "entries": entries,
                    "data": s_data
                }
                if self._ast:
                    self._ast.append({"type": "raw", "text": ""})
                self._ast.append(sec_node)
                ast_sec_names.add(s_name.strip().lower())

        lines = []
        for node in self._ast:
            if node["type"] == "raw":
                lines.append(node["text"])
            elif node["type"] == "section":
                lines.append(node["raw_header"])
                for entry in node.get("entries", []):
                    if entry["type"] == "raw":
                        lines.append(entry["text"])
                    elif entry["type"] == "kv":
                        val_str = str(entry["val"])
                        comment = entry.get("comment", "")
                        lines.append(f"{entry['raw_key']}{entry['separator']}{val_str}{comment}")

        out_content = "\n".join(lines).rstrip() + "\n"

        dir_name = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(dir_name, exist_ok=True)
        tmp_path = os.path.join(dir_name, f"._tmp_skin_{os.getpid()}_{os.path.basename(filepath)}")
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(out_content)

        os.replace(tmp_path, filepath)
