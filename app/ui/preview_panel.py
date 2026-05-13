"""Hosts stacked preview layout views."""

from __future__ import annotations

from collections.abc import Callable

from pathlib import Path

from PySide6.QtCore import QPoint, QMimeData, Signal
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget, QSizePolicy

from app.core.thumbnail_cache import ThumbnailCache
from app.views.base_view import BaseImageView
from app.views.filmstrip_view import FilmstripView
from app.views.justified_view import JustifiedView
from app.views.list_view import ListView
from app.views.masonry_view import MasonryView
from app.views.square_view import SquareGridView
from app.ui.drop_import import mime_looks_external_folder_import

_MODE_ORDER = ("masonry", "justified", "square", "filmstrip", "list")


class PreviewPanel(QWidget):
    selection_changed   = Signal(str)
    fullscreen_requested = Signal(str)
    delete_requested    = Signal(list)
    image_context_menu_requested = Signal(str, QPoint)
    open_in_photoshop_requested = Signal(str)

    def __init__(self, thumb_cache: ThumbnailCache, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = thumb_cache
        self._stack = QStackedWidget()
        self._stack.setMinimumWidth(0)
        self._paths: list[str] = []
        self._thumb_size = 128
        self._show_names = True
        self._tile_bg = True

        self._view_types: dict[str, type[BaseImageView]] = {
            "masonry": MasonryView,
            "justified": JustifiedView,
            "square": SquareGridView,
            "filmstrip": FilmstripView,
            "list": ListView,
        }
        self._views: dict[str, BaseImageView | None] = {mode: None for mode in _MODE_ORDER}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._stack)

        self._mode = "square"
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(True)

        self._import_drop_cb: Callable[[QMimeData], None] | None = None
        self._import_folder: Path | None = None
        self._cache.thumbnail_ready.connect(self._on_thumbnail_ready)

    def _import_mime_acceptable(self, mime: QMimeData) -> bool:
        return bool(
            self._import_folder
            and mime_looks_external_folder_import(mime, self._import_folder)
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._import_mime_acceptable(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._import_mime_acceptable(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if self._import_drop_cb and self._import_mime_acceptable(event.mimeData()):
            self._import_drop_cb(event.mimeData())
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def set_import_drop_folder(self, folder: str | None) -> None:
        self._import_folder = Path(folder).resolve() if folder else None

    def set_import_drop_handler(self, fn: Callable[[QMimeData], None] | None) -> None:
        """Handle drops over the preview panel itself."""
        self._import_drop_cb = fn

    def _wire_view(self, view: BaseImageView) -> None:
        view.selection_changed.connect(self.selection_changed.emit)
        view.fullscreen_requested.connect(self.fullscreen_requested.emit)
        view.delete_requested.connect(self.delete_requested.emit)
        view.image_context_menu_requested.connect(self.image_context_menu_requested.emit)
        view.open_in_photoshop_requested.connect(self.open_in_photoshop_requested.emit)
        view.setMinimumWidth(0)

    def _on_thumbnail_ready(self, path: str, payload: object) -> None:
        self.active_view().apply_thumbnail(path, payload)

    def _ensure_view(self, mode: str) -> BaseImageView:
        existing = self._views.get(mode)
        if existing is not None:
            return existing
        cls = self._view_types.get(mode, SquareGridView)
        view = cls(self._cache)
        self._wire_view(view)
        self._views[mode] = view
        self._stack.addWidget(view)
        return view

    def active_view(self) -> BaseImageView:
        return self._ensure_view(self._mode)

    def set_layout_mode(self, mode: str) -> None:
        if mode not in self._view_types:
            return
        self._mode = mode
        self.setUpdatesEnabled(False)
        try:
            self._stack.setCurrentWidget(self._ensure_view(mode))
            self._apply_to_active()
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def set_paths(self, paths: list[str]) -> None:
        self._paths = list(paths)
        self.setUpdatesEnabled(False)
        try:
            self._apply_to_active()
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def _apply_to_active(self) -> None:
        v = self.active_view()
        v.set_thumbnail_size(self._thumb_size, reflow=False)
        v.set_show_filenames(self._show_names)
        v.set_tile_background(self._tile_bg)
        v.set_paths(self._paths)

    def apply_prefs(self, thumb_size: int, show_names: bool) -> None:
        self._thumb_size = thumb_size
        self._show_names = show_names
        self.setUpdatesEnabled(False)
        try:
            self._apply_to_active()
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def set_thumbnail_size(self, size: int) -> None:
        self._thumb_size = size
        self.setUpdatesEnabled(False)
        try:
            self.active_view().set_thumbnail_size(size, reflow=True)
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def set_show_filenames(self, show: bool) -> None:
        self._show_names = show
        self.active_view().set_show_filenames(show)

    def set_tile_background(self, enabled: bool) -> None:
        self._tile_bg = enabled
        self.active_view().set_tile_background(enabled)

    def selected_path(self) -> str | None:
        return self.active_view().selected_path()

    def selected_paths(self) -> list[str]:
        return self.active_view().selected_paths()

    def take_preview_focus(self) -> None:
        self.active_view().take_preview_focus()

    def select_primary_path(self, path: str) -> bool:
        return self.active_view().select_primary_path(path)