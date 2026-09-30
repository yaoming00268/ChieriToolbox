import sys
import registered
from PySide6.QtWidgets import QApplication
from gui import FileManagerGUI
def main():
    if not registered.is_menu_registered():
        registered.auto_register()
    app = QApplication(sys.argv)
    initial_paths = sys.argv[1:] if len(sys.argv) > 1 else None
    window = FileManagerGUI(initial_paths)
    window.show()
    sys.exit(app.exec())
if __name__ == "__main__":
    main()