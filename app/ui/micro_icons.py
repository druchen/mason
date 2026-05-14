"""Small procedural icons (toolbar, sort, filter) — QPainter line art."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPainterPath


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
    """Solid price-tag silhouette with a punched hole (Tagging Mode; scales with *d*)."""
    d = max(12, int(d))
    w = float(d)
    pm = QPixmap(d, d)
    pm.fill(Qt.GlobalColor.transparent)

    m = max(1.0, w * 0.11)
    rx = w * 0.21
    ry = m
    rw = w * 0.58
    rh = w * 0.40
    rr = min(w * 0.055, rw * 0.25, rh * 0.35)

    top = QPainterPath()
    top.addRoundedRect(QRectF(rx, ry, rw, rh), rr, rr)

    y_join = ry + rh - m * 0.12
    point = QPainterPath()
    point.moveTo(rx, y_join)
    point.lineTo(rx + rw, y_join)
    point.lineTo(w * 0.5, w - m * 0.32)
    point.closeSubpath()

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.NoPen)
    fill = QColor(228, 228, 228)
    p.fillPath(top, fill)
    p.fillPath(point, fill)

    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
    p.setBrush(QColor(255, 255, 255))
    hr = w * 0.09
    hcx = w * 0.5
    hcy = ry + rh * 0.30
    p.drawEllipse(QRectF(hcx - hr, hcy - hr, 2 * hr, 2 * hr))
    p.end()
    return pm


def tag_icon() -> QIcon:
    """Tagging Mode: 16px + 32px pixmap variants for sharp display on hidpi."""
    ic = QIcon()
    ic.addPixmap(tag_icon_pm(16))
    ic.addPixmap(tag_icon_pm(32))
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
