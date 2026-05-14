"""QTabWidget with a horizontal seam line that leaves a gap under the active tab."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QTabBar, QTabWidget, QVBoxLayout, QWidget


class MasonPanelHeader(QWidget):
    """Single-row title strip plus divider; matches mason tab bar height (no tabs)."""

    @staticmethod
    def title_bar_inner_height(widget: QWidget) -> int:
        fm = QFontMetrics(widget.font())
        return max(28, min(36, fm.height() + 11))

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        trailing: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._title = QLabel(title)
        self._title.setObjectName("masonPanelHeaderTitle")
        h = MasonPanelHeader.title_bar_inner_height(self)
        self._title.setFixedHeight(h)
        self._top_row: QWidget | None = None

        if trailing is None:
            self._title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            lay.addWidget(self._title)
        else:
            row = QWidget()
            row.setFixedHeight(h)
            row.setStyleSheet("background-color: #1f1f1f;")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 6, 0)
            hl.setSpacing(4)
            self._title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            hl.addWidget(self._title, 0, Qt.AlignmentFlag.AlignVCenter)
            hl.addStretch(1)
            hl.addWidget(trailing, 0, Qt.AlignmentFlag.AlignVCenter)
            self._top_row = row
            lay.addWidget(row)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.NoFrame)
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #666666;")
        self._divider_line = line
        lay.addWidget(self._divider_line)

        self.setStyleSheet(
            """
            QLabel#masonPanelHeaderTitle {
                background: #1f1f1f;
                color: #d8d8d8;
                padding-left: 12px;
                padding-right: 12px;
                border: none;
            }
            """
        )

    def top_row_widget(self) -> QWidget | None:
        """Header row containing title + optional trailing controls, or ``None`` if title-only."""
        return self._top_row

    def divider_line(self) -> QFrame:
        """One-pixel separator below the title row (same for all headers)."""
        return self._divider_line


class MasonTabWidget(QTabWidget):
    """Draws the tab/content divider as two segments with a gap under the selected tab."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mason_panel_tabs")
        self._dl = QFrame(self)
        self._dr = QFrame(self)
        for f in (self._dl, self._dr):
            f.setFrameShape(QFrame.Shape.NoFrame)
            f.setStyleSheet("background-color: #666666;")
            f.setFixedHeight(1)
            f.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.currentChanged.connect(self._position_dividers)
        self.tabBar().installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.tabBar() and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Show,
        ):
            self._position_dividers()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_dividers()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._position_dividers()

    def _position_dividers(self) -> None:
        tb = self.tabBar()
        y = max(0, tb.geometry().bottom() - 1)
        w = max(0, self.width())
        for f in (self._dl, self._dr):
            f.hide()
        if w <= 0:
            return
        idx = self.currentIndex()
        n = self.count()
        if n <= 1 or idx < 0:
            self._dr.setGeometry(0, y, w, 1)
            self._dr.show()
            self._dr.raise_()
            return
        r = tb.tabRect(idx)
        if not r.isValid():
            self._dr.setGeometry(0, y, w, 1)
            self._dr.show()
            self._dr.raise_()
            return
        left_x = self.mapFromGlobal(tb.mapToGlobal(QPoint(r.left(), r.bottom()))).x()
        right_x = self.mapFromGlobal(tb.mapToGlobal(QPoint(r.right() + 1, r.bottom()))).x()
        left_w = max(0, min(left_x, w))
        rs = max(0, min(right_x, w))
        if left_w > 0:
            self._dl.setGeometry(0, y, left_w, 1)
            self._dl.show()
            self._dl.raise_()
        if w > rs:
            self._dr.setGeometry(rs, y, w - rs, 1)
            self._dr.show()
            self._dr.raise_()


class TabBarGapDividerLine(QWidget):
    """One-pixel-tall line with a gap under the tab bar's current tab (e.g. preview header)."""

    def __init__(self, tab_bar: QTabBar, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tb = tab_bar
        self.setFixedHeight(1)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        tab_bar.currentChanged.connect(lambda *_: self.update())
        tab_bar.tabMoved.connect(lambda *_: self.update())
        tab_bar.installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._tb:
            et = event.type()
            if et in (
                QEvent.Type.Resize,
                QEvent.Type.Move,
                QEvent.Type.Show,
                QEvent.Type.DynamicPropertyChange,
            ):
                self.update()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        w = self.width()
        if w <= 0:
            return
        tb = self._tb
        n = tb.count()
        idx = tb.currentIndex()
        p = QPainter(self)
        p.setPen(QPen(QColor("#666666")))
        # Match preview tab styling: no "selected" tab when browsing a non-favorite folder.
        if tb.property("mason_browse_non_favorite"):
            p.drawLine(0, 0, w, 0)
            p.end()
            return
        if n <= 1 or idx < 0:
            p.drawLine(0, 0, w, 0)
            p.end()
            return
        r = tb.tabRect(idx)
        if not r.isValid():
            p.drawLine(0, 0, w, 0)
            p.end()
            return
        left_x = self.mapFromGlobal(tb.mapToGlobal(QPoint(r.left(), r.bottom()))).x()
        right_x = self.mapFromGlobal(tb.mapToGlobal(QPoint(r.right() + 1, r.bottom()))).x()
        left_w = max(0, min(left_x, w))
        rs = max(0, min(right_x, w))
        if left_w > 0:
            p.drawLine(0, 0, left_w, 0)
        if w > rs:
            p.drawLine(rs, 0, w, 0)
        p.end()
