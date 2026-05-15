"""Large preview + horizontally scrolling thumbnail strip (QListWidget icon mode).

Strip uses the same letterboxed square thumbnails and visible-item decode requests as
Essential. Only a window of paths is materialized as items for large folders.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QEvent, QRect, QSize, Qt, QTimer, Signal, QItemSelectionModel
from PySide6.QtGui import QBrush, QContextMenuEvent, QKeyEvent, QMouseEvent, QPalette, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QListView,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QSplitter,
    QLabel,
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
)

_STRIP_MARGIN = 8
_STRIP_SPACING = 8
_MIN_STRIP_SQUARE = 32
_ITEM_CHROME = 12
_SCROLL_EXPAND_PX = 6
_CHUNK = 64
_WIN_MIN = 96


class _FilmstripPreviewLabel(QLabel):
    """Top preview: double-click is delivered reliably (parent event filter is not)."""

    double_clicked_left = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self.double_clicked_left.emit()
        event.accept()


class _FilmstripStripList(QListWidget):
    """Horizontal strip: custom press so shift/Ctrl range matches full ``paths``, not Qt defaults."""

    thumb_double_clicked = Signal(str)

    def __init__(self, owner: "FilmstripView", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._owner = owner
        self._drag_press_pos: QPoint | None = None
        self._drag_anchor: QListWidgetItem | None = None
        # True after left-press on an item until left-release; blocks QListView rubber-band
        # selection on mouse-move (which was highlighting every thumb from press to cursor).
        self._left_gesture_from_item = False

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            it = self.itemAt(event.pos())
            if it is not None:
                self._left_gesture_from_item = True
                self._owner._strip_mouse_press(it, event)
                self._drag_anchor = it
                self._drag_press_pos = event.pos()
                event.accept()
                return
        self._left_gesture_from_item = False
        self._drag_anchor = None
        self._drag_press_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if (
            self._drag_press_pos is not None
            and self._drag_anchor is not None
            and (event.buttons() & Qt.MouseButton.LeftButton)
            and (event.pos() - self._drag_press_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            paths = self._owner._paths_for_drag_item(self._drag_anchor)
            preview = self._owner._drag_preview_for_item(self._drag_anchor)
            if paths:
                exec_external_file_drag(self, paths, preview)
            self._drag_press_pos = None
            self._drag_anchor = None
            return
        if self._left_gesture_from_item and (event.buttons() & Qt.MouseButton.LeftButton):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        sync = self._left_gesture_from_item and event.button() == Qt.MouseButton.LeftButton
        self._drag_press_pos = None
        self._drag_anchor = None
        self._left_gesture_from_item = False
        if sync:
            self._owner._sync_strip_list_selection()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        it = self.itemAt(event.pos())
        if it is not None:
            raw = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(raw, str):
                self.thumb_double_clicked.emit(raw)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # type: ignore[override]
        it = self.itemAt(event.pos())
        if it is not None:
            self._owner._strip_context_menu(it, event.globalPos())
            event.accept()
            return
        super().contextMenuEvent(event)


class FilmstripView(BaseImageView):
    """Large preview + single horizontal scrolling row of thumbnails."""

    def __init__(self, thumb_cache: ThumbnailCache, parent=None) -> None:
        super().__init__(thumb_cache, parent)
        self._selected_path: str | None = None
        self._selected_paths: set[str] = set()
        self._anchor_path: str | None = None
        self._pixmaps: dict[str, QPixmap] = {}
        self._path_to_item: dict[str, QListWidgetItem] = {}
        self._strip_thumb_side = self._thumbnail_size
        self._win_lo = 0
        self._win_hi = 0

        self._preview = _FilmstripPreviewLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(220)
        self._preview.setScaledContents(False)
        self._preview.setWordWrap(False)
        self._preview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._preview.customContextMenuRequested.connect(self._on_preview_context_menu)
        self._preview.double_clicked_left.connect(self._on_preview_double_click)

        self._strip_list = _FilmstripStripList(self)
        self._strip_list.setObjectName("filmstripStripList")
        self._strip_list.setViewMode(QListWidget.ViewMode.IconMode)
        self._strip_list.setMovement(QListWidget.Movement.Static)
        self._strip_list.setFlow(QListView.Flow.LeftToRight)
        self._strip_list.setWrapping(False)
        self._strip_list.setResizeMode(QListView.ResizeMode.Fixed)
        self._strip_list.setSpacing(_STRIP_SPACING)
        self._strip_list.setUniformItemSizes(True)
        self._strip_list.setItemAlignment(Qt.AlignmentFlag.AlignCenter)
        self._strip_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self._strip_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._strip_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._strip_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._strip_list.installEventFilter(self)
        self._strip_list.thumb_double_clicked.connect(self._on_strip_thumb_double_click)
        self._strip_list.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._strip_list.setItemDelegate(NoFillSelectionDelegate(self._strip_list))

        self._apply_strip_style()
        self._strip_list.horizontalScrollBar().valueChanged.connect(self._on_strip_scroll)

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self._preview)
        split.addWidget(self._strip_list)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(split)

        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._split = split

        mh = max(140, 2 * _STRIP_MARGIN + _MIN_STRIP_SQUARE + _ITEM_CHROME + 48)
        self._strip_list.setMinimumHeight(mh)

        self._preview_hi_res_timer = QTimer(self)
        self._preview_hi_res_timer.setSingleShot(True)
        self._preview_hi_res_timer.timeout.connect(self._thumb_strip_request_preview)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._paths:
            QTimer.singleShot(0, self._sync_strip_thumb_scale)

    # ------------------------------------------------------------------

    def _apply_strip_style(self) -> None:
        self._strip_list.setStyleSheet(
            f"""
            QListWidget#filmstripStripList {{
                background-color: {PREVIEW_SURFACE};
                border: none;
                outline: none;
                selection-background-color: transparent;
                show-decoration-selected: 0;
            }}
            QListWidget#filmstripStripList::item {{
                background: transparent;
                border: 2px solid transparent;
                border-radius: 2px;
                outline: none;
            }}
            QListWidget#filmstripStripList QScrollBar:horizontal {{
                border: none;
                background-color: {PREVIEW_SURFACE};
                height: 10px;
                margin: 0;
            }}
            QListWidget#filmstripStripList QScrollBar::handle:horizontal {{
                background: #5a5a5a;
                border-radius: 4px;
                min-width: 28px;
                margin: 2px;
            }}
            QListWidget#filmstripStripList QScrollBar::handle:horizontal:hover {{
                background: #707070;
            }}
            QListWidget#filmstripStripList QScrollBar::add-line:horizontal,
            QListWidget#filmstripStripList QScrollBar::sub-line:horizontal {{
                border: none;
                background: transparent;
                width: 0;
                height: 0;
            }}
            QListWidget#filmstripStripList QScrollBar::add-page:horizontal,
            QListWidget#filmstripStripList QScrollBar::sub-page:horizontal {{
                background: transparent;
            }}
            """
        )
        pal = self._strip_list.palette()
        for grp in (
            QPalette.ColorGroup.Active,
            QPalette.ColorGroup.Inactive,
            QPalette.ColorGroup.Disabled,
        ):
            pal.setBrush(grp, QPalette.ColorRole.Highlight, QBrush(Qt.GlobalColor.transparent))
        self._strip_list.setPalette(pal)

    def _reserved_strip_overhead_vertical(self) -> int:
        return 2 * _STRIP_MARGIN + _ITEM_CHROME

    def _outer_px(self) -> int:
        return max(_ITEM_CHROME + 1, int(self._strip_thumb_side) + _ITEM_CHROME)

    def _compute_strip_square_side(self, vp_h: int) -> int:
        if vp_h < 8:
            return max(_MIN_STRIP_SQUARE, min(512, self._thumbnail_size))
        raw = int(vp_h - self._reserved_strip_overhead_vertical())
        cap_hi = max(_MIN_STRIP_SQUARE, min(512, int(self._thumbnail_size)))
        return max(_MIN_STRIP_SQUARE, min(cap_hi, raw))

    def _cols_fit_in_viewport(self) -> int:
        outer = self._outer_px()
        vw = max(1, self._strip_list.viewport().width() - 2 * _STRIP_MARGIN)
        step = outer + _STRIP_SPACING
        if step <= 0:
            return 1
        return max(1, (vw + _STRIP_SPACING) // step)

    def _target_window_span(self) -> int:
        n = len(self._paths)
        if n == 0:
            return 0
        cols = self._cols_fit_in_viewport()
        span = max(_WIN_MIN, cols * 6 + 3 * _CHUNK)
        return min(n, span)

    def _set_window_around_index(self, idx: int, *, prefer_span: int | None = None) -> None:
        n = len(self._paths)
        if n == 0:
            self._win_lo = self._win_hi = 0
            return
        span = prefer_span if prefer_span is not None else self._target_window_span()
        span = max(1, min(n, span))
        half = span // 2
        lo = max(0, min(idx - half, n - span))
        hi = lo + span
        self._win_lo, self._win_hi = lo, hi

    def _ensure_index_in_window(self, idx: int) -> bool:
        """Expand or shift window so ``idx`` is inside. Returns True if window changed."""
        n = len(self._paths)
        if n == 0:
            return False
        idx = max(0, min(idx, n - 1))
        if self._win_lo <= idx < self._win_hi:
            return False
        old_lo, old_hi = self._win_lo, self._win_hi
        span = max(self._win_hi - self._win_lo, min(self._target_window_span(), n))
        span = max(1, min(n, span))
        half = span // 2
        lo = max(0, min(idx - half, n - span))
        hi = lo + span
        self._win_lo, self._win_hi = lo, hi
        return (lo, hi) != (old_lo, old_hi)

    def _ensure_range_in_window(self, lo_i: int, hi_i: int) -> bool:
        """Ensure ``[lo_i, hi_i]`` (inclusive indices) lies inside the window; grow if needed."""
        n = len(self._paths)
        if n == 0:
            return False
        lo_i = max(0, min(lo_i, n - 1))
        hi_i = max(0, min(hi_i, n - 1))
        if lo_i > hi_i:
            lo_i, hi_i = hi_i, lo_i
        margin = max(_CHUNK // 2, self._cols_fit_in_viewport())
        need_lo = max(0, lo_i - margin)
        need_hi = min(n, hi_i + 1 + margin)
        cur_lo, cur_hi = self._win_lo, self._win_hi
        if cur_lo <= need_lo and need_hi <= cur_hi:
            return False
        new_lo = min(cur_lo, need_lo)
        new_hi = max(cur_hi, need_hi)
        max_span = min(n, max(self._target_window_span(), new_hi - new_lo))
        if new_hi - new_lo > max_span:
            center = (lo_i + hi_i) // 2
            half = max_span // 2
            new_lo = max(0, min(center - half, n - max_span))
            new_hi = new_lo + max_span
        self._win_lo, self._win_hi = new_lo, new_hi
        return (new_lo, new_hi) != (cur_lo, cur_hi)

    def _repopulate_strip_items(self) -> None:
        self._strip_list.clear()
        self._path_to_item.clear()
        n = len(self._paths)
        if n == 0:
            return
        lo, hi = self._win_lo, self._win_hi
        lo = max(0, min(lo, n - 1))
        hi = max(lo + 1, min(hi, n))
        self._win_lo, self._win_hi = lo, hi
        outer = self._outer_px()
        cell = max(1, outer - _ITEM_CHROME)
        hint = QSize(outer, outer)
        for p in self._paths[lo:hi]:
            item = QListWidgetItem("")
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setSizeHint(hint)
            self._strip_list.addItem(item)
            self._path_to_item[p] = item
        self._strip_list.setGridSize(QSize(outer, outer))
        self._strip_list.setIconSize(QSize(cell, cell))
        self._sync_strip_list_selection()
        self._refresh_strip_icons()
        self._prune_strip_pixmaps()

    def _prune_strip_pixmaps(self) -> None:
        keep = set(self._path_to_item.keys()) | self._selected_paths
        if self._selected_path:
            keep.add(self._selected_path)
        for path in list(self._pixmaps.keys()):
            if path in keep:
                continue
            del self._pixmaps[path]
        for path, item in self._path_to_item.items():
            item.setIcon(self._icon_for_path(path))

    def _icon_for_path(self, path: str) -> QIcon:
        pm = self._pixmaps.get(path)
        if pm is None or pm.isNull():
            return QIcon()
        cell = max(1, self._outer_px() - _ITEM_CHROME)
        sq = fit_pixmap_letterbox_square(pm, cell, self._tile_background)
        return QIcon(sq)

    def _sync_strip_list_selection(self) -> None:
        self._strip_list.blockSignals(True)
        self._strip_list.clearSelection()
        last_item: QListWidgetItem | None = None
        for path in self._selected_paths:
            it = self._path_to_item.get(path)
            if it is not None:
                it.setSelected(True)
                last_item = it
        prim = self._path_to_item.get(self._selected_path or "")
        # Default setCurrentItem() uses ClearAndSelect; in horizontal Icon mode that can
        # select a whole "row" of items. NoUpdate only moves the current item for arrows.
        no_up = QItemSelectionModel.SelectionFlag.NoUpdate
        if prim is not None:
            self._strip_list.setCurrentItem(prim, no_up)
        elif last_item is not None:
            self._strip_list.setCurrentItem(last_item, no_up)
        self._strip_list.blockSignals(False)

    def _strip_mouse_press(self, item: QListWidgetItem, event: QMouseEvent) -> None:
        raw = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(raw, str):
            return
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        self._apply_pick_path(raw, ctrl, shift, True)
        self.setFocus()
        self._scroll_thumb_into_view(raw)
        self._thumb_strip_request_preview()

    def _strip_context_menu(self, item: QListWidgetItem, global_pos: QPoint) -> None:
        raw = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(raw, str):
            return
        self._apply_pick_path(raw, False, False, True)
        self.setFocus()
        self._scroll_thumb_into_view(raw)
        self._thumb_strip_request_preview()
        self.image_context_menu_requested.emit(raw, global_pos)

    def _paths_for_drag_item(self, anchor: QListWidgetItem) -> list[str]:
        raw = anchor.data(Qt.ItemDataRole.UserRole)
        if not isinstance(raw, str) or not Path(raw).is_file():
            return []
        if anchor.isSelected():
            sel: list[str] = []
            for it in self._strip_list.selectedItems():
                p = it.data(Qt.ItemDataRole.UserRole)
                if isinstance(p, str) and Path(p).is_file():
                    sel.append(p)
            if len(sel) > 1:
                order = [p for p in self._paths if p in set(sel)]
                return order if order else sel
        return [raw]

    def _drag_preview_for_item(self, anchor: QListWidgetItem) -> QPixmap | None:
        ic = anchor.icon()
        cell = max(48, self._outer_px() - _ITEM_CHROME)
        for sz in ic.availableSizes():
            pm = ic.pixmap(sz)
            if not pm.isNull():
                if pm.width() > cell:
                    return pm.copy(QRect(0, 0, cell, pm.height()))
                return pm
        return None

    def _sync_strip_thumb_scale(self) -> None:
        vp = self._strip_list.viewport()
        vh = vp.height()
        if vh < 24:
            return

        side_new = self._compute_strip_square_side(vh)
        prev_side = getattr(self, "_strip_thumb_side", None)
        resized = prev_side is None or prev_side != side_new
        self._strip_thumb_side = side_new

        outer = self._outer_px()
        cell = max(1, outer - _ITEM_CHROME)
        self._strip_list.setViewportMargins(_STRIP_MARGIN, _STRIP_MARGIN, _STRIP_MARGIN, _STRIP_MARGIN)

        self.setUpdatesEnabled(False)
        try:
            if self._path_to_item:
                if resized:
                    self._strip_list.setGridSize(QSize(outer, outer))
                    self._strip_list.setIconSize(QSize(cell, cell))
                    hint = QSize(outer, outer)
                    for it in self._path_to_item.values():
                        it.setSizeHint(hint)
                    self._strip_list.doItemsLayout()
                    self._refresh_strip_icons()
                    for p in self._path_to_item.keys():
                        self._thumb_cache.request(p, max(48, cell))
                else:
                    self._strip_list.setGridSize(QSize(outer, outer))
                    self._strip_list.setIconSize(QSize(cell, cell))
        finally:
            self.setUpdatesEnabled(True)
            self.update()

        QTimer.singleShot(0, self._ensure_visible_thumb_requests)

    def _on_preview_double_click(self) -> None:
        if self._selected_path:
            self.open_in_photoshop_requested.emit(self._selected_path)

    def _apply_pick_path(self, path: str, ctrl: bool, shift: bool, emit_changed: bool) -> None:
        win_changed = False
        if shift and self._anchor_path and self._anchor_path in self._paths:
            ai = self._paths.index(self._anchor_path)
            ci = self._paths.index(path)
            lo, hi = sorted([ai, ci])
            win_changed = self._ensure_range_in_window(lo, hi)
            new_range = set(self._paths[lo : hi + 1])
            if ctrl:
                self._selected_paths |= new_range
            else:
                self._selected_paths = new_range
        elif ctrl:
            if path in self._selected_paths:
                self._selected_paths.discard(path)
            else:
                self._selected_paths.add(path)
            self._anchor_path = path
            win_changed = self._ensure_index_in_window(self._paths.index(path)) or win_changed
        else:
            self._selected_paths = {path}
            self._anchor_path = path
            win_changed = self._ensure_index_in_window(self._paths.index(path)) or win_changed

        self._selected_path = path
        if win_changed:
            self._repopulate_strip_items()
        self._sync_strip_list_selection()
        if emit_changed:
            self.selection_changed.emit(path)

    def _on_strip_thumb_double_click(self, path: str) -> None:
        self.open_in_photoshop_requested.emit(path)

    def _scroll_thumb_into_view(self, path: str) -> None:
        changed = self._ensure_index_in_window(self._paths.index(path)) if path in self._paths else False
        if changed:
            self._repopulate_strip_items()
        item = self._path_to_item.get(path)
        if item is not None:
            self._strip_list.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)

    def _on_strip_scroll(self, _value: int) -> None:
        self._maybe_expand_strip_window()
        self._ensure_visible_thumb_requests()

    def _maybe_expand_strip_window(self) -> None:
        n = len(self._paths)
        if n == 0 or self._win_hi <= self._win_lo:
            return
        bar = self._strip_list.horizontalScrollBar()
        v, vmax = bar.value(), bar.maximum()
        changed = False
        if v <= _SCROLL_EXPAND_PX and self._win_lo > 0:
            step = min(_CHUNK, self._win_lo)
            anchor_path = self._strip_list.item(0).data(Qt.ItemDataRole.UserRole) if self._strip_list.count() else None
            self._win_lo -= step
            self._repopulate_strip_items()
            if isinstance(anchor_path, str):
                ap = self._path_to_item.get(anchor_path)
                if ap is not None:
                    self._strip_list.scrollToItem(ap, QAbstractItemView.ScrollHint.PositionAtLeft)
            changed = True
        elif vmax > 0 and vmax - v <= _SCROLL_EXPAND_PX and self._win_hi < n:
            step = min(_CHUNK, n - self._win_hi)
            last = self._strip_list.item(self._strip_list.count() - 1) if self._strip_list.count() else None
            anchor_path = last.data(Qt.ItemDataRole.UserRole) if last else None
            self._win_hi += step
            self._repopulate_strip_items()
            if isinstance(anchor_path, str):
                ap = self._path_to_item.get(anchor_path)
                if ap is not None:
                    self._strip_list.scrollToItem(ap, QAbstractItemView.ScrollHint.PositionAtRight)
            changed = True
        if changed:
            self._sync_strip_list_selection()

    def _ensure_visible_thumb_requests(self) -> None:
        cell = max(48, self._outer_px() - _ITEM_CHROME)
        request_thumbnails_for_visible_list_items(self._strip_list, cell, self._thumb_cache)
        self._prune_strip_pixmaps()

    def eventFilter(self, obj, ev) -> bool:  # type: ignore[override]
        if obj is self._strip_list:
            et = ev.type()
            if et == QEvent.Type.Resize:
                self._sync_strip_thumb_scale()
            elif et == QEvent.Type.KeyPress:
                ke = ev
                if isinstance(ke, QKeyEvent):
                    if ke.key() == Qt.Key.Key_Space:
                        if self._selected_path:
                            self.fullscreen_requested.emit(self._selected_path)
                        return True
                    if ke.key() == Qt.Key.Key_Delete:
                        sel = self.selected_paths()
                        if sel:
                            self.delete_requested.emit(sel)
                        return True
                    if ke.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
                        self._navigate(+1)
                        return True
                    if ke.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
                        self._navigate(-1)
                        return True
        return super().eventFilter(obj, ev)

    def _on_preview_context_menu(self, pos: QPoint) -> None:
        if self._selected_path:
            self.image_context_menu_requested.emit(self._selected_path, self._preview.mapToGlobal(pos))

    def _thumb_strip_request_preview(self) -> None:
        if not self._selected_path:
            return
        pw = max(200, self._preview.width() - 24)
        ph = max(150, self._preview.height() - 24)
        dpr = max(1.0, float(self._preview.devicePixelRatio()))
        req = int(max(600, pw, ph) * dpr + 0.5)
        self._thumb_cache.request(self._selected_path, req)

    def _refit_preview_from_cache(self) -> None:
        if not self._selected_path:
            return
        pm = self._pixmaps.get(self._selected_path)
        if pm is not None and not pm.isNull():
            self._set_preview(pm)

    def _schedule_hi_res_preview_fetch(self) -> None:
        if not self._selected_path:
            return
        self._preview_hi_res_timer.start(140)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._sync_strip_thumb_scale()
        self._refit_preview_from_cache()
        self._schedule_hi_res_preview_fetch()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        key = event.key()
        if key == Qt.Key.Key_Space:
            if self._selected_path:
                self.fullscreen_requested.emit(self._selected_path)
            return
        if key == Qt.Key.Key_Delete:
            sel = self.selected_paths()
            if sel:
                self.delete_requested.emit(sel)
            return
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._navigate(+1)
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._navigate(-1)
            return
        super().keyPressEvent(event)

    def _navigate(self, delta: int) -> None:
        if not self._paths:
            return
        cur = self._selected_path or self._paths[0]
        try:
            idx = self._paths.index(cur)
        except ValueError:
            idx = 0
        new_idx = (idx + delta) % len(self._paths)
        new_path = self._paths[new_idx]
        self._apply_pick_path(new_path, False, False, True)
        self._scroll_thumb_into_view(new_path)
        self._thumb_strip_request_preview()

    def apply_thumbnail(self, path: str, payload: object) -> None:
        pm = thumbnail_payload_to_pixmap(payload)
        if pm is None:
            return
        self._pixmaps[path] = pm
        item = self._path_to_item.get(path)
        if item is not None:
            item.setIcon(self._icon_for_path(path))
        if path == self._selected_path:
            self._set_preview(pm)

    def _set_preview(self, pm: QPixmap) -> None:
        if pm.isNull():
            self._preview.setText("No preview")
            self._preview.setPixmap(QPixmap())
            return
        pw = max(200, self._preview.width() - 24)
        ph = max(150, self._preview.height() - 24)
        scaled = pm.scaled(
            pw,
            ph,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview.setPixmap(scaled)
        self._preview.setText("")

    def selected_paths(self) -> list[str]:  # type: ignore[override]
        return [p for p in self._paths if p in self._selected_paths]

    def take_preview_focus(self) -> None:
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def select_primary_path(self, path: str) -> bool:
        if path not in self._paths:
            return False
        self._apply_pick_path(path, False, False, True)
        self._scroll_thumb_into_view(path)
        self._thumb_strip_request_preview()
        self.setFocus()
        return True

    def set_paths(self, paths: list[str]) -> None:
        if paths == self._paths:
            return
        self._paths = list(paths)
        self._selected_paths &= set(paths)
        self._anchor_path = None
        self._path_to_item.clear()
        self._strip_list.clear()
        self._win_lo = self._win_hi = 0

        if not self._paths:
            self._selected_paths.clear()
            self._selected_path = None
            self._preview.clear()
            self._preview.setText("No images")
            self._strip_list.horizontalScrollBar().setValue(0)
            return

        if not self._selected_paths:
            self._selected_paths = {self._paths[0]}
            self._selected_path = self._paths[0]
        else:
            self._selected_path = next(p for p in self._paths if p in self._selected_paths)

        idx = self._paths.index(self._selected_path)
        self._set_window_around_index(idx)
        self._repopulate_strip_items()
        self._strip_list.horizontalScrollBar().setValue(0)

        self._preview.setText("Loading…")
        QTimer.singleShot(0, self._sync_strip_thumb_scale)
        self._thumb_strip_request_preview()
        if self._selected_path:
            self.selection_changed.emit(self._selected_path)

    def set_thumbnail_size(self, size: int, *, reflow: bool = True) -> None:
        super().set_thumbnail_size(size, reflow=reflow)
        mh = max(140, 2 * _STRIP_MARGIN + _MIN_STRIP_SQUARE + _ITEM_CHROME + 48)
        self._strip_list.setMinimumHeight(mh)
        if reflow:
            QTimer.singleShot(0, self._sync_strip_thumb_scale)
            self._thumb_strip_request_preview()

    def set_tile_background(self, enabled: bool) -> None:
        super().set_tile_background(enabled)
        self._refresh_strip_icons()

    def selected_path(self) -> str | None:
        return self._selected_path
