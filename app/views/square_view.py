"""Square grid: uniform square cells (thumbnail slider = edge length in px).

Layout is a custom scroll grid — QListWidget IconMode + ResizeMode.Adjust shrank
cells to tiny tiles regardless of the size slider.

Each cell shows the largest inscribed square from the image (center crop: portrait
crops top/bottom, landscape crops left/right), scaled to fill the square.

Selection uses the same 1 px overlay outline as masonry/justified; filenames sit
below the square with no gray plate behind them."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QContextMenuEvent, QFontMetrics, QKeyEvent, QMouseEvent, QPixmap
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
                "background-color: #3c3c3c; color: #888; font-size: 18px; border: none;"
            )
        else:
            self._img.setStyleSheet("background-color: transparent; color: #888; font-size: 18px; border: none;")

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
        show_filename: bool,
        tile_background: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._side = side

        self._host = _SquareImageHost(side, self)
        self._name = QLabel()
        self._name.setWordWrap(False)
        self._name.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._name.setMaximumWidth(side)
        self._name.setFixedWidth(side)
        self._name.setVisible(show_filename)
        self._name.setStyleSheet("color: #ccc; font-size: 11px; background: transparent; border: none;")
        self._apply_name_text()

        self._name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self._host, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._name, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.setStyleSheet("background: transparent; border: none;")
        self._host.apply_tile_background(tile_background)
        self._drag_press_pos: QPoint | None = None

    def path(self) -> str:
        return self._path

    def set_side(self, side: int) -> None:
        self._side = side
        self._host.set_side(side)
        self._name.setMaximumWidth(side)
        self._name.setFixedWidth(side)
        self._apply_name_text()

    def set_show_filename(self, show: bool) -> None:
        self._name.setVisible(show)
        self._apply_name_text()

    def _apply_name_text(self) -> None:
        raw = Path(self._path).name
        fm = QFontMetrics(self._name.font())
        self._name.setText(fm.elidedText(raw, Qt.TextElideMode.ElideMiddle, max(8, self._side - 2)))

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
        self._tiles: dict[str, _SquareTile] = {}
        self._ncol = 1

        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

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
        self._thumb_cache.thumbnail_ready.connect(self._on_thumb_ready)
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self._vp_timer = QTimer(self)
        self._vp_timer.setSingleShot(True)
        self._vp_timer.timeout.connect(self._reflow)
        self._scroll.viewport().installEventFilter(self)

    def eventFilter(self, obj, ev) -> bool:  # type: ignore[override]
        if obj is self._scroll.viewport() and ev.type() == QEvent.Type.Resize:
            self._vp_timer.start(50)
        return super().eventFilter(obj, ev)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._paths:
            QTimer.singleShot(0, self._reflow)

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
                w.deleteLater()
        self._tiles.clear()

    def _reflow(self) -> None:
        self._clear_tiles()
        if not self._paths:
            return

        self._sync_content_width()
        sz = self._thumbnail_size
        vp_w = self._scroll.viewport().width()
        usable = max(sz, vp_w - 2 * _MARGIN)
        stride = sz + _GAP
        self._ncol = max(1, (usable + _GAP) // stride)

        for idx, path in enumerate(self._paths):
            r, c = divmod(idx, self._ncol)
            tile = _SquareTile(path, sz, self._show_filenames, self._tile_background)
            tile.clicked.connect(self._on_tile_clicked)
            tile.double_clicked.connect(self._on_tile_double_click)
            tile.context_menu_requested.connect(self._on_tile_context_menu)
            if path in self._selected_paths:
                tile.set_selected(True)
            self._tiles[path] = tile
            self._grid.addWidget(tile, r, c, alignment=Qt.AlignmentFlag.AlignTop)

        last_row = (len(self._paths) - 1) // self._ncol if self._paths else 0
        self._grid.setRowStretch(last_row + 1, 1)

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

    def _on_thumb_ready(self, path: str, pm: object) -> None:
        pm = thumbnail_payload_to_pixmap(pm)
        if pm is None:
            return
        tile = self._tiles.get(path)
        if tile:
            tile.set_pixmap(pm)

    def _on_scroll(self) -> None:
        self._request_visible_first()

    def _request_visible_first(self) -> None:
        sz = self._thumbnail_size
        vp = self._scroll.viewport()
        vp_rect = vp.rect()
        visible: list[str] = []
        offscreen: list[str] = []
        for path, tile in self._tiles.items():
            top_left = tile.mapTo(vp, tile.rect().topLeft())
            if vp_rect.intersects(QRect(top_left, tile.size())):
                visible.append(path)
            else:
                offscreen.append(path)
        for p in visible + offscreen:
            self._thumb_cache.request(p, sz)

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
                self._anchor_path if self._anchor_path and self._anchor_path in self._paths else self._paths[idx]
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
        self._paths = list(paths)
        self._selected_paths &= set(paths)
        if self._selected_path not in paths:
            self._selected_path = None
        self._reflow()

    def set_thumbnail_size(self, size: int) -> None:
        super().set_thumbnail_size(size)
        self._reflow()

    def _path_to_item_keys(self) -> list[str]:
        return list(self._tiles.keys())

    def set_show_filenames(self, show: bool) -> None:
        super().set_show_filenames(show)
        for t in self._tiles.values():
            t.set_show_filename(show)

    def set_tile_background(self, enabled: bool) -> None:
        super().set_tile_background(enabled)
        for t in self._tiles.values():
            t.apply_tile_background(enabled)

    def selected_path(self) -> str | None:
        return self._selected_path

    def take_preview_focus(self) -> None:
        self.setFocus(Qt.FocusReason.OtherFocusReason)
