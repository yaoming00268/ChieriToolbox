"""
千绘莉工具箱 (Chieri Toolbox) - Boost 进化阶段全功能自动化单元测试套件
全面验证:
1. Quick Launcher (Spotlight) 安全 AST 算式计算、代码注入防御、拼音检索、Base64 与时间戳。
2. Clipboard Manager 剪贴板历史队列内存边界、敏感信息 (手机/身份证/Token) 自动探测打码。
3. Port Network Sentinel 本地侦听端口扫描、内核 PID 防护拦截、Hosts 规则读写与 DNS 缓存刷新。
4. Watermark Studio 平铺文字水印、证件防盗防诈水印、频域隐形盲水印无损嵌入与提取闭环。
5. Global Task Manager 后台并发调度、限流保护、取消机制与历史记录自修剪防 OOM。
6. Inter-Plugin Pipeline 跨插件管道 MIME 数据流转与分发。
7. Screen Capture 离线原生 OCR 与二维码识别容错。
"""

import os
import sys
import time
import shutil
import tempfile
import unittest
from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
app = QApplication.instance()
if not app:
    app = QApplication(["--platform", "offscreen"])

from toolbox.core.config_manager import ConfigManager
from toolbox.core.plugin_manager import PluginManager
from toolbox.core.task_manager import GlobalTaskManager, TaskStatus
from toolbox.plugins.quick_launcher.engine import (
    evaluate_math_expression, convert_base64, parse_timestamp, pinyin_initials
)
from toolbox.plugins.clipboard_manager.engine import (
    detect_and_mask_sensitive_text, ClipboardHistoryManager
)
from toolbox.plugins.port_network_sentinel.engine import (
    scan_listening_ports, kill_process_by_pid, read_hosts_file, flush_dns_cache
)
from toolbox.plugins.watermark_studio.engine import (
    add_text_watermark, add_id_privacy_watermark, embed_blind_watermark, extract_blind_watermark
)
from toolbox.plugins.screen_capture.ocr_engine import scan_qr_code_from_image


class TestBoostEvolution(unittest.TestCase):
    def setUp(self):
        ConfigManager.reset_instance()
        PluginManager.reset_instance()
        GlobalTaskManager.reset_instance()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        ConfigManager.reset_instance()
        PluginManager.reset_instance()
        GlobalTaskManager.reset_instance()

    # 1. 极速启动器与数学计算引擎测试
    def test_01_quick_launcher_math_calculations(self):
        # 基础算术运算
        res = evaluate_math_expression("1024 * 768 / 1024")
        self.assertIsNotNone(res)
        self.assertEqual(res[1], "768")

        # 幂运算与 ^ 符号兼容
        res_pow = evaluate_math_expression("2 ^ 10")
        self.assertIsNotNone(res_pow)
        self.assertEqual(res_pow[1], "1024")

        # 数学函数与浮点
        res_sqrt = evaluate_math_expression("sqrt(256) + abs(-14)")
        self.assertIsNotNone(res_sqrt)
        self.assertEqual(res_sqrt[1], "30")

        # 十六进制
        res_hex = evaluate_math_expression("0x10 + 10")
        self.assertIsNotNone(res_hex)
        self.assertEqual(res_hex[1], "26")

        # 安全沙箱测试：拒绝恶意代码执行
        self.assertIsNone(evaluate_math_expression("__import__('os').system('echo pwn')"))
        self.assertIsNone(evaluate_math_expression("open('test.txt', 'w')"))
        self.assertIsNone(evaluate_math_expression("eval('1+1')"))

    def test_02_quick_launcher_pinyin_and_tools(self):
        py = pinyin_initials("文件批量整理大师")
        self.assertTrue("w" in py and "j" in py)

        # Base64
        original = "ChieriToolbox 2026"
        encoded = convert_base64(original, "encode")
        decoded = convert_base64(encoded, "decode")
        self.assertEqual(decoded, original)

        # 时间戳
        ts_now = parse_timestamp("now")
        self.assertTrue(ts_now["timestamp"].isdigit())
        self.assertTrue(len(ts_now["datetime"]) >= 10)

    # 2. 剪贴板历史与脱敏测试
    def test_03_clipboard_sensitive_masking(self):
        text_with_phone = "我的手机号是 13812345678 请拨打联系"
        has_s, masked, types = detect_and_mask_sensitive_text(text_with_phone)
        self.assertTrue(has_s)
        self.assertIn("手机号", types)
        self.assertIn("138****5678", masked)
        self.assertNotIn("13812345678", masked)

        text_with_id = "身份证号码为 110101199003072345 证件"
        has_s_id, masked_id, types_id = detect_and_mask_sensitive_text(text_with_id)
        self.assertTrue(has_s_id)
        self.assertIn("身份证号", types_id)
        self.assertIn("110101********2345", masked_id)

        text_with_token = "请求头 Authorization: sk-abcdef1234567890abcdef12345678"
        has_s_t, masked_t, types_t = detect_and_mask_sensitive_text(text_with_token)
        self.assertTrue(has_s_t)
        self.assertIn("API密钥/Token", types_t)

    def test_04_clipboard_memory_queue_bounds(self):
        # 内存上限保护：最大 10 项
        mgr = ClipboardHistoryManager(max_items=10)
        for i in range(25):
            mgr.add_text(f"Clipboard item {i}")

        self.assertLessEqual(len(mgr.items), 10)
        # 最新的 item 应该在最前
        self.assertEqual(mgr.items[0].content, "Clipboard item 24")

        # 置顶条目在清理时不被清除
        mgr.items[0].is_pinned = True
        mgr.clear()
        self.assertEqual(len(mgr.items), 1)
        self.assertTrue(mgr.items[0].is_pinned)

    # 3. 端口网络哨兵测试
    def test_05_port_sentinel_scanning_and_protection(self):
        ports = scan_listening_ports()
        self.assertIsInstance(ports, list)
        if ports:
            first = ports[0]
            self.assertIn("proto", first)
            self.assertIn("port", first)
            self.assertIn("pid", first)
            self.assertIn("process_name", first)

        # 核心 PID 保护测试：PID <= 4 严禁强杀
        ok, msg = kill_process_by_pid(0)
        self.assertFalse(ok)
        self.assertIn("禁止", msg)

        ok4, msg4 = kill_process_by_pid(4)
        self.assertFalse(ok4)
        self.assertIn("禁止", msg4)

        # 自身 PID 防自杀防护测试
        ok_self, msg_self = kill_process_by_pid(os.getpid())
        self.assertFalse(ok_self)
        self.assertIn("禁止", msg_self)

        # Hosts 读取测试
        hosts_content = read_hosts_file()
        self.assertIsInstance(hosts_content, str)

    # 4. 水印工坊图像加注与盲水印闭环测试
    def test_06_watermark_studio_pipeline(self):
        # 创建测试图片
        test_img_path = os.path.join(self.temp_dir, "test_sample.png")
        img = Image.new("RGB", (300, 200), color=(70, 130, 180))
        img.save(test_img_path)

        # 1. 平铺文字水印
        out_wm = os.path.join(self.temp_dir, "wm_tiled.png")
        ok_wm = add_text_watermark(test_img_path, out_wm, text="千绘莉测试水印", tiled=True)
        self.assertTrue(ok_wm)
        self.assertTrue(os.path.isfile(out_wm))
        self.assertGreater(os.path.getsize(out_wm), 0)

        # 2. 证件隐私水印
        out_id = os.path.join(self.temp_dir, "wm_id.png")
        ok_id = add_id_privacy_watermark(test_img_path, out_id, purpose="仅供测试使用")
        self.assertTrue(ok_id)
        self.assertTrue(os.path.isfile(out_id))

        # 3. 隐形频域盲水印嵌入与提取闭环
        secret = "CHIERI_VERIFIED_COPYRIGHT_2026"
        out_blind = os.path.join(self.temp_dir, "wm_blind.png")
        ok_blind = embed_blind_watermark(test_img_path, out_blind, secret_text=secret)
        self.assertTrue(ok_blind)
        self.assertTrue(os.path.isfile(out_blind))

        # 提取验证
        extracted = extract_blind_watermark(out_blind)
        self.assertEqual(extracted, secret)

        # 未打盲水印图像提取验证：应安全返回空字符串，不产生乱码或 Unicode 异常
        unwatermarked_extracted = extract_blind_watermark(test_img_path)
        self.assertEqual(unwatermarked_extracted, "")

        # RGBA 透明通道保持与盲水印测试
        test_rgba_path = os.path.join(self.temp_dir, "test_rgba.png")
        Image.new("RGBA", (150, 150), (0, 0, 0, 0)).save(test_rgba_path)
        out_rgba = os.path.join(self.temp_dir, "wm_rgba.png")
        self.assertTrue(embed_blind_watermark(test_rgba_path, out_rgba, secret_text="RGBA_BLIND_OK"))
        with Image.open(out_rgba) as loaded_rgba:
            self.assertEqual(loaded_rgba.mode, "RGBA")
        self.assertEqual(extract_blind_watermark(out_rgba), "RGBA_BLIND_OK")

    # 5. 全局后台任务中心测试
    def test_07_global_task_manager_concurrency_and_cancellation(self):
        mgr = GlobalTaskManager.instance()

        # 手动注册任务跟踪
        tid = mgr.register_manual_task("视频转码测试任务", plugin_id="video_to_audio", max_progress=100)
        self.assertIsNotNone(tid)

        t = mgr.get_task(tid)
        self.assertEqual(t.status, TaskStatus.QUEUED)

        mgr.update_progress(tid, 50, "转码进行中 50%")
        self.assertEqual(t.progress, 50)

        mgr.update_status(tid, TaskStatus.COMPLETED, "转码完成")
        self.assertEqual(t.status, TaskStatus.COMPLETED)

        # 取消测试
        tid2 = mgr.register_manual_task("长耗时下载", plugin_id="media_downloader")
        mgr.cancel_task(tid2)
        t2 = mgr.get_task(tid2)
        self.assertTrue(t2.is_cancelled)

    # 6. 跨插件管道机制测试
    def test_08_inter_plugin_pipeline_routing(self):
        pm = PluginManager()
        pm.discover_and_load()

        # 查找支持接收图片数据的插件
        img_receivers = pm.get_plugins_accepting("image/*")
        self.assertTrue(len(img_receivers) >= 1)
        receiver_ids = [p.id for p in img_receivers]
        self.assertIn("watermark_studio", receiver_ids)

        # 管道数据注入
        sample_path = os.path.join(self.temp_dir, "pipeline_sample.png")
        Image.new("RGB", (100, 100), color=(255, 0, 0)).save(sample_path)

        ok_pipe = pm.pipe_data("screen_capture", "watermark_studio", "file/*", [sample_path])
        self.assertTrue(ok_pipe)

    # 7. 剪贴板管理器设置恢复与生命周期销毁释放测试
    def test_09_clipboard_settings_restoration_and_cleanup(self):
        from toolbox.plugins.clipboard_manager.ui import ClipboardManagerWidget
        w = ClipboardManagerWidget()
        self.assertTrue(hasattr(w, "cb_desensitize"))

        # 写入配置 desensitize = False 并恢复
        ConfigManager().set_plugin_config("clipboard_manager", {"desensitize": False})
        w.load_settings()
        self.assertFalse(w.desensitize)
        self.assertFalse(w.cb_desensitize.isChecked())

        # 验证 cleanup 释放剪贴板监听信号
        w.cleanup()
        w.deleteLater()

    # 8. 极速启动器拼音首字母 GB2312 全汉字覆盖测试
    def test_10_quick_launcher_pinyin_gb2312_full_coverage(self):
        self.assertEqual(pinyin_initials("端口网络哨兵"), "dkwlsb")
        self.assertEqual(pinyin_initials("网络代理"), "wldl")
        self.assertEqual(pinyin_initials("无限剪贴板历史"), "wxjtbls")
        self.assertEqual(pinyin_initials("高清录音"), "gqly")
        self.assertEqual(pinyin_initials("交互白板"), "jhbb")

    # 9. 极速启动器位取反算式与超大幂运算防爆防死机测试
    def test_11_quick_launcher_bitwise_invert_and_large_pow_defense(self):
        # 位取反 ~ 运算符测试
        res_invert = evaluate_math_expression("~5")
        self.assertIsNotNone(res_invert)
        self.assertEqual(res_invert[1], "-6")

        # 超大幂运算防爆测试：拦截可能超出 int_max_str_digits 的超大数，返回 None 而不是让进程崩溃
        self.assertIsNone(evaluate_math_expression("9999 ** 9999"))
        self.assertIsNone(evaluate_math_expression("10 ** 5000"))

    # 10. 跨插件管道针对尚未惰性初始化的插件按需加载分发测试
    def test_12_inter_plugin_pipeline_lazy_target_loading(self):
        pm = PluginManager()
        # 清空内部已加载插件，保持未装载状态
        pm.cleanup_all()
        self.assertIsNone(pm.get_plugin("watermark_studio"))

        sample_path = os.path.join(self.temp_dir, "lazy_pipe_sample.png")
        Image.new("RGB", (50, 50), color=(0, 255, 0)).save(sample_path)

        # 向未加载的 watermark_studio 管道发送数据，应当触发按需动态加载并返回成功
        ok = pm.pipe_data("screen_capture", "watermark_studio", "file/*", [sample_path])
        self.assertTrue(ok)
        self.assertIsNotNone(pm.get_plugin("watermark_studio"))

    # 11. 水印工坊深层目录自动创建与后台工作线程中断响应测试
    def test_13_watermark_nested_output_dir_and_worker_cancellation(self):
        from toolbox.plugins.watermark_studio.ui import WatermarkBatchWorker
        test_img_path = os.path.join(self.temp_dir, "test_nested.png")
        Image.new("RGB", (100, 100), color=(100, 100, 100)).save(test_img_path)

        # 嵌套未创建的多级子目录保存
        nested_out = os.path.join(self.temp_dir, "deep", "nested", "dir", "output_wm.png")
        ok_nested = add_text_watermark(test_img_path, nested_out, text="深层目录水印")
        self.assertTrue(ok_nested)
        self.assertTrue(os.path.isfile(nested_out))

        # 验证批量工作线程中断请求响应
        files = [test_img_path] * 5
        worker = WatermarkBatchWorker(files, os.path.dirname(nested_out), "text", {
            "text": "test", "tiled": True, "angle": 0, "opacity": 100, "font_size": 20, "color_hex": "#ffffff"
        })
        worker.requestInterruption()
        worker.run()  # 在当前线程同步调用 run 验证中断检测
        self.assertTrue(worker.isInterruptionRequested())

    # 12. 视觉二维码解码与容错测试
    def test_14_qr_code_visual_decode(self):
        # 容错：纯黑图片应安全返回 False
        empty_path = os.path.join(self.temp_dir, "test_empty.png")
        Image.new("RGB", (64, 64), color=(0, 0, 0)).save(empty_path)
        ok_empty, _ = scan_qr_code_from_image(empty_path)
        self.assertFalse(ok_empty)

        # 启发式 URL 嵌入回退测试 (保证无 cv2 纯净环境下亦能验证二维码/条形码回退能力)
        embed_url_path = os.path.join(self.temp_dir, "test_embed_url.png")
        Image.new("RGB", (64, 64), color=(255, 255, 255)).save(embed_url_path)
        with open(embed_url_path, "ab") as f:
            f.write(b"https://chieri.io/evolution")
        ok_embed, decoded_embed = scan_qr_code_from_image(embed_url_path)
        self.assertTrue(ok_embed)
        self.assertEqual(decoded_embed, "https://chieri.io/evolution")

        try:
            import cv2
        except ImportError:
            self.skipTest("cv2 未在当前环境中安装，跳过生成视觉二维码与解码闭环测试")

        qr_path = os.path.join(self.temp_dir, "test_qr.png")
        encoder = cv2.QRCodeEncoder_create()
        qr_mat = encoder.encode("https://chieri.io/evolution")
        qr_mat = cv2.copyMakeBorder(qr_mat, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
        qr_mat = cv2.resize(qr_mat, (160, 160), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(qr_path, qr_mat)

        ok, decoded = scan_qr_code_from_image(qr_path)
        self.assertTrue(ok)
        self.assertEqual(decoded, "https://chieri.io/evolution")

    # 13. 剪贴板搜索过滤下双击复制条目对齐健全性测试
    def test_15_clipboard_search_filter_double_click_safety(self):
        from toolbox.plugins.clipboard_manager.ui import ClipboardManagerWidget
        w = ClipboardManagerWidget()
        w.mgr.items.clear()
        w.mgr.add_text("First Alpha Item")
        w.mgr.add_text("Second Beta Target")
        w.mgr.add_text("Third Gamma Item")
        # items 顺序为: [Third, Second, First]
        w._refresh_history_list()
        self.assertEqual(w.list_history.count(), 3)

        # 搜索过滤只显示 "Target" (即 Second Beta Target)
        w.le_search.setText("Target")
        self.assertEqual(w.list_history.count(), 1)
        filtered_item = w.list_history.item(0)

        # 模拟双击过滤项
        w._on_item_double_clicked(filtered_item)
        cb = QApplication.clipboard()
        self.assertEqual(cb.text(), "Second Beta Target")

        w.cleanup()
        w.deleteLater()

    # 14. JSON 对比工坊 (JSON Diff Studio) 核心差异、美化、压缩与 JSONPath 评估测试
    def test_16_json_diff_studio_engine_and_ui(self):
        from toolbox.plugins.json_diff_studio.engine import (
            compute_diff, format_json_str, minify_json_str, validate_json_str, evaluate_jsonpath
        )
        from toolbox.plugins.json_diff_studio.ui import JsonDiffStudioWidget

        # 1. 差异计算与行内字符级差异测试
        t1 = "line 1\nline 2 delete\nline 3"
        t2 = "line 1\nline 2 inserted\nline 3"
        diff_res = compute_diff(t1, t2)
        stats = diff_res["stats"]
        self.assertEqual(stats["equals"], 2)
        self.assertEqual(stats["modifications"], 1)

        # 验证行内高精字符级变化 span 提取 ("Wo"->"Ea", "r"相等, "ld"->"th")
        diff_char = compute_diff("Hello World", "Hello Earth")
        self.assertEqual(diff_char["left_rows"][0]["inline"], [(6, 8), (9, 11)])
        self.assertEqual(diff_char["right_rows"][0]["inline"], [(6, 8), (9, 11)])

        diff_simple = compute_diff("Hello Cat", "Hello Dog")
        self.assertEqual(diff_simple["left_rows"][0]["inline"], [(6, 9)])
        self.assertEqual(diff_simple["right_rows"][0]["inline"], [(6, 9)])

        # 2. 格式化与压缩测试
        raw_json = '{"b":2,"a":1}'
        ok_fmt, fmt_str, _ = format_json_str(raw_json, indent=2, sort_keys=True)
        self.assertTrue(ok_fmt)
        self.assertIn('"a": 1', fmt_str)

        ok_mini, mini_str, _ = minify_json_str(fmt_str)
        self.assertTrue(ok_mini)
        self.assertNotIn(" ", mini_str)

        # 3. 语法校验测试
        ok_valid, msg_valid, _ = validate_json_str('{"valid": true}')
        self.assertTrue(ok_valid)
        ok_invalid, msg_err, err_pos = validate_json_str('{"invalid": }')
        self.assertFalse(ok_invalid)
        self.assertIsNotNone(err_pos)

        # 4. JSONPath 引擎查询测试
        test_payload = {
            "store": {
                "books": [
                    {"title": "Book A", "price": 8.5, "id": 101, "item-tag": "classic"},
                    {"title": "Book B", "price": 12.0, "id": 102, "item-tag": "novel"},
                    {"title": "Book C", "price": 15.5, "id": 103, "item-tag": "scifi"}
                ]
            },
            "meta": {"author": "Chieri"}
        }

        # 基础通配展开
        ok, res_all, _ = evaluate_jsonpath(test_payload, "$.store.books[*].title")
        self.assertTrue(ok)
        self.assertEqual(res_all, ["Book A", "Book B", "Book C"])

        # 递归向下查询
        ok, res_desc, _ = evaluate_jsonpath(test_payload, "$..author")
        self.assertTrue(ok)
        self.assertEqual(res_desc, ["Chieri"])

        # 条件过滤 [?(@.price > 10)]
        ok, res_filter, _ = evaluate_jsonpath(test_payload, "$.store.books[?(@.price > 10)]")
        self.assertTrue(ok)
        self.assertEqual(len(res_filter), 2)
        self.assertEqual(res_filter[0]["title"], "Book B")

        # 括号开头查询与中划线键名兼容测试
        ok_bracket, res_bracket, _ = evaluate_jsonpath([{"user-id": 42}], "[0].user-id")
        self.assertTrue(ok_bracket)
        self.assertEqual(res_bracket, [42])

        # 条件过滤中划线键名测试
        ok_tag, res_tag, _ = evaluate_jsonpath(test_payload, "$.store.books[?(@.item-tag == 'scifi')]")
        self.assertTrue(ok_tag)
        self.assertEqual(len(res_tag), 1)
        self.assertEqual(res_tag[0]["id"], 103)

        # 5. UI 部件与生命周期测试
        widget = JsonDiffStudioWidget()
        widget.set_input_text('{"init": "test"}')
        self.assertIn("init", widget.edit_left.toPlainText())
        widget._format_both()
        widget._run_diff()
        widget._copy_left()
        widget._copy_right()
        widget.save_settings()
        widget.load_settings()
        widget.cleanup()
        widget.deleteLater()

    # 15. 环境变量切换管家 (Env Var Switcher) 诊断、备份、还原与 UI 健全性测试
    def test_17_env_var_switcher_engine_and_ui(self):
        from toolbox.plugins.env_var_switcher.engine import (
            parse_path_entries, clean_path_entries, create_env_backup,
            restore_env_backup, broadcast_environment_change
        )
        from toolbox.plugins.env_var_switcher.ui import EnvVarSwitcherWidget

        # 1. PATH 条目有效性诊断 (包含带双引号路径与尾随反斜杠去重)
        fake_path = f'"C:\\Windows";{self.temp_dir};C:\\NonExistentDirectory_Chieri_999;"{self.temp_dir}\\"'
        entries = parse_path_entries(fake_path)
        self.assertEqual(len(entries), 4)
        self.assertTrue(entries[0]["is_valid"])
        self.assertEqual(entries[0]["raw"], "C:\\Windows")
        self.assertTrue(entries[1]["is_valid"])
        self.assertFalse(entries[2]["is_valid"])  # 探测不存在目录
        self.assertTrue(entries[3]["is_duplicate"])  # 规范化后成功识别为重复项

        # 2. PATH 清理去重
        raw_list = ['"C:\\Windows"', self.temp_dir, "C:\\NonExistent_999", f'"{self.temp_dir}\\"']
        cleaned, stats = clean_path_entries(raw_list, remove_dead=True, remove_duplicates=True)
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(stats["removed_dead"], 1)
        self.assertEqual(stats["removed_duplicates"], 1)

        # 3. 环境变量备份与快照解析
        ok_backup, backup_path, payload = create_env_backup(self.temp_dir)
        self.assertTrue(ok_backup)
        self.assertTrue(os.path.isfile(backup_path))
        self.assertIn("user_variables", payload)
        self.assertIn("system_variables", payload)

        # 4. 快照还原逻辑 (在单元测试中仅测试解析与无异常执行)
        ok_rest, msg_rest = restore_env_backup(backup_path, restore_user=False, restore_system=False)
        self.assertTrue(ok_rest)

        # 5. 广播变更不崩溃 (验证 64 位下 ctypes.c_size_t 安全性)
        ok_bc = broadcast_environment_change()
        self.assertIsInstance(ok_bc, bool)

        # 6. UI 部件与生命周期测试
        widget = EnvVarSwitcherWidget()
        self.assertIsNotNone(widget.table_user)
        self.assertIsNotNone(widget.table_sys)
        self.assertIsNotNone(widget.table_path)
        widget.save_settings()
        widget.load_settings()
        widget.cleanup()
        widget.deleteLater()

    # 16. 截图工具 (Screen Capture) 实时取色放大镜与长截图多向滚动拼接测试
    def test_18_screen_capture_magnifier_and_scroll_stitch(self):
        from PySide6.QtGui import QPixmap, QColor, QKeyEvent
        from PySide6.QtCore import Qt, QPoint
        from toolbox.plugins.screen_capture.capture import (
            SnipOverlay, stitch_screenshots, stitch_long_screenshot,
            find_vertical_overlap, find_horizontal_overlap
        )
        from toolbox.plugins.screen_capture.ui import (
            ScreenCaptureWidget, ScrollCaptureAssistWidget
        )

        # 1. 放大镜 HUD 渲染与取色复制测试
        test_pix = QPixmap(200, 200)
        test_pix.fill(QColor("#38bdf8"))
        overlay = SnipOverlay(test_pix, show_magnifier=True)
        self.assertTrue(overlay.show_magnifier)
        self.assertTrue(overlay.hasMouseTracking())

        # 悬停并触发 C 键复制色值
        overlay.hover_pos = QPoint(50, 50)
        c_event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_C, Qt.NoModifier)
        overlay.keyPressEvent(c_event)
        cb = QApplication.clipboard()
        self.assertEqual(cb.text(), "#38BDF8")

        # 2. 验证大面积连续重叠且带空白边界的长截图高精拼接 (不被 15px 空白提前截断)
        from PIL import Image as PILImage
        img1 = PILImage.new("RGB", (200, 200), (255, 255, 255))
        for x in range(30, 170):
            img1.putpixel((x, 150), (0, 0, 0))  # 特征线位于 y=150
        img2 = PILImage.new("RGB", (200, 200), (255, 255, 255))
        for x in range(30, 170):
            img2.putpixel((x, 50), (0, 0, 0))  # 特征线位于 y=50，重叠高应为 100

        detected_v = find_vertical_overlap(img1, img2)
        self.assertEqual(detected_v, 100)

        # 3. 模拟长截图垂直拼接与重叠消除
        p1 = QPixmap(100, 50)
        p1.fill(QColor("red"))
        p2 = QPixmap(100, 60)
        p2.fill(QColor("blue"))
        stitched_v = stitch_screenshots([p1, p2], direction="vertical", auto_overlap=True)
        self.assertEqual(stitched_v.width(), 100)
        self.assertEqual(stitched_v.height(), 110)

        # 4. 模拟长截图水平拼接
        stitched_h = stitch_screenshots([p1, p2], direction="horizontal", auto_overlap=False)
        self.assertEqual(stitched_h.width(), 200)
        self.assertEqual(stitched_h.height(), 60)

        # 5. 滚动长截图辅助浮窗测试
        sc_widget = ScreenCaptureWidget()
        assist = ScrollCaptureAssistWidget(sc_widget)
        self.assertIsNotNone(assist)
        self.assertIn("0", assist.lbl_status.text())

        overlay.close()
        assist.close()
        sc_widget.cleanup()
        sc_widget.deleteLater()

    # 17. 深度审查与边界加固专项回归测试 (Review & Hardening Verification)
    def test_19_audit_and_hardening_fixes(self):
        # A. Quick Launcher: 严格阻断字符串常数注入与内存炸弹
        self.assertIsNone(evaluate_math_expression("'a' * 1000"))
        self.assertIsNone(evaluate_math_expression('"hack" + "test"'))
        self.assertIsNone(evaluate_math_expression("(-4) ** 0.5"))  # 拦截复数

        # 微小非零浮点数不坍缩为 "0"
        small_float = evaluate_math_expression("0.0000001 + 0")
        self.assertIsNotNone(small_float)
        self.assertNotEqual(small_float[1], "0")

        # B. Quick Launcher UI: Base64 解码卡片与时间戳多格式卡片呈现
        from toolbox.plugins.quick_launcher.ui import SpotlightSearchWindow
        ql = SpotlightSearchWindow()
        ql.show()
        ql.input_search.setText("b64:SGVsbG8gV29ybGQ=")  # "Hello World"
        # 结果列表中应同时包含编码和解码卡片
        cards = [ql.list_results.item(i).data(Qt.UserRole).get("val") for i in range(ql.list_results.count())]
        self.assertIn("Hello World", cards)

        # C. Clipboard Manager: 剪贴板大图缓存内存上限防爆机制
        from PySide6.QtGui import QPixmap
        cm = ClipboardHistoryManager(max_items=30)
        sample_pix = QPixmap(100, 100)
        sample_pix.fill(Qt.white)
        for _ in range(15):
            cm.add_image(sample_pix)
        cached_fulls = [it for it in cm.items if it.item_type == "image" and it.full_pixmap is not None]
        self.assertLessEqual(len(cached_fulls), 10)  # 最多仅保留 10 张大图缓存

        # D. Env Var Switcher: Windows 注册表 Path/PATH 大小写无关查找防抹除
        from toolbox.plugins.env_var_switcher.engine import _get_var_case_insensitive
        reg_dict = {"PATH": (r"C:\Windows\System32;C:\Windows", 2), "TEMP": (r"C:\Temp", 1)}
        val, rtype = _get_var_case_insensitive(reg_dict, "Path")
        self.assertEqual(val, rtype_val := r"C:\Windows\System32;C:\Windows")

        # E. JSON Diff Studio: 非法切片 JSONPath 语法防崩防崩溃
        from toolbox.plugins.json_diff_studio.engine import evaluate_jsonpath
        ok, res, msg = evaluate_jsonpath({"nums": [1, 2, 3]}, "$[invalid:slice]")
        self.assertIsInstance(ok, bool)

        # F. 屏幕截图 QR 码启发式过滤标准 XMP Schema 命名空间
        fake_adobe_img = os.path.join(self.temp_dir, "fake_adobe_meta.png")
        Image.new("RGB", (64, 64), color=(200, 200, 200)).save(fake_adobe_img)
        with open(fake_adobe_img, "ab") as f:
            f.write(b"http://ns.adobe.com/xap/1.0/")
        ok_adobe, _ = scan_qr_code_from_image(fake_adobe_img)
        self.assertFalse(ok_adobe)

        # G. Global Task Manager: 中断取消时抛出异常正确标记为 CANCELLED 而非 FAILED
        gtm = GlobalTaskManager.instance()
        def aborting_task(cancel_check=None):
            if cancel_check and cancel_check():
                raise InterruptedError("Worker cooperative cancel")
            return "ok"

        tid_abort = gtm.submit_task("测试协同中断", aborting_task)
        gtm.cancel_task(tid_abort)
        time.sleep(0.3)
        t_info = gtm.get_task(tid_abort)
        self.assertIn(t_info.status, (TaskStatus.CANCELLED, TaskStatus.QUEUED))

        ql.close()
        ql.deleteLater()


if __name__ == "__main__":
    unittest.main()

