"""Compact list with leading thumbnails.

Multi-select: Ctrl+click (toggle) and Shift+click (range) via ExtendedSelection.
Space: open fullscreen. Delete: delete selected files.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, QEvent, QSize, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QMouseEvent, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QVBoxLayout,
)

from app.core.thumbnail_cache import ThumbnailCache, thumbnail_payload_to_pixmap
from app.views.base_view import BaseImageView
from app.views.file_drag import exec_external_file_drag

# Left inset for each row (stylesheet padding-left; shifts icon + text together).
_LIST_VIEWPORT_LEFT_MARGIN = 12
_LIST_ICON_TEXT_GAP = 14


class _ListRowDelegate(QStyledItemDelegate):
    """Strip inner focus ring / nested text highlight so selection reads as one blue outline."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # type: ignore[override]
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        if opt.state & QStyle.StateFlag.State_Selected:
            opt.palette.setColor(QPalette.ColorRole.Highlight, QColor(90, 180, 245, 51))
            opt.palette.setColor(
                QPalette.ColorRole.HighlightedText,
                opt.palette.color(QPalette.ColorRole.Text),
            )
        super().paint(painter, opt, index)


class ListView(BaseImageView):
    def __init__(self, thumb_cache: ThumbnailCache, parent=None) -> None:
        super().__init__(thumb_cache, parent)
        self._selected_path: str | None = None
        self._path_to_item: dict[str, QListWidgetItem] = {}
        self._pixmaps: dict[str, QPixmap] = {}

        self._list = QListWidget()
        self._list.setViewMode(QListWidget.ViewMode.ListMode)
        self._list.setMovement(QListWidget.Movement.Static)
        self._list.setSpacing(2)
        self._list.setUniformItemSizes(False)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_list_context_menu)
        self._list.itemDoubleClicked.connect(self._on_list_item_double_clicked)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.verticalScrollBar().valueChanged.connect(lambda _: self._request_visible_icons())
        self._list.installEventFilter(self)

        self._list_layout_timer = QTimer(self)
        self._list_layout_timer.setSingleShot(True)
        self._list_layout_timer.timeout.connect(self._sync_list_item_size_hints)

        self._list_drag_press_pos: QPoint | None = None
        self._list_drag_anchor: QListWidgetItem | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._list)
        self._list.setItemDelegate(_ListRowDelegate(self._list))
        self._apply_styles()

    def _list_icon_pixel_size(self) -> int:
        return max(48, min(512, self._thumbnail_size))

    def _fit_pixmap_to_square(self, pm: QPixmap, side: int) -> QPixmap:
        """Letterbox / pillarbox into a fixed square so list icon column width is uniform."""
        if pm.isNull() or side <= 0:
            return QPixmap()
        out = QPixmap(side, side)
        out.fill(QColor("#3c3c3c"))
        scaled = pm.scaled(
            side,
            side,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (side - scaled.width()) // 2
        y = (side - scaled.height()) // 2
        painter = QPainter(out)
        painter.drawPixmap(x, y, scaled)
        painter.end()
        return out

    def _list_icon_pixmap(self, pm: QPixmap) -> QPixmap:
        """Square letterboxed thumb plus trailing gap so the filename sits farther from the image."""
        side = self._list_icon_pixel_size()
        gap = _LIST_ICON_TEXT_GAP
        inner = self._fit_pixmap_to_square(pm, side)
        if gap <= 0:
            return inner
        out = QPixmap(side + gap, side)
        out.fill(QColor("#3c3c3c"))
        p = QPainter(out)
        p.drawPixmap(0, 0, inner)
        p.end()
        return out

    def _list_row_height_px(self) -> int:
        icon_sz = self._list_icon_pixel_size()
        chrome = 12
        chrome += QFontMetrics(self._list.font()).height() + 4
        return icon_sz + chrome

    def _hint_viewport_width(self) -> int:
        vw = self._list.viewport().width()
        if vw < 16:
            vw = max(0, self._list.width() - self._list.verticalScrollBar().sizeHint().width())
        return max(120, vw)

    def _sync_list_item_size_hints(self) -> None:
        if not self._list.count():
            return
        w = self._hint_viewport_width()
        h = self._list_row_height_px()
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it is not None:
                it.setSizeHint(QSize(w, h))
        self._list.doItemsLayout()

    def _schedule_list_layout_sync(self) -> None:
        self._list_layout_timer.start(55)

    def _flush_list_layout_sync(self) -> None:
        self._list_layout_timer.stop()
        self._sync_list_item_size_hints()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._schedule_list_layout_sync()

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
        side = self._list_icon_pixel_size()
        for sz in ic.availableSizes():
            pm = ic.pixmap(sz)
            if not pm.isNull():
                if pm.width() > side:
                    return pm.copy(QRect(0, 0, side, pm.height()))
                return pm
        return None

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
            elif et == QEvent.Type.Resize:
                self._schedule_list_layout_sync()
        return super().eventFilter(obj, event)

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

    def apply_thumbnail(self, path: str, payload: object) -> None:
        pm = thumbnail_payload_to_pixmap(payload)
        if pm is None:
            return
        self._pixmaps[path] = pm
        item = self._path_to_item.get(path)
        if item:
            item.setIcon(QIcon(self._list_icon_pixmap(pm)))

    def _refresh_all_list_icons(self) -> None:
        for path, item in self._path_to_item.items():
            pm = self._pixmaps.get(path)
            if pm is not None and not pm.isNull():
                item.setIcon(QIcon(self._list_icon_pixmap(pm)))

    def _request_visible_icons(self) -> None:
        icon_sz = self._list_icon_pixel_size()
        vp = self._list.viewport()
        vp_rect = vp.rect()
        self.setUpdatesEnabled(False)
        try:
            for i in range(self._list.count()):
                item = self._list.item(i)
                if item is None:
                    continue
                r = self._list.visualItemRect(item)
                if not r.isValid() or not vp_rect.intersects(r):
                    continue
                p = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(p, str):
                    self._thumb_cache.request(p, icon_sz)
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def set_paths(self, paths: list[str]) -> None:
        if paths == self._paths:
            return
        self._paths = list(paths)
        self._path_to_item.clear()
        self._list.clear()
        icon_sz = self._list_icon_pixel_size()
        self._list.setIconSize(QSize(icon_sz + _LIST_ICON_TEXT_GAP, icon_sz))
        for p in paths:
            item = QListWidgetItem(Path(p).name)
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setToolTip(p)
            self._list.addItem(item)
            self._path_to_item[p] = item
            cached = self._pixmaps.get(p)
            if cached is not None and not cached.isNull():
                item.setIcon(QIcon(self._list_icon_pixmap(cached)))
        self._request_visible_icons()
        self._apply_styles()
        QTimer.singleShot(0, self._flush_list_layout_sync)

    def set_thumbnail_size(self, size: int, *, reflow: bool = True) -> None:
        super().set_thumbnail_size(size, reflow=reflow)
        icon_sz = self._list_icon_pixel_size()
        self._list.setIconSize(QSize(icon_sz + _LIST_ICON_TEXT_GAP, icon_sz))
        if reflow:
            self._refresh_all_list_icons()
            self._request_visible_icons()
            self._flush_list_layout_sync()

    def set_tile_background(self, enabled: bool) -> None:
        super().set_tile_background(enabled)
        self._apply_styles()

    def _apply_styles(self) -> None:
        m = int(_LIST_VIEWPORT_LEFT_MARGIN)
        self._list.setStyleSheet(
            f"""
            QListWidget {{ background: transparent; }}
            QListWidget::item {{
                background: #3c3c3c;
                border: 2px solid transparent;
                border-radius: 2px;
                outline: none;
                padding-top: 2px;
                padding-bottom: 2px;
                padding-right: 2px;
                padding-left: {m}px;
            }}
            QListWidget::item:selected {{
                background: rgba(90, 180, 245, 0.2);
                border: 2px solid #5ab4f5;
                outline: none;
            }}
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
