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

