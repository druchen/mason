"""Scale pixmap to fit inside a box without cropping or stretching."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap


def fit_pixmap_in_box(pm: QPixmap, box_w: int, box_h: int) -> QPixmap:
    """Return pixmap scaled uniformly so the entire image fits in box_w×box_h."""
    if pm.isNull():
        return pm
    box_w = max(1, box_w)
    box_h = max(1, box_h)
    iw, ih = pm.width(), pm.height()
    if iw <= 0 or ih <= 0:
        return pm
    return pm.scaled(
        box_w,
        box_h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def max_thumb_dim_for_aspect(box_w: int, box_h: int, iw: int, ih: int) -> int:
    """Lower bound on thumbnail longest-side so downsampling preserves the fitted display size."""
    if iw <= 0 or ih <= 0:
        return max(box_w, box_h, 64)
    box_w = max(1, box_w)
    box_h = max(1, box_h)
    # width-limited-by-height-at-box_h, height-limited-by-width-at_box_w scalings
    need = max(box_w * ih / iw, iw * box_h / ih, float(box_w), float(box_h))
    return max(64, min(2048, int(math.ceil(max(need, box_w, box_h)))))
