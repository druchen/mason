"""Small procedural icons (toolbar, sort, filter) — QPainter line art."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def chevron_down_small_pm() -> QPixmap:
    w, h = 10, 6
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(220, 220, 220))
    pen.setWidthF(1.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawLine(1, 2, 5, 5)
    p.drawLine(5, 5, 9, 2)
    p.end()
    return pm


def sort_direction_arrow_pm(*, up: bool, d: int = 14) -> QPixmap:
    pm = QPixmap(d, d)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(160, 160, 160))
    pen.setWidthF(2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    cx = d / 2.0
    if up:
        p.drawLine(QPointF(cx, d - 2.5), QPointF(cx, 4.0))
        p.drawLine(QPointF(cx - 4.0, 6.0), QPointF(cx, 2.5))
        p.drawLine(QPointF(cx + 4.0, 6.0), QPointF(cx, 2.5))
    else:
        p.drawLine(QPointF(cx, 2.5), QPointF(cx, d - 3.5))
        p.drawLine(QPointF(cx - 4.0, d - 6.0), QPointF(cx, d - 3.5))
        p.drawLine(QPointF(cx + 4.0, d - 6.0), QPointF(cx, d - 3.5))
    p.end()
    return pm


def gear_pm(d: int = 16) -> QPixmap:
    """Simple cog: hub + radial teeth (matches light gray line icons)."""
    pm = QPixmap(d, d)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(160, 160, 160))
    pen.setWidthF(1.75)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    cx, cy = d / 2.0, d / 2.0
    p.translate(cx, cy)
    hub_r = 3.25
    p.drawEllipse(QRectF(-hub_r, -hub_r, 2 * hub_r, 2 * hub_r))
    n = 8
    tooth_len = 3.4
    base_r = hub_r + 0.4
    for i in range(n):
        ang = (i * 2 * math.pi / n) - math.pi / 2
        x0 = base_r * math.cos(ang)
        y0 = base_r * math.sin(ang)
        x1 = (base_r + tooth_len) * math.cos(ang)
        y1 = (base_r + tooth_len) * math.sin(ang)
        p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
    p.end()
    return pm


def gear_icon() -> QIcon:
    return QIcon(gear_pm(16))


def tag_icon_pm(d: int = 16) -> QPixmap:
    """Price tag (Tagging Mode); line art to match sort / gear micro-icons."""
    d = max(12, int(d))
    pm = QPixmap(d, d)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(160, 160, 160))
    pen.setWidthF(max(1.2, d * 0.1))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    margin = d * 0.14
    usable = max(4.0, d - 2.0 * margin)
    # Elongated pentagon: flat left edge, chamfered right forming a point (hole near tip).
    w_tag = usable * 0.72
    h_tag = usable * 0.40
    chamfer = w_tag * 0.38

    cx, cy = d / 2.0, d / 2.0
    p.translate(cx, cy)
    p.rotate(45.0)
    p.translate(-w_tag / 2.0, -h_tag / 2.0)

    outline = QPainterPath()
    outline.moveTo(0.0, 0.0)
    outline.lineTo(w_tag - chamfer, 0.0)
    outline.lineTo(w_tag, h_tag / 2.0)
    outline.lineTo(w_tag - chamfer, h_tag)
    outline.lineTo(0.0, h_tag)
    outline.closeSubpath()
    p.drawPath(outline)

    hole_r = max(0.75, h_tag * 0.17)
    hole_cx = w_tag - chamfer * 0.52
    hole_cy = h_tag / 2.0
    p.drawEllipse(QRectF(hole_cx - hole_r, hole_cy - hole_r, 2.0 * hole_r, 2.0 * hole_r))
    p.end()
    return pm


def tag_icon() -> QIcon:
    """Tagging Mode: 16px + 32px pixmap variants for sharp display on hidpi."""
    ic = QIcon()
    ic.addPixmap(tag_icon_pm(16))
    ic.addPixmap(tag_icon_pm(32))
    return ic


def scan_tags_icon_pm(d: int = 16) -> QPixmap:
    """Viewfinder corners (scan folder for embedded tags)."""
    d = max(12, int(d))
    pm = QPixmap(d, d)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(160, 160, 160))
    pen.setWidthF(max(1.2, d * 0.11))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    inset = d * 0.18
    arm = d * 0.28
    right = d - inset
    bottom = d - inset
    # top-left
    p.drawLine(QPointF(inset, inset + arm), QPointF(inset, inset))
    p.drawLine(QPointF(inset, inset), QPointF(inset + arm, inset))
    # top-right
    p.drawLine(QPointF(right - arm, inset), QPointF(right, inset))
    p.drawLine(QPointF(right, inset), QPointF(right, inset + arm))
    # bottom-left
    p.drawLine(QPointF(inset, bottom - arm), QPointF(inset, bottom))
    p.drawLine(QPointF(inset, bottom), QPointF(inset + arm, bottom))
    # bottom-right
    p.drawLine(QPointF(right - arm, bottom), QPointF(right, bottom))
    p.drawLine(QPointF(right, bottom - arm), QPointF(right, bottom))
    p.end()
    return pm


def scan_tags_icon() -> QIcon:
    ic = QIcon()
    ic.addPixmap(scan_tags_icon_pm(12))
    ic.addPixmap(scan_tags_icon_pm(24))
    return ic


def no_sign_pm(d: int = 14) -> QPixmap:
    """Circle with diagonal (clear / prohibit)."""
    pm = QPixmap(d, d)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(160, 160, 160))
    pen.setWidthF(1.85)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    inset = 2.25
    p.drawEllipse(QRectF(inset, inset, d - 2 * inset, d - 2 * inset))
    margin = 4.0
    p.drawLine(QPointF(margin, d - margin), QPointF(d - margin, margin))
    p.end()
    return pm


# Shared by sort asc, filter clear, toolbar settings (matches sort control).
ICON_TOOLBUTTON_QSS = """
QToolButton {
    background-color: transparent;
    border: none;
    border-radius: 2px;
    padding: 1px;
}
QToolButton:hover { background-color: #222222; }
QToolButton:pressed { background-color: #505050; }
"""

# Tagging Mode toggle (checked = active); extends base icon toolbutton look.
TAGGING_MODE_TOOLBUTTON_QSS = (
    ICON_TOOLBUTTON_QSS
    + """
QToolButton:checked {
    background-color: #505050;
}
QToolButton:checked:hover {
    background-color: #5a5a5a;
}
"""
)
