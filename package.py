"""
千绘莉多功能工具箱 - 统一打包与独立安装包构建工具 (package.py)
内置 Inno Setup 编译组件支持，摆脱对系统级外部 Inno Setup 安装的依赖。
"""

import os
import sys
import argparse
import subprocess
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from toolbox.core.plugin_exporter import PluginExporter
from toolbox.core.paths import get_bin_dir


def check_iscc() -> Optional[str]:
    iscc_path = PluginExporter.find_iscc_executable()
    if iscc_path and os.path.isfile(iscc_path):
        is_embedded = "bin" in iscc_path.lower() and "innosetup" in iscc_path.lower()
        tag = "[内置便携组件]" if is_embedded else "[系统外部安装]"
        print(f"[OK] 找到 Inno Setup 编译器 {tag}: {iscc_path}")
        return iscc_path
    print("[-] 未能在工程 bin/InnoSetup 或系统中找到 Inno Setup 编译器 (ISCC.exe)")
    return None


def build_installer(iss_path: Optional[str] = None, output_dir: Optional[str] = None) -> bool:
    """使用内置/检测到的 Inno Setup 编译安装包"""
    iscc = check_iscc()
    if not iscc:
        print("[错误] 缺少 Inno Setup 编译器，无法生成原生 EXE 安装包")
        return False

    if not iss_path:
        cand_iss = [
            os.path.join(PROJECT_ROOT, "build_installer.iss"),
            os.path.join(PROJECT_ROOT, "ChieriToolbox.iss"),
        ]
        for c in cand_iss:
            if os.path.isfile(c):
                iss_path = c
                break

    if not iss_path or not os.path.isfile(iss_path):
        print(f"[错误] 未找到 Inno Setup 脚本文件: {iss_path}")
        return False

    cmd = [iscc, iss_path]
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        cmd.append(f"/O{output_dir}")

    print(f"\n[构建] 开始使用 Inno Setup 编译安装包...")
    print(f"脚本文件: {iss_path}")
    print(f"编译器路径: {iscc}")

    try:
        proc = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace")
        if proc.returncode == 0:
            print("\n=======================================================")
            print(" [√] Inno Setup 原生 EXE 安装包编译成功！")
            print("=======================================================")
            return True
        else:
            print(f"\n[错误] ISCC 编译失败 (返回码 {proc.returncode}):")
            print(proc.stderr or proc.stdout[-800:])
            return False
    except Exception as e:
        print(f"[异常] 执行 Inno Setup 异常: {e}")
        return False


def export_plugin(plugin_id: str, output_dir: Optional[str] = None, compile_setup: bool = True) -> bool:
    """使用内置 Inno Setup 编译组件导出独立插件"""
    if not output_dir:
        output_dir = os.path.join(PROJECT_ROOT, "dist", f"Plugin_{plugin_id}")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n[导出插件] 正在导出独立应用: {plugin_id} -> {output_dir}")
    res = PluginExporter.export_plugin(
        plugin_id=plugin_id,
        output_dir=output_dir,
        create_shortcuts=True,
        autostart_default=False,
        create_archive=True,
        compile_inno_setup=compile_setup
    )

    if res.get("success"):
        print(f"[√] 插件 {plugin_id} 导出成功！")
        if res.get("installer_exe"):
            print(f"    原生安装包: {res['installer_exe']}")
        if res.get("archive_path"):
            print(f"    绿色便携包: {res['archive_path']}")
        return True
    else:
        print(f"[-] 插件 {plugin_id} 导出失败: {res.get('error')}")
        return False


def main():
    parser = argparse.ArgumentParser(description="千绘莉工具箱统一打包构建工具 (内置 Inno Setup 支持)")
    parser.add_argument("--check-iscc", action="store_true", help="检测并显示 Inno Setup 编译器路径")
    parser.add_argument("--installer", action="store_true", help="编译主工具箱原生 Inno Setup 安装包")
    parser.add_argument("--iss", type=str, default=None, help="指定的 .iss 脚本路径")
    parser.add_argument("--plugin", type=str, default=None, help="导出指定插件为独立应用/安装包 (如 media_downloader)")
    parser.add_argument("--all-plugins", action="store_true", help="一键导出所有插件")
    parser.add_argument("--output", type=str, default=None, help="指定构建输出目录")

    args = parser.parse_args()

    if args.check_iscc:
        check_iscc()
        return

    if args.plugin:
        ok = export_plugin(args.plugin, output_dir=args.output, compile_setup=True)
        sys.exit(0 if ok else 1)

    if args.all_plugins:
        from toolbox.core.plugin_manager import PluginManager
        pm = PluginManager()
        plugins = pm.discover_and_load()
        success_cnt = 0
        for p in plugins:
            if export_plugin(p.id, output_dir=args.output, compile_setup=True):
                success_cnt += 1
        print(f"\n[全量导出完成] 成功: {success_cnt}/{len(plugins)}")
        sys.exit(0 if success_cnt == len(plugins) else 1)

    # 默认行为: 检查编译器并编译主安装包
    if args.installer or (not args.plugin and not args.all_plugins and not args.check_iscc):
        ok = build_installer(iss_path=args.iss, output_dir=args.output)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
