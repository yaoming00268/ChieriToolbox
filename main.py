"""
千绘莉的多功能工具箱 (Chieri Toolbox)
统一跨工作区启动入口
"""

import sys
import os
import json
import subprocess
import tempfile
import traceback

if sys.platform == "win32":
    import ctypes
    system_icu = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "icuuc.dll")
    if os.path.exists(system_icu):
        try:
            ctypes.CDLL(system_icu)
        except Exception:
            pass

# 针对 Windows 窗口模式 (--noconsole) 命令行传参时的控制台控制与流重定向
if sys.platform == "win32" and len(sys.argv) > 1:
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h_stdout = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        h_stderr = kernel32.GetStdHandle(-12)  # STD_ERROR_HANDLE
        type_stdout = kernel32.GetFileType(h_stdout) if h_stdout else 0
        # FILE_TYPE_CHAR = 2, FILE_TYPE_PIPE = 3, FILE_TYPE_DISK = 1
        if type_stdout in (1, 3):
            # 标准输出被管道或文件重定向 (如 subprocess capture_output 或 shell 重定向)
            if sys.stdout is None:
                import io
                import msvcrt
                try:
                    fd_out = msvcrt.open_osfhandle(h_stdout, 0)
                    sys.stdout = io.TextIOWrapper(open(fd_out, "wb", closefd=False), encoding="utf-8", errors="replace")
                except Exception:
                    pass
            if sys.stderr is None:
                import io
                import msvcrt
                try:
                    fd_err = msvcrt.open_osfhandle(h_stderr, 0)
                    sys.stderr = io.TextIOWrapper(open(fd_err, "wb", closefd=False), encoding="utf-8", errors="replace")
                except Exception:
                    pass
        else:
            # 交互式控制台模式下挂载至父进程控制台
            if kernel32.AttachConsole(-1):
                try:
                    sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                    sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                except Exception:
                    pass
    except Exception:
        pass


class SafeStream:
    """在 Windows 无控制台模式下避免输出流为 None 引发异常的安全输出流"""
    def write(self, text):
        pass

    def flush(self):
        pass


if sys.stdout is None:
    sys.stdout = SafeStream()
if sys.stderr is None:
    sys.stderr = SafeStream()

# 将当前根目录加入系统模块搜索路径
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

try:
    from toolbox.app import ToolboxApp
except Exception as e:
    import traceback
    print(f"[main.py] ToolboxApp import failed: {e}", file=sys.stderr)
    traceback.print_exc()
    ToolboxApp = None


def run_smoke_test() -> int:
    """
    自动化自检与打包深度烟雾测试入口。
    全面验证：
    1. 运行态环境与路径自适应系统 (paths)
    2. 配置管理器持久化读写
    3. 内置外部二进制工具寻路与真实进程执行 (ffmpeg, 7z, ffprobe, ffplay)
    4. 7-Zip 与 7z.dll 真实加解压流
    5. 全量 22 个功能插件动态发现与 UI 界面实例化
    """
    print("=" * 60)
    print(">>> 启动千绘莉多功能工具箱打包分发深度自检 (Smoke Test)...")
    print("=" * 60)

    from toolbox.core.paths import is_frozen, get_bundle_dir, get_app_root, get_bin_path, get_config_path
    from toolbox.core.config_manager import ConfigManager
    from toolbox.core.plugin_manager import PluginManager
    from toolbox.plugins.media_downloader.downloader import find_ffmpeg_executable
    from toolbox.plugins.archive_manager.engine import find_7z_executable

    report = {
        "status": "pending",
        "frozen": is_frozen(),
        "executable": sys.executable,
        "bundle_dir": get_bundle_dir(),
        "app_root": get_app_root(),
        "config_path": get_config_path(),
        "binaries": {},
        "plugins": [],
        "errors": []
    }

    print(f"[*] 运行环境: {'PyInstaller 冻结打包态 (Frozen)' if is_frozen() else '源码解释态 (Source)'}")
    print(f"[*] 宿主程序: {sys.executable}")
    print(f"[*] 资源根路径: {get_bundle_dir()}")
    print(f"[*] 程序根路径: {get_app_root()}")

    # 1. 配置管理器持久化读写测试
    print("\n--- 1. 验证配置管理器 (ConfigManager) ---")
    try:
        cfg = ConfigManager()
        cfg_theme = cfg.get("theme", "system")
        cfg.set("last_smoke_test", "passed")
        cfg.save()
        report["config_status"] = "ok"
        print(f"[OK] 配置读写正常，当前配置文件路径: {cfg.config_file} (主题: {cfg_theme})")
    except Exception as e:
        err = f"ConfigManager 读写失败: {e}"
        report["errors"].append(err)
        print(f"[FAIL] {err}")

    # 2. 外部二进制工具寻路与真实执行验证
    print("\n--- 2. 验证核心二进制工具寻路与执行 ---")
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    tools = [
        ("ffmpeg", find_ffmpeg_executable(), ["-version"]),
        ("7z", find_7z_executable(), ["i"]),
        ("ffprobe", get_bin_path("ffprobe.exe"), ["-version"]),
        ("ffplay", get_bin_path("ffplay.exe"), ["-version"]),
    ]

    for name, path, test_args in tools:
        report["binaries"][name] = path
        if not path or not os.path.isfile(path):
            err = f"未找到外部工具: {name} (寻路路径: {path})"
            report["errors"].append(err)
            print(f"[FAIL] {name}: 缺失二进制文件!")
            continue

        try:
            cmd = [path] + test_args
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                text=True,
                timeout=10
            )
            if proc.returncode == 0:
                print(f"[OK] {name}: 寻路成功 ({path})，指令执行返回码 0")
            else:
                err = f"{name} 执行异常，返回码: {proc.returncode}"
                report["errors"].append(err)
                print(f"[FAIL] {name}: 执行失败 (返回码 {proc.returncode})")
        except Exception as e:
            err = f"{name} 子进程调用失败: {e}"
            report["errors"].append(err)
            print(f"[FAIL] {name}: {err}")

    # 3. 7-Zip 压缩解压真实闭环业务测试
    print("\n--- 3. 验证 7-Zip 与 7z.dll 实际压缩/解压闭环 ---")
    p7z = find_7z_executable()
    if p7z and os.path.isfile(p7z):
        tmp_dir = tempfile.mkdtemp()
        try:
            sample_txt = os.path.join(tmp_dir, "sample.txt")
            sample_7z = os.path.join(tmp_dir, "sample.7z")
            extract_dir = os.path.join(tmp_dir, "extracted")
            with open(sample_txt, "w", encoding="utf-8") as f:
                f.write("ChieriToolbox Smoke Test 2026")

            # 压缩
            subprocess.run([p7z, "a", sample_7z, sample_txt], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags, check=True)
            # 解压
            subprocess.run([p7z, "x", sample_7z, f"-o{extract_dir}", "-y"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags, check=True)
            
            restored_txt = os.path.join(extract_dir, "sample.txt")
            if os.path.isfile(restored_txt):
                with open(restored_txt, "r", encoding="utf-8") as f:
                    content = f.read()
                if "ChieriToolbox" in content:
                    print(f"[OK] 7-Zip LZMA2 压缩与解包自检全通")
                else:
                    report["errors"].append("7-Zip 解压文本校验失败")
                    print(f"[FAIL] 7-Zip 解压文本校验失败")
            else:
                report["errors"].append("7-Zip 解压产物丢失")
                print(f"[FAIL] 7-Zip 解压产物丢失")
        except Exception as e:
            err = f"7-Zip 功能测试异常: {e}"
            report["errors"].append(err)
            print(f"[FAIL] {err}")
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # 4. 全量 28 个插件动态发现与 UI 实例化验证
    print("\n--- 4. 验证全量 28 个插件动态发现与 UI 实例化 ---")
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance()
    if not _app:
        _app = QApplication(["--platform", "offscreen"])

    try:
        pm = PluginManager()
        pm.discover_and_load()
        plugins = pm.get_all_plugins()
        print(f"[*] 成功扫描并加载插件总数: {len(plugins)} / 28")

        for p in plugins:
            try:
                w = p.create_widget()
                if w is None:
                    err = f"插件 [{p.id}] create_widget() 返回了 None"
                    report["errors"].append(err)
                    print(f"[FAIL] 插件 [{p.id}] 界面构造失败")
                else:
                    report["plugins"].append({
                        "id": p.id,
                        "name": p.name,
                        "category": p.category,
                        "version": p.version,
                        "widget_class": w.__class__.__name__
                    })
                    print(f"[OK] 插件: [{p.name}] (ID: {p.id}) -> UI: {w.__class__.__name__}")
            except Exception as e:
                err = f"插件 [{p.id}] 界面实例化异常: {e}\n{traceback.format_exc()}"
                report["errors"].append(err)
                print(f"[FAIL] 插件 [{p.id}] 界面异常: {e}")

        if len(plugins) < 28:
            err = f"预期加载至少 28 个插件，实际仅加载 {len(plugins)} 个！"
            report["errors"].append(err)
            print(f"[FAIL] {err}")
    except Exception as e:
        err = f"PluginManager 流程异常: {e}\n{traceback.format_exc()}"
        report["errors"].append(err)
        print(f"[FAIL] {err}")

    # 5. 验证独立插件 Setup 安装包导出引擎 (PluginExporter)
    print("\n--- 5. 验证独立插件 Setup 安装包导出 (PluginExporter) ---")
    try:
        import shutil
        from toolbox.core.plugin_exporter import PluginExporter
        from toolbox.ui.plugin_export_dialog import PluginExportDialog
        from toolbox.ui.standalone_exporter_dialog import StandaloneExporterDialog
        export_tmp = tempfile.mkdtemp()
        res = PluginExporter.export_plugin(
            plugin_id="force_killer",
            output_dir=export_tmp,
            package_type="setup",
            create_shortcuts=False,
            autostart_default=False,
            create_archive=True,
            generate_pyinstaller_spec=True
        )
        if res.get("success"):
            target_out = res.get("output_dir")
            archive_p = res.get("archive_path")
            has_launch = os.path.isfile(os.path.join(target_out, "launch.bat"))
            has_installer = os.path.isfile(os.path.join(target_out, "installer.py"))
            has_setup = os.path.isfile(os.path.join(target_out, "setup.bat"))
            has_zip = archive_p and os.path.isfile(archive_p)
            if has_launch and has_installer and has_setup and has_zip:
                print(f"[OK] PluginExporter 独立安装包生成与 ZIP 封装成功")
            else:
                err = f"PluginExporter 导出文件不完整: launch={has_launch}, installer={has_installer}, setup={has_setup}, zip={has_zip}"
                report["errors"].append(err)
                print(f"[FAIL] {err}")
        else:
            err = f"PluginExporter 导出失败: {res.get('error')}"
            report["errors"].append(err)
            print(f"[FAIL] {err}")
        shutil.rmtree(export_tmp, ignore_errors=True)
    except Exception as e:
        err = f"PluginExporter 测试异常: {e}\n{traceback.format_exc()}"
        report["errors"].append(err)
        print(f"[FAIL] {err}")

    # 6. 验证插件系统托盘与快捷菜单 (TrayManager)
    print("\n--- 6. 验证插件系统托盘与快捷菜单 (TrayManager) ---")
    try:
        from toolbox.core.tray_manager import TrayManager, PluginTrayIcon
        tray_mgr = TrayManager()
        test_plugin = plugins[0]
        tray_icon = tray_mgr.add_plugin_tray_icon(
            test_plugin,
            on_open_callback=lambda: None,
            on_settings_callback=lambda: None,
            on_exit_callback=lambda: None,
            on_export_callback=lambda: None
        )
        if tray_icon and test_plugin.id in tray_mgr.get_active_plugin_ids():
            print(f"[OK] TrayManager 成功注册插件托盘图标: [{test_plugin.name}]")
        else:
            err = "TrayManager 注册插件托盘图标失败"
            report["errors"].append(err)
            print(f"[FAIL] {err}")
        tray_mgr.remove_tray_icon(test_plugin.id)
        tray_mgr.cleanup_all()
    except Exception as e:
        err = f"TrayManager 测试异常: {e}\n{traceback.format_exc()}"
        report["errors"].append(err)
        print(f"[FAIL] {err}")

    # 7. 验证自定义分组与默认启动分组配置 (Custom Groups & Default Group)
    print("\n--- 7. 验证自定义分组与默认启动分组配置 ---")
    try:
        from toolbox.ui.home_page import HomePage
        hp = HomePage(plugins=plugins)
        if hp.card_widgets:
            card = hp.card_widgets[0]
            assert hasattr(card, "card_context_menu_requested"), "Card missing context menu signal"
            print(f"[OK] HomePage 卡片右键快捷上下文菜单信号绑定完备")

        grp_name = "烟雾测试临时分组"
        target_pid = plugins[0].id
        try:
            hp._add_plugin_to_group(target_pid, grp_name, default_category=plugins[0].category)
            if cfg.is_plugin_in_group(target_pid, grp_name, plugins[0].category):
                print(f"[OK] 自定义分组添加插件成功")
            else:
                err = "自定义分组添加插件失败"
                report["errors"].append(err)
                print(f"[FAIL] {err}")

            hp._remove_plugin_from_group(target_pid, grp_name, default_category=plugins[0].category)
            if not cfg.is_plugin_in_group(target_pid, grp_name, plugins[0].category):
                print(f"[OK] 自定义分组移出插件成功")
            else:
                err = "自定义分组移出插件失败"
                report["errors"].append(err)
                print(f"[FAIL] {err}")

            cfg.set_default_group("全部")
            assert cfg.get_default_group() == "全部"
            cfg.set_default_group(grp_name)
            assert cfg.get_default_group() == grp_name
            cfg.set_default_group("全部")
        finally:
            # 彻底清理烟雾测试临时创建的自定义分组，杜绝污染用户本地配置文件
            cfg.delete_custom_group(grp_name, auto_save=True)
            cfg.set_default_group("全部")

        print(f"[OK] 默认启动分组读写与持久化配置正常 (已自动销毁临时分组)")
        hp.close()
    except Exception as e:
        err = f"HomePage 自定义分组测试异常: {e}\n{traceback.format_exc()}"
        report["errors"].append(err)
        print(f"[FAIL] {err}")

    # 8. 验证独立插件运行引擎与专属设置面板 (StandaloneRunner)
    print("\n--- 8. 验证独立插件运行引擎与设置对话框 ---")
    try:
        from toolbox.standalone_runner import StandalonePluginMainWindow
        from toolbox.ui.standalone_settings_dialog import StandalonePluginSettingsDialog
        target_plugin = plugins[0]
        swin = StandalonePluginMainWindow(target_plugin)
        assert target_plugin.name in swin.windowTitle()
        sdlg = StandalonePluginSettingsDialog(target_plugin, parent=swin)
        assert target_plugin.name in sdlg.windowTitle()
        sdlg.close()
        swin.close()
        print(f"[OK] StandalonePluginMainWindow 与 StandalonePluginSettingsDialog 实例化成功")
    except Exception as e:
        err = f"StandaloneRunner 测试异常: {e}\n{traceback.format_exc()}"
        report["errors"].append(err)
        print(f"[FAIL] {err}")

    # 9. 验证 B 站媒体下载器新功能模块链路 (暂停/恢复、断点检测、单项画质微调、内置 Inno Setup)
    print("\n--- 9. 验证 B 站媒体下载器新功能链路与依赖完整性 ---")
    try:
        from toolbox.plugins.media_downloader.downloader import (
            MediaDownloadWorker,
            check_item_downloaded,
            get_task_target_filename
        )
        from toolbox.plugins.media_downloader.ui import MediaDownloaderWidget
        from toolbox.plugins.media_downloader.api import QUALITY_MAP

        # 9.1 文件名与已下载智能检测
        test_task = {"title": "测试视频", "part": "P01_测试", "bvid": "BV1_SMOKE"}
        fn = get_task_target_filename(test_task, audio_only=False)
        assert fn.endswith(".mp4"), f"生成文件名异常: {fn}"
        
        # 9.2 暂停/恢复状态机
        worker = MediaDownloadWorker(
            video_url="http://127.0.0.1/fake_v",
            audio_url="http://127.0.0.1/fake_a",
            save_dir=get_app_root(),
            title="smoke_test_task"
        )
        assert not worker._is_paused
        worker.pause()
        assert worker._is_paused
        worker.resume()
        assert not worker._is_paused

        # 9.3 下载器界面新特性属性校验
        mw = MediaDownloaderWidget()
        assert hasattr(mw, "btn_detect_downloaded"), "缺少已下载检测按钮"
        assert hasattr(mw, "btn_retry_failed"), "缺少一键重试未下载按钮"
        assert hasattr(mw, "btn_pause_resume"), "缺少暂停/恢复按钮"
        assert hasattr(mw, "combo_item_quality"), "缺少单项画质选择框"
        assert hasattr(mw, "btn_apply_quality_to_checked"), "缺少批量应用画质按钮"
        assert hasattr(mw, "cb_skip_existing"), "缺少跳过已下载复选框"
        assert hasattr(mw, "_retry_failed_items"), "缺少重试未下载项方法"
        assert hasattr(mw, "_detect_downloaded_items"), "缺少检测已下载方法"
        assert hasattr(mw, "_apply_quality_to_checked"), "缺少批量应用画质方法"
        mw.close()

        # 9.4 内置 Inno Setup 编译器定位健全性
        iscc = PluginExporter.find_iscc_executable()
        if iscc and os.path.isfile(iscc):
            report["binaries"]["inno_setup_iscc"] = iscc
            print(f"[OK] B站下载器新功能、状态机与内置 Inno Setup 验证全部通过 (ISCC: {iscc})")
        else:
            err = "未能在打包环境中找到内置 Inno Setup 编译器 (ISCC.exe)"
            report["errors"].append(err)
            print(f"[FAIL] {err}")
    except Exception as e:
        err = f"B站下载器新功能验证异常: {e}\n{traceback.format_exc()}"
        report["errors"].append(err)
        print(f"[FAIL] {err}")

    # 汇总输出与报告持久化
    report["status"] = "passed" if not report["errors"] else "failed"
    report_file = os.path.join(get_app_root(), "smoke_test_report.json")
    try:
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n[+] 诊断测试报告已持久化写入: {report_file}")
    except Exception as e:
        print(f"[-] 写入报告失败: {e}")

    print("=" * 60)
    if report["status"] == "passed":
        print(">>> 综合自检结果: 全部通过 (PASSED)！打包环境完备可靠。")
    else:
        print(f">>> 综合自检结果: 存在错误 (FAILED)！共 {len(report['errors'])} 项错误。")
    print("=" * 60 + "\n")

    return 0 if report["status"] == "passed" else 1


def run_visual_test(out_png: str = "verified_packaged_window.png") -> int:
    """自动化视觉验收截屏"""
    import time
    from PySide6.QtWidgets import QApplication
    from toolbox.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.resize(1120, 750)
    win.show()
    for _ in range(10):
        QApplication.processEvents()
        time.sleep(0.1)

    pix = win.grab()
    out_path = os.path.abspath(out_png)
    pix.save(out_path)
    print(f"[+] 成功生成窗口渲染快照: {out_path} ({os.path.getsize(out_path)} 字节)")
    win.close()
    return 0


def main():
    initial_args = sys.argv[1:] if len(sys.argv) > 1 else None

    # 命令行快速自检模式
    if initial_args and any(arg in initial_args for arg in ("--smoke-test", "--check", "--diagnose")):
        sys.exit(run_smoke_test())

    # 自动化视觉渲染截屏验收模式
    if initial_args and any(arg in initial_args for arg in ("--visual-test", "--screenshot")):
        out_name = "verified_packaged_window.png"
        for arg in initial_args:
            if arg.endswith(".png"):
                out_name = arg
        sys.exit(run_visual_test(out_name))

    # 独立插件启动模式 (--plugin <id> [--autostart])
    if initial_args and "--plugin" in initial_args:
        idx = initial_args.index("--plugin")
        if idx + 1 < len(initial_args):
            target_plugin_id = initial_args[idx + 1]
            autostart = "--autostart" in initial_args
            extra_paths = [arg for arg in initial_args if not arg.startswith("--") and arg != target_plugin_id]
            from toolbox.standalone_runner import launch_standalone
            sys.exit(launch_standalone(target_plugin_id, autostart=autostart, initial_paths=extra_paths))

    # 单实例唤醒与参数转发机制 (避免资源管理器右键多选引发多进程风暴)
    if not (initial_args and any(arg in initial_args for arg in ("--no-single-instance", "--plugin", "--smoke-test", "--check", "--diagnose", "--visual-test", "--screenshot"))):
        try:
            from toolbox.app import check_and_forward_single_instance
            if check_and_forward_single_instance(initial_args):
                print("[SingleInstance] 已将参数转发至正在运行的工具箱主窗口实例，退出当前冗余进程。")
                sys.exit(0)
        except Exception:
            pass

    try:
        if ToolboxApp is None:
            raise RuntimeError("ToolboxApp 模块导入失败，请检查安装环境与依赖项。")
        app = ToolboxApp(sys.argv)
        sys.exit(app.run(initial_args))
    except Exception as e:
        crash_log = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "crash.log")
        try:
            with open(crash_log, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()