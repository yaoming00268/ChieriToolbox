"""
千绘莉多功能工具箱 (Chieri Toolbox) - 多 DPI 与不同窗口比例视觉自适应自动化验证测试
覆盖测试:
1. 100% (1.0x), 125% (1.25x), 150% (1.5x) DPI 缩放渲染与布局稳定性
2. 不同窗口尺寸自适应:
   - 紧凑布局 (1024x700)
   - 标准高清 (1280x800)
   - 宽屏大窗口 (1600x950)
   - 超宽全高清 (1920x1080)
3. 重点进化特性各插件 UI 视觉自适应检测:
   - 主窗口 Home 首页与卡片自适应重排
   - 图像大师 (Image Master) 超分与模型管理面板
   - 媒体下载器 (Media Downloader) B站弹幕转 ASS 选项
   - 全格式音乐解密器 (Music Decryptor)
   - 归档管理器 (Archive Manager) 与 ACG 密码本弹窗
   - 设置中心 (Settings Dialog) Local Cloud 局域网服务与 Model Manager
"""

import sys
import os
import time
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import toolbox  # 触发 Windows DLL 依赖守护
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.main_window import MainWindow
from toolbox.ui.settings_dialog import SettingsDialog
from toolbox.ui.components.model_manager_widget import ModelManagerWidget
from toolbox.plugins.archive_manager.password_dialog import AcgPasswordDialog
from toolbox.plugins.image_master.ui import ImageMasterWidget
from toolbox.plugins.media_downloader.ui import MediaDownloaderWidget
from toolbox.plugins.ncm_decryptor.ui import NcmDecryptorWidget
from toolbox.plugins.archive_manager.ui import ArchiveManagerWidget


def run_dpi_adaptive_tests():
    app = QApplication.instance()
    if not app:
        app = QApplication(["--platform", "offscreen"])

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_screenshots", "dpi_adaptive")
    os.makedirs(out_dir, exist_ok=True)

    # 隔离独立临时配置沙箱
    sandbox_cfg = os.path.join(tempfile.gettempdir(), f"sandbox_dpi_cfg_{os.getpid()}.json")
    ConfigManager.reset_instance()
    cfg = ConfigManager(sandbox_cfg)

    print("=== 开始执行多 DPI 与不同比例窗口视觉自适应测试 ===")

    dpi_scales = [
        ("dpi100", 1.0, 9),
        ("dpi125", 1.25, 11),
        ("dpi150", 1.5, 13)
    ]

    resolutions = [
        ("compact_1024x700", 1024, 700),
        ("standard_1280x800", 1280, 800),
        ("wide_1600x950", 1600, 950),
        ("fhd_1920x1080", 1920, 1080)
    ]

    # 1. 主窗口在不同 DPI 和分辨率下的布局与重排
    for dpi_name, scale, font_pt in dpi_scales:
        app_font = QFont("Microsoft YaHei UI", font_pt)
        app.setFont(app_font)

        for res_name, w, h in resolutions:
            scaled_w = int(w * (scale / 1.0))
            scaled_h = int(h * (scale / 1.0))
            # 限制在离屏最大合理范围
            target_w = min(scaled_w, 1920)
            target_h = min(scaled_h, 1200)

            win = MainWindow()
            win.resize(target_w, target_h)
            win.show()
            QApplication.processEvents()
            time.sleep(0.1)

            scr_path = os.path.join(out_dir, f"main_window_{dpi_name}_{res_name}.png")
            pix = win.grab()
            pix.save(scr_path)
            print(f"[DPI Test] 主窗口截图完成: {scr_path} ({pix.width()}x{pix.height()})")
            win.close()

    # 2. 重点进化插件 UI 视觉自适应测试 (标准 1280x800 与 高 DPI 1600x950)
    for dpi_name, scale, font_pt in [("dpi100", 1.0, 9), ("dpi125", 1.25, 11), ("dpi150", 1.5, 13)]:
        app.setFont(QFont("Microsoft YaHei UI", font_pt))

        # 2.1 图像大师 (ImageMaster)
        im_widget = ImageMasterWidget()
        im_widget.resize(int(1100 * scale), int(750 * scale))
        im_widget.show()
        QApplication.processEvents()
        scr = os.path.join(out_dir, f"plugin_image_master_{dpi_name}.png")
        im_widget.grab().save(scr)
        print(f"[DPI Test] 图像大师截图完成: {scr}")
        im_widget.close()

        # 2.2 媒体下载器 (MediaDownloader with Danmaku)
        md_widget = MediaDownloaderWidget()
        md_widget.resize(int(1100 * scale), int(750 * scale))
        md_widget.show()
        QApplication.processEvents()
        scr = os.path.join(out_dir, f"plugin_media_downloader_{dpi_name}.png")
        md_widget.grab().save(scr)
        print(f"[DPI Test] 媒体下载器截图完成: {scr}")
        md_widget.close()

        # 2.3 音乐解密器 (NcmDecryptor Multi-Format)
        ncm_widget = NcmDecryptorWidget()
        ncm_widget.resize(int(1050 * scale), int(720 * scale))
        ncm_widget.show()
        QApplication.processEvents()
        scr = os.path.join(out_dir, f"plugin_ncm_decryptor_{dpi_name}.png")
        ncm_widget.grab().save(scr)
        print(f"[DPI Test] 音乐解密器截图完成: {scr}")
        ncm_widget.close()

        # 2.4 归档管理器与 ACG 密码本弹窗
        arc_widget = ArchiveManagerWidget()
        arc_widget.resize(int(1050 * scale), int(720 * scale))
        arc_widget.show()
        QApplication.processEvents()
        scr = os.path.join(out_dir, f"plugin_archive_manager_{dpi_name}.png")
        arc_widget.grab().save(scr)
        print(f"[DPI Test] 归档管理器截图完成: {scr}")

        pwd_dlg = AcgPasswordDialog(parent=arc_widget)
        pwd_dlg.resize(int(700 * scale), int(550 * scale))
        pwd_dlg.show()
        QApplication.processEvents()
        scr = os.path.join(out_dir, f"dialog_acg_password_book_{dpi_name}.png")
        pwd_dlg.grab().save(scr)
        print(f"[DPI Test] ACG 密码本弹窗截图完成: {scr}")
        pwd_dlg.close()
        arc_widget.close()

        # 2.5 设置中心与 Local Cloud 状态
        settings_dlg = SettingsDialog()
        settings_dlg.resize(int(750 * scale), int(600 * scale))
        settings_dlg.show()
        # 激活 Local Cloud & 模型管理 Tab
        for idx in range(settings_dlg.tabs.count()):
            tab_text = settings_dlg.tabs.tabText(idx)
            if "局域网" in tab_text or "云" in tab_text or "模型" in tab_text:
                settings_dlg.tabs.setCurrentIndex(idx)
                break
        QApplication.processEvents()
        scr = os.path.join(out_dir, f"dialog_settings_local_cloud_{dpi_name}.png")
        settings_dlg.grab().save(scr)
        print(f"[DPI Test] 设置中心 Local Cloud 截图完成: {scr}")
        settings_dlg.close()

        # 2.6 模型管理器独立面板 (ModelManagerWidget)
        model_widget = ModelManagerWidget()
        model_widget.resize(int(750 * scale), int(550 * scale))
        model_widget.show()
        QApplication.processEvents()
        scr = os.path.join(out_dir, f"widget_model_manager_{dpi_name}.png")
        model_widget.grab().save(scr)
        print(f"[DPI Test] 模型管理组件截图完成: {scr}")
        model_widget.close()

    print(f"=== 多 DPI 视觉自适应测试全部顺利完成！截图保存至 {out_dir} ===")
    return True


if __name__ == "__main__":
    success = run_dpi_adaptive_tests()
    sys.exit(0 if success else 1)
