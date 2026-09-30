"""
PyInstaller Runtime Hook: 修复 Windows 下 Python 3.8+ 对 PySide6 / shiboken6 的 DLL 加载目录限制
"""

import os
import sys

if sys.platform == "win32":
    bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    app_root = os.path.dirname(os.path.abspath(sys.executable))

    # 注册 DLL 加载路径 (PySide6, shiboken6, bin)
    bases = [bundle_dir, app_root, os.path.join(app_root, "_internal")]
    for base in bases:
        for sub in ["", "PySide6", "shiboken6", "bin"]:
            dll_dir = os.path.join(base, sub)
            if os.path.isdir(dll_dir):
                try:
                    os.add_dll_directory(dll_dir)
                except Exception:
                    pass

    # 将 bin 目录注入 PATH，确保 yt-dlp 等依赖全局 ffmpeg 的工具立即可用
    bin_dirs = [
        os.path.join(app_root, "bin"),
        os.path.join(bundle_dir, "bin"),
        os.path.join(app_root, "_internal", "bin"),
    ]
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    for b in reversed(bin_dirs):
        if os.path.isdir(b) and b not in path_entries:
            path_entries.insert(0, b)
    os.environ["PATH"] = os.pathsep.join(path_entries)
