"""Top toolbar: side-panel toggle at the left, search centred, settings at the right."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QToolButton,
    QWidget,
)

from app.ui.micro_icons import ICON_TOOLBUTTON_QSS, gear_icon, left_panel_icon

_SEARCH_MIN_W = 320
_SEARCH_MAX_W = 560

_TOOLBAR_BORDER = "#383838"
_TOOLBAR_BORDER_HOVER = "#4a4a4a"
_TOOLBAR_BORDER_FOCUS = "#357abd"


class MainToolbar(QFrame):
    layout_mode_changed = Signal(str)
    search_changed = Signal(str)
    settings_clicked = Signal()
    left_panel_toggled = Signal(bool)

    # Only the tile grid survives. The selector is gone, but the mode plumbing
    # in window.py and preview_panel still expects a list.
    MODES = ["essential"]

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

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)

        self._left_toggle = QToolButton()
        self._left_toggle.setObjectName("leftPanelToggle")
        self._left_toggle.setCheckable(True)
        self._left_toggle.setChecked(True)
        self._left_toggle.setIcon(left_panel_icon(18))
        self._left_toggle.setIconSize(QSize(18, 18))
        self._left_toggle.setFixedSize(34, 34)
        self._left_toggle.setToolTip("Show or hide the side panel")
        self._left_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._left_toggle.setStyleSheet(ICON_TOOLBUTTON_QSS)
        self._left_toggle.toggled.connect(self.left_panel_toggled.emit)
        lay.addWidget(self._left_toggle, 0, Qt.AlignmentFlag.AlignVCenter)

        # Equal stretches either side centre the field. The toggle and the gear
        # share a 34px footprint, so it lands on the true window centre rather
        # than the centre of the space between them.
        lay.addStretch(1)

        self._search = QLineEdit()
        self._search.setObjectName("toolbarSearch")
        self._search.setPlaceholderText("Search")
        self._search.setMinimumWidth(_SEARCH_MIN_W)
        self._search.setMaximumWidth(_SEARCH_MAX_W)
        self._search.textChanged.connect(self.search_changed.emit)

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
                padding-right: 10px;
                padding-left: 10px;
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

        lay.addWidget(self._search, 1, Qt.AlignmentFlag.AlignVCenter)

        lay.addStretch(1)

        self._settings_btn = QToolButton()
        self._settings_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._settings_btn.setAutoRaise(True)
        self._settings_btn.setStyleSheet(ICON_TOOLBUTTON_QSS)
        self._settings_btn.setToolTip("Open settings…")
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.clicked.connect(self.settings_clicked.emit)
        lay.addWidget(self._settings_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self._sync_search_height()
        self.set_mode("essential")

    def _sync_search_height(self) -> None:
        fm = QFontMetrics(self.font())
        h = max(22, min(28, fm.height() + 10))
        self._search.setFixedHeight(h)
        # Match the panel toggle's footprint so the two ends read as a pair. The
        # gear glyph sits inset in its viewbox, so it is drawn a touch larger to
        # land at the same optical weight, and rendered at its final size rather
        # than scaled up from a smaller pixmap.
        self._settings_btn.setFixedSize(34, 34)
        self._settings_btn.setIconSize(QSize(20, 20))
        self._settings_btn.setIcon(gear_icon(20))

    def _on_mode_clicked(self, mode: str) -> None:
        self.set_mode(mode)
        self.layout_mode_changed.emit(mode)

    def set_mode(self, mode: str) -> None:
        for m, btn in self._buttons.items():
            btn.setChecked(m == mode)

    def set_left_panel_shown(self, shown: bool) -> None:
        """Reflect state without emitting, for restoring at startup."""
        self._left_toggle.blockSignals(True)
        self._left_toggle.setChecked(bool(shown))
        self._left_toggle.blockSignals(False)

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
        return "essential"
