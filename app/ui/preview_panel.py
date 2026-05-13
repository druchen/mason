"""Hosts stacked preview layout views."""

from __future__ import annotations

from collections.abc import Callable

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QMimeData, Signal
from PySide6.QtGui import QCursor, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget, QSizePolicy

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

        self._views: dict[str, BaseImageView] = {
            "masonry":   MasonryView(thumb_cache),
            "justified": JustifiedView(thumb_cache),
            "square":    SquareGridView(thumb_cache),
            "filmstrip": FilmstripView(thumb_cache),
            "list":      ListView(thumb_cache),
        }
        for v in self._views.values():
            v.selection_changed.connect(self.selection_changed.emit)
            v.fullscreen_requested.connect(self.fullscreen_requested.emit)
            v.delete_requested.connect(self.delete_requested.emit)
            v.image_context_menu_requested.connect(self.image_context_menu_requested.emit)
            v.open_in_photoshop_requested.connect(self.open_in_photoshop_requested.emit)
            v.setMinimumWidth(0)

        for mode in _MODE_ORDER:
            self._stack.addWidget(self._views[mode])

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._stack)

        self._mode = "square"
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(True)

        self._import_drop_cb: Callable[[QMimeData], None] | None = None
        self._app_drop_filter_installed = False
        self._import_folder: Path | None = None

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
        """Handle drops of images from other apps anywhere over the preview subtree."""
        app = QApplication.instance()
        if app is not None and self._app_drop_filter_installed:
            app.removeEventFilter(self)
            self._app_drop_filter_installed = False
        self._import_drop_cb = fn
        if fn is not None and app is not None:
            app.installEventFilter(self)
            self._app_drop_filter_installed = True

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if self._import_drop_cb is None:
            return super().eventFilter(watched, event)
        et = event.type()
        if et not in (
            QEvent.Type.DragEnter,
            QEvent.Type.DragMove,
            QEvent.Type.Drop,
        ):
            return super().eventFilter(watched, event)

        gp = QCursor.pos()
        if isinstance(watched, QWidget):
            try:
                ev = event
                gp = watched.mapToGlobal(ev.position().toPoint())
            except (AttributeError, TypeError):
                pass
        if not self.rect().contains(self.mapFromGlobal(gp)):
            return super().eventFilter(watched, event)

        if et == QEvent.Type.DragEnter:
            de = event
            if isinstance(de, QDragEnterEvent) and self._import_mime_acceptable(de.mimeData()):
                de.acceptProposedAction()
                return True
            return super().eventFilter(watched, event)
        if et == QEvent.Type.DragMove:
            dm = event
            if isinstance(dm, QDragMoveEvent) and self._import_mime_acceptable(dm.mimeData()):
                dm.acceptProposedAction()
                return True
            return super().eventFilter(watched, event)
        if et == QEvent.Type.Drop:
            drop = event
            if isinstance(drop, QDropEvent) and self._import_drop_cb and self._import_mime_acceptable(
                drop.mimeData()
            ):
                self._import_drop_cb(drop.mimeData())
                drop.acceptProposedAction()
                return True
            return super().eventFilter(watched, event)
        return super().eventFilter(watched, event)

    def active_view(self) -> BaseImageView:
        return self._views[self._mode]

    def set_layout_mode(self, mode: str) -> None:
        if mode not in self._views:
            return
        self._mode = mode
        self._stack.setCurrentIndex(_MODE_ORDER.index(mode))
        self._apply_to_active()

    def set_paths(self, paths: list[str]) -> None:
        self._paths = list(paths)
        self._apply_to_active()

    def _apply_to_active(self) -> None:
        v = self.active_view()
        v.set_thumbnail_size(self._thumb_size)
        v.set_show_filenames(self._show_names)
        v.set_tile_background(self._tile_bg)
        v.set_paths(self._paths)

    def apply_prefs(self, thumb_size: int, show_names: bool) -> None:
        self._thumb_size = thumb_size
        self._show_names = show_names
        self._apply_to_active()

    def set_thumbnail_size(self, size: int) -> None:
        self._thumb_size = size
        self.active_view().set_thumbnail_size(size)

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