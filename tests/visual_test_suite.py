"""
千绘莉多功能工具箱 - 自动化可视化视觉闭环验证脚本
验证项:
1. 正常窗口模式 (1120x750): 顶部标签栏文字完整显示，支持水平滚动，卡片自适应排布
2. 标签栏滚动状态: 模拟滚轮/滑条平移，完整呈现右侧超出屏幕的全部胶囊分类
3. 放大/全屏模式 (1700x950): 卡片网格自适应拓展至 5 列以上，消除右侧大面积留白
4. 设置中心 Tab 3 ("界面视觉与特效"): 双层透明度滑动条 (背景透光度 + 组件透明度) 与卡片尺寸间距控件
5. 卡片尺寸与间距自定义调整后的实时重绘效果
"""

import sys
import os
import time
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from toolbox.ui.main_window import MainWindow
from toolbox.ui.settings_dialog import SettingsDialog
from toolbox.core.config_manager import ConfigManager

def run_visual_verification():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_screenshots")
    os.makedirs(out_dir, exist_ok=True)

    # 隔离独立临时配置沙箱，杜绝污染正式配置
    sandbox_cfg = os.path.join(tempfile.gettempdir(), f"sandbox_visual_cfg_{os.getpid()}.json")
    ConfigManager.reset_instance()
    cfg = ConfigManager(sandbox_cfg)

    # 1. 正常窗口模式
    win = MainWindow()
    win.resize(1120, 750)
    win.show()
    QApplication.processEvents()
    time.sleep(0.5)
    QApplication.processEvents()

    p1 = win.grab()
    p1_path = os.path.join(out_dir, "verified_v2_normal_window.png")
    p1.save(p1_path)
    print(f"[Visual] Saved normal window: {p1_path}")

    # 2. 标签栏滚动状态 (向右滚动到底部)
    hp = win.home_page
    h_bar = hp.cat_scroll.horizontalScrollBar()
    h_bar.setValue(h_bar.maximum())
    QApplication.processEvents()
    time.sleep(0.3)
    p2 = win.grab()
    p2_path = os.path.join(out_dir, "verified_v2_category_scrolled.png")
    p2.save(p2_path)
    print(f"[Visual] Saved category scrolled: {p2_path}")

    # 恢复分类滚动条
    h_bar.setValue(0)
    QApplication.processEvents()

    # 3. 放大模式 (1700x950) -> 验证 5 列卡片自适应展开
    win.resize(1700, 950)
    QApplication.processEvents()
    time.sleep(0.5)
    QApplication.processEvents()
    p3 = win.grab()
    p3_path = os.path.join(out_dir, "verified_v2_enlarged_reflow.png")
    p3.save(p3_path)
    print(f"[Visual] Saved enlarged reflow (cols={hp._current_columns}): {p3_path}")

    # 4. 设置中心 Tab 3 ("界面视觉与特效")
    settings_dlg = SettingsDialog(parent=win)
    # 切换到 Tab 3 (索引为 2: 功能模块管理=0, 启动与多开=1, 界面视觉与特效=2)
    settings_dlg.tabs.setCurrentIndex(2)
    settings_dlg.resize(720, 580)
    settings_dlg.show()
    QApplication.processEvents()
    time.sleep(0.4)
    p4 = settings_dlg.grab()
    p4_path = os.path.join(out_dir, "verified_v2_settings_tab3.png")
    p4.save(p4_path)
    print(f"[Visual] Saved settings dialog Tab 3: {p4_path}")

    # 测试滑动条调节：背景透光度 85%, 组件透明度 90%, 卡片宽度 330, 卡片高度 180, 间距 22
    settings_dlg.slider_bg_opacity.setValue(85)
    settings_dlg.slider_comp_opacity.setValue(90)
    settings_dlg.slider_card_w.setValue(330)
    settings_dlg.slider_card_h.setValue(180)
    settings_dlg.slider_card_spacing.setValue(22)
    settings_dlg._apply_settings_action()
    QApplication.processEvents()
    time.sleep(0.3)

    p4_modified = settings_dlg.grab()
    p4_mod_path = os.path.join(out_dir, "verified_v2_settings_tab3_modified.png")
    p4_modified.save(p4_mod_path)
    print(f"[Visual] Saved settings dialog modified: {p4_mod_path}")

    settings_dlg.close()

    # 5. 查看主窗口在自定义尺寸下的卡片实时自适应呈现
    QApplication.processEvents()
    time.sleep(0.4)
    p5 = win.grab()
    p5_path = os.path.join(out_dir, "verified_v2_cards_custom_sized.png")
    p5.save(p5_path)
    print(f"[Visual] Saved custom sized cards (cols={hp._current_columns}): {p5_path}")

    # 恢复默认设置
    cfg = win.config_manager
    cfg.set_window_opacity(1.0)
    cfg.set_bg_opacity(1.0)
    cfg.set_component_opacity(1.0)
    cfg.set_card_width(280)
    cfg.set_card_height(165)
    cfg.set_card_spacing(18)
    cfg.save()
    hp._on_settings_changed()
    win.resize(1120, 750)
    QApplication.processEvents()

    win.close()
    ConfigManager.reset_instance()
    if os.path.exists(sandbox_cfg):
        try:
            os.remove(sandbox_cfg)
        except Exception:
            pass
    print("[Visual] Verification completed successfully.")

if __name__ == "__main__":
    run_visual_verification()
