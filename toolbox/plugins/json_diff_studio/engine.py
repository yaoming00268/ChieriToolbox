"""
JSON 对比与分析工坊 (JSON Diff Studio) - 引擎模块
提供高精文本/JSON双栏差异计算、字符级差异提取、JSON格式化/压缩校验、以及纯 Python JSONPath 查询解析。
"""

import json
import re
import difflib
from typing import Any, Dict, List, Optional, Tuple, Union


def compute_diff(text1: str, text2: str) -> Dict[str, Any]:
    """
    计算两段文本/JSON的高精度逐行差异，并输出对齐的双栏行数据与统计指标。
    """
    lines1 = text1.splitlines()
    lines2 = text2.splitlines()

    matcher = difflib.SequenceMatcher(None, lines1, lines2)
    left_rows: List[Dict[str, Any]] = []
    right_rows: List[Dict[str, Any]] = []

    stats = {
        "additions": 0,
        "deletions": 0,
        "modifications": 0,
        "equals": 0
    }

    left_idx = 0
    right_idx = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            count = i2 - i1
            stats["equals"] += count
            for k in range(count):
                left_idx += 1
                right_idx += 1
                left_rows.append({
                    "line_num": left_idx,
                    "text": lines1[i1 + k],
                    "type": "equal",
                    "inline": []
                })
                right_rows.append({
                    "line_num": right_idx,
                    "text": lines2[j1 + k],
                    "type": "equal",
                    "inline": []
                })
        elif tag == "replace":
            len1 = i2 - i1
            len2 = j2 - j1
            max_len = max(len1, len2)
            stats["modifications"] += max_len
            for k in range(max_len):
                inline_l = []
                inline_r = []
                t1 = lines1[i1 + k] if k < len1 else ""
                t2 = lines2[j1 + k] if k < len2 else ""

                if k < len1 and k < len2:
                    # 逐字符计算行内高精差异
                    c_matcher = difflib.SequenceMatcher(None, t1, t2)
                    for ctag, ci1, ci2, cj1, cj2 in c_matcher.get_opcodes():
                        if ctag in ("replace", "delete"):
                            inline_l.append((ci1, ci2))
                        if ctag in ("replace", "insert"):
                            inline_r.append((cj1, cj2))
                elif k < len1:
                    inline_l = [(0, len(t1))]
                elif k < len2:
                    inline_r = [(0, len(t2))]

                if k < len1:
                    left_idx += 1
                    left_rows.append({
                        "line_num": left_idx,
                        "text": t1,
                        "type": "replace",
                        "inline": inline_l
                    })
                else:
                    left_rows.append({
                        "line_num": None,
                        "text": "",
                        "type": "empty",
                        "inline": []
                    })

                if k < len2:
                    right_idx += 1
                    right_rows.append({
                        "line_num": right_idx,
                        "text": t2,
                        "type": "replace",
                        "inline": inline_r
                    })
                else:
                    right_rows.append({
                        "line_num": None,
                        "text": "",
                        "type": "empty",
                        "inline": []
                    })
        elif tag == "delete":
            count = i2 - i1
            stats["deletions"] += count
            for k in range(count):
                left_idx += 1
                t = lines1[i1 + k]
                left_rows.append({
                    "line_num": left_idx,
                    "text": t,
                    "type": "delete",
                    "inline": [(0, len(t))]
                })
                right_rows.append({
                    "line_num": None,
                    "text": "",
                    "type": "empty",
                    "inline": []
                })
        elif tag == "insert":
            count = j2 - j1
            stats["additions"] += count
            for k in range(count):
                right_idx += 1
                t = lines2[j1 + k]
                left_rows.append({
                    "line_num": None,
                    "text": "",
                    "type": "empty",
                    "inline": []
                })
                right_rows.append({
                    "line_num": right_idx,
                    "text": t,
                    "type": "insert",
                    "inline": [(0, len(t))]
                })

    return {
        "left_rows": left_rows,
        "right_rows": right_rows,
        "stats": stats,
        "total_rows": len(left_rows)
    }


def format_json_str(text: str, indent: int = 2, sort_keys: bool = False) -> Tuple[bool, str, Optional[str]]:
    """格式化/美化 JSON 字符串"""
    text = text.strip()
    if not text:
        return True, "", None
    try:
        obj = json.loads(text)
        formatted = json.dumps(obj, indent=indent, sort_keys=sort_keys, ensure_ascii=False)
        return True, formatted, None
    except json.JSONDecodeError as e:
        return False, text, f"JSON 语法错误 (行 {e.lineno}, 列 {e.colno}): {e.msg}"
    except Exception as e:
        return False, text, f"格式化异常: {e}"


def minify_json_str(text: str) -> Tuple[bool, str, Optional[str]]:
    """压缩单行 JSON 字符串 (移除多余空格换行)"""
    text = text.strip()
    if not text:
        return True, "", None
    try:
        obj = json.loads(text)
        minified = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
        return True, minified, None
    except json.JSONDecodeError as e:
        return False, text, f"JSON 语法错误 (行 {e.lineno}, 列 {e.colno}): {e.msg}"
    except Exception as e:
        return False, text, f"压缩异常: {e}"


def validate_json_str(text: str) -> Tuple[bool, str, Optional[Tuple[int, int]]]:
    """校验 JSON 语法完整性，返回 (是否合法, 描述信息, (错误行, 错误列)或None)"""
    text = text.strip()
    if not text:
        return True, "内容为空", None
    try:
        json.loads(text)
        return True, "JSON 语法验证通过 (合规)", None
    except json.JSONDecodeError as e:
        return False, f"语法错误: {e.msg} (第 {e.lineno} 行, 第 {e.colno} 列)", (e.lineno, e.colno)
    except Exception as e:
        return False, f"解析异常: {e}", None


# =========================================================================
# 轻量纯 Python JSONPath 查询引擎 (支持 $, ., .., [*], [0], [?(@.x > y)])
# =========================================================================

def _eval_filter_expression(item: Any, expr: str) -> bool:
    """评估过滤表达式，例如 @.price > 10, @.active == true, @.name == 'apple'"""
    if not isinstance(item, dict):
        return False

    expr = expr.strip()
    # 匹配操作符比较: @.prop op value (支持属性名包含连字符 - 与下划线 _)
    m = re.match(r"^@\.([a-zA-Z0-9_\-]+)\s*(==|!=|>=|<=|>|<)\s*(.+)$", expr)
    if m:
        prop, op, raw_val = m.groups()
        if prop not in item:
            return False
        left = item[prop]
        raw_val = raw_val.strip()
        # 类型推导
        if raw_val.lower() == "true":
            right = True
        elif raw_val.lower() == "false":
            right = False
        elif raw_val.lower() == "null":
            right = None
        elif (raw_val.startswith('"') and raw_val.endswith('"')) or (raw_val.startswith("'") and raw_val.endswith("'")):
            right = raw_val[1:-1]
        else:
            try:
                right = float(raw_val) if "." in raw_val else int(raw_val)
            except ValueError:
                right = raw_val

        try:
            if op == "==":
                return left == right
            elif op == "!=":
                return left != right
            elif op == ">":
                return left > right
            elif op == "<":
                return left < right
            elif op == ">=":
                return left >= right
            elif op == "<=":
                return left <= right
        except TypeError:
            return False

    # 简单属性存在性检查: @.prop
    m_prop = re.match(r"^@\.([a-zA-Z0-9_\-]+)$", expr)
    if m_prop:
        prop = m_prop.group(1)
        return prop in item and bool(item[prop])

    return False


def _recursive_descent(data: Any, key: str, results: List[Any], visited: Optional[set] = None, depth: int = 0):
    """递归向下搜索指定键名，内置环路检测与递归深度防护"""
    if depth > 100:
        return
    if visited is None:
        visited = set()
    data_id = id(data)
    if data_id in visited:
        return
    visited.add(data_id)

    if isinstance(data, dict):
        for k, v in data.items():
            if key == "*" or k == key:
                results.append(v)
            _recursive_descent(v, key, results, visited, depth + 1)
    elif isinstance(data, list):
        for item in data:
            _recursive_descent(item, key, results, visited, depth + 1)


def evaluate_jsonpath(data: Any, query: str) -> Tuple[bool, List[Any], str]:
    """
    对内存中的 JSON 对象执行 JSONPath 查询。
    支持语法:
      - $ : 根节点
      - $.store.book : 点操作符层级
      - $..author : 递归向下查找
      - $.* : 匹配当前层级所有字段
      - $[0], $[-1] : 索引查找
      - $[*] : 列表通配展开
      - $[0:2] : 切片
      - $[?(@.price > 10)] : 条件过滤
    """
    try:
        query = query.strip()
        if not query:
            return True, [data], "空查询，返回根对象"

        if not query.startswith("$"):
            if query.startswith("["):
                query = "$" + query
            else:
                query = "$." + query

        # 处理根节点
        curr_targets = [data]

        # 解析 tokens
        # 拆分模式: 处理 .. 或 . 或 [xxx]
        i = 0
        q_len = len(query)

        while i < q_len and curr_targets:
            if query[i] == "$":
                i += 1
                continue

            if query[i:i+2] == "..":
                # 递归向下
                i += 2
                # 获取下一个标识符
                match = re.match(r"^([a-zA-Z0-9_\-]+|\*)", query[i:])
                if match:
                    key = match.group(1)
                    i += len(key)
                    next_targets = []
                    for t in curr_targets:
                        _recursive_descent(t, key, next_targets)
                    curr_targets = next_targets
                continue

            if query[i] == ".":
                i += 1
                if i < q_len and query[i] == "[":
                    # 兼容 .[0] 写法，步进跳过点号直接交由中括号解析器
                    continue
                match = re.match(r"^([a-zA-Z0-9_\-]+|\*)", query[i:])
                if match:
                    key = match.group(1)
                    i += len(key)
                    next_targets = []
                    for t in curr_targets:
                        if isinstance(t, dict):
                            if key == "*":
                                next_targets.extend(t.values())
                            elif key in t:
                                next_targets.append(t[key])
                    curr_targets = next_targets
                continue

            if query[i] == "[":
                end_bracket = query.find("]", i)
                if end_bracket == -1:
                    return False, [], f"括号未闭合: {query[i:]}"
                bracket_content = query[i+1:end_bracket].strip()
                i = end_bracket + 1

                next_targets = []
                # 1. 过滤表达式: ?(...)
                if bracket_content.startswith("?(") and bracket_content.endswith(")"):
                    expr = bracket_content[2:-1]
                    for t in curr_targets:
                        if isinstance(t, list):
                            for item in t:
                                if _eval_filter_expression(item, expr):
                                    next_targets.append(item)
                        elif isinstance(t, dict):
                            if _eval_filter_expression(t, expr):
                                next_targets.append(t)
                # 2. 通配符 [*]
                elif bracket_content == "*":
                    for t in curr_targets:
                        if isinstance(t, list):
                            next_targets.extend(t)
                        elif isinstance(t, dict):
                            next_targets.extend(t.values())
                # 3. 切片 [start:end]
                elif ":" in bracket_content:
                    parts = bracket_content.split(":")
                    try:
                        start = int(parts[0].strip()) if parts[0].strip() else None
                    except ValueError:
                        start = None
                    try:
                        end = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else None
                    except ValueError:
                        end = None
                    for t in curr_targets:
                        if isinstance(t, list):
                            next_targets.extend(t[start:end])
                # 4. 单数字索引 [0]
                elif re.match(r"^-?\d+$", bracket_content):
                    idx = int(bracket_content)
                    for t in curr_targets:
                        if isinstance(t, list) and -len(t) <= idx < len(t):
                            next_targets.append(t[idx])
                # 5. 引号属性 ['prop']
                elif (bracket_content.startswith("'") and bracket_content.endswith("'")) or \
                     (bracket_content.startswith('"') and bracket_content.endswith('"')):
                    prop_key = bracket_content[1:-1]
                    for t in curr_targets:
                        if isinstance(t, dict) and prop_key in t:
                            next_targets.append(t[prop_key])
                else:
                    # 兼容未加引号的纯文本键名
                    for t in curr_targets:
                        if isinstance(t, dict) and bracket_content in t:
                            next_targets.append(t[bracket_content])

                curr_targets = next_targets
                continue

            # 未识别字符步进
            i += 1

        return True, curr_targets, f"查询成功，命中 {len(curr_targets)} 个匹配项"
    except Exception as e:
        return False, [], f"JSONPath 解析错误: {e}"
