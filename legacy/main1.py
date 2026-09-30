import ctypes
import os
import sys
from registered import is_admin
from setup_menu import remove_context_menu, add_context_menu
if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "auto":
            add_context_menu()
        elif sys.argv[1] == "remove":
            remove_context_menu()
    else:
        print("1. 注册文件夹右键菜单喵")
        print("2. 移除文件夹右键菜单喵")
        choice = input("请主人输入选择(1或2)：")
        if choice == "1":
            if is_admin():
                add_context_menu()
            else:
                script = os.path.abspath(__file__)
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" auto', None, 1)
        elif choice == "2":
            if is_admin():
                remove_context_menu()
            else:
                script = os.path.abspath(__file__)
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" remove', None, 1)
        input("按回车键退出喵...")