"""Variable-height column masonry (waterfall) layout.

Rules:
- Images placed into the shortest column (like Pinterest).
- Column width is fixed; tile height derived from original aspect ratio.
- No stretching — pixmap fitted with KeepAspectRatio.
- Selected images highlighted with light-blue 1-px outline.

Performance:
- Dimensions read from image_cache (SQLite-backed).
- Thumbnails requested visible-first.
- The scroll widget's inner width is clamped to the viewport so the layout cannot extend past the right edge; no horizontal scrollbar.

Multi-select:
- Plain click: single select.
- Ctrl+click: toggle membership.
- Shift+click: range select anchored to last non-shift click.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QEvent, QRect, QTimer, Signal
from PySide6.QtGui import QContextMenuEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core import image_cache
from app.core.thumbnail_cache import ThumbnailCache, thumbnail_payload_to_pixmap
from app.views.base_view import BaseImageView
from app.views.file_drag import exec_external_file_drag
from app.views.pixmap_fit import fit_pixmap_in_box, max_thumb_dim_for_aspect
from app.views.selection_overlay import SelectionOutlineOverlay

# Horizontal padding so selection borders aren’t clipped at viewport edges (symmetric side margins).
SIDE_MARGIN_BASE = 8
SELECTION_SIDE_INSET = 4
# Extra reserve on the content’s right: scroll viewport clips the last column’s focus border without this.
RIGHT_EDGE_SLOP_PX = 10


class _MasonryTile(QFrame):
    clicked = Signal(str)
    double_clicked = Signal(str)
    context_menu_requested = Signal(str, QPoint)

    def __init__(
        self,
        path: str,
        col_w: int,
        w: int,
        h: int,
        show_filename: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._w = max(1, w)
        self._h = max(1, h)

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWidth(0)
        self.setMidLineWidth(0)

        self._img = QLabel()
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setScaledContents(False)

        self._title = QLabel(Path(path).name if show_filename else "")
        self._title.setWordWrap(True)
        self._title.setMaximumWidth(col_w)
        self._title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._title.setVisible(show_filename)

        oh = max(1, int(round(col_w * self._h / self._w)))
        self._img.setFixedSize(col_w, oh)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(2)
        lay.addWidget(self._img)
        lay.addWidget(self._title)

        self._sel_overlay = SelectionOutlineOverlay(self)
        self._sel_overlay.sync_geometry()

        self._img.setStyleSheet(
            "background-color: #3c3c3c; border-radius: 0px; color: #888; border: none;"
        )
        self._img.setText("…")
        self._img.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedWidth(col_w)
        self._drag_press_pos: QPoint | None = None

    def path(self) -> str:
        return self._path

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._sel_overlay.sync_geometry()

    def set_selected(self, selected: bool) -> None:
        self._sel_overlay.set_outline_visible(selected)

    def set_show_filename(self, show: bool) -> None:
        self._title.setText(Path(self._path).name if show else "")
        self._title.setVisible(show)

    def set_pixmap(self, pm: QPixmap) -> None:
        if pm.isNull():
            self._img.setPixmap(QPixmap())
            self._img.setText("…")
            return
        fitted = fit_pixmap_in_box(pm, self._img.width(), self._img.height())
        self._img.setPixmap(fitted)
        self._img.setText("")

    def thumb_dim(self) -> int:
        return max_thumb_dim_for_aspect(
            self._img.width(),
            self._img.height(),
            self._w,
            self._h,
        )

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_press_pos = event.position().toPoint()
            self.clicked.emit(self._path)
        else:
            self._drag_press_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if (
            self._drag_press_pos is not None
            and (event.buttons() & Qt.MouseButton.LeftButton)
            and (event.position().toPoint() - self._drag_press_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._drag_press_pos = None
            pm = self._img.pixmap()
            preview = None if pm.isNull() else pm
            exec_external_file_drag(self, [self._path], preview)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self._drag_press_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self.double_clicked.emit(self._path)
        event.accept()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # type: ignore[override]
        self.context_menu_requested.emit(self._path, event.globalPos())
        event.accept()


class MasonryView(BaseImageView):
    def __init__(self, thumb_cache: ThumbnailCache, parent=None) -> None:
        super().__init__(thumb_cache, parent)
        self._selected_path: str | None = None
        self._selected_paths: set[str] = set()
        self._anchor_path: str | None = None

        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._content = QWidget()
        self._row = QHBoxLayout(self._content)
        sm = SIDE_MARGIN_BASE + SELECTION_SIDE_INSET
        self._row.setContentsMargins(sm, 8, sm + RIGHT_EDGE_SLOP_PX, 8)
        self._row.setSpacing(8)
        self._tiles: dict[str, _MasonryTile] = {}

        self._scroll.setWidget(self._content)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._scroll)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._thumb_cache.thumbnail_ready.connect(self._on_thumb_ready)
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._vp_resize_debounce = QTimer(self)
        self._vp_resize_debounce.setSingleShot(True)
        self._vp_resize_debounce.timeout.connect(self._reflow)
        self._scroll.viewport().installEventFilter(self)

    def eventFilter(self, obj, ev) -> bool:
        if obj is self._scroll.viewport() and ev.type() == QEvent.Type.Resize:
            self._vp_resize_debounce.start(75)
        return super().eventFilter(obj, ev)

    # ------------------------------------------------------------------
    # Inner width for column math (viewport already excludes scrollbar)
    # ------------------------------------------------------------------

    def _inner_width(self) -> int:
        sm = SIDE_MARGIN_BASE + SELECTION_SIDE_INSET
        vp = self._scroll.viewport()
        return max(50, vp.width() - 2 * sm - RIGHT_EDGE_SLOP_PX)

    def _clamp_scroll_inner_width(self) -> None:
        w = max(0, self._scroll.viewport().width())
        self._content.setMaximumWidth(w)

    # ------------------------------------------------------------------
    # Thumbnail / selection handlers
    # ------------------------------------------------------------------

    def _on_thumb_ready(self, path: str, pm: object) -> None:
        pm = thumbnail_payload_to_pixmap(pm)
        if pm is None:
            return
        tile = self._tiles.get(path)
        if tile:
            tile.set_pixmap(pm)

    def _apply_pick_path(self, path: str, ctrl: bool, shift: bool, emit_changed: bool) -> None:
        if shift and self._anchor_path and self._anchor_path in self._paths:
            ai = self._paths.index(self._anchor_path)
            ci = self._paths.index(path)
            lo, hi = sorted([ai, ci])
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
        else:
            self._selected_paths = {path}
            self._anchor_path = path

        self._selected_path = path
        self._sync_tile_styles()
        if emit_changed:
            self.selection_changed.emit(path)

    def _scroll_selected_into_view(self) -> None:
        if not self._selected_path:
            return
        tile = self._tiles.get(self._selected_path)
        if tile:
            self._scroll.ensureWidgetVisible(tile)

    def _keyboard_step(self, delta: int, mods: Qt.KeyboardModifier | None = None) -> None:
        if not self._paths:
            return
        m = mods if mods is not None else QApplication.queryKeyboardModifiers()
        shift = bool(m & Qt.KeyboardModifier.ShiftModifier)

        cur = self._selected_path if self._selected_path in self._paths else None
        if cur is None:
            self._apply_pick_path(self._paths[0], False, False, True)
            self.setFocus()
            self._scroll_selected_into_view()
            return

        idx = self._paths.index(cur)
        ni = max(0, min(len(self._paths) - 1, idx + delta))
        if ni == idx:
            return
        new_path = self._paths[ni]

        if shift:
            anchor = (
                self._anchor_path if self._anchor_path and self._anchor_path in self._paths else cur
            )
            ai = self._paths.index(anchor)
            lo, hi = sorted([ai, ni])
            self._anchor_path = anchor
            self._selected_paths = set(self._paths[lo : hi + 1])
            self._selected_path = new_path
            self._sync_tile_styles()
            self.selection_changed.emit(new_path)
        else:
            self._apply_pick_path(new_path, False, False, True)

        self.setFocus()
        self._scroll_selected_into_view()

    def _on_tile_clicked(self, path: str) -> None:
        mods = QApplication.queryKeyboardModifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        self._apply_pick_path(path, ctrl, shift, True)
        self.setFocus()

    def _on_tile_double_click(self, path: str) -> None:
        self.open_in_photoshop_requested.emit(path)

    def _on_tile_context_menu(self, path: str, global_pos: QPoint) -> None:
        self._apply_pick_path(path, False, False, True)
        self.setFocus()
        self.image_context_menu_requested.emit(path, global_pos)

    def _on_scroll(self) -> None:
        self._request_visible_first()

    def _sync_tile_styles(self) -> None:
        for p, tile in self._tiles.items():
            tile.set_selected(p in self._selected_paths)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _clear_columns(self) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._tiles.clear()

    def _reflow(self) -> None:
        if not self._paths:
            self._clear_columns()
            return

        self._clamp_scroll_inner_width()

        vw = self._inner_width()
        min_col = max(self._thumbnail_size, 80)
        ncols = max(1, vw // min_col)
        col_w = max(80, (vw - 8 * (ncols - 1)) // ncols)

        self._clear_columns()
        dims = image_cache.probe_batch(self._paths)

        col_layouts: list[QVBoxLayout] = []
        heights: list[float] = []

        for _ in range(ncols):
            cw = QWidget()
            cl = QVBoxLayout(cw)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(8)
            col_layouts.append(cl)
            heights.append(0.0)
            self._row.addWidget(cw)

        for path in self._paths:
            d = dims.get(path)
            w, h = d if d else (1, 1)
            j = min(range(ncols), key=lambda k: heights[k])
            tile = _MasonryTile(path, col_w, w, h, self._show_filenames)
            tile.clicked.connect(self._on_tile_clicked)
            tile.double_clicked.connect(self._on_tile_double_click)
            tile.context_menu_requested.connect(self._on_tile_context_menu)
            if path in self._selected_paths:
                tile.set_selected(True)
            self._tiles[path] = tile
            col_layouts[j].addWidget(tile)
            oh = max(1, int(round(col_w * h / max(1, w))))
            heights[j] += oh + 8 + (20 if self._show_filenames else 0)

        for cl in col_layouts:
            cl.addStretch(1)

        QTimer.singleShot(0, self._request_visible_first)

    def _request_visible_first(self) -> None:
        viewport = self._scroll.viewport()
        vp_rect = viewport.rect()
        visible: list[str] = []
        offscreen: list[str] = []
        for path, tile in self._tiles.items():
            tile_in_vp = tile.mapTo(viewport, tile.rect().topLeft())
            if vp_rect.intersects(QRect(tile_in_vp, tile.size())):
                visible.append(path)
            else:
                offscreen.append(path)
        for p in visible + offscreen:
            tile = self._tiles.get(p)
            if isinstance(tile, _MasonryTile):
                self._thumb_cache.request(p, tile.thumb_dim())

    # ------------------------------------------------------------------
    # Key events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Space:
            sel = self.selected_paths()
            if sel:
                self.fullscreen_requested.emit(sel[-1])
        elif key == Qt.Key.Key_Delete:
            sel = self.selected_paths()
            if sel:
                self.delete_requested.emit(sel)
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._keyboard_step(+1, event.modifiers())
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._keyboard_step(-1, event.modifiers())
        elif key == Qt.Key.Key_End:
            if self._paths:
                mods = event.modifiers()
                self._apply_pick_path(self._paths[-1], bool(mods & Qt.KeyboardModifier.ControlModifier),
                                     bool(mods & Qt.KeyboardModifier.ShiftModifier), True)
                self.setFocus()
                self._scroll_selected_into_view()
        elif key == Qt.Key.Key_Home:
            if self._paths:
                mods = event.modifiers()
                self._apply_pick_path(self._paths[0], bool(mods & Qt.KeyboardModifier.ControlModifier),
                                      bool(mods & Qt.KeyboardModifier.ShiftModifier), True)
                self.setFocus()
                self._scroll_selected_into_view()
        else:
            super().keyPressEvent(event)

    def take_preview_focus(self) -> None:
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def select_primary_path(self, path: str) -> bool:
        if path not in self._paths:
            return False
        self._apply_pick_path(path, False, False, True)
        self._scroll_selected_into_view()
        self.setFocus()
        return True

    # ------------------------------------------------------------------
    # BaseImageView interface
    # ------------------------------------------------------------------

    def selected_path(self) -> str | None:
        return self._selected_path

    def selected_paths(self) -> list[str]:
        return list(self._selected_paths)

    def set_paths(self, paths: list[str]) -> None:
        self._paths = list(paths)
        # Drop stale selections
        self._selected_paths &= set(paths)
        self._reflow()

    def set_thumbnail_size(self, size: int) -> None:
        super().set_thumbnail_size(size)
        self._reflow()

    def set_show_filenames(self, show: bool) -> None:
        if show == self._show_filenames:
            return
        super().set_show_filenames(show)
        self.setUpdatesEnabled(False)
        try:
            for t in self._tiles.values():
                t.set_show_filename(show)
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def set_tile_background(self, enabled: bool) -> None:
        super().set_tile_background(enabled)
