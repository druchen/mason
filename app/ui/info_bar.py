"""Status bar: item count, thumbnail size slider, file-names toggle."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QSlider, QWidget


class InfoBar(QFrame):
    thumbnail_size_changed = Signal(int)
    show_filenames_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(12)

        self._count = QLabel("0 items")
        lay.addWidget(self._count)

        lay.addStretch(1)

        lay.addWidget(QLabel("Size:"))
        self._slider = QSlider()
        self._slider.setOrientation(Qt.Orientation.Horizontal)
        self._slider.setMinimum(48)
        self._slider.setMaximum(512)
        self._slider.setValue(128)
        self._slider.setFixedWidth(200)
        self._slider.valueChanged.connect(self.thumbnail_size_changed.emit)
        lay.addWidget(self._slider)

        self._names = QCheckBox("File names")
        self._names.setChecked(True)
        self._names.toggled.connect(self.show_filenames_changed.emit)
        lay.addWidget(self._names)

    def set_item_count(self, n: int) -> None:
        self._count.setText(f"{n} item" + ("" if n == 1 else "s"))

    def set_thumbnail_size(self, value: int) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(int(value))
        self._slider.blockSignals(False)

    def thumbnail_size(self) -> int:
        return int(self._slider.value())

    def set_show_filenames(self, on: bool) -> None:
        self._names.blockSignals(True)
        self._names.setChecked(on)
        self._names.blockSignals(False)

    def filenames_enabled(self) -> bool:
        return self._names.isChecked()
