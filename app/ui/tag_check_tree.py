"""QTreeWidget: row click toggles checkbox; drag-drop reorder; viewport-safe hit testing."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDropEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemDelegate,
    QProxyStyle,
    QStyle,
    QStyleFactory,
    QStyleOption,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
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

# Filter panel: no persistent row highlight; hover on any row; selection state ignored visually.
_TAG_CHECK_TREE_QSS_FILTER = """
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
QTreeWidget::item:selected,
QTreeWidget::item:selected:active {
    background-color: transparent;
    border: none;
    outline: none;
}
QTreeWidget::item:hover {
    background-color: #3a3a3a;
}
"""

# Square checkbox edge (logical px) for tag trees. Edit this to resize; used with Fusion-backed style.
TAG_TREE_CHECKBOX_PX = 14


class _CompactTagTreeStyle(QProxyStyle):

    indicator_px: int = 14

    def styleHint(
        self,
        hint: QStyle.StyleHint,
        option: QStyleOption | None = None,
        widget=None,
        returnData=None,
    ) -> int:
        if hint == QStyle.StyleHint.SH_ScrollBar_Transient:
            return 1
        return super().styleHint(hint, option, widget, returnData)

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

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption | None,
        painter: QPainter | None,
        widget=None,
    ) -> None:
        if (
            element
            in (
                QStyle.PrimitiveElement.PE_IndicatorCheckBox,
                QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck,
            )
            and option is not None
            and painter is not None
            and widget is not None
            and widget.__class__.__name__ == "TagCheckTreeWidget"
        ):
            self._draw_tag_tree_checkbox(painter, option)
            return
        super().drawPrimitive(element, option, painter, widget)

    def _draw_tag_tree_checkbox(self, painter: QPainter, option: QStyleOption) -> None:
        """Dark neutral rounded box; checked = slightly stronger gray border + tick."""
        r = option.rect
        if r.width() < 2 or r.height() < 2:
            return
        st = option.state
        enabled = bool(st & QStyle.StateFlag.State_Enabled)
        hover = enabled and bool(st & QStyle.StateFlag.State_MouseOver)

        checked = bool(st & QStyle.StateFlag.State_On)
        indeterminate = bool(st & QStyle.StateFlag.State_NoChange) and not checked
        if isinstance(option, QStyleOptionViewItem):
            cs = option.checkState
            if cs == Qt.CheckState.Checked:
                checked, indeterminate = True, False
            elif cs == Qt.CheckState.PartiallyChecked:
                checked, indeterminate = False, True
            else:
                checked, indeterminate = False, False

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rf = QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 3.0

        if not enabled:
            bg = QColor("#262626")
            border = QColor("#383838")
        elif hover and checked:
            bg = QColor("#363636")
            border = QColor("#787878")
        elif hover:
            bg = QColor("#323232")
            border = QColor("#4e4e4e")
        elif checked:
            bg = QColor("#2e2e2e")
            border = QColor("#6a6a6a")
        else:
            bg = QColor("#2a2a2a")
            border = QColor("#404040")

        pen_w = 1.0

        painter.setPen(QPen(border, pen_w))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rf, radius, radius)

        if checked and not indeterminate:
            tick = QColor("#b0b0b0" if enabled else "#707070")
            painter.setPen(QPen(tick, 1.65))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            cx = rf.center().x()
            cy = rf.center().y()
            path = QPainterPath()
            path.moveTo(cx - 3.2, cy - 0.2)
            path.lineTo(cx - 0.9, cy + 2.3)
            path.lineTo(cx + 3.4, cy - 2.7)
            painter.drawPath(path)
        elif indeterminate:
            dash = QColor("#909090" if enabled else "#606060")
            painter.setPen(QPen(dash, 1.5))
            iy = int(round(rf.center().y()))
            painter.drawLine(int(rf.left() + 3), iy, int(rf.right() - 3), iy)

        painter.restore()


class TagCheckTreeWidget(QTreeWidget):

    reordered = Signal()

    def __init__(self, parent=None, *, filter_panel: bool = False) -> None:
        super().__init__(parent)
        self._tags_panel = None
        self.setStyleSheet(_TAG_CHECK_TREE_QSS_FILTER if filter_panel else _TAG_CHECK_TREE_QSS)
        # Windows "windowsvista"/"windows11" styles often ignore PM_ExclusiveIndicator* for view
        # checkboxes; Fusion honors them. Tree-only so the rest of the app stays native.
        base = QStyleFactory.create("Fusion") or QApplication.style()
        self._tree_style = _CompactTagTreeStyle(base)
        self._tree_style.indicator_px = TAG_TREE_CHECKBOX_PX
        self.setStyle(self._tree_style)
        # Keep keyboard focus on the preview: clicks toggle checks but do not focus this tree.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._press_pos_vp: QPoint | None = None
        self._press_item: QTreeWidgetItem | None = None

    def set_tags_panel(self, panel) -> None:
        self._tags_panel = panel

    def closeEditor(self, editor: QWidget, hint: QAbstractItemDelegate.EndEditHint) -> None:  # type: ignore[override]
        panel = self._tags_panel
        if panel is not None:
            panel.on_tree_close_editor(editor, hint)
        super().closeEditor(editor, hint)

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

    def inline_edit_left_inset(self, item: QTreeWidgetItem) -> int:
        """Pixels from the item rect's left edge to where label / inline field text should start."""
        vr = self.visualItemRect(item)
        if not vr.isValid():
            return 28
        return max(0, self._native_checkbox_right(item, vr) - vr.left() + 4)

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
            if self.itemWidget(item, 0) is not None:
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
