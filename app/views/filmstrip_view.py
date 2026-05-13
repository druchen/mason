"""Large preview + horizontally scrolling thumbnail strip.

Thumbnails letterbox-fit inside square cells sized from the splitter / viewport height
(cap is the thumbnail size slider). Letterbox areas stay transparent.

Selection overlay matches masonry/justified."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QEvent, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QContextMenuEvent, QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QScrollArea,
    QSplitter,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.core.thumbnail_cache import ThumbnailCache, thumbnail_payload_to_pixmap
from app.views.base_view import BaseImageView
from app.views.file_drag import exec_external_file_drag
from app.views.pixmap_fit import fit_pixmap_in_box
from app.views.selection_overlay import SelectionOutlineOverlay

_STRIP_MARGIN = 8
_STRIP_SPACING = 8
_MIN_STRIP_SQUARE = 32


class _FilmstripPreviewLabel(QLabel):
    """Top preview: double-click is delivered reliably (parent event filter is not)."""

    double_clicked_left = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        # Windows may report NoButton for the synthesized double-click; any double-click opens.
        self.double_clicked_left.emit()
        event.accept()


class _StripImageHost(QWidget):
    """Square cell; pixmap scaled to fit entirely inside (no crop). Letterbox transparent."""

    def __init__(self, side: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._side = side
        self.setFixedSize(side, side)

        self._img = QLabel(self)
        self._img.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setScaledContents(False)
        self._img.setFixedSize(side, side)
        self._img.move(0, 0)
        self._img.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._overlay = SelectionOutlineOverlay(self)
        self._overlay.sync_geometry()
        self.refresh_letterbox_style()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._overlay.sync_geometry()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        event.ignore()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        event.ignore()

    def set_selected(self, on: bool) -> None:
        self._overlay.set_outline_visible(on)

    def refresh_letterbox_style(self) -> None:
        apply_tile_background(self._img, False)

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
        fitted = fit_pixmap_in_box(pm, self._side, self._side)
        self._img.setPixmap(fitted)
        self._img.setText("")

    def displayed_pixmap(self) -> QPixmap:
        return self._img.pixmap()


def apply_tile_background(label: QLabel, enabled: bool) -> None:
    """Filmstrip letterbox stays transparent; tile_background pref is ignored here."""
    del enabled
    label.setStyleSheet(
        "background-color: transparent; color: #888; font-size: 13pt; border: none;"
    )


class _FilmstripThumb(QWidget):
    clicked = Signal(str)
    double_clicked = Signal(str)
    context_menu_requested = Signal(str, QPoint)

    def __init__(
        self,
        path: str,
        side: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._side = side

        self._host = _StripImageHost(side, self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._host, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: transparent; border: none;")
        self._drag_press_pos: QPoint | None = None

    def path(self) -> str:
        return self._path

    def set_side(self, side: int) -> None:
        self._side = side
        self._host.set_side(side)

    def apply_tile_background(self, enabled: bool) -> None:
        del enabled
        self._host.refresh_letterbox_style()

    def set_pixmap(self, pm: QPixmap) -> None:
        self._host.set_pixmap(pm)

    def set_selected(self, on: bool) -> None:
        self._host.set_selected(on)

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(self._side, self._side)

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


class FilmstripView(BaseImageView):
    """Large preview + single horizontal scrolling row of thumbnails."""

    def __init__(self, thumb_cache: ThumbnailCache, parent=None) -> None:
        super().__init__(thumb_cache, parent)
        self._selected_path: str | None = None
        self._selected_paths: set[str] = set()
        self._anchor_path: str | None = None
        self._pixmaps: dict[str, QPixmap] = {}
        self._tiles: dict[str, _FilmstripThumb] = {}
        self._strip_thumb_side = self._thumbnail_size

        self._preview = _FilmstripPreviewLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(220)
        self._preview.setScaledContents(False)
        self._preview.setWordWrap(False)
        self._preview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._preview.customContextMenuRequested.connect(self._on_preview_context_menu)
        self._preview.double_clicked_left.connect(self._on_preview_double_click)

        self._strip_scroll = QScrollArea()
        self._strip_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._strip_scroll.setWidgetResizable(False)
        self._strip_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._strip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._strip_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._strip_inner = QWidget()
        outer = QVBoxLayout(self._strip_inner)
        outer.setContentsMargins(0, 0, 0, 0)

        self._strip_row = QWidget()
        self._strip_lay = QHBoxLayout(self._strip_row)
        self._strip_lay.setContentsMargins(
            _STRIP_MARGIN,
            _STRIP_MARGIN,
            _STRIP_MARGIN,
            _STRIP_MARGIN,
        )
        self._strip_lay.setSpacing(_STRIP_SPACING)

        outer.addStretch(1)
        outer.addWidget(self._strip_row, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        outer.addStretch(1)

        self._strip_scroll.setWidget(self._strip_inner)
        self._strip_scroll.viewport().installEventFilter(self)

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self._preview)
        split.addWidget(self._strip_scroll)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(split)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._split = split
        self._strip_scroll.horizontalScrollBar().valueChanged.connect(self._on_strip_scroll)

        mh = max(140, self._reserved_strip_overhead_vertical() + _MIN_STRIP_SQUARE + 48)
        self._strip_scroll.setMinimumHeight(mh)

        # High-res preview requests are expensive. Calling them on every resize event
        # (splitter drags, column width changes) floods the thread pool and pixmap updates,
        # which on Windows can look like rapid blinking / tiny transient windows (HWND churn).
        self._preview_hi_res_timer = QTimer(self)
        self._preview_hi_res_timer.setSingleShot(True)
        self._preview_hi_res_timer.timeout.connect(self._thumb_strip_request_preview)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._paths:
            QTimer.singleShot(0, self._sync_strip_thumb_scale)

    # ------------------------------------------------------------------

    def _reserved_strip_overhead_vertical(self) -> int:
        """Margins (top+bottom of strip row HBox)."""
        return 2 * _STRIP_MARGIN

    def _compute_strip_square_side(self, vp_h: int) -> int:
        """Square edge from viewport height, capped by the global thumbnail size slider."""
        if vp_h < 8:
            return max(_MIN_STRIP_SQUARE, min(512, self._thumbnail_size))
        raw = int(vp_h - self._reserved_strip_overhead_vertical())
        cap_hi = max(_MIN_STRIP_SQUARE, min(512, int(self._thumbnail_size)))
        return max(_MIN_STRIP_SQUARE, min(cap_hi, raw))

    # ------------------------------------------------------------------

    def _resize_strip_inner_width(self, side: int | None = None) -> None:
        side = self._strip_thumb_side if side is None else side
        n = len(self._tiles)
        vp = self._strip_scroll.viewport()
        vw = max(1, vp.width())

        if n == 0:
            vh = max(1, vp.height())
            self._strip_inner.setFixedSize(vw, vh)
            return

        wm = self._strip_lay.contentsMargins()
        mw = wm.left() + wm.right()
        inner_w = mw + n * side + max(0, n - 1) * self._strip_lay.spacing()
        self._strip_inner.setFixedWidth(max(inner_w, vw))

    # ------------------------------------------------------------------

    def _sync_strip_thumb_scale(self) -> None:
        vp = self._strip_scroll.viewport()
        vw = max(1, vp.width())
        vh = vp.height()
        if vh < 24:
            return

        side_new = self._compute_strip_square_side(vh)
        prev_side = getattr(self, "_strip_thumb_side", None)
        resized = prev_side is None or prev_side != side_new
        self._strip_thumb_side = side_new

        self.setUpdatesEnabled(False)
        try:
            self._strip_inner.setFixedHeight(vh)
            self._strip_inner.setMinimumWidth(vw)

            if self._tiles:
                if resized:
                    for tile in self._tiles.values():
                        tile.set_side(side_new)

            self._resize_strip_inner_width(side_new)

            if self._tiles and resized:
                for p in self._tiles.keys():
                    self._thumb_cache.request(p, side_new)
        finally:
            self.setUpdatesEnabled(True)
            self.update()

        if self._tiles and resized:
            QTimer.singleShot(0, self._strip_timer)

    # ------------------------------------------------------------------

    def _on_preview_double_click(self) -> None:
        if self._selected_path:
            self.open_in_photoshop_requested.emit(self._selected_path)

    def _on_strip_tile_context_menu(self, path: str, global_pos: QPoint) -> None:
        self._apply_pick_path(path, False, False, True)
        self.setFocus()
        self._scroll_thumb_into_view(path)
        self._thumb_strip_request_preview()
        self.image_context_menu_requested.emit(path, global_pos)

    def _sync_tile_styles(self) -> None:
        for p, tile in self._tiles.items():
            tile.set_selected(p in self._selected_paths)

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

    def _on_thumb_clicked(self, path: str) -> None:
        mods = QApplication.queryKeyboardModifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        self._apply_pick_path(path, ctrl, shift, True)
        self.setFocus()
        self._scroll_thumb_into_view(path)
        self._thumb_strip_request_preview()

    def _on_strip_thumb_double_click(self, path: str) -> None:
        self.open_in_photoshop_requested.emit(path)

    def _scroll_thumb_into_view(self, path: str) -> None:
        tile = self._tiles.get(path)
        if tile:
            self._strip_scroll.ensureWidgetVisible(tile)

    # ------------------------------------------------------------------

    def _strip_timer(self) -> None:
        QTimer.singleShot(0, self._ensure_visible_thumb_requests)

    def _on_strip_scroll(self) -> None:
        self._ensure_visible_thumb_requests()

    def _ensure_visible_thumb_requests(self) -> None:
        vp = self._strip_scroll.viewport()
        vp_rect = vp.rect()
        sz = max(48, self._strip_thumb_side)
        visible: list[str] = []
        for path, tile in self._tiles.items():
            if tile.parentWidget() is None:
                continue
            tl = vp.mapFromGlobal(tile.mapToGlobal(QPoint(0, 0)))
            if vp_rect.intersects(QRect(tl, tile.size())):
                visible.append(path)
        self.setUpdatesEnabled(False)
        try:
            for p in visible:
                self._thumb_cache.request(p, sz)
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def eventFilter(self, obj, ev) -> bool:  # type: ignore[override]
        if obj is self._strip_scroll.viewport() and ev.type() == QEvent.Type.Resize:
            self._sync_strip_thumb_scale()
        return super().eventFilter(obj, ev)

    def _on_preview_context_menu(self, pos: QPoint) -> None:
        if self._selected_path:
            self.image_context_menu_requested.emit(self._selected_path, self._preview.mapToGlobal(pos))

    # ------------------------------------------------------------------

    def _thumb_strip_request_preview(self) -> None:
        if not self._selected_path:
            return
        pw = max(200, self._preview.width() - 24)
        ph = max(150, self._preview.height() - 24)
        dpr = max(1.0, float(self._preview.devicePixelRatio()))
        # Must match or exceed on-screen box (HiDPI) so we are not upscaling a tiny thumb.
        req = int(max(600, pw, ph) * dpr + 0.5)
        self._thumb_cache.request(self._selected_path, req)

    def _refit_preview_from_cache(self) -> None:
        """Rescale the large preview from RAM during live resize (no worker)."""
        if not self._selected_path:
            return
        pm = self._pixmaps.get(self._selected_path)
        if pm is not None and not pm.isNull():
            self._set_preview(pm)

    def _schedule_hi_res_preview_fetch(self) -> None:
        """Queue a single high-res decode after resize gestures settle."""
        if not self._selected_path:
            return
        self._preview_hi_res_timer.start(140)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._sync_strip_thumb_scale()
        self._refit_preview_from_cache()
        self._schedule_hi_res_preview_fetch()

    # ------------------------------------------------------------------

    def _clear_strip(self) -> None:
        while self._strip_lay.count():
            item = self._strip_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._tiles.clear()

    def _rebuild_strip(self) -> None:
        self.setUpdatesEnabled(False)
        try:
            self._clear_strip()
            vp = self._strip_scroll.viewport()
            vw = max(1, vp.width())
            vh = vp.height()

            if not self._paths:
                self._preview.clear()
                self._preview.setText("No images")
                self._strip_thumb_side = self._thumbnail_size
                self._strip_inner.setFixedSize(vw, max(vh, 1))
                return

            self._strip_inner.setMinimumWidth(vw)
            self._strip_inner.setFixedHeight(max(vh, 1))

            self._strip_thumb_side = self._compute_strip_square_side(max(vh, self._reserved_strip_overhead_vertical() + _MIN_STRIP_SQUARE))
            side = self._strip_thumb_side

            for p in self._paths:
                tile = _FilmstripThumb(p, side)
                tile.clicked.connect(self._on_thumb_clicked)
                tile.double_clicked.connect(self._on_strip_thumb_double_click)
                tile.context_menu_requested.connect(self._on_strip_tile_context_menu)
                if p in self._selected_paths:
                    tile.set_selected(True)
                self._tiles[p] = tile
                cached = self._pixmaps.get(p)
                if cached is not None and not cached.isNull():
                    tile.set_pixmap(cached)
                self._strip_lay.addWidget(tile)

            self._resize_strip_inner_width(side)
        finally:
            self.setUpdatesEnabled(True)
            self.update()

        QTimer.singleShot(0, self._strip_timer)
        QTimer.singleShot(0, self._sync_strip_thumb_scale)

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

    # ------------------------------------------------------------------

    def apply_thumbnail(self, path: str, payload: object) -> None:
        pm = thumbnail_payload_to_pixmap(payload)
        if pm is None:
            return
        self._pixmaps[path] = pm
        tile = self._tiles.get(path)
        if tile:
            tile.set_pixmap(pm)
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

        if not self._paths:
            self._selected_paths.clear()
            self._selected_path = None
            self._rebuild_strip()
            return

        if not self._selected_paths:
            self._selected_paths = {self._paths[0]}
            self._selected_path = self._paths[0]
        else:
            self._selected_path = next(p for p in self._paths if p in self._selected_paths)

        self._preview.setText("Loading…")
        self._rebuild_strip()
        self._thumb_strip_request_preview()
        if self._selected_path:
            self.selection_changed.emit(self._selected_path)

    def set_thumbnail_size(self, size: int, *, reflow: bool = True) -> None:
        super().set_thumbnail_size(size, reflow=reflow)
        mh = max(140, self._reserved_strip_overhead_vertical() + _MIN_STRIP_SQUARE + 48)
        self._strip_scroll.setMinimumHeight(mh)
        if reflow:
            self._sync_strip_thumb_scale()
            self._thumb_strip_request_preview()

    def set_tile_background(self, enabled: bool) -> None:
        super().set_tile_background(enabled)
        for t in self._tiles.values():
            t.apply_tile_background(enabled)

    def selected_path(self) -> str | None:
        return self._selected_path
