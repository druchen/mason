"""QTabWidget with a horizontal seam line that leaves a gap under the active tab."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QTabBar, QTabWidget, QWidget


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
        if obj is self._tb and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Show,
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
