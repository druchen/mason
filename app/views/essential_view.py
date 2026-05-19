"""Essential layout: letterboxed thumbnails in a QListWidget (Icon mode).

Column count (2–16) follows the global thumbnail slider (48–512). Grid metrics are derived
from the list viewport width with a fixed left inset; tile width uses the remaining width,
and any remainder after the grid becomes the right viewport margin.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal, QSize
from PySide6.QtGui import QBrush, QKeyEvent, QMouseEvent, QPalette, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QListView,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.thumbnail_cache import ThumbnailCache, thumbnail_payload_to_pixmap
from app.views.base_view import BaseImageView
from app.views.file_drag import exec_external_file_drag
from app.views.selection_overlay import NoFillSelectionDelegate
from app.views.letterbox_icons import (
    PREVIEW_SURFACE,
    fit_pixmap_letterbox_square,
    request_thumbnails_for_visible_list_items,
    visible_item_paths_with_margin,
)

_GAP = 8
_VIEWPORT_VPAD = 8  # top/bottom only; horizontal inset is ml/mr from tile math
_VIEWPORT_LPAD = 12  # fixed space from viewport left edge to first tile column
_ITEM_CHROME = 12
_SLIDER_LO = 48
_SLIDER_HI = 512
_COLS_WHEN_SLIDER_MIN = 16
_COLS_WHEN_SLIDER_MAX = 2


class EssentialView(BaseImageView):
    def __init__(self, thumb_cache: ThumbnailCache, parent=None) -> None:
        super().__init__(thumb_cache, parent)
        self._selected_path: str | None = None
        self._selected_paths: set[str] = set()
        self._pixmaps: dict[str, QPixmap] = {}
        self._path_to_item: dict[str, QListWidgetItem] = {}
        self._ncol = 4
        self._outer_px = 140
        self._cell_px = 128

        self._list = QListWidget()
        self._list.setObjectName("essentialPreviewList")
        self._list.setViewMode(QListWidget.ViewMode.IconMode)
        self._list.setMovement(QListWidget.Movement.Static)
        self._list.setFlow(QListView.Flow.LeftToRight)
        self._list.setWrapping(True)
        # Fixed: we own grid metrics in _flush_icon_layout. "Adjust" lets Qt relayout the
        # icon grid independently, which fights viewport margins and leaves a wide gap on the right.
        self._list.setResizeMode(QListView.ResizeMode.Fixed)
        self._list.setSpacing(_GAP)
        self._list.setUniformItemSizes(True)
        self._list.setItemAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # Avoid a stray rubber-band frame after external file drag (QDrag.exec).
        self._list.setSelectionRectVisible(False)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._list.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self._list.setItemDelegate(NoFillSelectionDelegate(self._list))

        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.verticalScrollBar().valueChanged.connect(lambda _: self._request_visible_icons())
        self._list.installEventFilter(self)
        self._list.viewport().installEventFilter(self)

        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self._flush_icon_layout)

        self._drag_press_pos: QPoint | None = None
        self._drag_anchor: QListWidgetItem | None = None
        # QListView delivers mouse to the viewport; suppress its drag-select until we drag out or release.
        self._suppress_list_vp_drag_select = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._list)

        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self._apply_list_style()

    def _columns_per_row(self) -> int:
        t = max(_SLIDER_LO, min(_SLIDER_HI, int(self._thumbnail_size)))
        span = max(1, _SLIDER_HI - _SLIDER_LO)
        steps = _COLS_WHEN_SLIDER_MIN - _COLS_WHEN_SLIDER_MAX
        idx = min(steps, max(0, (t - _SLIDER_LO) * steps // span))
        return _COLS_WHEN_SLIDER_MIN - idx

    def _compute_tile_metrics(self, vp_w: int) -> tuple[int, int, int, int, int]:
        """Return ncol, outer, cell, margin_left, margin_right for viewport width ``vp_w``."""
        ncol = self._columns_per_row()
        vp_w = max(40, int(vp_w))
        if ncol < 1:
            return 4, 1, 1, 0, 0
        ml = min(_VIEWPORT_LPAD, max(0, vp_w - 1))
        vp_inner = max(1, vp_w - ml)
        outer = (vp_inner - (ncol - 1) * _GAP) // ncol
        outer = max(_ITEM_CHROME + 1, outer)
        used = ncol * outer + (ncol - 1) * _GAP
        mr = max(0, vp_w - ml - used)
        cell = max(1, outer - _ITEM_CHROME)
        return ncol, outer, cell, ml, mr

    def _apply_list_style(self) -> None:
        self._list.setStyleSheet(
            f"""
            QListWidget#essentialPreviewList {{
                background-color: {PREVIEW_SURFACE};
                border: none;
                outline: none;
                selection-background-color: transparent;
                show-decoration-selected: 0;
            }}
            QListWidget#essentialPreviewList::item {{
                background: transparent;
                border: 2px solid transparent;
                border-radius: 2px;
                outline: none;
            }}
            QListWidget#essentialPreviewList QScrollBar:vertical {{
                border: none;
                background-color: {PREVIEW_SURFACE};
                width: 10px;
                margin: 0;
            }}
            QListWidget#essentialPreviewList QScrollBar::handle:vertical {{
                background: #5a5a5a;
                border-radius: 4px;
                min-height: 28px;
                margin: 2px;
            }}
            QListWidget#essentialPreviewList QScrollBar::handle:vertical:hover {{
                background: #707070;
            }}
            QListWidget#essentialPreviewList QScrollBar::add-line:vertical,
            QListWidget#essentialPreviewList QScrollBar::sub-line:vertical {{
                border: none;
                background: transparent;
                height: 0;
                width: 0;
            }}
            QListWidget#essentialPreviewList QScrollBar::add-page:vertical,
            QListWidget#essentialPreviewList QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            """
        )
        pal = self._list.palette()
        for grp in (
            QPalette.ColorGroup.Active,
            QPalette.ColorGroup.Inactive,
            QPalette.ColorGroup.Disabled,
        ):
            pal.setBrush(grp, QPalette.ColorRole.Highlight, QBrush(Qt.GlobalColor.transparent))
        self._list.setPalette(pal)

    def _schedule_layout(self) -> None:
        self._layout_timer.start(50)

    def _flush_icon_layout(self) -> None:
        self._layout_timer.stop()

        def _apply(vp_w: int) -> tuple[int, int, int, int, int]:
            ncol, outer, cell, ml, mr = self._compute_tile_metrics(vp_w)
            self._list.setViewportMargins(ml, _VIEWPORT_VPAD, mr, _VIEWPORT_VPAD)
            self._list.setGridSize(QSize(outer, outer))
            self._list.setIconSize(QSize(cell, cell))
            return ncol, outer, cell, ml, mr

        # One reflow pass; a second pass only if viewport width changed (e.g. scrollbar appeared).
        vp0 = max(120, int(self._list.viewport().width()))
        ncol, outer, cell, ml, mr = _apply(vp0)
        vp1 = max(120, int(self._list.viewport().width()))
        if vp1 != vp0:
            ncol, outer, cell, ml, mr = _apply(vp1)

        self._ncol = ncol
        self._outer_px = outer
        self._cell_px = cell

        hint = QSize(outer, outer)
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it is not None:
                it.setSizeHint(hint)

        self._list.doItemsLayout()
        self._refresh_all_icons()
        QTimer.singleShot(0, self._request_visible_icons)

    def _prune_pixmaps_not_in(self, keep: set[str]) -> None:
        for path in list(self._pixmaps.keys()):
            if path in keep:
                continue
            del self._pixmaps[path]
            it = self._path_to_item.get(path)
            if it is not None:
                it.setIcon(QIcon())

    def _icon_for_path(self, path: str) -> QIcon:
        pm = self._pixmaps.get(path)
        if pm is None or pm.isNull():
            return QIcon()
        sq = fit_pixmap_letterbox_square(pm, self._cell_px, self._tile_background)
        return QIcon(sq)

    def _refresh_all_icons(self) -> None:
        for path, item in self._path_to_item.items():
            item.setIcon(self._icon_for_path(path))

    def _request_visible_icons(self) -> None:
        keep = visible_item_paths_with_margin(self._list, 320)
        keep |= self._selected_paths
        request_thumbnails_for_visible_list_items(self._list, self._cell_px, self._thumb_cache)
        self._prune_pixmaps_not_in(keep)

    def _finish_list_external_drag_gesture(self) -> None:
        """After QDrag.exec() (including cancel), reset view state so the next click is not Ctrl-add."""
        self._drag_press_pos = None
        self._drag_anchor = None
        self._suppress_list_vp_drag_select = False
        self._list.setState(QAbstractItemView.State.NoState)
        QTimer.singleShot(0, self._deferred_reset_list_view_state)

    def _deferred_reset_list_view_state(self) -> None:
        self._list.setState(QAbstractItemView.State.NoState)

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if obj is self._list:
            et = event.type()
            if et == QEvent.Type.KeyPress:
                ke = event
                if isinstance(ke, QKeyEvent):
                    if ke.key() == Qt.Key.Key_Escape:
                        if not self._list.selectedItems():
                            return False
                        self._list.clearSelection()
                        return True
                    if ke.key() == Qt.Key.Key_Space:
                        sel = self.selected_paths()
                        if sel:
                            self.fullscreen_requested.emit(sel[-1])
                        return True
                    if ke.key() == Qt.Key.Key_Delete:
                        sel = self.selected_paths()
                        if sel:
                            self.delete_requested.emit(sel)
                        return True
                return False
            if et == QEvent.Type.Resize:
                self._schedule_layout()
            return super().eventFilter(obj, event)

        if obj is self._list.viewport():
            et = event.type()
            if et == QEvent.Type.KeyPress:
                ke = event
                if isinstance(ke, QKeyEvent):
                    if ke.key() == Qt.Key.Key_Escape:
                        if not self._list.selectedItems():
                            return False
                        self._list.clearSelection()
                        return True
                    if ke.key() == Qt.Key.Key_Space:
                        sel = self.selected_paths()
                        if sel:
                            self.fullscreen_requested.emit(sel[-1])
                        return True
                    if ke.key() == Qt.Key.Key_Delete:
                        sel = self.selected_paths()
                        if sel:
                            self.delete_requested.emit(sel)
                        return True
                return False
            if et == QEvent.Type.MouseButtonPress:
                me = event
                if isinstance(me, QMouseEvent) and me.button() == Qt.MouseButton.LeftButton:
                    self._drag_anchor = self._list.itemAt(me.pos())
                    self._drag_press_pos = me.pos() if self._drag_anchor else None
                    self._suppress_list_vp_drag_select = self._drag_anchor is not None
                else:
                    self._drag_press_pos = None
                    self._drag_anchor = None
                    self._suppress_list_vp_drag_select = False
                return False
            if et == QEvent.Type.MouseMove:
                me = event
                if not isinstance(me, QMouseEvent):
                    return super().eventFilter(obj, event)
                if (
                    self._drag_press_pos is not None
                    and self._drag_anchor is not None
                    and (me.buttons() & Qt.MouseButton.LeftButton)
                    and (me.pos() - self._drag_press_pos).manhattanLength()
                    >= QApplication.startDragDistance()
                ):
                    paths = self._paths_for_drag(self._drag_anchor)
                    preview = self._drag_preview(self._drag_anchor)
                    if paths:
                        exec_external_file_drag(self._list, paths, preview)
                    self._finish_list_external_drag_gesture()
                    return False
                if self._suppress_list_vp_drag_select and (me.buttons() & Qt.MouseButton.LeftButton):
                    return True
                return False
            if et == QEvent.Type.MouseButtonRelease:
                self._drag_press_pos = None
                self._drag_anchor = None
                self._suppress_list_vp_drag_select = False
                return False
            return super().eventFilter(obj, event)

        return super().eventFilter(obj, event)

    def _paths_for_drag(self, anchor: QListWidgetItem) -> list[str]:
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

    def _drag_preview(self, anchor: QListWidgetItem) -> QPixmap | None:
        ic = anchor.icon()
        side = max(48, int(self._cell_px))
        for sz in ic.availableSizes():
            pm = ic.pixmap(sz)
            if not pm.isNull():
                if pm.width() > side:
                    return pm.copy(QRect(0, 0, side, pm.height()))
                return pm
        return None

    def _on_context_menu(self, pos: QPoint) -> None:
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

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        p = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(p, str):
            self.open_in_photoshop_requested.emit(p)

    def _on_selection_changed(self) -> None:
        items = self._list.selectedItems()
        self._selected_paths = set()
        for it in items:
            p = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(p, str):
                self._selected_paths.add(p)
        if not items:
            self._selected_path = None
            self.selection_changed.emit("")
            return
        path = items[-1].data(Qt.ItemDataRole.UserRole)
        if isinstance(path, str):
            self._selected_path = path
            self.selection_changed.emit(path)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._schedule_layout()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._schedule_layout()

    def set_paths(self, paths: list[str]) -> None:
        if paths == self._paths:
            self._schedule_layout()
            return
        new_set = set(paths)
        self._pixmaps = {k: v for k, v in self._pixmaps.items() if k in new_set}
        self._paths = list(paths)
        self._path_to_item.clear()
        self._list.clear()
        self._selected_paths &= set(paths)
        if self._selected_path not in paths:
            self._selected_path = None
        self._list.verticalScrollBar().setValue(0)

        for p in paths:
            item = QListWidgetItem("")
            item.setData(Qt.ItemDataRole.UserRole, p)
            self._list.addItem(item)
            self._path_to_item[p] = item

        self._flush_icon_layout()

    def set_thumbnail_size(self, size: int, *, reflow: bool = True) -> None:
        super().set_thumbnail_size(size, reflow=reflow)
        self._schedule_layout()

    def set_tile_background(self, enabled: bool) -> None:
        super().set_tile_background(enabled)
        self._refresh_all_icons()

    def invalidate_thumbnails(self, paths: set[str]) -> None:
        if not paths:
            return
        for path in paths:
            self._pixmaps.pop(path, None)
            item = self._path_to_item.get(path)
            if item is not None:
                item.setIcon(QIcon())
        self._request_visible_icons()

    def apply_thumbnail(self, path: str, payload: object) -> None:
        pm = thumbnail_payload_to_pixmap(payload)
        if pm is None:
            return
        self._pixmaps[path] = pm
        item = self._path_to_item.get(path)
        if item:
            item.setIcon(self._icon_for_path(path))

    def selected_paths(self) -> list[str]:
        return [p for p in self._paths if p in self._selected_paths]

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
        self._selected_paths = {path}
        self.selection_changed.emit(path)
        self._list.scrollToItem(item)
        self._list.setFocus()
        return True

    def take_preview_focus(self) -> None:
        self._list.setFocus(Qt.FocusReason.OtherFocusReason)
