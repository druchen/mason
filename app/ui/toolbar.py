"""Top toolbar: layout modes + search."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QWidget,
)


class MainToolbar(QFrame):
    layout_mode_changed = Signal(str)
    search_changed = Signal(str)

    MODES = ["masonry", "justified", "square", "filmstrip", "list"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: dict[str, QToolButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(4)

        lay.addWidget(QLabel("Layout:"))
        for mode in self.MODES:
            btn = QToolButton()
            btn.setText(mode.title())
            btn.setCheckable(True)
            self._group.addButton(btn)
            btn.clicked.connect(lambda checked, m=mode: self._on_mode_clicked(m))
            self._buttons[mode] = btn
            lay.addWidget(btn)

        lay.addStretch(1)

        lay.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by filename…")
        self._search.setMinimumWidth(200)
        self._search.textChanged.connect(self.search_changed.emit)
        lay.addWidget(self._search)

        self.set_mode("square")

    def _on_mode_clicked(self, mode: str) -> None:
        self.set_mode(mode)
        self.layout_mode_changed.emit(mode)

    def set_mode(self, mode: str) -> None:
        for m, btn in self._buttons.items():
            btn.setChecked(m == mode)

    def search_query(self) -> str:
        return self._search.text()

    def set_search_query(self, text: str) -> None:
        self._search.blockSignals(True)
        self._search.setText(text)
        self._search.blockSignals(False)

    def current_mode(self) -> str:
        for m, btn in self._buttons.items():
            if btn.isChecked():
                return m
        return "square"
