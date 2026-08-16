"""Small procedural icons (toolbar, sort, filter) — QPainter line art."""

from __future__ import annotations

import re

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


# Material Design "settings" cog, 24x24 grid. Two subpaths: the cog body and
# the centre circle, which the odd-even fill rule turns into a hole.
_GEAR_PATH = (
    "M19.43 12.98c.04-.32.07-.64.07-.98s-.03-.66-.07-.98l2.11-1.65c.19-.15.24-.42.12-.64"
    "l-2-3.46c-.12-.22-.39-.3-.61-.22l-2.49 1c-.52-.4-1.08-.73-1.69-.98l-.38-2.65"
    "C14.46 2.18 14.25 2 14 2h-4c-.25 0-.46.18-.49.42l-.38 2.65c-.61.25-1.17.59-1.69.98"
    "l-2.49-1c-.23-.09-.49 0-.61.22l-2 3.46c-.13.22-.07.49.12.64l2.11 1.65"
    "c-.04.32-.07.65-.07.98s.03.66.07.98l-2.11 1.65c-.19.15-.24.42-.12.64l2 3.46"
    "c.12.22.39.3.61.22l2.49-1c.52.4 1.08.73 1.69.98l.38 2.65c.03.24.24.42.49.42h4"
    "c.25 0 .46-.18.49-.42l.38-2.65c.61-.25 1.17-.59 1.69-.98l2.49 1c.23.09.49 0 .61-.22"
    "l2-3.46c.12-.22.07-.49-.12-.64l-2.11-1.65z"
    "M12 15.5c-1.93 0-3.5-1.57-3.5-3.5s1.57-3.5 3.5-3.5 3.5 1.57 3.5 3.5-1.57 3.5-3.5 3.5z"
)

_SVG_TOKEN = re.compile(r"([MmLlHhVvCcSsZz])|([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)")
_SVG_ARGC = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Z": 0}


def svg_path(d: str, size: float, viewbox: float = 24.0) -> QPainterPath:
    """Parse an SVG path's ``d`` attribute into a QPainterPath scaled to *size*.

    Covers the subset these icons use — M/L/H/V/C/S/Z, absolute and relative —
    so pasted glyphs render exactly without pulling QtSvg into the bundle.
    """
    k = size / viewbox
    path = QPainterPath()
    toks: list[str | float] = []
    for m in _SVG_TOKEN.finditer(d):
        toks.append(m.group(1) if m.group(1) else float(m.group(2)))

    cmd: str | None = None
    x = y = 0.0  # current point, in viewbox units
    start_x = start_y = 0.0
    ctrl_x = ctrl_y = None  # previous cubic's second control point, for S
    i = 0
    while i < len(toks):
        tok = toks[i]
        if isinstance(tok, str):
            i += 1
            if tok in "Zz":
                path.closeSubpath()
                x, y = start_x, start_y
                ctrl_x = ctrl_y = None
                cmd = None
            else:
                cmd = tok
            continue
        if cmd is None:
            i += 1
            continue
        n = _SVG_ARGC[cmd.upper()]
        a = [float(v) for v in toks[i : i + n]]  # type: ignore[arg-type]
        i += n
        rel = cmd.islower()
        op = cmd.upper()
        if op == "M":
            x, y = (x + a[0], y + a[1]) if rel else (a[0], a[1])
            path.moveTo(x * k, y * k)
            start_x, start_y = x, y
            ctrl_x = ctrl_y = None
            cmd = "l" if rel else "L"  # extra pairs after a moveto are linetos
        elif op == "L":
            x, y = (x + a[0], y + a[1]) if rel else (a[0], a[1])
            path.lineTo(x * k, y * k)
            ctrl_x = ctrl_y = None
        elif op == "H":
            x = x + a[0] if rel else a[0]
            path.lineTo(x * k, y * k)
            ctrl_x = ctrl_y = None
        elif op == "V":
            y = y + a[0] if rel else a[0]
            path.lineTo(x * k, y * k)
            ctrl_x = ctrl_y = None
        elif op == "C":
            x1, y1, x2, y2, nx, ny = a
            if rel:
                x1, y1, x2, y2, nx, ny = x + x1, y + y1, x + x2, y + y2, x + nx, y + ny
            path.cubicTo(x1 * k, y1 * k, x2 * k, y2 * k, nx * k, ny * k)
            ctrl_x, ctrl_y = x2, y2
            x, y = nx, ny
        elif op == "S":
            x2, y2, nx, ny = a
            if rel:
                x2, y2, nx, ny = x + x2, y + y2, x + nx, y + ny
            if ctrl_x is None or ctrl_y is None:
                x1, y1 = x, y
            else:
                x1, y1 = 2 * x - ctrl_x, 2 * y - ctrl_y
            path.cubicTo(x1 * k, y1 * k, x2 * k, y2 * k, nx * k, ny * k)
            ctrl_x, ctrl_y = x2, y2
            x, y = nx, ny
    return path


def gear_pm(d: int = 18, color: str = "#e0e0e0") -> QPixmap:
    """Material "settings" cog, filled."""
    pm = QPixmap(d, d)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(svg_path(_GEAR_PATH, float(d)))
    p.end()
    return pm


def gear_icon(d: int = 18) -> QIcon:
    return QIcon(gear_pm(d))






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


def left_panel_pm(d: int = 18, color: str = "#e0e0e0") -> QPixmap:
    """"Open panel, left": a rounded frame whose left column is filled solid.

    Drawn as an outer rounded rect minus an inner rectangle, which is exactly
    how the source glyph is built — the remainder is the border plus the solid
    left column.
    """
    pm = QPixmap(d, d)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    k = d / 32.0  # the glyph is authored on a 32x32 grid

    outer = QPainterPath()
    outer.addRoundedRect(2 * k, 4 * k, 28 * k, 24 * k, 2 * k, 2 * k)
    hole = QPainterPath()
    hole.addRect(12 * k, 6 * k, 16 * k, 20 * k)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(outer.subtracted(hole))
    p.end()
    return pm


def left_panel_icon(d: int = 18) -> QIcon:
    return QIcon(left_panel_pm(d))
