"""Compact sort dropdown + ascending toggle (used on preview header bar)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)

from app.core.sort_filter import SortKey, bump_random_sort_seed
from app.ui.micro_icons import ICON_TOOLBUTTON_QSS, chevron_down_small_pm, sort_direction_arrow_pm

_SORT_POPUP_WIDTH_PX = 120
_TOOLBAR_BORDER = "#383838"
_TOOLBAR_BORDER_HOVER = "#4a4a4a"


class _SortArrowLabel(QLabel):
    def __init__(self, combo: QComboBox, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._combo = combo
        self.setObjectName("sortControlArrow")
        self.setAutoFillBackground(False)
        self.setPixmap(chevron_down_small_pm())
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Choose sort…")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._combo.setFocus()
            self._combo.showPopup()
        super().mousePressEvent(event)


class SortControlBar(QWidget):
    sort_changed = Signal(str)
    ascending_changed = Signal(bool)

    SORT_LABELS: list[tuple[str, SortKey]] = [
        ("Name", "name"),
        ("Date Modified", "date_modified"),
        ("Date Created", "date_created"),
        ("Size", "size"),
        ("Type", "type"),
        ("Random", "random"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ascending = True

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)

        self._frame = QFrame()
        self._frame.setObjectName("sortControlFrame")
        inner = QHBoxLayout(self._frame)
        inner.setContentsMargins(0, 0, 3, 0)
        inner.setSpacing(1)

        self._prefix = QLabel("Sort by")
        self._prefix.setObjectName("sortControlPrefix")
        inner.addWidget(self._prefix, 0, Qt.AlignmentFlag.AlignVCenter)

        self._combo = QComboBox()
        self._combo.setObjectName("sortControlCombo")
        for label, key in self.SORT_LABELS:
            self._combo.addItem(label, key)
        self._combo.activated.connect(self._on_sort_activated)
        self._combo.setMinimumWidth(64)
        inner.addWidget(self._combo, 1, Qt.AlignmentFlag.AlignVCenter)

        self._arrow = _SortArrowLabel(self._combo, self._frame)
        inner.addWidget(self._arrow, 0, Qt.AlignmentFlag.AlignVCenter)

        self._apply_frame_style()

        self._asc = QToolButton()
        self._asc.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._asc.setAutoRaise(True)
        self._asc.setCheckable(False)
        self._asc.setFixedSize(QSize(22, 18))
        self._asc.setIconSize(QSize(12, 12))
        self._asc.setStyleSheet(ICON_TOOLBUTTON_QSS)
        self._asc.clicked.connect(self._on_asc_clicked)

        root.addWidget(self._frame, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(self._asc, 0, Qt.AlignmentFlag.AlignVCenter)

        self._configure_popup_width()
        self.set_field_height(max(22, min(28, QFontMetrics(self.font()).height() + 10)))
        self._refresh_asc_icon()

    def set_field_height(self, h: int) -> None:
        self._frame.setFixedHeight(h)
        self._arrow.setFixedSize(11, h)
        self._asc.setFixedSize(max(20, h), h)

    def _configure_popup_width(self) -> None:
        view = self._combo.view()
        if view is None:
            return
        view.setFixedWidth(_SORT_POPUP_WIDTH_PX)
        view.setTextElideMode(Qt.TextElideMode.ElideNone)

    def _apply_frame_style(self) -> None:
        self._frame.setStyleSheet(
            f"""
            QFrame#sortControlFrame {{
                background-color: #1a1a1a;
                border: 0.5px solid {_TOOLBAR_BORDER};
                border-radius: 3px;
            }}
            QFrame#sortControlFrame:hover {{
                border: 0.5px solid {_TOOLBAR_BORDER_HOVER};
            }}
            QLabel#sortControlPrefix {{
                color: #8c8c8c;
                background: transparent;
                border: none;
                padding-left: 4px;
                padding-right: 0px;
            }}
            QLabel#sortControlArrow {{
                background: transparent;
                border: none;
            }}
            QComboBox#sortControlCombo {{
                border: none;
                background: transparent;
                color: #8c8c8c;
                padding: 0px 2px;
                min-height: 0px;
            }}
            QComboBox#sortControlCombo::drop-down {{
                width: 0px;
                height: 0px;
                border: none;
            }}
            """
        )

    def _on_sort_activated(self, index: int) -> None:
        key = self._combo.itemData(index)
        if not isinstance(key, str):
            return
        if key == "random":
            bump_random_sort_seed()
        self.sort_changed.emit(key)

    def _on_asc_clicked(self) -> None:
        self._ascending = not self._ascending
        self._refresh_asc_icon()
        self.ascending_changed.emit(self._ascending)

    def _refresh_asc_icon(self) -> None:
        pm = sort_direction_arrow_pm(up=self._ascending, d=14)
        self._asc.setIcon(QIcon(pm))
        self._asc.setToolTip("Ascending" if self._ascending else "Descending")

    def set_sort(self, sort_by: SortKey, ascending: bool) -> None:
        idx = next((i for i in range(self._combo.count()) if self._combo.itemData(i) == sort_by), 0)
        self._combo.blockSignals(True)
        self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)
        self._ascending = ascending
        self._refresh_asc_icon()

    def sort_key(self) -> SortKey:
        k = self._combo.currentData()
        return str(k) if isinstance(k, str) else "name"

    def ascending(self) -> bool:
        return self._ascending
