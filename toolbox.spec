# -*- mode: python ; coding: utf-8 -*-
"""
千绘莉的多功能工具箱 (Chieri Toolbox)
PyInstaller 生产级独立发布规范配置 (toolbox.spec)
"""

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# 项目工程根目录绝对路径
project_dir = os.path.abspath(SPECPATH)

# 1. 递归收集 toolbox 的所有子模块 (包括所有 22 个插件及其 ui、engine、worker、api、parser 等全部组件)
toolbox_submodules = collect_submodules('toolbox')

# 2. 收集核心依赖库的动态/隐藏引用，确保冻结环境下各插件功能正常运行
hidden_imports = list(set([
    *toolbox_submodules,
    'PySide6.QtSvg',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'shiboken6',
    'mutagen',
    'mutagen.id3',
    'mutagen.flac',
    'mutagen.mp3',
    'mutagen.oggvorbis',
    'mutagen.mp4',
    'PySide6.QtNetwork',
    'lz4',
    'lz4.frame',
    'keyboard',
    'pyperclip',
    'PIL',
    'PIL.Image',
    'requests',
    'urllib3',
    'Crypto',
    'Crypto.Cipher',
    'Crypto.Cipher.AES',
    'Crypto.Util.Padding',
    'yt_dlp',
    'yt_dlp.cookies',
    'sqlite3',
    'winreg',
    'ctypes',
]))

# 3. 收集必要的数据与资源文件:
# - toolbox 核心源码模块与插件包源码 (确保动态插件机制与独立导出功能在冻结态完美可用)
# - bin/ 目录下的所有二进制工具 (ffmpeg.exe, 7z.exe, ffprobe.exe, ffplay.exe, 7z.dll)
# - app_icon.ico / app_icon.png 图标资源
# - 必需的 VC++ 运行时动态库与 shiboken 链接库 (避免由于机器环境缺少 VS2022 CRT 报错)
datas = [
    (os.path.join(project_dir, 'toolbox'), 'toolbox'),
    (os.path.join(project_dir, 'bin'), 'bin'),
    (os.path.join(project_dir, 'app_icon.ico'), '.'),
    (os.path.join(project_dir, 'app_icon.png'), '.'),
]

try:
    import PySide6
    pyside_dir = os.path.dirname(PySide6.__file__)
except Exception:
    pyside_dir = os.path.join(project_dir, '.venv', 'Lib', 'site-packages', 'PySide6')

try:
    import shiboken6
    shiboken_dir = os.path.dirname(shiboken6.__file__)
except Exception:
    shiboken_dir = os.path.join(project_dir, '.venv', 'Lib', 'site-packages', 'shiboken6')

if os.path.isdir(shiboken_dir):
    shiboken_dll = os.path.join(shiboken_dir, 'shiboken6.abi3.dll')
    if os.path.isfile(shiboken_dll):
        datas.append((shiboken_dll, '.'))
        datas.append((shiboken_dll, 'PySide6'))

if os.path.isdir(pyside_dir):
    for f in ['msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'pyside6.abi3.dll']:
        p = os.path.join(pyside_dir, f)
        if os.path.isfile(p):
            datas.append((p, '.'))

# 去重数据文件，避免重复打包条目
datas = list(dict.fromkeys(datas))

# 4. 排除无用且体积极其庞大的 Qt 模块，精简安装包体积并防止 PyQt5 冲突
excludes = [
    'PySide6.QtWebEngine',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineQuick',
    'PySide6.QtPdf',
    'PySide6.QtPdfWidgets',
    'PySide6.QtDesigner',
    'PySide6.QtQml',
    'PySide6.QtQuick',
    'PyQt5',
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'PyQt5.sip',
    'PyQt6',
    'tkinter',
    'unittest',
]

rthook_file = os.path.join(project_dir, 'rthook_pyside6_fix.py')

a = Analysis(
    [os.path.join(project_dir, 'main.py')],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[rthook_file] if os.path.isfile(rthook_file) else [],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

# 过滤因系统 PATH 污染误引入的第三方冲突 DLL 及已排除模块的残留二进制
unused_binary_prefixes = ('icu', 'qt6pdf', 'qt6qml', 'qt6quick', 'qt6virtualkeyboard')
a.binaries = [
    x for x in a.binaries 
    if not os.path.basename(x[0]).lower().startswith(unused_binary_prefixes)
]

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ChieriToolbox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # 禁用 UPX 压缩以避免损坏 PySide6/Qt 动态链接库
    console=False,      # 纯窗口模式，不弹出黑框控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_dir, 'app_icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ChieriToolbox',
)

# 确保在 dist/ChieriToolbox 根目录下也有图标资源供桌面快捷方式或外部工具直接使用
import shutil
dist_target = os.path.join(project_dir, 'dist', 'ChieriToolbox')
for ico in ['app_icon.ico', 'app_icon.png']:
    src = os.path.join(project_dir, ico)
    dst = os.path.join(dist_target, ico)
    if os.path.isfile(src):
        try:
            os.makedirs(dist_target, exist_ok=True)
            shutil.copy2(src, dst)
        except Exception:
            pass

