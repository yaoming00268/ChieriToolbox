import os
import sys
import winreg
def add_context_menu():
    try:
        python_exe = sys.executable
        script_path = os.path.abspath("main.py")
        command = f'"{python_exe}" "{script_path}" "%V"'
        menu_name = "千绘莉的文件管理器喵"
        key_bg = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, r"Directory\Background\shell\ChieriFileManager")
        winreg.SetValue(key_bg, "", winreg.REG_SZ, menu_name)
        key_cmd_bg = winreg.CreateKey(key_bg, "command")
        winreg.SetValue(key_cmd_bg, "", winreg.REG_SZ, command)
        key_dir = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, r"Directory\shell\ChieriFileManager")
        winreg.SetValue(key_dir, "", winreg.REG_SZ, menu_name)
        key_cmd_dir = winreg.CreateKey(key_dir, "command")
        winreg.SetValue(key_cmd_dir, "", winreg.REG_SZ, command)
        print("注册表写入成功，右键菜单已添加喵！")
    except Exception as e:
        print(f"添加失败喵：{e}")
def remove_context_menu():
    try:
        winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, r"Directory\Background\shell\ChieriFileManager\command")
        winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, r"Directory\Background\shell\ChieriFileManager")
        winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, r"Directory\shell\ChieriFileManager\command")
        winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, r"Directory\shell\ChieriFileManager")
        print("注册表键值已删除，右键菜单已移除喵！")
    except Exception as e:
        print(f"移除失败喵：{e}")
