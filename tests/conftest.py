import sys
import os
import ctypes

# Windows PySide6 DLL compatibility fix: Ensure Windows system icuuc.dll is preloaded
# to prevent incompatible conda Library/bin/icuuc.dll from shadowing the required runtime.
if sys.platform == "win32":
    system_icu = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "icuuc.dll")
    if os.path.exists(system_icu):
        try:
            ctypes.CDLL(system_icu)
        except Exception:
            pass

# Ensure global offscreen QApplication instance is initialized early for all headless test runs
from PySide6.QtWidgets import QApplication
_app = QApplication.instance()
if not _app:
    _app = QApplication(["--platform", "offscreen"])

import gc
import pytest

def pytest_runtest_teardown(item, nextitem):
    """
    Hook executed after every test case.
    Forcefully hides tray icons, closes top-level widgets, purges all remaining widgets
    via DeferredDelete event flushing, and invokes garbage collection to prevent memory ballooning
    and UI freezing during test suite execution.
    """
    app = QApplication.instance()
    if app:
        try:
            from PySide6.QtCore import QEvent
            from PySide6.QtWidgets import QSystemTrayIcon
            for tray in list(app.findChildren(QSystemTrayIcon)):
                try:
                    tray.hide()
                    tray.deleteLater()
                except Exception:
                    pass
            for widget in list(app.topLevelWidgets()):
                try:
                    if hasattr(widget, "app_tray_icon") and widget.app_tray_icon:
                        widget.app_tray_icon.hide()
                    if hasattr(widget, "tray_icon") and widget.tray_icon:
                        widget.tray_icon.hide()
                    if hasattr(widget, "cleanup"):
                        try:
                            widget.cleanup()
                        except Exception:
                            pass
                    widget.close()
                    widget.deleteLater()
                except Exception:
                    pass
            for widget in list(app.allWidgets()):
                try:
                    widget.deleteLater()
                except Exception:
                    pass
            app.sendPostedEvents(None, QEvent.DeferredDelete)
            app.processEvents()
        except Exception:
            pass
    try:
        from toolbox.core.plugin_manager import PluginManager
        PluginManager.reset_instance()
    except Exception:
        pass
    try:
        from toolbox.core.config_manager import ConfigManager
        ConfigManager().set_multi_window_mode(False)
    except Exception:
        pass
    gc.collect()


