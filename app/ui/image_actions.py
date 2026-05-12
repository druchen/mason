"""Cross-view helpers: open in Photoshop, Explorer, clipboard copy."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtGui import QClipboard, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None  # type: ignore[misc, assignment]


def launch_photoshop(photoshop_exe: str, image_path: str, parent: QWidget | None = None) -> str | None:
    """Start Photoshop with ``image_path``. Returns error message or None on success."""
    exe = (photoshop_exe or "").strip()
    if not exe or not Path(exe).is_file():
        return "Set the Photoshop executable in Settings (sort bar)."
    path = str(Path(image_path).resolve())
    if not Path(path).is_file():
        return "File does not exist."
    try:
        subprocess.Popen([exe, path], close_fds=True)  # noqa: S603
    except OSError as e:
        return str(e)
    return None


def locate_file_in_explorer(image_path: str) -> str | None:
    """Windows Explorer: open folder and select file. Returns error or None."""
    if os.name != "nt":
        return "Locate in folder is only implemented on Windows."
    p = Path(image_path)
    if not p.is_file():
        return "File does not exist."
    norm = os.path.normpath(str(p.resolve()))
    try:
        subprocess.run(["explorer", "/select,", norm], check=False)  # noqa: S603
    except OSError as e:
        return str(e)
    return None


def copy_image_to_clipboard(image_path: str) -> str | None:
    """Copy raster data to clipboard as image."""
    p = Path(image_path)
    if not p.is_file():
        return "File does not exist."
    pm = QPixmap(str(p))
    if not pm.isNull():
        QApplication.clipboard().setPixmap(pm, QClipboard.Mode.Clipboard)
        return None
    if PILImage is None:
        return "Could not load image for clipboard."
    try:
        with PILImage.open(p) as im:
            im = im.convert("RGBA") if im.mode not in ("RGB", "RGBA") else im
            if im.mode == "RGBA":
                w, h = im.size
                buf = im.tobytes("raw", "RGBA")
                qimg = QImage(buf, w, h, 4 * w, QImage.Format.Format_RGBA8888)
            else:
                w, h = im.size
                buf = im.tobytes("raw", "RGB")
                qimg = QImage(buf, w, h, 3 * w, QImage.Format.Format_RGB888)
            pm2 = QPixmap.fromImage(qimg.copy())
            if pm2.isNull():
                return "Could not convert image for clipboard."
            QApplication.clipboard().setPixmap(pm2, QClipboard.Mode.Clipboard)
    except Exception as e:
        return str(e)
    return None
