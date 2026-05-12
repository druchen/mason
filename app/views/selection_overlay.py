"""Selection outline painted above thumbnail children.

Parent stylesheet borders lie *under* child widgets (e.g. opaque QLabel thumbnails),
which hides most of the frame; overlay is stacked on top."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


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
