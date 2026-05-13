"""Status bar: item count, thumbnail size slider."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSlider, QWidget


class InfoBar(QFrame):
    thumbnail_size_changed = Signal(int)

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
        self._slider.sliderReleased.connect(
            lambda: self.thumbnail_size_changed.emit(int(self._slider.value()))
        )
        lay.addWidget(self._slider)

    def set_item_count(self, n: int) -> None:
        self._count.setText(f"{n} item" + ("" if n == 1 else "s"))

    def set_thumbnail_size(self, value: int) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(int(value))
        self._slider.blockSignals(False)

    def thumbnail_size(self) -> int:
        return int(self._slider.value())
