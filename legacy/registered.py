import os
import sys
import winreg
import ctypes
from setup_menu import add_context_menu
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False
def is_menu_registered():
    try:
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Directory\Background\shell\ChieriFileManager")
        winreg.CloseKey(key)
        return True
    except Exception:
        return False
def auto_register():
    if is_admin():
        add_context_menu()
    else:
        script = os.path.abspath(__file__)
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" auto', None, 1)