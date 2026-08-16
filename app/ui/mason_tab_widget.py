"""QTabWidget with a horizontal seam line that leaves a gap under the active tab."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
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
    """Seam line under a tab bar, broken by the current tab.

    At the current tab's bottom corners the line curls up into the tab's side
    borders on a small radius, so the tab reads as standing in front of the seam
    rather than stopping just short of it. Drawing those elbows needs pixels
    *above* the seam, so the widget is ``CORNER_R + 1`` tall and is positioned by
    its owner to overlap the tab row, with the seam on its bottom edge.
    """

    CORNER_R = 3  # matches the tabs' border-top-*-radius
    TAB_RIGHT_MARGIN = 2  # QSS margin-right, i.e. tabRect is wider than the paint

    def __init__(self, tab_bar: QTabBar, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tb = tab_bar
        self.setFixedHeight(self.CORNER_R + 1)
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

    def _current_tab_edges(self) -> tuple[float, float] | None:
        """Centres of the current tab's painted side borders, in local x.

        ``None`` when no tab owns the seam and it should run unbroken.
        """
        tb = self._tb
        # Match preview tab styling: no "selected" tab when browsing a non-favorite folder.
        if tb.property("mason_browse_non_favorite"):
            return None
        if tb.count() <= 1 or tb.currentIndex() < 0:
            return None
        r = tb.tabRect(tb.currentIndex())
        if not r.isValid():
            return None
        # tabRect spans the tab's margin box; the border is drawn inside it.
        left = self.mapFromGlobal(tb.mapToGlobal(QPoint(r.left(), r.bottom()))).x()
        right = self.mapFromGlobal(
            tb.mapToGlobal(QPoint(r.right() - self.TAB_RIGHT_MARGIN, r.bottom()))
        ).x()
        if right <= left:
            return None
        return float(left) + 0.5, float(right) + 0.5

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        w = float(self.width())
        if w <= 0:
            return
        y = float(self.height()) - 0.5  # centre of the bottom row
        rad = float(self.CORNER_R)

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#666666"))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        edges = self._current_tab_edges()
        if edges is None:
            p.drawLine(QPointF(0.0, y), QPointF(w, y))
            p.end()
            return

        lx, rx = edges
        # Left run, curling up into the tab's left border. Both arcs sweep 90°
        # counter-clockwise, which in Qt's angle system rounds the inside of the
        # corner the same way the tab's top corners are rounded.
        if lx - rad > 0.0:
            left = QPainterPath()
            left.moveTo(0.0, y)
            left.lineTo(lx - rad, y)
            left.arcTo(QRectF(lx - 2 * rad, y - 2 * rad, 2 * rad, 2 * rad), 270.0, 90.0)
            p.drawPath(left)

        # Down from the tab's right border into the right run.
        if rx + rad < w:
            right = QPainterPath()
            right.moveTo(rx, y - rad)
            right.arcTo(QRectF(rx, y - 2 * rad, 2 * rad, 2 * rad), 180.0, 90.0)
            right.lineTo(w, y)
            p.drawPath(right)
        p.end()
