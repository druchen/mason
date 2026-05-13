"""Abstract base for preview layout views."""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from app.core.thumbnail_cache import ThumbnailCache


class BaseImageView(QWidget):
    """Common interface for masonry, grid, filmstrip, list, etc."""

    selection_changed = Signal(str)
    fullscreen_requested = Signal(str)
    delete_requested = Signal(list)
    image_context_menu_requested = Signal(str, QPoint)
    open_in_photoshop_requested = Signal(str)

    def __init__(self, thumb_cache: "ThumbnailCache", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._thumb_cache = thumb_cache
        self._thumbnail_size = 128
        self._tile_background = True
        self._paths: list[str] = []

    def thumb_cache(self) -> "ThumbnailCache":
        return self._thumb_cache

    def paths(self) -> list[str]:
        return list(self._paths)

    def thumbnail_size(self) -> int:
        return self._thumbnail_size

    def tile_background(self) -> bool:
        return self._tile_background

    @abstractmethod
    def set_paths(self, paths: list[str]) -> None:
        """Replace displayed image paths."""

    @abstractmethod
    def select_primary_path(self, path: str) -> bool:
        """Select ``path`` as the sole primary selection if it appears in the current paths."""

    def set_thumbnail_size(self, size: int, *, reflow: bool = True) -> None:
        del reflow
        self._thumbnail_size = max(48, min(512, int(size)))

    def set_tile_background(self, enabled: bool) -> None:
        self._tile_background = bool(enabled)

    def selected_path(self) -> str | None:
        return getattr(self, "_selected_path", None)

    def selected_paths(self) -> list[str]:
        p = self.selected_path()
        return [p] if p else []

    def take_preview_focus(self) -> None:
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def apply_thumbnail(self, path: str, payload: object) -> None:
        del path, payload
