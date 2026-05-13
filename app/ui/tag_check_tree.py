"""QTreeWidget: row click toggles checkbox; drag-drop reorder; viewport-safe hit testing."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QDropEvent, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QProxyStyle,
    QStyle,
    QStyleFactory,
    QStyleOption,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
)

# Vertical spacing, compact square checkbox, no selection in branch gutter.
_TAG_CHECK_TREE_QSS = """
QTreeWidget {
    show-decoration-selected: 0;
    outline: none;
    background: transparent;
    border: none;
}
QTreeWidget:focus {
    outline: none;
}
QTreeWidget::item {
    padding-top: 5px;
    padding-bottom: 5px;
    border: none;
    outline: none;
}
QTreeWidget::item:selected {
    background-color: #505050;
    color: #f0f0f0;
    border: none;
    outline: none;
}
QTreeWidget::item:selected:active {
    background-color: #505050;
}
QTreeWidget::item:hover:!selected {
    background-color: #3a3a3a;
}
"""

# Square checkbox edge (logical px) for tag trees. Edit this to resize; used with Fusion-backed style.
TAG_TREE_CHECKBOX_PX = 14


class _CompactTagTreeStyle(QProxyStyle):

    indicator_px: int = 14

    def pixelMetric(
        self,
        metric: QStyle.PixelMetric,
        option: QStyleOption | None = None,
        widget=None,
    ) -> int:
        if metric in (
            QStyle.PixelMetric.PM_ExclusiveIndicatorWidth,
            QStyle.PixelMetric.PM_ExclusiveIndicatorHeight,
        ):
            return self.indicator_px
        return super().pixelMetric(metric, option, widget)

    def subElementRect(
        self,
        element: QStyle.SubElement,
        option: QStyleOption | None,
        widget=None,
    ) -> QRect:
        r = super().subElementRect(element, option, widget)
        if element != QStyle.SubElement.SE_ItemViewItemCheckIndicator or not r.isValid():
            return r
        d = self.indicator_px
        ny = r.top() + max(0, (r.height() - d) // 2)
        out = QRect(r.left(), ny, d, d)
        if isinstance(option, QStyleOptionViewItem):
            out = out.intersected(option.rect)
        return out


class TagCheckTreeWidget(QTreeWidget):

    reordered = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_TAG_CHECK_TREE_QSS)
        # Windows "windowsvista"/"windows11" styles often ignore PM_ExclusiveIndicator* for view
        # checkboxes; Fusion honors them. Tree-only so the rest of the app stays native.
        base = QStyleFactory.create("Fusion") or QApplication.style()
        self._tree_style = _CompactTagTreeStyle(base)
        self._tree_style.indicator_px = TAG_TREE_CHECKBOX_PX
        self.setStyle(self._tree_style)
        self._press_pos_vp: QPoint | None = None
        self._press_item: QTreeWidgetItem | None = None

    def _viewport_pos(self, event: QMouseEvent) -> QPoint:
        p = event.position().toPoint()
        return self.viewport().mapFrom(self, p)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos_vp = self._viewport_pos(event)
            self._press_item = self.itemAt(self._press_pos_vp)
        else:
            self._press_pos_vp = None
            self._press_item = None
        super().mousePressEvent(event)

    def _check_indicator_rect(self, item: QTreeWidgetItem) -> QRect:
        opt = QStyleOptionViewItem()
        opt.initFrom(self)
        opt.rect = self.visualItemRect(item)
        opt.text = item.text(0)
        opt.icon = item.icon(0)
        opt.checkState = item.checkState(0)
        opt.features = (
            QStyleOptionViewItem.ViewItemFeature.HasDisplay
            | QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        )
        if not opt.icon.isNull():
            opt.features |= QStyleOptionViewItem.ViewItemFeature.HasDecoration
        if item.childCount() > 0:
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

    def _native_checkbox_right(self, item: QTreeWidgetItem, vr: QRect) -> int:
        cb = self._check_indicator_rect(item)
        ind = self.style().pixelMetric(
            QStyle.PixelMetric.PM_ExclusiveIndicatorWidth, None, self
        )
        if ind <= 0:
            ind = self._tree_style.indicator_px
        margin = 6
        native = vr.left() + ind + margin
        if cb.isValid() and cb.width() > 0 and cb.width() <= 48:
            native = max(native, cb.right() + 2)
        return int(native)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        try:
            if event.button() != Qt.MouseButton.LeftButton or self._press_pos_vp is None:
                return
            vp_now = self._viewport_pos(event)
            if (vp_now - self._press_pos_vp).manhattanLength() >= QApplication.startDragDistance():
                return
            item = self.itemAt(vp_now)
            if item is None or item != self._press_item:
                return
            if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                return
            vr = self.visualItemRect(item)
            if not vr.contains(vp_now):
                return
            if vp_now.x() <= self._native_checkbox_right(item, vr):
                return
            item.setCheckState(
                0,
                Qt.CheckState.Checked
                if item.checkState(0) == Qt.CheckState.Unchecked
                else Qt.CheckState.Unchecked,
            )
        finally:
            self._press_pos_vp = None
            self._press_item = None
            super().mouseReleaseEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        super().dropEvent(event)
        self.reordered.emit()
