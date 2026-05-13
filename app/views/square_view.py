"""Square grid: uniform square cells (thumbnail slider = edge length in px).

Each cell shows the largest inscribed square from the image (center crop),
scaled to fill the square. No filename labels.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QContextMenuEvent, QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.thumbnail_cache import ThumbnailCache, thumbnail_payload_to_pixmap
from app.views.base_view import BaseImageView
from app.views.file_drag import exec_external_file_drag
from app.views.selection_overlay import SelectionOutlineOverlay

_GAP = 8
_MARGIN = 8


def _inscribed_square_crop(pm: QPixmap) -> QPixmap:
    """Largest axis-aligned square inside the image (only two sides cropped)."""
    w, h = pm.width(), pm.height()
    if w <= 0 or h <= 0:
        return pm
    if w == h:
        return pm
    side = min(w, h)
    x = (w - side) // 2
    y = (h - side) // 2
    return pm.copy(QRect(x, y, side, side))


class _SquareImageHost(QWidget):
    """Fixed square area for pixmap + selection outline on top."""

    def __init__(self, side: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._side = side
        self.setFixedSize(side, side)

        self._img = QLabel(self)
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setScaledContents(False)
        self._img.setFixedSize(side, side)
        self._img.move(0, 0)
        self._img.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._overlay = SelectionOutlineOverlay(self)
        self._overlay.sync_geometry()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        event.ignore()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        event.ignore()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._overlay.sync_geometry()

    def set_side(self, side: int) -> None:
        self._side = side
        self.setFixedSize(side, side)
        self._img.setFixedSize(side, side)
        self._img.move(0, 0)
        self._overlay.sync_geometry()

    def set_pixmap(self, pm: QPixmap) -> None:
        if pm.isNull():
            self._img.clear()
            self._img.setText("…")
            return
        sq = _inscribed_square_crop(pm)
        scaled = sq.scaled(
            self._side,
            self._side,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._img.setPixmap(scaled)
        self._img.setText("")

    def apply_tile_background(self, enabled: bool) -> None:
        if enabled:
            self._img.setStyleSheet(
                "background-color: #3c3c3c; color: #888; font-size: 13pt; border: none;"
            )
        else:
            self._img.setStyleSheet(
                "background-color: transparent; color: #888; font-size: 13pt; border: none;"
            )

    def set_selected(self, on: bool) -> None:
        self._overlay.set_outline_visible(on)

    def displayed_pixmap(self) -> QPixmap:
        return self._img.pixmap()


class _SquareTile(QWidget):
    clicked = Signal(str)
    double_clicked = Signal(str)
    context_menu_requested = Signal(str, QPoint)

    def __init__(
        self,
        path: str,
        side: int,
        tile_background: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._side = side

        self._host = _SquareImageHost(side, self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._host, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.setStyleSheet("background: transparent; border: none;")
        self._host.apply_tile_background(tile_background)
        self._drag_press_pos: QPoint | None = None

    def path(self) -> str:
        return self._path

    def set_side(self, side: int) -> None:
        self._side = side
        self._host.set_side(side)

    def apply_tile_background(self, enabled: bool) -> None:
        self._host.apply_tile_background(enabled)

    def set_pixmap(self, pm: QPixmap) -> None:
        self._host.set_pixmap(pm)

    def set_selected(self, on: bool) -> None:
        self._host.set_selected(on)

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
            pm = self._host.displayed_pixmap()
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


class SquareGridView(BaseImageView):
    def __init__(self, thumb_cache: ThumbnailCache, parent=None) -> None:
        super().__init__(thumb_cache, parent)
        self._selected_path: str | None = None
        self._selected_paths: set[str] = set()
        self._anchor_path: str | None = None
        self._pixmaps: dict[str, QPixmap] = {}
        self._tiles: dict[str, _SquareTile] = {}
        self._ncol = 1
        self._layout_sig: tuple[int, int] | None = None

        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Always-on avoids viewport-width oscillation from scrollbar show/hide.
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self._content = QWidget()
        self._grid = QGridLayout(self._content)
        self._grid.setContentsMargins(_MARGIN, _MARGIN, _MARGIN, _MARGIN)
        self._grid.setHorizontalSpacing(_GAP)
        self._grid.setVerticalSpacing(_GAP)
        self._scroll.setWidget(self._content)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._scroll)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self._vp_timer = QTimer(self)
        self._vp_timer.setSingleShot(True)
        self._vp_timer.timeout.connect(self._reflow)
        self._scroll.viewport().installEventFilter(self)

    def eventFilter(self, obj, ev) -> bool:  # type: ignore[override]
        if obj is self._scroll.viewport() and ev.type() == QEvent.Type.Resize:
            self._vp_timer.start(75)
        return super().eventFilter(obj, ev)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _sync_content_width(self) -> None:
        w = max(0, self._scroll.viewport().width())
        self._content.setMinimumWidth(w)
        self._content.setMaximumWidth(w)

    def _clear_tiles(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.deleteLater()
        self._tiles.clear()

    def _reflow(self) -> None:
        if not self._paths:
            self._content.setVisible(False)
            try:
                self._clear_tiles()
                self._layout_sig = None
            finally:
                self._content.setVisible(True)
            self.update()
            return

        self._sync_content_width()
        sz = self._thumbnail_size
        vp_w = self._scroll.viewport().width()
        usable = max(sz, vp_w - 2 * _MARGIN)
        new_ncol = max(1, (usable + _GAP) // (sz + _GAP))
        sig = (sz, new_ncol)
        if (
            self._layout_sig == sig
            and len(self._tiles) == len(self._paths)
            and all(p in self._tiles for p in self._paths)
        ):
            return

        self._content.setVisible(False)
        try:
            self._clear_tiles()
            self._ncol = new_ncol

            for idx, path in enumerate(self._paths):
                r, c = divmod(idx, self._ncol)
                tile = _SquareTile(path, sz, self._tile_background)
                tile.clicked.connect(self._on_tile_clicked)
                tile.double_clicked.connect(self._on_tile_double_click)
                tile.context_menu_requested.connect(self._on_tile_context_menu)
                if path in self._selected_paths:
                    tile.set_selected(True)
                self._tiles[path] = tile
                cached = self._pixmaps.get(path)
                if cached is not None and not cached.isNull():
                    tile.set_pixmap(cached)
                self._grid.addWidget(tile, r, c, alignment=Qt.AlignmentFlag.AlignTop)

            last_row = (len(self._paths) - 1) // self._ncol if self._paths else 0
            self._grid.setRowStretch(last_row + 1, 1)
            self._layout_sig = sig
        finally:
            self._content.setVisible(True)
        self.update()

        QTimer.singleShot(0, self._request_visible_first)

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

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

    def _sync_tile_styles(self) -> None:
        for p, tile in self._tiles.items():
            tile.set_selected(p in self._selected_paths)

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

    def selected_paths(self) -> list[str]:  # type: ignore[override]
        return [p for p in self._paths if p in self._selected_paths]

    # ------------------------------------------------------------------
    # Thumbnails
    # ------------------------------------------------------------------

    def apply_thumbnail(self, path: str, payload: object) -> None:
        pm = thumbnail_payload_to_pixmap(payload)
        if pm is None:
            return
        self._pixmaps[path] = pm
        tile = self._tiles.get(path)
        if tile:
            tile.set_pixmap(pm)

    def _on_scroll(self) -> None:
        self._request_visible_first()

    def _request_visible_first(self) -> None:
        sz = self._thumbnail_size
        viewport = self._scroll.viewport()
        vp_rect = viewport.rect()
        self.setUpdatesEnabled(False)
        try:
            for p, tile in self._tiles.items():
                if tile.parentWidget() is None:
                    continue
                tl = viewport.mapFromGlobal(tile.mapToGlobal(QPoint(0, 0)))
                if vp_rect.intersects(QRect(tl, tile.size())):
                    self._thumb_cache.request(p, sz)
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def _index_of_selected(self) -> int | None:
        if not self._selected_path or self._selected_path not in self._paths:
            return None
        return self._paths.index(self._selected_path)

    def _keyboard_step_grid(self, dr: int, dc: int, mods: Qt.KeyboardModifier) -> None:
        if not self._paths or self._ncol < 1:
            return
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        idx = self._index_of_selected()
        n = len(self._paths)

        if idx is None:
            self._apply_pick_path(self._paths[0], False, False, True)
            self._scroll_into_view(self._paths[0])
            return

        r, c = divmod(idx, self._ncol)
        nr, nc = r + dr, c + dc
        if nr < 0 or nc < 0 or nc >= self._ncol:
            return
        ni = nr * self._ncol + nc
        if ni >= n:
            return

        new_path = self._paths[ni]
        if shift:
            anchor = (
                self._anchor_path
                if self._anchor_path and self._anchor_path in self._paths
                else self._paths[idx]
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

        self._scroll_into_view(new_path)

    def _scroll_into_view(self, path: str) -> None:
        tile = self._tiles.get(path)
        if tile:
            self._scroll.ensureWidgetVisible(tile)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        key = event.key()
        mods = event.modifiers()

        if key == Qt.Key.Key_Space:
            sel = self.selected_paths()
            if sel:
                self.fullscreen_requested.emit(sel[-1])
            return
        if key == Qt.Key.Key_Delete:
            sel = self.selected_paths()
            if sel:
                self.delete_requested.emit(sel)
            return

        if key == Qt.Key.Key_Right:
            self._keyboard_step_grid(0, 1, mods)
            return
        if key == Qt.Key.Key_Left:
            self._keyboard_step_grid(0, -1, mods)
            return
        if key == Qt.Key.Key_Down:
            self._keyboard_step_grid(1, 0, mods)
            return
        if key == Qt.Key.Key_Up:
            self._keyboard_step_grid(-1, 0, mods)
            return

        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # BaseImageView interface
    # ------------------------------------------------------------------

    def set_paths(self, paths: list[str]) -> None:
        if paths == self._paths:
            return
        self._paths = list(paths)
        self._selected_paths &= set(paths)
        if self._selected_path not in paths:
            self._selected_path = None
        self._reflow()

    def set_thumbnail_size(self, size: int, *, reflow: bool = True) -> None:
        super().set_thumbnail_size(size, reflow=reflow)
        if reflow:
            self._reflow()

    def set_tile_background(self, enabled: bool) -> None:
        super().set_tile_background(enabled)
        for t in self._tiles.values():
            t.apply_tile_background(enabled)

    def selected_path(self) -> str | None:
        return self._selected_path

    def take_preview_focus(self) -> None:
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def select_primary_path(self, path: str) -> bool:
        if path not in self._paths:
            return False
        self._apply_pick_path(path, False, False, True)
        self._scroll_into_view(path)
        self.setFocus()
        return True
