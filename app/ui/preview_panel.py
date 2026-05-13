"""Hosts stacked preview layout views."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QMimeData, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QFontMetrics
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from app.core.sort_filter import SortKey
from app.core.thumbnail_cache import ThumbnailCache
from app.ui.drop_import import mime_looks_external_folder_import
from app.ui.sort_control import SortControlBar
from app.views.base_view import BaseImageView
from app.views.filmstrip_view import FilmstripView
from app.views.justified_view import JustifiedView
from app.views.list_view import ListView
from app.views.masonry_view import MasonryView
from app.views.square_view import SquareGridView

_MODE_ORDER = ("masonry", "justified", "square", "filmstrip", "list")


class PreviewPanel(QWidget):
    selection_changed = Signal(str)
    fullscreen_requested = Signal(str)
    delete_requested = Signal(list)
    image_context_menu_requested = Signal(str, QPoint)
    open_in_photoshop_requested = Signal(str)
    sort_changed = Signal(str)
    ascending_changed = Signal(bool)
    favorite_folder_selected = Signal(str)
    favorites_order_changed = Signal(list)

    def __init__(self, thumb_cache: ThumbnailCache, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = thumb_cache
        self._syncing_fav_tabs = False

        self._stack = QStackedWidget()
        self._stack.setMinimumWidth(0)
        self._paths: list[str] = []
        self._thumb_size = 128
        self._tile_bg = True

        self._view_types: dict[str, type[BaseImageView]] = {
            "masonry": MasonryView,
            "justified": JustifiedView,
            "square": SquareGridView,
            "filmstrip": FilmstripView,
            "list": ListView,
        }
        self._views: dict[str, BaseImageView | None] = {mode: None for mode in _MODE_ORDER}

        self._fav_tabs = QTabBar()
        self._fav_tabs.setMovable(True)
        self._fav_tabs.setExpanding(False)
        self._fav_tabs.setUsesScrollButtons(True)
        self._fav_tabs.setDrawBase(False)
        self._fav_tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self._fav_tabs.currentChanged.connect(self._on_fav_tab_changed)
        self._fav_tabs.tabMoved.connect(self._on_fav_tabs_moved)
        self._fav_tabs.setStyleSheet(
            """
            QTabBar { background: transparent; }
            QTabBar::tab {
                min-height: 18px;
                max-height: 22px;
                padding: 1px 8px;
                margin-right: 1px;
            }
            """
        )

        self._sort_bar = SortControlBar()
        self._sort_bar.sort_changed.connect(self.sort_changed.emit)
        self._sort_bar.ascending_changed.connect(self.ascending_changed.emit)
        self._sort_bar.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        self._header = QWidget()
        hdr_lay = QHBoxLayout(self._header)
        hdr_lay.setContentsMargins(4, 1, 4, 1)
        hdr_lay.setSpacing(6)
        hdr_lay.addWidget(self._fav_tabs, stretch=1)
        hdr_lay.addWidget(self._sort_bar, stretch=0)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._header, 0)
        lay.addWidget(self._stack, stretch=1)

        self._mode = "square"
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(True)

        self._import_drop_cb: Callable[[QMimeData], None] | None = None
        self._import_folder: Path | None = None
        self._cache.thumbnail_ready.connect(self._on_thumbnail_ready)

        self._sync_header_height()

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

    def _sync_header_height(self) -> None:
        fm = QFontMetrics(self.font())
        h = max(18, min(22, fm.height() + 4))
        self._header.setFixedHeight(h)
        self._fav_tabs.setFixedHeight(h)
        self._sort_bar.set_field_height(h)

    def _parse_favorites_entries(self, data: object) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not isinstance(data, list):
            return out
        seen: set[str] = set()
        for raw in data:
            if isinstance(raw, str):
                try:
                    p = Path(raw.strip().strip('"')).expanduser()
                    if not p.is_dir():
                        continue
                    n = str(p.resolve())
                except OSError:
                    continue
                if n not in seen:
                    seen.add(n)
                    out.append({"path": n, "name": None})
            elif isinstance(raw, dict):
                p = raw.get("path")
                if not p:
                    continue
                try:
                    pp = Path(str(p)).expanduser()
                    if not pp.is_dir():
                        continue
                    n = str(pp.resolve())
                except OSError:
                    continue
                if n in seen:
                    continue
                seen.add(n)
                name = raw.get("name")
                nm = str(name).strip() if isinstance(name, str) and str(name).strip() else None
                out.append({"path": n, "name": nm})
        return out

    def set_favorites_tabs(self, data: object) -> None:
        entries = self._parse_favorites_entries(data)
        self._syncing_fav_tabs = True
        self._fav_tabs.blockSignals(True)
        try:
            while self._fav_tabs.count():
                self._fav_tabs.removeTab(0)
            for e in entries:
                p = str(e["path"])
                label = e.get("name")
                display = str(label).strip() if isinstance(label, str) and label.strip() else Path(p).name
                idx = self._fav_tabs.addTab(display)
                self._fav_tabs.setTabToolTip(idx, p)
                self._fav_tabs.setTabData(idx, e)
        finally:
            self._fav_tabs.blockSignals(False)
            self._syncing_fav_tabs = False

    def sync_favorite_tab_for_path(self, path: str) -> None:
        try:
            target = str(Path(path).resolve())
        except OSError:
            target = path
        idx = -1
        for i in range(self._fav_tabs.count()):
            d = self._fav_tabs.tabData(i)
            if not isinstance(d, dict):
                continue
            p = d.get("path")
            if not isinstance(p, str):
                continue
            try:
                if str(Path(p).resolve()) == target:
                    idx = i
                    break
            except OSError:
                if p == target:
                    idx = i
                    break
        self._syncing_fav_tabs = True
        self._fav_tabs.blockSignals(True)
        try:
            if idx >= 0:
                self._fav_tabs.setCurrentIndex(idx)
        finally:
            self._fav_tabs.blockSignals(False)
            self._syncing_fav_tabs = False

    def _on_fav_tab_changed(self, index: int) -> None:
        if self._syncing_fav_tabs or index < 0:
            return
        d = self._fav_tabs.tabData(index)
        if not isinstance(d, dict):
            return
        p = d.get("path")
        if isinstance(p, str) and Path(p).is_dir():
            self.favorite_folder_selected.emit(p)

    def _on_fav_tabs_moved(self, _from: int, _to: int) -> None:
        del _from, _to
        out: list[dict[str, Any]] = []
        for i in range(self._fav_tabs.count()):
            d = self._fav_tabs.tabData(i)
            if isinstance(d, dict) and d.get("path"):
                out.append(dict(d))
        if out:
            self.favorites_order_changed.emit(out)

    def sort_key(self) -> SortKey:
        return self._sort_bar.sort_key()

    def ascending(self) -> bool:
        return self._sort_bar.ascending()

    def set_sort(self, sort_by: SortKey, ascending: bool) -> None:
        self._sort_bar.set_sort(sort_by, ascending)

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
        v.set_tile_background(self._tile_bg)
        v.set_paths(self._paths)

    def apply_prefs(self, thumb_size: int) -> None:
        self._thumb_size = thumb_size
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