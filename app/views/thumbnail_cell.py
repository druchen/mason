"""Reusable thumbnail tile with optional filename label."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ThumbnailCell(QWidget):
    """Square tile showing an image thumbnail and optional filename."""

    clicked = Signal(str)

    def __init__(
        self,
        path: str,
        thumb_px: int,
        show_filename: bool,
        tile_background: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._thumb_px = thumb_px
        self._show_filename = show_filename
        self._pixmap: QPixmap | None = None

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setFixedSize(thumb_px, thumb_px)
        self._image_label.setScaledContents(False)

        self._name_label = QLabel(Path(path).name)
        self._name_label.setWordWrap(True)
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._name_label.setMaximumWidth(thumb_px)
        self._name_label.setVisible(show_filename)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        lay.addWidget(self._image_label)
        lay.addWidget(self._name_label)

        self.setMaximumWidth(thumb_px + 12)
        self.apply_tile_background(tile_background)
        self._apply_placeholder()

    def path(self) -> str:
        return self._path

    def set_thumbnail_size(self, thumb_px: int) -> None:
        self._thumb_px = thumb_px
        self._image_label.setFixedSize(thumb_px, thumb_px)
        self._name_label.setMaximumWidth(thumb_px)
        self.setMaximumWidth(thumb_px + 12)
        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self._thumb_px,
                self._thumb_px,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._image_label.setPixmap(scaled)
            self._image_label.setText("")
        else:
            self._apply_placeholder()

    def apply_tile_background(self, enabled: bool) -> None:
        if enabled:
            self._image_label.setStyleSheet(
                "background-color: #3c3c3c; border-radius: 4px; color: #888; font-size: 18px;"
            )
        else:
            self._image_label.setStyleSheet("background-color: transparent; color: #888; font-size: 18px;")

    def set_show_filename(self, show: bool) -> None:
        self._show_filename = show
        self._name_label.setVisible(show)

    def set_pixmap(self, pm: QPixmap) -> None:
        self._pixmap = pm
        if pm.isNull():
            self._apply_placeholder()
            return
        scaled = pm.scaled(
            self._thumb_px,
            self._thumb_px,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)
        self._image_label.setText("")

    def _apply_placeholder(self) -> None:
        self._image_label.clear()
        self._image_label.setText("…")

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit(self._path)
        super().mousePressEvent(event)
