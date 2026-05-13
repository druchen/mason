"""Justified grid: every row spans the same width R with uniform pixel gap G."""

from __future__ import annotations

import math
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

OUTER_MARGIN = 8
GAP = 8
# Inset inside each justified row so selection borders aren’t clipped at viewport edges.
SELECTION_SIDE_INSET = 4
# Keeps the last tile’s right border inside the scroll viewport (avoids 3-sided selection frame).
RIGHT_EDGE_SLOP_PX = 10


def _aspect(iw: int, ih: int) -> float:
    return max(1, iw) / max(1, ih)


def _pack_row(
    row_width: int,
    gap: int,
    entries: list[tuple[str, int, int]],
) -> tuple[int, list[tuple[str, int, int]]]:
    """``(path, iw, ih)`` → ``row_h_px, [(path, w_px, row_h_px), ...]``.
    Satisfies ``sum(widths) + (n−1)×gap == row_width``.
    """
    row_width = max(1, row_width)
    n = len(entries)
    if n == 0:
        return 1, []

    gaps = gap * max(0, n - 1)
    content = row_width - gaps
    if content < n:
        content = max(1, row_width // max(1, n))

    if n == 1:
        p, iw, ih = entries[0]
        iw_, ih_ = max(1, iw), max(1, ih)
        row_h = int(round(content * ih_ / iw_))
        row_h = max(1, min(8192, row_h))
        return row_h, [(p, content, row_h)]

    sum_a = sum(_aspect(iw, ih) for _, iw, ih in entries)

    row_h_f = content / sum_a if sum_a > 0 else 40.0
    row_h_px = max(1, int(round(row_h_f)))

    frac: list[float] = []
    for _, iw_, ih_ in entries:
        frac.append(row_h_px * _aspect(iw_, ih_))

    w_int = [max(1, math.floor(fw)) for fw in frac]

    shortage = content - sum(w_int)
    if shortage > 0:
        prio = sorted(range(n), key=lambda i: frac[i] - w_int[i], reverse=True)
        for k in range(shortage):
            w_int[prio[k % n]] += 1
    elif shortage < 0:
        need_drop = -shortage
        prio = sorted(range(n), key=lambda i: frac[i] - w_int[i])
        idx = 0
        while need_drop > 0 and idx < n * 8192:
            j = prio[idx % n]
            if w_int[j] > 1:
                w_int[j] -= 1
                need_drop -= 1
            idx += 1

    drift = content - sum(w_int)
    if drift != 0:
        j = max(range(n), key=lambda idx: frac[idx])
        w_int[j] = max(1, w_int[j] + drift)

    # Guaranteed exact total (scrollbar / HiDPI can otherwise leave +/-1 px drift).
    err = content - sum(w_int)
    if err != 0 and n >= 1:
        jj = max(range(n), key=lambda idx: frac[idx]) if frac else n - 1
        cand = (
            jj if w_int[jj] + err >= 1
            else next((idx for idx in range(n) if w_int[idx] + err >= 1), jj)
        )
        w_int[cand] = max(1, w_int[cand] + err)

    packed = [(entries[k][0], w_int[k], row_h_px) for k in range(n)]
    return row_h_px, packed


class _JustTile(QFrame):
    clicked = Signal(str)
    double_clicked = Signal(str)
    context_menu_requested = Signal(str, QPoint)

    def __init__(
        self,
        path: str,
        pixel_w: int,
        pixel_h: int,
        show_filename: bool,
        iw: int,
        ih: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._iw = max(1, iw)
        self._ih = max(1, ih)

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWidth(0)
        self.setMidLineWidth(0)

        pw, ph = max(1, pixel_w), max(1, pixel_h)

        self._img = QLabel()
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setScaledContents(False)
        self._img.setFixedSize(pw, ph)

        self._title = QLabel(Path(path).name if show_filename else "")
        self._title.setWordWrap(True)
        self._title.setMaximumWidth(pw)
        self._title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._title.setVisible(show_filename)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(2)
        lay.addWidget(self._img)
        lay.addWidget(self._title)

        self.setFixedWidth(pw)

        self._sel_overlay = SelectionOutlineOverlay(self)
        self._sel_overlay.sync_geometry()

        self._img.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

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
            self._img.setText("…")
            self._img.setPixmap(QPixmap())
            return
        fitted = fit_pixmap_in_box(pm, self._img.width(), self._img.height())
        self._img.setPixmap(fitted)
        self._img.setText("")

    def thumb_dim(self) -> int:
        return max_thumb_dim_for_aspect(self._img.width(), self._img.height(), self._iw, self._ih)

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


class JustifiedView(BaseImageView):
    def __init__(self, thumb_cache: ThumbnailCache, parent=None) -> None:
        super().__init__(thumb_cache, parent)
        self._selected_path: str | None = None
        self._selected_paths: set[str] = set()
        self._anchor_path: str | None = None
        self._pixmaps: dict[str, QPixmap] = {}

        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Keep viewport width stable; AsNeeded can oscillate and trigger endless rebuild on Windows.
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._outer = QWidget()
        self._outer_lay = QVBoxLayout(self._outer)
        om = OUTER_MARGIN
        self._outer_lay.setContentsMargins(om, om, om, om)
        self._outer_lay.setSpacing(GAP)
        self._scroll.setWidget(self._outer)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._scroll)

        self._tiles: dict[str, _JustTile] = {}
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._vp_resize_debounce = QTimer(self)
        self._vp_resize_debounce.setSingleShot(True)
        self._vp_resize_debounce.timeout.connect(self._build)
        self._scroll.viewport().installEventFilter(self)

    def eventFilter(self, obj, ev) -> bool:
        """Rebuild after viewport size stabilizes (scrollbar / splitter / HiDPI)."""
        if obj is self._scroll.viewport() and ev.type() == QEvent.Type.Resize:
            self._vp_resize_debounce.start(75)
        return super().eventFilter(obj, ev)

    def _row_outer_width(self) -> int:
        vp = self._scroll.viewport().width()
        return max(40, vp - 2 * OUTER_MARGIN - RIGHT_EDGE_SLOP_PX)

    def _row_pack_width(self) -> int:
        return max(20, self._row_outer_width() - 2 * SELECTION_SIDE_INSET)

    def _clamp_outer_width(self) -> None:
        w = max(0, self._scroll.viewport().width())
        self._outer.setMaximumWidth(w)

    def _row_natural_span(self, target_h: int, grp: list[tuple[str, int, int]]) -> float:
        g = sum(target_h * _aspect(iw, ih) for _, iw, ih in grp)
        if len(grp) > 1:
            g += (len(grp) - 1) * GAP
        return g

    def apply_thumbnail(self, path: str, payload: object) -> None:
        pm = thumbnail_payload_to_pixmap(payload)
        if pm is None:
            return
        self._pixmaps[path] = pm
        t = self._tiles.get(path)
        if t:
            t.set_pixmap(pm)

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
        tile = self._tiles.get(self._selected_path or "")
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

    def _on_click(self, path: str) -> None:
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

    def _clear_rows(self) -> None:
        while self._outer_lay.count():
            item = self._outer_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._tiles.clear()

    def _build(self) -> None:
        self._clear_rows()
        if not self._paths:
            return

        self._clamp_outer_width()
        R_outer = self._row_outer_width()
        R_pack = self._row_pack_width()

        dims_map = image_cache.probe_batch(self._paths)
        meta = [(p, *dims_map.get(p, (1, 1))) for p in self._paths]

        target_h = max(48, self._thumbnail_size)
        rows: list[list[tuple[str, int, int]]] = []
        cur_row: list[tuple[str, int, int]] = []

        for entry in meta:
            if not cur_row:
                cur_row.append(entry)
                continue

            trial = cur_row + [entry]
            if self._row_natural_span(target_h, trial) <= R_pack:
                cur_row = trial
            else:
                rows.append(cur_row)
                cur_row = [entry]

        if cur_row:
            rows.append(cur_row)

        for grp in rows:
            _, widths_and_h = _pack_row(R_pack, GAP, grp)
            rw = QWidget()
            rw.setFixedWidth(R_outer)
            hl = QHBoxLayout(rw)
            hl.setContentsMargins(SELECTION_SIDE_INSET, 0, SELECTION_SIDE_INSET, 0)
            hl.setSpacing(GAP)

            for (path_, w_px, h_px), src in zip(widths_and_h, grp):
                path_, iw, ih = src
                tile = _JustTile(path_, w_px, h_px, self._show_filenames, iw, ih)
                tile.clicked.connect(self._on_click)
                tile.double_clicked.connect(self._on_tile_double_click)
                tile.context_menu_requested.connect(self._on_tile_context_menu)
                if path_ in self._selected_paths:
                    tile.set_selected(True)
                self._tiles[path_] = tile
                cached = self._pixmaps.get(path_)
                if cached is not None and not cached.isNull():
                    tile.set_pixmap(cached)
                hl.addWidget(tile)

            self._outer_lay.addWidget(rw)

        self._outer_lay.addStretch(1)
        QTimer.singleShot(0, self._request_visible_first)

    def _request_visible_first(self) -> None:
        viewport = self._scroll.viewport()
        vp_rect = viewport.rect()
        visible: list[str] = []
        for path, tile in self._tiles.items():
            if tile.parentWidget() is None:
                continue
            tile_in_vp = viewport.mapFromGlobal(tile.mapToGlobal(QPoint(0, 0)))
            if vp_rect.intersects(QRect(tile_in_vp, tile.size())):
                visible.append(path)

        self.setUpdatesEnabled(False)
        try:
            for p in visible:
                tile = self._tiles.get(p)
                if tile:
                    self._thumb_cache.request(p, tile.thumb_dim())
        finally:
            self.setUpdatesEnabled(True)
            self.update()

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
        elif key == Qt.Key.Key_End and self._paths:
            mods = event.modifiers()
            self._apply_pick_path(self._paths[-1], bool(mods & Qt.KeyboardModifier.ControlModifier),
                                   bool(mods & Qt.KeyboardModifier.ShiftModifier), True)
            self.setFocus()
            self._scroll_selected_into_view()
        elif key == Qt.Key.Key_Home and self._paths:
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

    def selected_path(self) -> str | None:
        return self._selected_path

    def selected_paths(self) -> list[str]:
        return list(self._selected_paths)

    def set_paths(self, paths: list[str]) -> None:
        if paths == self._paths:
            return
        self._paths = list(paths)
        self._selected_paths &= set(paths)
        self._build()

    def set_thumbnail_size(self, size: int, *, reflow: bool = True) -> None:
        super().set_thumbnail_size(size, reflow=reflow)
        if reflow:
            self._build()

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
