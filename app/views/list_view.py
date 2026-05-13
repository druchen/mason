"""Compact list with leading thumbnails.

Multi-select: Ctrl+click (toggle) and Shift+click (range) via ExtendedSelection.
Space: open fullscreen. Delete: delete selected files.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QEvent, QSize, QTimer
from PySide6.QtGui import QIcon, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from app.core.thumbnail_cache import ThumbnailCache, thumbnail_payload_to_pixmap
from app.views.base_view import BaseImageView
from app.views.file_drag import exec_external_file_drag


class ListView(BaseImageView):
    def __init__(self, thumb_cache: ThumbnailCache, parent=None) -> None:
        super().__init__(thumb_cache, parent)
        self._selected_path: str | None = None
        self._path_to_item: dict[str, QListWidgetItem] = {}

        self._list = QListWidget()
        self._list.setViewMode(QListWidget.ViewMode.ListMode)
        self._list.setMovement(QListWidget.Movement.Static)
        self._list.setSpacing(2)
        self._list.setUniformItemSizes(True)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_list_context_menu)
        self._list.itemDoubleClicked.connect(self._on_list_item_double_clicked)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.installEventFilter(self)

        self._list_drag_press_pos: QPoint | None = None
        self._list_drag_anchor: QListWidgetItem | None = None

        self._thumb_cache.thumbnail_ready.connect(self._on_thumb_ready)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._list)
        self._apply_styles()

    def _on_list_context_menu(self, pos: QPoint) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        p = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(p, str):
            return
        self._list.blockSignals(True)
        self._list.clearSelection()
        item.setSelected(True)
        self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        self._on_selection_changed()
        self.image_context_menu_requested.emit(p, self._list.mapToGlobal(pos))

    def _on_list_item_double_clicked(self, item: QListWidgetItem) -> None:
        p = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(p, str):
            self.open_in_photoshop_requested.emit(p)

    def _paths_for_list_drag(self, anchor: QListWidgetItem) -> list[str]:
        raw = anchor.data(Qt.ItemDataRole.UserRole)
        if not isinstance(raw, str) or not Path(raw).is_file():
            return []
        if anchor.isSelected():
            sel: list[str] = []
            for it in self._list.selectedItems():
                p = it.data(Qt.ItemDataRole.UserRole)
                if isinstance(p, str) and Path(p).is_file():
                    sel.append(p)
            if len(sel) > 1:
                order = [p for p in self._paths if p in set(sel)]
                return order if order else sel
        return [raw]

    def _list_drag_preview(self, anchor: QListWidgetItem) -> QPixmap | None:
        ic = anchor.icon()
        for sz in ic.availableSizes():
            pm = ic.pixmap(sz)
            if not pm.isNull():
                return pm
        return None

    # ------------------------------------------------------------------
    # Event filter
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if obj is self._list:
            et = event.type()
            if et == QEvent.Type.MouseButtonPress:
                me = event
                if isinstance(me, QMouseEvent) and me.button() == Qt.MouseButton.LeftButton:
                    self._list_drag_anchor = self._list.itemAt(me.pos())
                    self._list_drag_press_pos = me.pos() if self._list_drag_anchor else None
                else:
                    self._list_drag_press_pos = None
                    self._list_drag_anchor = None
            elif et == QEvent.Type.MouseMove:
                me = event
                if (
                    isinstance(me, QMouseEvent)
                    and self._list_drag_press_pos is not None
                    and self._list_drag_anchor is not None
                    and (me.buttons() & Qt.MouseButton.LeftButton)
                    and (me.pos() - self._list_drag_press_pos).manhattanLength()
                    >= QApplication.startDragDistance()
                ):
                    paths = self._paths_for_list_drag(self._list_drag_anchor)
                    preview = self._list_drag_preview(self._list_drag_anchor)
                    if paths:
                        exec_external_file_drag(self._list, paths, preview)
                    self._list_drag_press_pos = None
                    self._list_drag_anchor = None
            elif et == QEvent.Type.MouseButtonRelease:
                self._list_drag_press_pos = None
                self._list_drag_anchor = None
            elif et == QEvent.Type.KeyPress:
                key = event.key()
                if key == Qt.Key.Key_Space:
                    sel = self.selected_paths()
                    if sel:
                        self.fullscreen_requested.emit(sel[-1])
                    return True
                if key == Qt.Key.Key_Delete:
                    sel = self.selected_paths()
                    if sel:
                        self.delete_requested.emit(sel)
                    return True
                return False
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        items = self._list.selectedItems()
        if not items:
            return
        path = items[-1].data(Qt.ItemDataRole.UserRole)
        if isinstance(path, str):
            self._selected_path = path
            self.selection_changed.emit(path)

    def selected_paths(self) -> list[str]:
        result: list[str] = []
        for item in self._list.selectedItems():
            p = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(p, str):
                result.append(p)
        return result

    # ------------------------------------------------------------------
    # Thumbnail delivery (O(1) lookup)
    # ------------------------------------------------------------------

    def _on_thumb_ready(self, path: str, pm: object) -> None:
        pm = thumbnail_payload_to_pixmap(pm)
        if pm is None:
            return
        item = self._path_to_item.get(path)
        if item:
            item.setIcon(QIcon(pm))

    # ------------------------------------------------------------------
    # BaseImageView interface
    # ------------------------------------------------------------------

    def set_paths(self, paths: list[str]) -> None:
        self._paths = list(paths)
        self._path_to_item.clear()
        self._list.clear()
        icon_sz = max(24, min(96, self._thumbnail_size))
        self._list.setIconSize(QSize(icon_sz, icon_sz))
        for p in paths:
            item = QListWidgetItem(Path(p).name if self._show_filenames else "")
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setToolTip(p)
            self._list.addItem(item)
            self._path_to_item[p] = item
            self._thumb_cache.request(p, icon_sz)
        self._apply_styles()

    def set_thumbnail_size(self, size: int) -> None:
        super().set_thumbnail_size(size)
        icon_sz = max(24, min(96, self._thumbnail_size))
        self._list.setIconSize(QSize(icon_sz, icon_sz))
        for p in self._path_to_item:
            self._thumb_cache.request(p, icon_sz)

    def set_show_filenames(self, show: bool) -> None:
        super().set_show_filenames(show)
        for path, item in self._path_to_item.items():
            item.setText(Path(path).name if show else "")

    def set_tile_background(self, enabled: bool) -> None:
        super().set_tile_background(enabled)
        self._apply_styles()

    def _apply_styles(self) -> None:
        self._list.setStyleSheet(
            """
            QListWidget { background: transparent; }
            QListWidget::item {
                background: #3c3c3c;
                border: 2px solid transparent;
                border-radius: 2px;
                padding: 2px;
            }
            QListWidget::item:selected {
                background: rgba(90, 180, 245, 0.2);
                border: 2px solid #5ab4f5;
            }
            """
        )

    def selected_path(self) -> str | None:
        return self._selected_path

    def select_primary_path(self, path: str) -> bool:
        item = self._path_to_item.get(path)
        if item is None:
            return False
        self._list.blockSignals(True)
        self._list.clearSelection()
        item.setSelected(True)
        self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        self._selected_path = path
        self.selection_changed.emit(path)
        self._list.scrollToItem(item)
        return True

    def take_preview_focus(self) -> None:
        self._list.setFocus(Qt.FocusReason.OtherFocusReason)
