"""Drag image file(s) out to other applications (file URLs + optional bitmap MIME)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import QDrag, QPixmap
from PySide6.QtWidgets import QWidget


def exec_external_file_drag(
    source: QWidget,
    paths: list[str],
    pixmap: QPixmap | None = None,
) -> Qt.DropAction:
    """Start a copy drag with local file URL(s). Optional pixmap for preview + image/* paste targets."""
    urls: list[QUrl] = []
    for p in paths:
        fp = Path(p)
        if fp.is_file():
            urls.append(QUrl.fromLocalFile(str(fp.resolve())))
    if not urls:
        return Qt.DropAction.IgnoreAction

    mime = QMimeData()
    mime.setUrls(urls)
    if pixmap is not None and not pixmap.isNull():
        mime.setImageData(pixmap.toImage())

    drag = QDrag(source)
    drag.setMimeData(mime)
    if pixmap is not None and not pixmap.isNull():
        edge = max(48, min(128, pixmap.width(), pixmap.height()))
        thumb = pixmap.scaled(
            edge,
            edge,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        drag.setPixmap(thumb)

    return drag.exec(Qt.DropAction.CopyAction)
