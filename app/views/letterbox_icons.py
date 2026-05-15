"""Shared letterboxed square thumbnails for QListWidget icon views (Essential, Filmstrip strip).

Opaque pad uses ``PREVIEW_SURFACE`` so letterbox bars match the preview panel without
extra compositing cost.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QListWidget

from app.core.thumbnail_cache import ThumbnailCache

PREVIEW_SURFACE = "#2b2b2b"


def fit_pixmap_letterbox_square(pm: QPixmap, side: int, _tile_background: bool) -> QPixmap:
    """Letterbox ``pm`` into ``side``×``side``; pad matches ``PREVIEW_SURFACE``."""
    if pm.isNull() or side <= 0:
        return QPixmap()
    out = QPixmap(side, side)
    out.fill(QColor(PREVIEW_SURFACE))
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


def request_thumbnails_for_visible_list_items(
    list_widget: QListWidget,
    decode_px: int,
    thumb_cache: ThumbnailCache,
) -> None:
    """Queue decodes for list items whose visual rect intersects the viewport."""
    req = max(48, int(decode_px))
    vp = list_widget.viewport()
    vp_rect = vp.rect()
    for i in range(list_widget.count()):
        item = list_widget.item(i)
        if item is None:
            continue
        r = list_widget.visualItemRect(item)
        if not r.isValid() or not vp_rect.intersects(r):
            continue
        p = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(p, str):
            thumb_cache.request(p, req)


def item_paths_intersecting_rect(list_widget: QListWidget, rect: QRect) -> set[str]:
    """Paths for items whose ``visualItemRect`` intersects ``rect`` (viewport coordinates)."""
    out: set[str] = set()
    for i in range(list_widget.count()):
        item = list_widget.item(i)
        if item is None:
            continue
        r = list_widget.visualItemRect(item)
        if not r.isValid() or not rect.intersects(r):
            continue
        p = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(p, str):
            out.add(p)
    return out


def visible_item_paths_with_margin(list_widget: QListWidget, margin_px: int = 256) -> set[str]:
    """Paths near the viewport (strict visible plus ``margin_px`` pad) for pixmap retention."""
    m = max(0, int(margin_px))
    vp = list_widget.viewport()
    return item_paths_intersecting_rect(list_widget, vp.rect().adjusted(-m, -m, m, m))
