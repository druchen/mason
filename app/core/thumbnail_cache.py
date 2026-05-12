"""Background thumbnail generation with disk cache (WebP format)."""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

from app.core.settings import app_data_dir


def thumbnail_payload_to_pixmap(obj: object) -> QPixmap | None:
    """Turn ``thumbnail_ready`` payload into a QPixmap. Call from the GUI thread only."""
    if isinstance(obj, QPixmap):
        return None if obj.isNull() else obj
    if isinstance(obj, QImage):
        if obj.isNull():
            return None
        pm = QPixmap.fromImage(obj)
        return None if pm.isNull() else pm
    return None


def _cache_key(path: str, mtime: float, max_dim: int) -> str:
    h = hashlib.sha256()
    h.update(path.encode("utf-8", errors="surrogateescape"))
    h.update(b"\0")
    h.update(str(mtime).encode())
    h.update(b"\0")
    h.update(str(max_dim).encode())
    return h.hexdigest()


def _pil_to_qimage(im: Image.Image) -> QImage:
    """Build a QImage from PIL (safe to call from worker threads)."""
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA") if "A" in im.getbands() else im.convert("RGB")
    if im.mode == "RGB":
        w, h = im.size
        buf = im.tobytes("raw", "RGB")
        qimg = QImage(buf, w, h, 3 * w, QImage.Format.Format_RGB888)
        return qimg.copy()
    w, h = im.size
    buf = im.tobytes("raw", "RGBA")
    qimg = QImage(buf, w, h, 4 * w, QImage.Format.Format_RGBA8888)
    return qimg.copy()


class _ThumbWorker(QRunnable):
    def __init__(
        self,
        path: str,
        max_dim: int,
        cache_dir: Path,
        owner: "ThumbnailCache",
    ) -> None:
        super().__init__()
        self._path = path
        self._max_dim = max_dim
        self._cache_dir = cache_dir
        self._owner = owner

    def run(self) -> None:
        path = self._path
        max_dim = self._max_dim
        try:
            st = os.stat(path)
            mtime = st.st_mtime
        except OSError:
            self._owner._emit_failed(path)
            return

        key = _cache_key(path, mtime, max_dim)
        cache_file = self._cache_dir / f"{key}.webp"
        qimg: QImage | None = None

        # Try loading from WebP cache
        if cache_file.is_file():
            try:
                with Image.open(cache_file) as cached:
                    cached.load()
                    qimg = _pil_to_qimage(cached)
            except Exception:
                qimg = None

        # Generate thumbnail from source image
        if qimg is None or qimg.isNull():
            try:
                with Image.open(path) as im:
                    im = im.copy()
                    # Store dimensions into the cache while we have the image open.
                    try:
                        from app.core.image_cache import store_dims
                        store_dims(path, mtime, im.width, im.height)
                    except Exception:
                        pass
                    im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                    if im.mode not in ("RGB", "RGBA"):
                        im = im.convert("RGBA") if "A" in im.getbands() else im.convert("RGB")
                    qimg = _pil_to_qimage(im)
                    # Save as WebP (better compression than JPEG, lossless option)
                    buf = io.BytesIO()
                    im.convert("RGB").save(buf, format="WEBP", quality=85, method=4)
                    self._cache_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        with open(cache_file, "wb") as f:
                            f.write(buf.getvalue())
                    except OSError:
                        pass
            except Exception:
                self._owner._emit_failed(path)
                return

        if qimg is None or qimg.isNull():
            self._owner._emit_failed(path)
            return
        self._owner._emit_ready(path, qimg)


class ThumbnailCache(QObject):
    """Request thumbnails; results delivered asynchronously via signals."""

    thumbnail_ready = Signal(str, object)   # path, QImage (convert on GUI thread)
    thumbnail_failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(4)
        self._cache_dir = app_data_dir() / "thumbnails"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._pending: set[str] = set()

    def _emit_ready(self, path: str, image: QImage) -> None:
        self._pending.discard(path)
        try:
            self.thumbnail_ready.emit(path, image)
        except RuntimeError:
            pass

    def _emit_failed(self, path: str) -> None:
        self._pending.discard(path)
        try:
            self.thumbnail_failed.emit(path)
        except RuntimeError:
            pass

    @Slot(str, int)
    def request(self, path: str, max_dim: int) -> None:
        """Queue thumbnail generation. Emits thumbnail_ready when done."""
        if path in self._pending:
            return
        self._pending.add(path)
        self._pool.start(_ThumbWorker(path, max_dim, self._cache_dir, self))

    def clear_pending(self) -> None:
        self._pending.clear()
