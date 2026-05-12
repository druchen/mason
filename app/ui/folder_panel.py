"""Folder tree (directories only)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, Signal
from PySide6.QtWidgets import QFileSystemModel, QLabel, QTreeView, QVBoxLayout, QWidget


class FolderPanel(QWidget):
    folder_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = QFileSystemModel()
        self._model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        self._model.setRootPath("")

        self._tree = QTreeView()
        self._tree.setModel(self._model)
        for col in range(1, 4):
            self._tree.hideColumn(col)
        self._tree.setHeaderHidden(True)
        self._tree.clicked.connect(self._on_clicked)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("Folders"))
        lay.addWidget(self._tree)

    def _on_clicked(self, index: QModelIndex) -> None:
        path = self._model.filePath(index)
        if Path(path).is_dir():
            self.folder_selected.emit(path)

    def set_root_path(self, path: str) -> None:
        self._tree.setRootIndex(self._model.index(path))

    def select_path(self, path: str) -> None:
        p = Path(path)
        if p.is_dir():
            idx = self._model.index(str(p))
            if idx.isValid():
                self._tree.setCurrentIndex(idx)
                self._tree.expand(idx)
