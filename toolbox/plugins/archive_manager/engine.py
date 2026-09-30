"""
全能压缩与解压引擎
支持 7-Zip、WinRAR、Python 内置 zipfile/tarfile 与 lz4，支持密码加密/解密与内容预览。
"""

import os
import shutil
import subprocess
import tarfile
import zipfile
from typing import Dict, List, Optional, Tuple
from PySide6.QtCore import QThread, Signal

try:
    import lz4.frame
except ImportError:
    lz4 = None


def find_7z_executable() -> Optional[str]:
    """寻找 7-Zip 可执行文件"""
    try:
        from toolbox.core.paths import get_bin_path
        local_7z = get_bin_path("7z.exe")
        if local_7z and os.path.isfile(local_7z):
            return local_7z
    except Exception:
        pass

    candidates = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        shutil.which("7z"),
        shutil.which("7za")
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def find_winrar_executable() -> Optional[str]:
    """寻找 WinRAR 可执行文件"""
    candidates = [
        r"C:\Program Files\WinRAR\WinRAR.exe",
        r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
        shutil.which("WinRAR")
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def get_available_engines() -> Dict[str, str]:
    """获取系统当前可用的解压缩核心与路径"""
    engines = {}
    p7z = find_7z_executable()
    if p7z:
        engines["7-Zip"] = p7z
    pw = find_winrar_executable()
    if pw:
        engines["WinRAR"] = pw
    engines["Python 内置 (zip/tar)"] = "internal"
    if lz4:
        engines["LZ4 高速引擎"] = "lz4"
    return engines


def list_archive_contents(archive_path: str, password: Optional[str] = None) -> List[Dict]:
    """列出压缩包内的文件结构 (名称, 原始大小, 压缩大小)"""
    if not os.path.isfile(archive_path):
        return []

    p7z = find_7z_executable()
    ext = os.path.splitext(archive_path)[1].lower()

    # 1. 尝试 7-Zip 列出 (支持几乎所有格式)
    if p7z:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        cmd = [p7z, "l", "-slt", archive_path]
        if password:
            cmd.append(f"-p{password}")
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=15
            )
            if proc.returncode == 0:
                items = []
                cur_item = {}
                for line in proc.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("Path = "):
                        if cur_item.get("Path") and cur_item.get("Path") != archive_path:
                            items.append(cur_item)
                        cur_item = {"Path": line[7:]}
                    elif line.startswith("Size = "):
                        cur_item["Size"] = int(line[7:]) if line[7:].isdigit() else 0
                    elif line.startswith("Folder = "):
                        cur_item["Folder"] = line[9:] == "+"
                if cur_item.get("Path") and cur_item.get("Path") != archive_path:
                    items.append(cur_item)
                return items
        except Exception:
            pass

    # 2. Python 内置 zipfile 列出
    if ext == ".zip":
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                items = []
                for info in zf.infolist():
                    items.append({
                        "Path": info.filename,
                        "Size": info.file_size,
                        "Folder": info.is_dir()
                    })
                return items
        except Exception:
            pass

    # 3. Python 内置 tarfile 列出
    if ext in (".tar", ".gz", ".tgz", ".bz2", ".xz"):
        try:
            with tarfile.open(archive_path, "r:*") as tf:
                items = []
                for info in tf.getmembers():
                    items.append({
                        "Path": info.name,
                        "Size": info.size,
                        "Folder": info.isdir()
                    })
                return items
        except Exception:
            pass

    return []


def _is_safe_path(base_dir: str, path: str) -> bool:
    target = os.path.abspath(os.path.join(base_dir, path))
    return target.startswith(os.path.abspath(base_dir) + os.sep)


def _safe_extract_zip(zf: zipfile.ZipFile, target_dir: str, pwd: Optional[bytes] = None):
    base_resolved = os.path.abspath(target_dir)
    for member in zf.infolist():
        target = os.path.abspath(os.path.join(base_resolved, member.filename))
        if not target.startswith(base_resolved + os.sep) and target != base_resolved:
            print(f"[ArchiveManager] 警告: 拦截到 ZipSlip 路径越界成员: {member.filename}")
            continue
        zf.extract(member, target_dir, pwd=pwd)


def _safe_extract_tar(tf: tarfile.TarFile, target_dir: str):
    base_resolved = os.path.abspath(target_dir)
    safe_members = []
    for member in tf.getmembers():
        target = os.path.abspath(os.path.join(base_resolved, member.name))
        if not target.startswith(base_resolved + os.sep) and target != base_resolved:
            print(f"[ArchiveManager] 警告: 拦截到 TarSlip 路径越界成员: {member.name}")
            continue
        safe_members.append(member)
    tf.extractall(target_dir, members=safe_members)


def extract_archive(
    archive_path: str,
    output_dir: str,
    password: Optional[str] = None
) -> Tuple[bool, str]:
    """解压归档包"""
    if not os.path.isfile(archive_path):
        return False, f"压缩文件不存在: {archive_path}"

    os.makedirs(output_dir, exist_ok=True)
    ext = os.path.splitext(archive_path)[1].lower()
    archive_norm = os.path.normpath(archive_path)

    # 1. 如果是 .lz4 格式
    if ext == ".lz4":
        if not lz4:
            return False, "系统未安装 lz4 模块"
        try:
            base_name = os.path.splitext(os.path.basename(archive_path))[0]
            out_file = os.path.join(output_dir, base_name)
            with open(archive_path, "rb") as fin:
                decomp = lz4.frame.decompress(fin.read())
            with open(out_file, "wb") as fout:
                fout.write(decomp)
            return True, f"LZ4 解压成功: {out_file}"
        except Exception as e:
            return False, f"LZ4 解压失败: {str(e)}"

    # 2. 对 tar 及其变体归档 (.tar, .tar.gz, .tgz, .tar.bz2, .tar.xz)，无密码时优先使用 Python 内置 tarfile 一步到位完全展开
    is_tar_family = ext == ".tar" or archive_norm.lower().endswith((".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"))
    if is_tar_family and not password:
        try:
            with tarfile.open(archive_norm, "r:*") as tf:
                _safe_extract_tar(tf, output_dir)
            return True, f"内置 TAR 引擎解压完成: {output_dir}"
        except Exception:
            pass

    # 3. 优先调用 7-Zip CLI
    p7z = find_7z_executable()
    if p7z:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        cmd = [p7z, "x", archive_norm, f"-o{output_dir}", "-y"]
        if password:
            cmd.append(f"-p{password}")
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=300
            )
            if proc.returncode == 0:
                # 检查是否解压出了中间 .tar 文件（例如 7z 解压 .tar.gz 仅解包了 gzip 壳层）
                if archive_norm.lower().endswith((".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
                    for item in os.listdir(output_dir):
                        if item.lower().endswith(".tar"):
                            tar_item_p = os.path.join(output_dir, item)
                            if os.path.isfile(tar_item_p):
                                try:
                                    with tarfile.open(tar_item_p, "r:*") as tf:
                                        _safe_extract_tar(tf, output_dir)
                                    os.remove(tar_item_p)
                                except Exception:
                                    pass
                return True, f"7-Zip 解压成功至: {output_dir}"
            elif "Wrong password" in proc.stderr or "Wrong password" in proc.stdout:
                return False, "解压密码错误，请检查输入的解压密码。"
        except Exception:
            pass

    # 3. 备选调用 WinRAR CLI
    p_rar = find_winrar_executable()
    if p_rar:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        cmd = [p_rar, "x", "-y"]
        if password:
            cmd.append(f"-p{password}")
        cmd.extend([archive_norm, output_dir + os.sep])
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=300
            )
            if proc.returncode == 0:
                return True, f"WinRAR 解压成功至: {output_dir}"
        except Exception:
            pass

    # 4. Python 内置 zipfile
    if ext == ".zip":
        try:
            with zipfile.ZipFile(archive_norm, "r") as zf:
                pwd_bytes = password.encode("utf-8") if password else None
                _safe_extract_zip(zf, output_dir, pwd=pwd_bytes)
            return True, f"内置 ZIP 引擎解压完成: {output_dir}"
        except RuntimeError as e:
            if "password" in str(e).lower():
                return False, "解压密码错误或未提供密码。"
            return False, f"ZIP 解压失败: {str(e)}"
        except Exception as e:
            return False, f"ZIP 解压失败: {str(e)}"

    # 5. Python 内置 tarfile
    if ext in (".tar", ".gz", ".tgz", ".bz2", ".xz"):
        try:
            with tarfile.open(archive_norm, "r:*") as tf:
                _safe_extract_tar(tf, output_dir)
            return True, f"内置 TAR 引擎解压完成: {output_dir}"
        except Exception as e:
            return False, f"TAR 解压失败: {str(e)}"

    return False, "无法解压该格式：系统未安装 7-Zip 或 WinRAR，且内置引擎不支持该格式。"


def create_archive(
    source_paths: List[str],
    output_archive: str,
    format_type: str = "zip",
    password: Optional[str] = None,
    compression_level: int = 5
) -> Tuple[bool, str]:
    """创建压缩归档包"""
    if not source_paths:
        return False, "未选择任何待压缩文件。"

    os.makedirs(os.path.dirname(os.path.abspath(output_archive)), exist_ok=True)
    fmt = format_type.lower()
    p7z = find_7z_executable()

    # 1. LZ4 压缩
    if fmt == "lz4":
        if not lz4:
            return False, "未安装 lz4 模块"
        try:
            # LZ4 单文件流压缩
            first = source_paths[0]
            with open(first, "rb") as fin:
                data = fin.read()
            compressed = lz4.frame.compress(data, compression_level=compression_level)
            with open(output_archive, "wb") as fout:
                fout.write(compressed)
            return True, f"LZ4 压缩完成: {output_archive}"
        except Exception as e:
            return False, f"LZ4 压缩失败: {str(e)}"

    # 2. 如果要求带密码保护
    if password:
        if p7z and (fmt in ("zip", "7z")):
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            cmd = [
                p7z, "a", output_archive,
                f"-mx={compression_level}",
                "-y",
                f"-p{password}"
            ]
            if fmt == "7z":
                cmd.append("-mhe=on")  # 加密文件名

            for p in source_paths:
                cmd.append(p)

            try:
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=creationflags,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=300
                )
                if proc.returncode == 0 and os.path.exists(output_archive):
                    return True, f"7-Zip 加密压缩完成: {output_archive}"
                else:
                    return False, proc.stderr[:300] if proc.stderr else "7z 加密打包失败"
            except Exception as e:
                return False, str(e)

        pw = find_winrar_executable()
        if pw and (fmt in ("zip", "rar")):
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            cmd = [pw, "a", "-y", f"-p{password}", output_archive] + source_paths
            try:
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=creationflags,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=300
                )
                if proc.returncode == 0 and os.path.exists(output_archive):
                    return True, f"WinRAR 加密压缩完成: {output_archive}"
                else:
                    return False, proc.stderr[:300] if proc.stderr else "WinRAR 加密打包失败"
            except Exception as e:
                return False, str(e)

        return False, "创建带密码保护的压缩包需要系统安装 7-Zip 或 WinRAR，内置引擎无法进行加密压缩。"

    # 3. 7z 格式归档 (无密码)
    if fmt == "7z":
        if not p7z:
            return False, "创建 7z 格式归档需要系统安装 7-Zip，请安装 7-Zip 或切换为 ZIP 格式。"
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        cmd = [
            p7z, "a", output_archive,
            f"-mx={compression_level}",
            "-y"
        ]
        for p in source_paths:
            cmd.append(p)
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=300
            )
            if proc.returncode == 0 and os.path.exists(output_archive):
                return True, f"7-Zip 压缩打包完成: {output_archive}"
            else:
                return False, proc.stderr[:300] if proc.stderr else "7z 打包失败"
        except Exception as e:
            return False, str(e)

    # 3. Python 内置 zipfile 打包
    if fmt == "zip":
        try:
            with zipfile.ZipFile(
                output_archive, "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=compression_level
            ) as zf:
                for src in source_paths:
                    if os.path.isfile(src):
                        zf.write(src, arcname=os.path.basename(src))
                    elif os.path.isdir(src):
                        base_root = os.path.basename(src.rstrip("/\\"))
                        for root, _, files in os.walk(src):
                            for f in files:
                                full_p = os.path.join(root, f)
                                rel_p = os.path.relpath(full_p, src)
                                arcname = os.path.join(base_root, rel_p)
                                zf.write(full_p, arcname=arcname)
            return True, f"ZIP 压缩包创建完成: {output_archive}"
        except Exception as e:
            return False, f"ZIP 压缩失败: {str(e)}"

    # 4. Python 内置 tar.gz 打包
    if fmt in ("tar", "tar.gz", "tgz"):
        mode = "w:gz" if "gz" in fmt else "w"
        try:
            with tarfile.open(output_archive, mode) as tf:
                for src in source_paths:
                    tf.add(src, arcname=os.path.basename(src))
            return True, f"TAR 归档创建完成: {output_archive}"
        except Exception as e:
            return False, f"TAR 打包失败: {str(e)}"

    return False, f"不支持的归档格式: {fmt}"


class ArchiveWorker(QThread):
    """归档操作异步工作线程"""
    finished = Signal(bool, str)
    log_message = Signal(str)

    def __init__(self, mode: str, **kwargs):
        super().__init__()
        self.mode = mode
        self.kwargs = kwargs

    def run(self):
        if self.mode == "extract":
            archive = self.kwargs["archive_path"]
            out_dir = self.kwargs["output_dir"]
            pwd = self.kwargs.get("password")
            self.log_message.emit(f"[解压] 正在解压: {os.path.basename(archive)} -> {out_dir}")
            ok, msg = extract_archive(archive, out_dir, pwd)
            self.finished.emit(ok, msg)
        elif self.mode == "compress":
            sources = self.kwargs["source_paths"]
            output = self.kwargs["output_archive"]
            fmt = self.kwargs.get("format_type", "zip")
            pwd = self.kwargs.get("password")
            lvl = self.kwargs.get("compression_level", 5)
            self.log_message.emit(f"[压缩] 正在打包 {len(sources)} 项至: {os.path.basename(output)}")
            ok, msg = create_archive(sources, output, fmt, pwd, lvl)
            self.finished.emit(ok, msg)
