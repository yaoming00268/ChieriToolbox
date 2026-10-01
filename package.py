"""
千绘莉多功能工具箱 - 统一打包与独立安装包构建工具 (package.py)
内置 Inno Setup 编译组件支持，摆脱对系统级外部 Inno Setup 安装的依赖。

功能架构:
1. PyInstaller 独立分发打包: 将整个工程及其 22 个插件解耦打包至 dist/ChieriToolbox
2. 自动化打包深度冒烟测试 (Smoke Test): 运行打包出的 ChieriToolbox.exe --smoke-test，验证全量插件与依赖
3. 绿色免安装便携版归档 (Portable Zip): 高效压缩打包产物至 dist/ChieriToolbox-v2.0.0-Portable.zip
4. 原生 Inno Setup 安装包构建 (Setup Installer): 使用内置 bin/InnoSetup/ISCC.exe 编译 dist/Setup_ChieriToolbox.exe
5. 单插件 / 全量插件解耦独立导出支持 (export_plugin)
"""

import os
import sys
import shutil
import argparse
import subprocess
from typing import Optional

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from toolbox.core.plugin_exporter import PluginExporter
from toolbox.core.paths import get_bin_dir


def get_python_executable() -> str:
    """获取具备打包环境依赖的 Python 解释器路径"""
    venv_py = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
    if os.path.isfile(venv_py):
        return venv_py
    return sys.executable


def check_iscc() -> Optional[str]:
    iscc_path = PluginExporter.find_iscc_executable()
    if iscc_path and os.path.isfile(iscc_path):
        is_embedded = "bin" in iscc_path.lower() and "innosetup" in iscc_path.lower()
        tag = "[内置便携组件]" if is_embedded else "[系统外部安装]"
        print(f"[OK] 找到 Inno Setup 编译器 {tag}: {iscc_path}")
        return iscc_path
    print("[-] 未能在工程 bin/InnoSetup 或系统中找到 Inno Setup 编译器 (ISCC.exe)")
    return None


def build_pyinstaller(spec_path: Optional[str] = None) -> bool:
    """使用 PyInstaller 执行主程序及其全部插件的一体化独立分发打包"""
    if not spec_path:
        spec_path = os.path.join(PROJECT_ROOT, "toolbox.spec")

    if not os.path.isfile(spec_path):
        print(f"[错误] 未找到 PyInstaller 配置文件: {spec_path}")
        return False

    py_exec = get_python_executable()
    cmd = [py_exec, "-m", "PyInstaller", "--clean", "-y", spec_path]

    print(f"\n=======================================================")
    print(f" [1/4 构建步骤] 开始执行 PyInstaller 分发打包...")
    print(f" Spec 配置文件: {spec_path}")
    print(f" Python 解释器: {py_exec}")
    print(f"=======================================================")

    try:
        proc = subprocess.run(cmd, cwd=PROJECT_ROOT)
        if proc.returncode == 0:
            output_exe = os.path.join(PROJECT_ROOT, "dist", "ChieriToolbox", "ChieriToolbox.exe")
            if os.path.isfile(output_exe):
                exe_size = os.path.getsize(output_exe) / (1024 * 1024)
                print(f"\n[√] PyInstaller 构建成功！独立可执行文件: {output_exe} ({exe_size:.2f} MB)")
                return True
            else:
                print(f"[错误] 构建完成但未找到产物: {output_exe}")
                return False
        else:
            print(f"[错误] PyInstaller 打包失败，退出码: {proc.returncode}")
            return False
    except Exception as e:
        print(f"[异常] 执行 PyInstaller 异常: {e}")
        return False


def run_smoke_test(exe_path: Optional[str] = None) -> bool:
    """对打包生成的独立可执行文件执行深度冒烟自检"""
    if not exe_path:
        exe_path = os.path.join(PROJECT_ROOT, "dist", "ChieriToolbox", "ChieriToolbox.exe")

    if not os.path.isfile(exe_path):
        print(f"[错误] 未找到待验证的可执行文件: {exe_path}")
        return False

    report_path = os.path.join(os.path.dirname(exe_path), "smoke_test_report.json")
    if os.path.isfile(report_path):
        try:
            os.remove(report_path)
        except Exception:
            pass

    print(f"\n=======================================================")
    print(f" [2/4 测试步骤] 启动打包产物深度冒烟自检 (Smoke Test)...")
    print(f" 测试目标: {exe_path}")
    print(f"=======================================================")

    try:
        proc = subprocess.run(
            [exe_path, "--smoke-test"],
            cwd=os.path.dirname(exe_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180
        )
        if proc.stdout:
            try:
                print(proc.stdout)
            except Exception:
                safe_out = proc.stdout.encode(sys.stdout.encoding or "gbk", errors="replace").decode(sys.stdout.encoding or "gbk", errors="replace")
                print(safe_out)
        if proc.stderr:
            try:
                print(proc.stderr)
            except Exception:
                safe_err = proc.stderr.encode(sys.stderr.encoding or "gbk", errors="replace").decode(sys.stderr.encoding or "gbk", errors="replace")
                print(safe_err)

        # 深度验证 smoke_test_report.json 报告
        if os.path.isfile(report_path):
            try:
                import json
                with open(report_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                status = data.get("status")
                errors = data.get("errors", [])
                plugins = data.get("plugins", [])
                binaries = data.get("binaries", {})
                print(f"[自检报告解析] 状态: {status} | 插件数: {len(plugins)}/22 | 外部二进制: {list(binaries.keys())} | 错误数: {len(errors)}")
                if status == "passed" and len(errors) == 0 and len(plugins) >= 22 and proc.returncode == 0:
                    print("\n=======================================================")
                    print(f" [√] 打包独立可执行文件冒烟测试深度验证全数通过 (PASSED)！共 {len(plugins)} 项插件与新特性完备。")
                    print("=======================================================")
                    return True
                else:
                    print(f"[错误] 冒烟测试自检报告未满足通过条件: status={status}, errors={errors}")
                    return False
            except Exception as e_json:
                print(f"[-] 解析 smoke_test_report.json 异常: {e_json}")

        if proc.returncode == 0:
            print("\n=======================================================")
            print(" [√] 打包独立可执行文件冒烟测试返回码 0！")
            print("=======================================================")
            return True
        else:
            print(f"[错误] 打包产物冒烟自检失败，退出码: {proc.returncode}")
            return False
    except Exception as e:
        print(f"[异常] 执行冒烟自检异常: {e}")
        return False


def build_portable_zip(source_dir: Optional[str] = None, output_zip: Optional[str] = None) -> bool:
    """将打包完成的目录封装为绿色免安装 Portable ZIP 包"""
    if not source_dir:
        source_dir = os.path.join(PROJECT_ROOT, "dist", "ChieriToolbox")
    if not output_zip:
        output_zip = os.path.join(PROJECT_ROOT, "dist", "ChieriToolbox-v2.0.0-Portable.zip")

    if not os.path.isdir(source_dir):
        print(f"[错误] 待压缩目录不存在: {source_dir}")
        return False

    print(f"\n=======================================================")
    print(f" [3/4 封装步骤] 开始生成绿色免安装 Portable ZIP 压缩包...")
    print(f" 源目录: {source_dir}")
    print(f" 目标文件: {output_zip}")
    print(f"=======================================================")

    if os.path.exists(output_zip):
        try:
            os.remove(output_zip)
        except Exception:
            pass

    # 优先采用内置 7-Zip (7z.exe) 进行 LZMA/Deflate 高压缩比封包
    p7z = os.path.join(PROJECT_ROOT, "bin", "7z.exe")
    if os.path.isfile(p7z):
        cmd = [
            p7z, "a", "-tzip", "-mx=9",
            output_zip,
            "*",
            "-xr!*.log",
            "-xr!*.tmp",
            "-xr!*.m4s",
            "-xr!*.bak",
            "-xr!smoke_test_report.json",
            "-xr!verified_*.png",
            "-xr!toolbox_config.json",
            "-xr!*.local.json",
            "-xr!test_*.txt"
        ]
        try:
            proc = subprocess.run(cmd, cwd=source_dir, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if proc.returncode == 0 and os.path.isfile(output_zip):
                size_mb = os.path.getsize(output_zip) / (1024 * 1024)
                print(f"[√] 7-Zip 高效压缩完成: {output_zip} ({size_mb:.2f} MB)")
                return True
            else:
                print(f"[-] 7z 压缩出现警告，转由 Python 内置 zipfile 模块处理")
        except Exception as e:
            print(f"[-] 7z 调用异常: {e}")

    # 备用方案: Python zipfile
    import zipfile
    exclude_patterns = [".log", ".tmp", ".m4s", ".bak", "smoke_test_report.json", "verified_", "toolbox_config.json", ".local.json", "test_"]
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(source_dir):
            for f in files:
                if any(f.endswith(pat) or pat in f for pat in exclude_patterns):
                    continue
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, source_dir)
                zf.write(full_path, rel_path)

    size_mb = os.path.getsize(output_zip) / (1024 * 1024)
    print(f"[√] Python zipfile 压缩完成: {output_zip} ({size_mb:.2f} MB)")
    return True


def build_installer(iss_path: Optional[str] = None, output_dir: Optional[str] = None) -> bool:
    """使用内置/检测到的 Inno Setup 编译原生 EXE 安装包"""
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

    print(f"\n=======================================================")
    print(f" [4/4 封装步骤] 开始使用 Inno Setup 编译原生 EXE 安装包...")
    print(f" 脚本文件: {iss_path}")
    print(f" 编译器路径: {iscc}")
    print(f"=======================================================")

    try:
        proc = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace")
        if proc.returncode == 0:
            setup_exe = os.path.join(output_dir or os.path.join(PROJECT_ROOT, "dist"), "Setup_ChieriToolbox.exe")
            exe_size = os.path.getsize(setup_exe) / (1024 * 1024) if os.path.isfile(setup_exe) else 0
            print("\n=======================================================")
            print(f" [√] Inno Setup 原生 EXE 安装包编译成功！{setup_exe} ({exe_size:.2f} MB)")
            print("=======================================================")
            return True
        else:
            print(f"\n[错误] ISCC 编译失败 (返回码 {proc.returncode}):")
            print(proc.stderr or proc.stdout[-800:])
            return False
    except Exception as e:
        print(f"[异常] 执行 Inno Setup 异常: {e}")
        return False


def upload_artifacts() -> bool:
    """调用 GitHub Releases 发布脚本上传打包产物 (Setup_ChieriToolbox.exe 和 Portable.zip)"""
    upload_script = os.path.join(PROJECT_ROOT, "scratch", "upload_release.py")
    if not os.path.isfile(upload_script):
        print(f"[错误] 未找到上传脚本: {upload_script}")
        return False

    py_exec = get_python_executable()
    cmd = [py_exec, upload_script]
    print(f"\n=======================================================")
    print(f" [5/5 上传步骤] 开始同步发布分发包至 GitHub Releases...")
    print(f" 上传脚本: {upload_script}")
    print(f" Python 解释器: {py_exec}")
    print(f"=======================================================")

    try:
        proc = subprocess.run(cmd, cwd=PROJECT_ROOT)
        if proc.returncode == 0:
            print("\n=======================================================")
            print(" [√] GitHub Releases 资产同步上传与校验大获全胜！")
            print("=======================================================")
            return True
        else:
            print(f"[错误] GitHub Releases 上传脚本执行失败，退出码: {proc.returncode}")
            return False
    except Exception as e:
        print(f"[异常] 执行 GitHub Releases 上传异常: {e}")
        return False


def build_all(spec_path: Optional[str] = None, iss_path: Optional[str] = None, do_upload: bool = False) -> bool:
    """全流程一体化构建: PyInstaller打包 -> 产物冒烟自检 -> 便携ZIP封装 -> Inno Setup安装包编译 (可选 GitHub 上传)"""
    print("\n#######################################################")
    print("      千绘莉多功能工具箱 (Chieri Toolbox) 一键全量打包流程")
    print("#######################################################\n")

    # 步骤 1: PyInstaller 打包
    if not build_pyinstaller(spec_path):
        print("[-] PyInstaller 构建失败，终止全量打包流程。")
        return False

    # 步骤 2: 产物自检
    if not run_smoke_test():
        print("[-] 打包产物冒烟测试未通过，终止全量打包流程。")
        return False

    # 步骤 3: 便携版 ZIP 压缩
    if not build_portable_zip():
        print("[-] 便携版 ZIP 生成失败，终止全量打包流程。")
        return False

    # 步骤 4: Inno Setup 原生 EXE 安装包
    if not build_installer(iss_path):
        print("[-] Inno Setup 安装包构建失败，终止全量打包流程。")
        return False

    # 步骤 5 (可选): GitHub Releases 同步上传
    if do_upload:
        if not upload_artifacts():
            print("[-] GitHub Releases 资产上传失败，请检查网络或凭据。")
            return False

    print("\n=======================================================")
    print(" [√] 千绘莉多功能工具箱全量分发包与安装包构建大获全胜！")
    print("=======================================================\n")
    return True


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
    parser.add_argument("--all", action="store_true", help="执行完整构建流程 (PyInstaller 打包 -> 冒烟测试 -> 便携 ZIP -> 原生 EXE 安装包)")
    parser.add_argument("--bundle", action="store_true", help="仅执行 PyInstaller 打包构建 dist/ChieriToolbox")
    parser.add_argument("--smoke-test", action="store_true", help="仅对已打包的可执行文件执行冒烟深度测试")
    parser.add_argument("--portable", "--zip", action="store_true", dest="portable", help="仅生成绿色免安装 Portable ZIP 压缩包")
    parser.add_argument("--installer", action="store_true", help="仅编译主工具箱原生 Inno Setup 安装包")
    parser.add_argument("--upload", action="store_true", help="上传构建产物 (Setup 与 Portable) 至 GitHub Releases")
    parser.add_argument("--iss", type=str, default=None, help="指定的 .iss 脚本路径")
    parser.add_argument("--spec", type=str, default=None, help="指定的 .spec 脚本路径")
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

    if args.bundle:
        ok = build_pyinstaller(spec_path=args.spec)
        sys.exit(0 if ok else 1)

    if args.smoke_test:
        ok = run_smoke_test()
        sys.exit(0 if ok else 1)

    if args.portable:
        ok = build_portable_zip()
        sys.exit(0 if ok else 1)

    if args.installer:
        ok = build_installer(iss_path=args.iss, output_dir=args.output)
        sys.exit(0 if ok else 1)

    if args.upload and not args.all:
        ok = upload_artifacts()
        sys.exit(0 if ok else 1)

    # 默认行为或显式指定 --all: 执行全流程一体化构建
    ok = build_all(spec_path=args.spec, iss_path=args.iss, do_upload=args.upload)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
