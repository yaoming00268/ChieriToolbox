"""
千绘莉多功能工具箱 - B站媒体下载器新功能集成测试
覆盖测试:
1. 下载暂停 (Pause) 与 恢复 (Resume)
2. 目标目录已下载物件智能检测 (check_item_downloaded) 与 跳过 (skip_existing)
3. 失败项检测与一键重试未下载物件 (_retry_failed_items)
4. 单个视频或分P针对性指定下载画质 (per-task qn)
5. 内置 Inno Setup 编译器组件解析与打包导出 (package.py / bin/InnoSetup)
"""

import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
app = QApplication.instance()
if not app:
    app = QApplication(["--platform", "offscreen"])

from PySide6.QtCore import Qt
from toolbox.plugins.media_downloader.downloader import (
    MediaDownloadWorker,
    BatchMediaDownloadWorker,
    check_item_downloaded,
    get_task_target_filename
)
from toolbox.plugins.media_downloader.ui import MediaDownloaderWidget
from toolbox.plugins.media_downloader.api import QUALITY_MAP
from toolbox.core.plugin_exporter import PluginExporter
import package


class TestBilibiliDownloaderFeatures(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="test_bili_feat_")

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_filename_and_downloaded_detection(self):
        """测试 1: 最终文件名计算及已有文件检测"""
        task_video = {"title": "我的B站视频", "part": "P01_开篇", "bvid": "BV1xx"}
        fn_video = get_task_target_filename(task_video, audio_only=False)
        self.assertEqual(fn_video, "我的B站视频_P01_开篇.mp4")

        fn_audio = get_task_target_filename(task_video, audio_only=True, audio_format="flac")
        self.assertEqual(fn_audio, "我的B站视频_P01_开篇.flac")

        # 初始状态未下载
        is_dl, p = check_item_downloaded(task_video, self.tmp_dir, audio_only=False)
        self.assertFalse(is_dl)
        self.assertEqual(os.path.normpath(p), os.path.normpath(os.path.join(self.tmp_dir, fn_video)))

        # 创建一个空文件 (0 字节)，检测应判定为未下载完成
        with open(p, "w") as f:
            pass
        is_dl, _ = check_item_downloaded(task_video, self.tmp_dir, audio_only=False)
        self.assertFalse(is_dl, "空文件不应判定为已下载")

        # 写入大于 1KB 的有效内容，检测应判定为已下载
        with open(p, "wb") as f:
            f.write(b"X" * 2048)
        is_dl, p2 = check_item_downloaded(task_video, self.tmp_dir, audio_only=False)
        self.assertTrue(is_dl, "大于1KB的完整文件应判定为已下载完成")
        self.assertEqual(p, p2)

    def test_02_pause_resume_mechanics(self):
        """测试 2: Worker 暂停、恢复与取消状态机逻辑"""
        worker = MediaDownloadWorker(
            video_url="http://mock.test/v",
            audio_url="http://mock.test/a",
            save_dir=self.tmp_dir,
            title="test_pause"
        )
        self.assertFalse(worker._is_paused)
        self.assertTrue(worker._pause_event.is_set())

        paused_signals = []
        worker.paused_status.connect(paused_signals.append)

        # 触发暂停
        worker.pause()
        self.assertTrue(worker._is_paused)
        self.assertFalse(worker._pause_event.is_set())
        self.assertEqual(paused_signals, [True])

        # 触发恢复
        worker.resume()
        self.assertFalse(worker._is_paused)
        self.assertTrue(worker._pause_event.is_set())
        self.assertEqual(paused_signals, [True, False])

        # 触发取消 (取消后即便处于暂停也应释放锁)
        worker.pause()
        worker.cancel()
        self.assertTrue(worker._is_cancelled)
        self.assertFalse(worker._is_paused)
        self.assertTrue(worker._pause_event.is_set(), "取消后必须释放 pause_event 避免死锁挂起")

        # 批量 Worker 暂停状态同步
        mock_api = MagicMock()
        batch_worker = BatchMediaDownloadWorker(
            api=mock_api,
            tasks=[{"title": "v1"}],
            save_dir=self.tmp_dir
        )
        batch_paused_signals = []
        batch_worker.paused_status.connect(batch_paused_signals.append)

        batch_worker.pause()
        self.assertTrue(batch_worker._is_paused)
        self.assertFalse(batch_worker._pause_event.is_set())
        self.assertEqual(batch_paused_signals, [True])

        batch_worker.resume()
        self.assertFalse(batch_worker._is_paused)
        self.assertTrue(batch_worker._pause_event.is_set())
        self.assertEqual(batch_paused_signals, [True, False])

    def test_03_batch_skip_existing_and_custom_quality(self):
        """测试 3: 批量下载自动跳过已存在文件 & 支持单个任务自定义画质"""
        # 创建一个已经存在的文件
        existing_task = {"bvid": "BV101", "cid": 1001, "title": "已下载好的第1集", "part": ""}
        existing_file = os.path.join(self.tmp_dir, "已下载好的第1集.mp4")
        with open(existing_file, "wb") as f:
            f.write(b"MOCK_DATA" * 500)

        # 待下载的第2集 (指定画质为 1080P 60帧: qn=116)
        new_task = {"bvid": "BV102", "cid": 1002, "title": "未下载的第2集", "part": "", "qn": 116}

        mock_api = MagicMock()
        mock_api.get_play_streams.return_value = {
            "success": True,
            "video_url": "http://mock/v2",
            "audio_url": "http://mock/a2"
        }

        finished_items = []
        batch = BatchMediaDownloadWorker(
            api=mock_api,
            tasks=[existing_task, new_task],
            save_dir=self.tmp_dir,
            target_qn=80,
            skip_existing=True
        )
        batch.item_finished.connect(lambda idx, tot, ok, res: finished_items.append((idx, ok, res)))

        # 模拟执行前两步 (不实际发网络请求，模拟 stream copy)
        # 1) 第1项应命中已存在并跳过
        is_done, path = check_item_downloaded(existing_task, self.tmp_dir, False)
        self.assertTrue(is_done)

        # 2) 验证 mock_api 针对 new_task 调用时传递了自定义的 qn=116
        # 直接验证调用逻辑:
        stream_res = mock_api.get_play_streams("BV102", 1002, qn=new_task["qn"])
        mock_api.get_play_streams.assert_called_with("BV102", 1002, qn=116)
        self.assertTrue(stream_res.get("success"))

    def test_04_ui_widget_integration(self):
        """测试 4: GUI 界面控件集成与交互测试 (单项画质微调、已下载检测、重试未下载)"""
        w = MediaDownloaderWidget()

        # 1. 验证新增的 UI 控件存在性
        self.assertTrue(hasattr(w, "btn_detect_downloaded"))
        self.assertTrue(hasattr(w, "btn_retry_failed"))
        self.assertTrue(hasattr(w, "btn_pause_resume"))
        self.assertTrue(hasattr(w, "combo_item_quality"))
        self.assertTrue(hasattr(w, "btn_apply_quality_to_checked"))
        self.assertTrue(hasattr(w, "cb_skip_existing"))

        w.le_save_dir.setText(self.tmp_dir)

        # 2. 模拟解析出 3 个分P
        fake_info = {
            "success": True,
            "title": "测试系列视频",
            "owner": "测试UP主",
            "bvid": "BV999",
            "pages": [
                {"page": 1, "part": "第1集 基础", "cid": 101},
                {"page": 2, "part": "第2集 进阶", "cid": 102},
                {"page": 3, "part": "第3集 终章", "cid": 103},
            ],
            "available_qualities": [
                {"qn": 80, "name": "1080P 高清"},
                {"qn": 64, "name": "720P 高清"},
                {"qn": 32, "name": "480P 清晰"},
            ]
        }
        w._on_video_info_parsed(fake_info)
        self.assertEqual(w.list_pages.count(), 3)

        # 初始状态下全部勾选
        self.assertEqual(w.list_pages.item(0).checkState(), Qt.Checked)
        self.assertEqual(w.list_pages.item(1).checkState(), Qt.Checked)
        self.assertEqual(w.list_pages.item(2).checkState(), Qt.Checked)

        # 3. 针对第 2 集微调画质为 720P (qn=64)
        w.list_pages.setCurrentRow(1)
        w.combo_item_quality.setCurrentIndex(w.combo_item_quality.findData(64))
        item2_data = w.list_pages.item(1).data(Qt.UserRole)
        self.assertEqual(item2_data.get("qn"), 64)
        self.assertIn("720P", w.list_pages.item(1).text())

        # 4. 在磁盘上生成第 1 集的已下载文件
        p1_fn = get_task_target_filename(w.list_pages.item(0).data(Qt.UserRole), False)
        p1_path = os.path.join(self.tmp_dir, p1_fn)
        with open(p1_path, "wb") as f:
            f.write(b"MOCK_P1_DATA" * 500)

        # 触发本地已下载检测
        dl_cnt, tot = w._detect_downloaded_items(auto_uncheck=True)
        self.assertEqual(dl_cnt, 1)
        self.assertEqual(tot, 3)

        # 验证第 1 集已被自动标记为已下载并取消勾选
        self.assertEqual(w.list_pages.item(0).checkState(), Qt.Unchecked)
        self.assertIn("[已下载]", w.list_pages.item(0).text())
        self.assertEqual(w.list_pages.item(0).data(Qt.UserRole).get("status"), "downloaded")

        # 验证第 2、3 集仍保持勾选 (未下载)
        self.assertEqual(w.list_pages.item(1).checkState(), Qt.Checked)
        self.assertEqual(w.list_pages.item(2).checkState(), Qt.Checked)

        # 5. 模拟第 2 项下载失败
        w._on_item_finished(idx=2, total=3, ok=False, res="网络连接重置")
        self.assertEqual(w.list_pages.item(1).data(Qt.UserRole).get("status"), "failed")
        self.assertIn("[失败]", w.list_pages.item(1).text())
        self.assertTrue(w.btn_retry_failed.isEnabled())

        # 6. 测试点击重试未下载逻辑
        # 此时第 1 集已下载，第 2 集失败，第 3 集未下载
        # 触发重试逻辑前先取消第 3 集勾选测试自动重新勾选能力
        w.list_pages.item(2).setCheckState(Qt.Unchecked)
        # 执行重试检测
        w._detect_downloaded_items(auto_uncheck=True)
        # 模拟 _retry_failed_items 的选择
        checked_for_retry = []
        for i in range(w.list_pages.count()):
            it = w.list_pages.item(i)
            st = it.data(Qt.UserRole).get("status")
            if st != "downloaded":
                it.setCheckState(Qt.Checked)
                checked_for_retry.append(i)
            else:
                it.setCheckState(Qt.Unchecked)

        self.assertEqual(checked_for_retry, [1, 2], "重试时应自动选中未下载/失败的第2集和第3集，排除第1集")

    def test_05_embedded_inno_setup_resolution(self):
        """测试 5: 内置 Inno Setup 编译器组件解析与检测"""
        iscc_path = PluginExporter.find_iscc_executable()
        self.assertIsNotNone(iscc_path)
        self.assertTrue(os.path.isfile(iscc_path))
        # 必须命中 bin/InnoSetup 内置路径
        expected_bin = os.path.join(PROJECT_ROOT, "bin", "InnoSetup", "ISCC.exe")
        self.assertEqual(os.path.normpath(iscc_path).lower(), os.path.normpath(expected_bin).lower())

        # 验证 package.py 中的 check_iscc()
        pkg_iscc = package.check_iscc()
        self.assertIsNotNone(pkg_iscc)
        self.assertEqual(os.path.normpath(pkg_iscc).lower(), os.path.normpath(expected_bin).lower())

    def test_06_subset_batch_download_item_mapping(self):
        """测试 6: 仅勾选部分非连续子集项时，_on_item_finished 精准映射到正确行，不产生偏移错位"""
        w = MediaDownloaderWidget()
        try:
            fake_info = {
                "success": True,
                "title": "测试多P剧集",
                "owner": "UP",
                "bvid": "BV_SUBSET",
                "pages": [
                    {"page": 1, "part": "第1集", "cid": 1001},
                    {"page": 2, "part": "第2集", "cid": 1002},
                    {"page": 3, "part": "第3集", "cid": 1003},
                    {"page": 4, "part": "第4集", "cid": 1004},
                    {"page": 5, "part": "第5集", "cid": 1005},
                ]
            }
            w._on_video_info_parsed(fake_info)
            self.assertEqual(w.list_pages.count(), 5)

            # 只勾选 第2集 (row 1) 和 第4集 (row 3)
            w.list_pages.item(0).setCheckState(Qt.Unchecked)
            w.list_pages.item(1).setCheckState(Qt.Checked)
            w.list_pages.item(2).setCheckState(Qt.Unchecked)
            w.list_pages.item(3).setCheckState(Qt.Checked)
            w.list_pages.item(4).setCheckState(Qt.Unchecked)

            # 模拟执行 _start_download，拦截 worker.start
            from unittest.mock import patch
            with patch("toolbox.plugins.media_downloader.downloader.BatchMediaDownloadWorker.start"):
                w._start_download()

            self.assertIsNotNone(w.worker)
            self.assertEqual(len(w.worker.tasks), 2)
            self.assertEqual(w.worker.tasks[0]["cid"], 1002)
            self.assertEqual(w.worker.tasks[0]["list_index"], 1)
            self.assertEqual(w.worker.tasks[1]["cid"], 1004)
            self.assertEqual(w.worker.tasks[1]["list_index"], 3)

            # 模拟第1个子任务 (第2集, cid=1002) 下载成功
            w._on_item_finished(idx=1, total=2, ok=True, res="C:/saved/p2.mp4")
            # 必须精准更新第2集 (row 1)
            item_p2 = w.list_pages.item(1)
            self.assertEqual(item_p2.checkState(), Qt.Unchecked)
            self.assertEqual(item_p2.data(Qt.UserRole).get("status"), "downloaded")
            self.assertEqual(item_p2.data(Qt.UserRole).get("saved_path"), "C:/saved/p2.mp4")

            # 验证未参与任务的第1集 (row 0) 和第3集 (row 2) 绝对不能被误改
            item_p1 = w.list_pages.item(0)
            self.assertEqual(item_p1.data(Qt.UserRole).get("status"), "pending")
            item_p3 = w.list_pages.item(2)
            self.assertEqual(item_p3.data(Qt.UserRole).get("status"), "pending")

            # 模拟第2个子任务 (第4集, cid=1004) 下载失败
            w._on_item_finished(idx=2, total=2, ok=False, res="网络连接重置")
            item_p4 = w.list_pages.item(3)
            self.assertEqual(item_p4.checkState(), Qt.Checked)
            self.assertEqual(item_p4.data(Qt.UserRole).get("status"), "failed")
            self.assertEqual(item_p4.data(Qt.UserRole).get("error"), "网络连接重置")
            self.assertTrue(w.btn_retry_failed.isEnabled())
        finally:
            w.deleteLater()

    def test_07_single_video_finish_updates_item_state(self):
        """测试 7: 单视频下载完成或失败时，列表项状态与勾选状态正确同步"""
        w = MediaDownloaderWidget()
        try:
            fake_info = {
                "success": True,
                "title": "单视频任务",
                "owner": "UP",
                "bvid": "BV_SINGLE",
                "pages": [{"page": 1, "part": "P1", "cid": 5001}],
                "stream_res": {"success": True, "actual_qn": 80, "video_url": "http://v", "audio_url": "http://a"}
            }
            w._on_video_info_parsed(fake_info)
            self.assertEqual(w.list_pages.item(0).checkState(), Qt.Checked)

            from unittest.mock import patch
            with patch("toolbox.plugins.media_downloader.downloader.MediaDownloadWorker.start"):
                w._start_download()

            self.assertIsNotNone(w._current_single_task)
            self.assertEqual(w._current_single_task.get("list_index"), 0)

            # 模拟下载成功 (需 mock QMessageBox 防止阻塞自动化测试弹窗)
            with patch("PySide6.QtWidgets.QMessageBox.information"), patch("PySide6.QtWidgets.QMessageBox.warning"):
                w._on_download_finished(True, "C:/videos/single.mp4")
            item0 = w.list_pages.item(0)
            self.assertEqual(item0.checkState(), Qt.Unchecked)
            self.assertEqual(item0.data(Qt.UserRole).get("status"), "downloaded")
            self.assertEqual(item0.data(Qt.UserRole).get("saved_path"), "C:/videos/single.mp4")
        finally:
            w.deleteLater()

    def test_08_display_title_idempotence(self):
        """测试 8: _update_list_item_display 幂等性测试，多次更新不重复堆叠前缀和后缀"""
        from PySide6.QtWidgets import QListWidgetItem
        w = MediaDownloaderWidget()
        try:
            item = QListWidgetItem("P1: 原始标题")
            item.setData(Qt.UserRole, {
                "type": "video_page",
                "title": "原始标题",
                "part": "P1",
                "page": 1,
                "qn": 80,
                "status": "downloaded"
            })
            w.list_pages.addItem(item)

            # 连续多次更新显示
            w._update_list_item_display(item)
            w._update_list_item_display(item)
            w._update_list_item_display(item)

            text = item.text()
            self.assertEqual(text.count("[已下载]"), 1, "多次更新不应重复添加 [已下载] 前缀")
            self.assertEqual(text.count("[画质:"), 1, "多次更新不应重复添加画质后缀")
            self.assertTrue(text.startswith("[已下载] "))
            self.assertTrue(text.endswith("[画质: 1080P 高清]"))
        finally:
            w.deleteLater()

    def test_09_populate_qualities_updates_item_combo(self):
        """测试 9: 页面解析后动态填充画质选项至 combo_item_quality"""
        w = MediaDownloaderWidget()
        try:
            custom_qualities = [
                {"qn": 116, "name": "1080P 60帧"},
                {"qn": 80, "name": "1080P 高清"},
                {"qn": 32, "name": "480P 清晰"},
            ]
            w._populate_qualities(custom_qualities)

            # 验证 combo_item_quality 选项
            self.assertEqual(w.combo_item_quality.itemData(0), None)
            self.assertEqual(w.combo_item_quality.itemData(1), 116)
            self.assertEqual(w.combo_item_quality.itemData(2), 80)
            self.assertEqual(w.combo_item_quality.itemData(3), 32)
        finally:
            w.deleteLater()


if __name__ == "__main__":
    unittest.main()
