"""QListWidget: clicking the row (not only the check indicator) toggles ItemIsUserCheckable."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem, QStyle, QStyleOptionViewItem


class TagCheckListWidget(QListWidget):
    """Toggle checkbox on row click; preserve default behavior on the indicator; ignore drag gestures."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._press_pos: QPoint | None = None
        self._press_item_row: int | None = None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = QPoint(event.pos())
            it = self.itemAt(event.pos())
            self._press_item_row = self.row(it) if it is not None else None
        else:
            self._press_pos = None
            self._press_item_row = None
        super().mousePressEvent(event)

    def _check_indicator_rect(self, item: QListWidgetItem) -> QRect:
        """Style rect for the row's check box (PySide6 QListWidget.initStyleOption is not index-based)."""
        opt = QStyleOptionViewItem()
        opt.initFrom(self)
        opt.rect = self.visualItemRect(item)
        opt.text = item.text()
        opt.icon = item.icon()
        opt.checkState = item.checkState()
        opt.features = (
            QStyleOptionViewItem.ViewItemFeature.HasDisplay
            | QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        )
        if not opt.icon.isNull():
            opt.features |= QStyleOptionViewItem.ViewItemFeature.HasDecoration
        if self.currentItem() is item:
            opt.state |= QStyle.StateFlag.State_Selected
        if self.hasFocus() and self.currentItem() is item:
            opt.state |= QStyle.StateFlag.State_HasFocus
        return self.style().subElementRect(
            QStyle.SubElement.SE_ItemViewItemCheckIndicator,
            opt,
            self,
        )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        try:
            if event.button() != Qt.MouseButton.LeftButton or self._press_pos is None:
                return
            if (event.pos() - self._press_pos).manhattanLength() >= QApplication.startDragDistance():
                return
            item = self.itemAt(event.pos())
            if item is None or self._press_item_row is None or self.row(item) != self._press_item_row:
                return
            if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                return
            cb = self._check_indicator_rect(item)
            pos = event.pos()
            if cb.isValid() and cb.contains(pos):
                return
            if not cb.isValid():
                vr = self.visualItemRect(item)
                edge = min(32, max(18, vr.width() // 4))
                if pos.x() <= vr.left() + edge:
                    return
            item.setCheckState(
                Qt.CheckState.Checked
                if item.checkState() == Qt.CheckState.Unchecked
                else Qt.CheckState.Unchecked
            )
        finally:
            self._press_pos = None
            self._press_item_row = None
            super().mouseReleaseEvent(event)
