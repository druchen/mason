"""Top toolbar: centered layout modes; search + sort + settings on the right."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QFontMetrics,
    QIcon,
    QMouseEvent,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
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

_SORT_POPUP_WIDTH_PX = 120
_TOOLBAR_BORDER = "#383838"
_TOOLBAR_BORDER_HOVER = "#4a4a4a"
_TOOLBAR_BORDER_FOCUS = "#357abd"


def _toolbar_search_magnifier_icon() -> QIcon:
    d = 16
    pm = QPixmap(d, d)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(230, 230, 230))
    pen.setWidthF(1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(3, 3, 6, 6)
    p.drawLine(9, 9, 14, 14)
    p.end()
    return QIcon(pm)


def _toolbar_sort_chevron_pixmap() -> QPixmap:
    w, h = 10, 6
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(220, 220, 220))
    pen.setWidthF(1.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawLine(1, 2, 5, 5)
    p.drawLine(5, 5, 9, 2)
    p.end()
    return pm


class _ToolbarSortArrow(QLabel):

    def __init__(self, combo: QComboBox, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._combo = combo
        self.setObjectName("toolbarSortArrow")
        self.setAutoFillBackground(False)
        self.setPixmap(_toolbar_sort_chevron_pixmap())
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Choose sort…")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._combo.setFocus()
            self._combo.showPopup()
        super().mousePressEvent(event)


class MainToolbar(QFrame):
    layout_mode_changed = Signal(str)
    search_changed = Signal(str)
    sort_changed = Signal(str)
    ascending_changed = Signal(bool)
    settings_clicked = Signal()

    MODES = ["masonry", "justified", "square", "filmstrip", "list"]

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
        self._search = QLineEdit()
        self._search.setObjectName("toolbarSearch")
        self._search.setPlaceholderText("Search")
        self._search.setMinimumWidth(200)
        self._search.setMaximumWidth(320)
        self._search.textChanged.connect(self.search_changed.emit)

        _lead = QAction(self._search)
        _lead.setIcon(_toolbar_search_magnifier_icon())
        self._search.addAction(_lead, QLineEdit.ActionPosition.LeadingPosition)

        pal = self._search.palette()
        pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.PlaceholderText, QColor(140, 140, 140))
        self._search.setPalette(pal)

        self._search.setStyleSheet(
            f"""
            QLineEdit#toolbarSearch {{
                background-color: #1a1a1a;
                border: 0.5px solid {_TOOLBAR_BORDER};
                border-radius: 4px;
                padding-top: 2px;
                padding-bottom: 2px;
                padding-right: 8px;
                padding-left: 4px;
                color: #ececec;
                selection-background-color: #5ab4f5;
                selection-color: #ffffff;
            }}
            QLineEdit#toolbarSearch:hover:!focus {{
                border: 0.5px solid {_TOOLBAR_BORDER_HOVER};
            }}
            QLineEdit#toolbarSearch:focus {{
                border: 0.5px solid {_TOOLBAR_BORDER_FOCUS};
            }}
            """
        )

        search_row.addWidget(self._search)

        sort_row = QHBoxLayout()
        sort_row.setSpacing(8)
        sort_row.addStretch(1)

        self._sort_frame = QFrame()
        self._sort_frame.setObjectName("toolbarSortFrame")
        sort_inner = QHBoxLayout(self._sort_frame)
        sort_inner.setContentsMargins(0, 0, 4, 0)
        sort_inner.setSpacing(2)

        self._sort_prefix = QLabel("Sort by")
        self._sort_prefix.setObjectName("toolbarSortPrefix")
        sort_inner.addWidget(self._sort_prefix, 0, Qt.AlignmentFlag.AlignVCenter)

        self._sort = QComboBox()
        self._sort.setObjectName("toolbarSortCombo")
        for label, key in self.SORT_LABELS:
            self._sort.addItem(label, key)
        self._sort.currentIndexChanged.connect(self._emit_sort)
        self._sort.setMinimumWidth(72)
        sort_inner.addWidget(self._sort, 1)

        self._sort_arrow = _ToolbarSortArrow(self._sort, self._sort_frame)
        sort_inner.addWidget(self._sort_arrow, 0, Qt.AlignmentFlag.AlignVCenter)

        self._apply_sort_frame_style(False)
        self._sort.installEventFilter(self)

        self._sort_frame.setMinimumWidth(158)
        self._sort_frame.setMaximumWidth(280)
        sort_row.addWidget(self._sort_frame)

        self._configure_sort_popup_width()

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

        self._sync_toolbar_field_heights()

        self._refresh_asc_visual()
        self.set_mode("square")

    def _configure_sort_popup_width(self) -> None:
        view = self._sort.view()
        if view is None:
            return
        view.setFixedWidth(_SORT_POPUP_WIDTH_PX)
        view.setTextElideMode(Qt.TextElideMode.ElideNone)

    def _sync_toolbar_field_heights(self) -> None:
        fm = QFontMetrics(self.font())
        h = max(22, min(28, fm.height() + 10))
        self._search.setFixedHeight(h)
        self._sort_frame.setFixedHeight(h)
        self._sort_arrow.setFixedSize(12, h)

    def _apply_sort_frame_style(self, focused: bool) -> None:
        border = _TOOLBAR_BORDER_FOCUS if focused else _TOOLBAR_BORDER
        hover_border = _TOOLBAR_BORDER_HOVER if not focused else border
        self._sort_frame.setStyleSheet(
            f"""
            QFrame#toolbarSortFrame {{
                background-color: #1a1a1a;
                border: 0.5px solid {border};
                border-radius: 4px;
            }}
            QFrame#toolbarSortFrame:hover {{
                border: 0.5px solid {hover_border};
            }}
            QLabel#toolbarSortPrefix {{
                color: #8c8c8c;
                background: transparent;
                border: none;
                padding-left: 6px;
                padding-right: 0px;
            }}
            QLabel#toolbarSortArrow {{
                background: transparent;
                border: none;
            }}
            QComboBox#toolbarSortCombo {{
                border: none;
                background: transparent;
                color: #8c8c8c;
                padding-top: 2px;
                padding-bottom: 2px;
                padding-left: 2px;
                padding-right: 4px;
                min-height: 0px;
            }}
            QComboBox#toolbarSortCombo:hover {{
                border: none;
            }}
            QComboBox#toolbarSortCombo::drop-down {{
                width: 0px;
                height: 0px;
                border: none;
            }}
            """
        )

    def _sort_focus_family(self, w: QWidget | None) -> bool:
        if w is None:
            return False
        if w is self._sort:
            return True
        view = self._sort.view()
        if view is not None and (w is view or view.isAncestorOf(w)):
            return True
        return False

    def _sync_sort_frame_focus_from_app(self) -> None:
        self._apply_sort_frame_style(self._sort_focus_family(QApplication.focusWidget()))

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:  # type: ignore[override]
        if obj is self._sort:
            et = ev.type()
            if et == QEvent.Type.FocusIn:
                self._apply_sort_frame_style(True)
            elif et == QEvent.Type.FocusOut:
                QTimer.singleShot(0, self._sync_sort_frame_focus_from_app)
        return super().eventFilter(obj, ev)

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
