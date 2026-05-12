"""Second row: folder path + sort controls."""

from __future__ import annotations

from PySide6.QtCore import Signal, QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QWidget,
)

from app.core.sort_filter import SortKey


class NavBar(QFrame):
    sort_changed = Signal(str)
    ascending_changed = Signal(bool)
    settings_clicked = Signal()

    SORT_LABELS: list[tuple[str, SortKey]] = [
        ("Name", "name"),
        ("Date modified", "date_modified"),
        ("Date created", "date_created"),
        ("Size", "size"),
        ("Type", "type"),
        ("Random", "random"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(8)

        lay.addWidget(QLabel("Folder:"))
        self._path = QLineEdit()
        self._path.setReadOnly(True)
        self._path.setPlaceholderText("Select a folder in the left panel")
        lay.addWidget(self._path, stretch=1)

        lay.addWidget(QLabel("Sort by:"))
        self._sort = QComboBox()
        for label, key in self.SORT_LABELS:
            self._sort.addItem(label, key)
        self._sort.currentIndexChanged.connect(self._emit_sort)
        lay.addWidget(self._sort)

        self._asc = QToolButton()
        self._asc.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._asc.setAutoRaise(True)
        self._asc.setFixedSize(QSize(32, 26))
        self._asc.setCheckable(True)
        self._asc.setChecked(True)
        self._asc.toggled.connect(self._on_asc_toggled)
        lay.addWidget(self._asc)

        self._settings_btn = QToolButton()
        self._settings_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._settings_btn.setAutoRaise(True)
        self._settings_btn.setText("Settings")
        self._settings_btn.setToolTip("Open settings…")
        self._settings_btn.clicked.connect(self.settings_clicked.emit)
        lay.addWidget(self._settings_btn)

        self._refresh_asc_visual()

    def _refresh_asc_visual(self) -> None:
        if self._asc.isChecked():
            self._asc.setArrowType(Qt.ArrowType.UpArrow)
            self._asc.setToolTip("Ascending")
        else:
            self._asc.setArrowType(Qt.ArrowType.DownArrow)
            self._asc.setToolTip("Descending")

    def _emit_sort(self) -> None:
        key = self._sort.currentData()
        if isinstance(key, str):
            self.sort_changed.emit(key)

    def _on_asc_toggled(self, asc: bool) -> None:
        self._refresh_asc_visual()
        self.ascending_changed.emit(asc)

    def set_folder_path(self, path: str) -> None:
        self._path.setText(path)

    def folder_path(self) -> str:
        return self._path.text()

    def set_sort(self, sort_by: SortKey, ascending: bool) -> None:
        idx = next((i for i in range(self._sort.count()) if self._sort.itemData(i) == sort_by), 0)
        self._sort.blockSignals(True)
        self._sort.setCurrentIndex(idx)
        self._sort.blockSignals(False)
        self._asc.blockSignals(True)
        self._asc.setChecked(ascending)
        self._asc.blockSignals(False)
        self._refresh_asc_visual()

    def sort_key(self) -> SortKey:
        k = self._sort.currentData()
        return str(k) if isinstance(k, str) else "name"

    def ascending(self) -> bool:
        return self._asc.isChecked()
