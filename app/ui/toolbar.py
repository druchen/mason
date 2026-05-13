"""Top toolbar: centered layout modes; search + sort + settings on the right."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.sort_filter import SortKey


class MainToolbar(QFrame):
    layout_mode_changed = Signal(str)
    search_changed = Signal(str)
    sort_changed = Signal(str)
    ascending_changed = Signal(bool)
    settings_clicked = Signal()

    MODES = ["masonry", "justified", "square", "filmstrip", "list"]

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
        self._buttons: dict[str, QToolButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)

        lay.addStretch(1)

        modes_host = QWidget()
        modes_lay = QHBoxLayout(modes_host)
        modes_lay.setContentsMargins(0, 0, 0, 0)
        modes_lay.setSpacing(6)
        fm = QFontMetrics(self.font())
        mode_w = max(fm.horizontalAdvance(m.title()) for m in self.MODES) + 28
        btn_h = 40
        for mode in self.MODES:
            btn = QToolButton()
            btn.setText(mode.title())
            btn.setCheckable(True)
            btn.setFixedSize(mode_w, btn_h)
            self._group.addButton(btn)
            btn.clicked.connect(lambda checked, m=mode: self._on_mode_clicked(m))
            self._buttons[mode] = btn
            modes_lay.addWidget(btn)
        lay.addWidget(modes_host, alignment=Qt.AlignmentFlag.AlignVCenter)

        lay.addStretch(1)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(4)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addStretch(1)
        search_row.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by filename…")
        self._search.setMinimumWidth(200)
        self._search.textChanged.connect(self.search_changed.emit)
        search_row.addWidget(self._search)

        sort_row = QHBoxLayout()
        sort_row.setSpacing(8)
        sort_row.addStretch(1)
        sort_row.addWidget(QLabel("Sort by:"))
        self._sort = QComboBox()
        for label, key in self.SORT_LABELS:
            self._sort.addItem(label, key)
        self._sort.currentIndexChanged.connect(self._emit_sort)
        sort_row.addWidget(self._sort)

        self._asc = QToolButton()
        self._asc.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._asc.setAutoRaise(True)
        self._asc.setFixedSize(QSize(32, 28))
        self._asc.setCheckable(True)
        self._asc.setChecked(True)
        self._asc.toggled.connect(self._on_asc_toggled)
        sort_row.addWidget(self._asc)

        self._settings_btn = QToolButton()
        self._settings_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._settings_btn.setAutoRaise(True)
        self._settings_btn.setText("Settings")
        self._settings_btn.setToolTip("Open settings…")
        self._settings_btn.clicked.connect(self.settings_clicked.emit)
        sort_row.addWidget(self._settings_btn)

        right_lay.addLayout(search_row)
        right_lay.addLayout(sort_row)
        lay.addWidget(right, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._refresh_asc_visual()
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
