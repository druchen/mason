"""Fullscreen single-image viewer.

Open with Space; close with Space or Escape.
Navigate with Left / Right (or Up / Down) arrow keys.
Click anywhere to close.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image as PILImage
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QImage, QKeyEvent, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


def _pil_to_pixmap(im: PILImage.Image) -> QPixmap:
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA") if "A" in im.getbands() else im.convert("RGB")
    if im.mode == "RGB":
        w, h = im.size
        buf = im.tobytes("raw", "RGB")
        qimg = QImage(buf, w, h, 3 * w, QImage.Format.Format_RGB888)
    else:
        w, h = im.size
        buf = im.tobytes("raw", "RGBA")
        qimg = QImage(buf, w, h, 4 * w, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class FullscreenView(QWidget):
    """Top-level fullscreen overlay. Emits signals for navigation and close."""

    closed = Signal()
    navigation_changed = Signal(str)    # emitted when current image changes

    def __init__(
        self,
        paths: list[str],
        current: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        )
        self.setStyleSheet("background: black;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._paths = list(paths)
        self._idx = self._paths.index(current) if current in self._paths else 0

        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setStyleSheet("background: black;")

        self._info_label = QLabel()
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info_label.setStyleSheet(
            "color: #cccccc; background: rgba(0,0,0,160);"
            "padding: 4px 12px; font-size: 10pt;"
        )
        self._info_label.setFixedHeight(30)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._img_label, stretch=1)
        lay.addWidget(self._info_label)

        self.showFullScreen()
        self._show_current()
        self.setFocus()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _show_current(self) -> None:
        if not self._paths:
            return
        path = self._paths[self._idx]
        name = Path(path).name
        self._info_label.setText(
            f"{name}    {self._idx + 1} / {len(self._paths)}"
            "    |    Space / Esc to close"
        )
        self._load_image(path)
        self.navigation_changed.emit(path)

    def _load_image(self, path: str) -> None:
        try:
            screen = self.screen().availableGeometry()
            max_w, max_h = screen.width(), screen.height() - 30
            with PILImage.open(path) as im:
                im.load()
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGBA") if "A" in im.getbands() else im.convert("RGB")
                im.thumbnail((max_w, max_h), PILImage.Resampling.LANCZOS)
                pm = _pil_to_pixmap(im)
            self._img_label.setPixmap(pm)
            self._img_label.setText("")
        except Exception as exc:
            self._img_label.setPixmap(QPixmap())
            self._img_label.setText(f"Cannot load image\n{exc}")
            self._img_label.setStyleSheet("background: black; color: #888; font-size: 11pt;")

    def _go_next(self) -> None:
        if self._paths:
            self._idx = (self._idx + 1) % len(self._paths)
            self._show_current()

    def _go_prev(self) -> None:
        if self._paths:
            self._idx = (self._idx - 1) % len(self._paths)
            self._show_current()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Escape, Qt.Key.Key_Return):
            self._close()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._go_next()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._go_prev()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self._close()

    def _close(self) -> None:
        self.close()
        self.closed.emit()
