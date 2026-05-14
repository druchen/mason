"""Status bar: item count, thumbnail size slider."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QWidget


class InfoBar(QFrame):
    thumbnail_size_changed = Signal(int)

    _BTN_STYLE = """
        QPushButton {
            background: transparent;
            border: none;
            color: #d0d0d0;
            font-size: 18px;
            font-weight: 300;
            padding: 2px 6px;
            min-width: 22px;
        }
        QPushButton:hover {
            color: #ffffff;
        }
        QPushButton:pressed {
            color: #909090;
        }
        QPushButton:disabled {
            color: #505050;
        }
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 24, 4)
        lay.setSpacing(12)

        self._count = QLabel("0 items")
        lay.addWidget(self._count)

        lay.addStretch(1)

        self._minus = QPushButton("−")
        self._minus.setFlat(True)
        self._minus.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._minus.setCursor(Qt.CursorShape.PointingHandCursor)
        self._minus.setStyleSheet(self._BTN_STYLE)
        self._minus.clicked.connect(lambda: self._nudge_slider(-1))

        self._slider = QSlider()
        self._slider.setOrientation(Qt.Orientation.Horizontal)
        self._slider.setMinimum(48)
        self._slider.setMaximum(512)
        self._slider.setSingleStep(16)
        self._slider.setPageStep(64)
        self._slider.setValue(128)
        self._slider.setFixedWidth(200)
        self._slider.sliderReleased.connect(
            lambda: self.thumbnail_size_changed.emit(int(self._slider.value()))
        )
        self._slider.valueChanged.connect(self._sync_step_buttons)

        self._plus = QPushButton("+")
        self._plus.setFlat(True)
        self._plus.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plus.setStyleSheet(self._BTN_STYLE)
        self._plus.clicked.connect(lambda: self._nudge_slider(1))

        lay.addWidget(self._minus, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._slider, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._plus, 0, Qt.AlignmentFlag.AlignVCenter)

        self._sync_step_buttons()

    def _nudge_slider(self, direction: int) -> None:
        step = self._slider.singleStep()
        delta = step if direction > 0 else -step
        lo, hi = self._slider.minimum(), self._slider.maximum()
        v = max(lo, min(hi, int(self._slider.value()) + delta))
        self._slider.setValue(v)
        self.thumbnail_size_changed.emit(v)

    def _sync_step_buttons(self) -> None:
        v = int(self._slider.value())
        self._minus.setEnabled(v > self._slider.minimum())
        self._plus.setEnabled(v < self._slider.maximum())

    def set_item_count(self, n: int) -> None:
        self._count.setText(f"{n} item" + ("" if n == 1 else "s"))

    def set_thumbnail_size(self, value: int) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(int(value))
        self._slider.blockSignals(False)
        self._sync_step_buttons()

    def thumbnail_size(self) -> int:
        return int(self._slider.value())
