import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QPixmap

app = QApplication.instance()
if not app:
    app = QApplication(["--platform", "offscreen"])

from toolbox.ui.main_window import MainWindow

def capture_ui_snapshots(output_dir=None):
    if not output_dir:
        output_dir = sys.argv[1] if len(sys.argv) > 1 else "tests/ui_screenshots/after"
    os.makedirs(output_dir, exist_ok=True)
    win = MainWindow()
    win.show()
    app.processEvents()

    targets = [
        ("home", None),
        ("screen_capture", "screen_capture"),
        ("proxy_configurator", "proxy_configurator"),
        ("whiteboard", "whiteboard"),
        ("audio_cutter", "audio_cutter"),
        ("screen_recorder", "screen_recorder"),
    ]

    sizes = [
        (880, 600),
        (1120, 750),
        (1400, 900)
    ]

    for page_name, plugin_id in targets:
        if plugin_id:
            win.switch_to_plugin(plugin_id)
            # If screen_capture, switch to long screenshot tab as well
            if plugin_id == "screen_capture":
                # Find the widget and tab
                idx = win._plugin_page_indices.get(plugin_id)
                if idx is not None:
                    widget = win.stack.widget(idx)
                    # if widget is wrapped or direct
                    if hasattr(widget, "mode_tabs"):
                        widget.mode_tabs.setCurrentIndex(3)
        else:
            win.go_to_home()

        for w, h in sizes:
            win.resize(w, h)
            app.processEvents()
            time.sleep(0.05)
            app.processEvents()
            
            pix = win.grab()
            save_path = os.path.join(output_dir, f"{page_name}_{w}x{h}.png")
            pix.save(save_path)
            print(f"Captured: {save_path}")

    win.close()
    print("All captures completed.")

if __name__ == "__main__":
    capture_ui_snapshots()
