"""Selection outline painted above thumbnail children.

Parent stylesheet borders lie *under* child widgets (e.g. opaque QLabel thumbnails),
which hides most of the frame; overlay is stacked on top.

``NoFillSelectionDelegate`` paints items as **non-selected** (``State_Selected`` cleared) so
the Qt style does not fill the cell, then draws a blue outline on top. Stylesheets should keep
``::item:selected`` background/border transparent so they cannot re-tint the cell.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem, QWidget

_SEL_OUTLINE = QColor(90, 180, 245)
_SEL_PEN_WIDTH = 2
_SEL_RADIUS = 2.0


class SelectionOutlineOverlay(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("mason_sel_outline")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "#mason_sel_outline { "
            "border: 1px solid #5ab4f5; background: transparent; border-radius: 0;"
            " }"
        )
        self.hide()

    def sync_geometry(self, inset_px: int = 1) -> None:
        p = self.parentWidget()
        if not p:
            return
        m = max(0, inset_px)
        w = max(0, p.width() - 2 * m)
        h = max(0, p.height() - 2 * m)
        self.setGeometry(m, m, w, h)

    def set_outline_visible(self, on: bool) -> None:
        self.setVisible(on)
        if on:
            self.sync_geometry()
            self.raise_()


class NoFillSelectionDelegate(QStyledItemDelegate):
    """Paints without the style's selection fill; draws only a blue frame for selected rows/tiles."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # type: ignore[override]
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        opt.showDecorationSelected = False
        was_selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        if was_selected:
            opt.state &= ~QStyle.StateFlag.State_Selected
            for grp in (
                QPalette.ColorGroup.Active,
                QPalette.ColorGroup.Inactive,
                QPalette.ColorGroup.Disabled,
            ):
                opt.palette.setBrush(grp, QPalette.ColorRole.Highlight, QBrush(Qt.GlobalColor.transparent))
                opt.palette.setBrush(
                    grp,
                    QPalette.ColorRole.HighlightedText,
                    opt.palette.brush(grp, QPalette.ColorRole.Text),
                )
        super().paint(painter, opt, index)
        if was_selected:
            painter.save()
            pen = QPen(_SEL_OUTLINE)
            pen.setWidth(_SEL_PEN_WIDTH)
            pen.setCosmetic(True)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            inset = float(_SEL_PEN_WIDTH) * 0.5
            rf = QRectF(opt.rect).adjusted(inset, inset, -inset, -inset)
            painter.drawRoundedRect(rf, _SEL_RADIUS, _SEL_RADIUS)
            painter.restore()
