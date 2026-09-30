"""
文件批量整理大师 - 核心业务逻辑
提供安全的批量重命名、正则/模板替换、后缀统一与目录扁平化处理。
"""

import os
import re
import shutil
import time
import uuid
from typing import List, Tuple, Dict, Any


def scan_files(paths: List[str], recursive: bool = False) -> List[str]:
    """根据给定的路径列表，扫描所有目标文件（去重保持顺序）"""
    result = []
    seen = set()

    for p in paths:
        norm_p = os.path.normpath(p)
        if os.path.isfile(norm_p):
            if norm_p not in seen:
                seen.add(norm_p)
                result.append(norm_p)
        elif os.path.isdir(norm_p):
            if recursive:
                for root, _, files in os.walk(norm_p):
                    for f in files:
                        full_p = os.path.normpath(os.path.join(root, f))
                        if full_p not in seen:
                            seen.add(full_p)
                            result.append(full_p)
            else:
                for f in os.listdir(norm_p):
                    full_p = os.path.normpath(os.path.join(norm_p, f))
                    if os.path.isfile(full_p) and full_p not in seen:
                        seen.add(full_p)
                        result.append(full_p)
    return result


class FileRenameEngine:
    @staticmethod
    def preview_template_rename(
        files: List[str],
        pattern: str,
        start_index: int = 1,
        step: int = 1,
        pad_digits: int = 2
    ) -> List[Tuple[str, str, str, str]]:
        """
        模板重命名预览：
        支持在 pattern 中使用 {n} 作为序号占位符，如果没提供 {n}，默认按 pattern_{n} 生成。
        返回: [(原绝对路径, 新绝对路径, 原文件名, 新文件名), ...]
        """
        results = []
        has_placeholder = "{n}" in pattern
        current_num = start_index

        for old_path in files:
            folder, filename = os.path.split(old_path)
            _, ext = os.path.splitext(filename)

            num_str = str(current_num).zfill(pad_digits)
            if has_placeholder:
                new_basename = pattern.replace("{n}", num_str)
            else:
                new_basename = f"{pattern}_{num_str}" if pattern else num_str

            new_filename = f"{new_basename}{ext}"
            new_path = os.path.join(folder, new_filename)
            results.append((old_path, new_path, filename, new_filename))
            current_num += step

        return results

    @staticmethod
    def preview_replace_rename(
        files: List[str],
        find_str: str,
        replace_str: str,
        use_regex: bool = False
    ) -> List[Tuple[str, str, str, str]]:
        """
        查找替换重命名预览：
        支持普通字符串替换或正则表达式替换。
        """
        results = []
        for old_path in files:
            folder, filename = os.path.split(old_path)
            base_name, ext = os.path.splitext(filename)

            if use_regex:
                try:
                    new_base = re.sub(find_str, replace_str, base_name)
                except Exception:
                    new_base = base_name
            else:
                new_base = base_name.replace(find_str, replace_str)

            new_filename = f"{new_base}{ext}"
            new_path = os.path.join(folder, new_filename)
            results.append((old_path, new_path, filename, new_filename))

        return results

    @staticmethod
    def preview_extension_rename(
        files: List[str],
        old_ext_filter: str,
        new_ext: str
    ) -> List[Tuple[str, str, str, str]]:
        """
        批量后缀修改预览：
        old_ext_filter: 过滤条件，为空或 * 表示匹配所有
        """
        results = []
        match_all = not old_ext_filter or old_ext_filter.strip() == "*"
        norm_filter = old_ext_filter.strip().lower()
        if not norm_filter.startswith(".") and not match_all:
            norm_filter = "." + norm_filter

        norm_new_ext = new_ext.strip()
        if norm_new_ext and not norm_new_ext.startswith("."):
            norm_new_ext = "." + norm_new_ext

        for old_path in files:
            folder, filename = os.path.split(old_path)
            base, ext = os.path.splitext(filename)

            if match_all or ext.lower() == norm_filter:
                new_filename = f"{base}{norm_new_ext}"
                new_path = os.path.join(folder, new_filename)
                results.append((old_path, new_path, filename, new_filename))

        return results

    @staticmethod
    def execute_rename(plan_list: List[Tuple[str, str, str, str]]) -> Dict[str, Any]:
        """
        两阶段事务性安全执行重命名计划：
        阶段一：将待重命名文件重命名至唯一临时中间名，彻底解耦循环依赖（如 A<->B 互换）与链式依赖（如 1->2, 2->3）以及 Windows 大小写重命名。
        阶段二：将临时中间文件迁移至最终目标名称。若遇计划外冲突文件，自动递增后缀保护，若阶段一发生异常支持事务回滚。
        """
        success_count = 0
        skipped_count = 0
        errors = []

        valid_tasks = []
        for old_path, new_path, old_name, new_name in plan_list:
            if old_path == new_path:
                skipped_count += 1
                continue
            if not os.path.exists(old_path):
                errors.append(f"原文件不存在: {old_name}")
                continue
            valid_tasks.append((old_path, new_path, old_name, new_name))

        if not valid_tasks:
            return {
                "success": success_count,
                "skipped": skipped_count,
                "errors": errors
            }

        # 阶段一：重命名到唯一临时中间文件（解除所有依赖锁死）
        staged_items = []
        rollback_log = []
        phase1_failed = False

        for idx, (old_path, new_path, old_name, new_name) in enumerate(valid_tasks):
            dir_name = os.path.dirname(os.path.abspath(old_path))
            tmp_name = f"._rn_stage_{os.getpid()}_{int(time.time() * 1000)}_{idx}_{uuid.uuid4().hex[:8]}.tmp"
            tmp_path = os.path.join(dir_name, tmp_name)

            try:
                os.rename(old_path, tmp_path)
                staged_items.append((tmp_path, new_path, old_name, new_name))
                rollback_log.append((tmp_path, old_path))
            except Exception as e:
                errors.append(f"预重命名临时锁定 [{old_name}] 失败: {str(e)}")
                phase1_failed = True
                break

        # 若阶段一出现异常，立即回滚已暂存文件
        if phase1_failed:
            for tmp_p, orig_p in reversed(rollback_log):
                try:
                    if os.path.exists(tmp_p):
                        os.rename(tmp_p, orig_p)
                except Exception:
                    pass
            return {
                "success": 0,
                "skipped": skipped_count,
                "errors": errors
            }

        # 阶段二：从临时中间文件迁移至最终目标路径
        for tmp_path, new_path, old_name, new_name in staged_items:
            dest_dir = os.path.dirname(os.path.abspath(new_path))
            os.makedirs(dest_dir, exist_ok=True)
            target_path = new_path

            if os.path.exists(target_path):
                # 目标路径仍存在（非本批次文件冲突），执行冲突防覆盖重命名
                base, ext = os.path.splitext(target_path)
                c = 1
                while os.path.exists(f"{base}_{c}{ext}"):
                    c += 1
                target_path = f"{base}_{c}{ext}"

            try:
                os.replace(tmp_path, target_path)
                success_count += 1
            except Exception as e:
                # 尝试跨磁盘驱动器移动回退 (解决 Windows WinError 17: 系统无法将文件移到不同的磁盘驱动器)
                try:
                    shutil.move(tmp_path, target_path)
                    success_count += 1
                except Exception as e2:
                    orig_path = dict(rollback_log).get(tmp_path)
                    if orig_path:
                        try:
                            os.replace(tmp_path, orig_path)
                        except Exception:
                            try:
                                shutil.move(tmp_path, orig_path)
                            except Exception:
                                pass
                    errors.append(f"最终重命名 [{old_name}] -> [{os.path.basename(target_path)}] 失败: {str(e2)}")

        return {
            "success": success_count,
            "skipped": skipped_count,
            "errors": errors
        }


class FolderFlattenEngine:
    @staticmethod
    def flatten_folders(target_folders: List[str]) -> Dict[str, Any]:
        """
        扁平化目录：将 target_folders 内部的文件提取到其父级目录，并清理空的 target_folders
        """
        moved_count = 0
        cleaned_folders = 0
        errors = []

        for folder in target_folders:
            folder = os.path.normpath(folder)
            if not os.path.isdir(folder):
                continue

            parent_dir = os.path.dirname(folder)
            if not parent_dir or not os.path.exists(parent_dir):
                errors.append(f"无法确定上级目录: {folder}")
                continue

            try:
                for item in os.listdir(folder):
                    src_item = os.path.join(folder, item)
                    dst_item = os.path.join(parent_dir, item)

                    # 重名防覆盖
                    if os.path.exists(dst_item):
                        base, ext = os.path.splitext(item)
                        idx = 1
                        while os.path.exists(os.path.join(parent_dir, f"{base}_{idx}{ext}")):
                            idx += 1
                        dst_item = os.path.join(parent_dir, f"{base}_{idx}{ext}")

                    shutil.move(src_item, dst_item)
                    moved_count += 1

                # 移除空文件夹（仅当完全清空时安全删除）
                try:
                    if os.path.exists(folder):
                        if not os.listdir(folder):
                            os.rmdir(folder)
                            cleaned_folders += 1
                        else:
                            errors.append(f"目录未完全清空，保留文件夹: {folder}")
                except Exception as e:
                    errors.append(f"删除空目录失败 [{folder}]: {e}")

            except Exception as e:
                errors.append(f"处理目录 [{folder}] 异常: {e}")

        return {
            "moved_count": moved_count,
            "cleaned_folders": cleaned_folders,
            "errors": errors
        }
