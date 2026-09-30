import os
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QListWidget, QListWidgetItem)
class DragDropListWidget(QListWidget):
    paths_changed = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            for url in urls:
                path = url.toLocalFile()
                if path not in self.get_paths():
                    name = os.path.basename(path) or path
                    item = QListWidgetItem(name)
                    item.setData(Qt.UserRole, path)
                    self.addItem(item)
            self.paths_changed.emit()
            event.acceptProposedAction()
    def get_paths(self):
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]