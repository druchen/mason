"""Top toolbar: centered layout modes; search + settings on the right."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFontMetrics, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QToolButton,
    QWidget,
)

from app.ui.micro_icons import ICON_TOOLBUTTON_QSS, gear_icon


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


_TOOLBAR_BORDER = "#383838"
_TOOLBAR_BORDER_HOVER = "#4a4a4a"
_TOOLBAR_BORDER_FOCUS = "#357abd"


class MainToolbar(QFrame):
    layout_mode_changed = Signal(str)
    search_changed = Signal(str)
    settings_clicked = Signal()

    MODES = ["masonry", "justified", "square", "filmstrip", "list"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mainToolBar")
        self.setStyleSheet(
            """
            QFrame#mainToolBar {
                border: none;
                border-bottom: 3px solid #222222;
            }
            """
        )
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
        mode_w = 100
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
        right_lay = QHBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(8)
        right_lay.addStretch(1)

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

        right_lay.addWidget(self._search)

        self._settings_btn = QToolButton()
        self._settings_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._settings_btn.setAutoRaise(True)
        self._settings_btn.setIcon(gear_icon())
        self._settings_btn.setStyleSheet(ICON_TOOLBUTTON_QSS)
        self._settings_btn.setToolTip("Open settings…")
        self._settings_btn.clicked.connect(self.settings_clicked.emit)
        right_lay.addWidget(self._settings_btn)

        lay.addWidget(right, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._sync_search_height()
        self.set_mode("square")

    def _sync_search_height(self) -> None:
        fm = QFontMetrics(self.font())
        h = max(22, min(28, fm.height() + 10))
        self._search.setFixedHeight(h)
        self._settings_btn.setFixedSize(h, h)
        icon_d = max(14, min(20, h - 8))
        self._settings_btn.setIconSize(QSize(icon_d, icon_d))

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
