"""Background thumbnail generation with disk cache (WebP format).

Thumbnail tiers (shared across layouts, keyed by path + mtime + tier):

  * **512 px** — requests with longest-side hint ≤ 512 (grids, strip tiles, list icons, …).
  * **1024 px** — requests > 512 and ≤ 1024; one WebP derivative on disk.
  * **Full resolution** — requests > 1024: decode the original file (no WebP disk cache;
    bounded LRU session RAM cache via ``_ready_images``).
"""

from __future__ import annotations

import hashlib
import io
import os
from collections import OrderedDict
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

from app.core.settings import app_data_dir

# Cap decoded QImages kept for instant re-request; evicted tiers reload from WebP on disk.
_MAX_RAM_THUMB_ENTRIES = 512

_THUMB_TIER_SMALL = 512
_THUMB_TIER_LARGE = 1024
_TIER_ORIGINAL = 0  # sentinel: load full image, no downscaled WebP cache


def thumbnail_tier_pixels(requested: int) -> int:
    """Map requested decode hint to 512, 1024, or 0 (full/original)."""
    r = max(48, int(requested))
    if r <= _THUMB_TIER_SMALL:
        return _THUMB_TIER_SMALL
    if r <= _THUMB_TIER_LARGE:
        return _THUMB_TIER_LARGE
    return _TIER_ORIGINAL


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
            self._owner._emit_failed(path, max_dim)
            return

        key = _cache_key(path, mtime, max_dim)

        if max_dim == _TIER_ORIGINAL:
            qimg: QImage | None = None
            try:
                with Image.open(path) as im:
                    im = im.copy()
                    try:
                        from app.core.image_cache import store_dims
                        store_dims(path, mtime, im.width, im.height)
                    except Exception:
                        pass
                    if im.mode not in ("RGB", "RGBA"):
                        im = im.convert("RGBA") if "A" in im.getbands() else im.convert("RGB")
                    qimg = _pil_to_qimage(im)
            except Exception:
                self._owner._emit_failed(path, max_dim)
                return
            if qimg is None or qimg.isNull():
                self._owner._emit_failed(path, max_dim)
                return
            self._owner._emit_ready(path, qimg, key, max_dim)
            return

        cache_file = self._cache_dir / f"{key}.webp"
        qimg = None

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
                self._owner._emit_failed(path, max_dim)
                return

        if qimg is None or qimg.isNull():
            self._owner._emit_failed(path, max_dim)
            return
        self._owner._emit_ready(path, qimg, key, max_dim)


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
        self._pending: set[tuple[str, int]] = set()
        self._ready_images: OrderedDict[str, QImage] = OrderedDict()

    def cache_directory(self) -> Path:
        """Directory where WebP thumbnail cache files are stored."""
        return self._cache_dir

    def _remember_ready_image(self, key: str, image: QImage) -> None:
        """LRU store for decoded thumbnails; oldest entries evicted under memory pressure."""
        od = self._ready_images
        if key in od:
            del od[key]
        od[key] = image
        while len(od) > _MAX_RAM_THUMB_ENTRIES:
            od.popitem(last=False)

    def _emit_ready(self, path: str, image: QImage, key: str | None, tier_dim: int) -> None:
        self._pending.discard((path, tier_dim))
        if key:
            # Bounded hot cache so scrolling huge folders does not retain every decode.
            self._remember_ready_image(key, image)
        try:
            self.thumbnail_ready.emit(path, image)
        except RuntimeError:
            pass

    def _emit_failed(self, path: str, tier_dim: int) -> None:
        self._pending.discard((path, tier_dim))
        try:
            self.thumbnail_failed.emit(path)
        except RuntimeError:
            pass

    @Slot(str, int)
    def request(self, path: str, max_dim: int) -> None:
        """Queue thumbnail generation. Emits thumbnail_ready when done."""
        tier = thumbnail_tier_pixels(max_dim)
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            return
        key = _cache_key(path, mtime, tier)
        ready = self._ready_images.get(key)
        if ready is not None and not ready.isNull():
            self._ready_images.move_to_end(key)
            self._emit_ready(path, ready, key, tier)
            return
        if (path, tier) in self._pending:
            return
        self._pending.add((path, tier))
        self._pool.start(
            _ThumbWorker(
                path,
                tier,
                self._cache_dir,
                self,
            )
        )

    def invalidate_paths(self, paths: set[str]) -> None:
        """Drop in-flight work so the next ``request`` re-reads files from disk."""
        if not paths:
            return
        self._pending = {(p, t) for p, t in self._pending if p not in paths}

    def clear_pending(self) -> None:
        self._pending.clear()

    def purge_disk_and_memory(self) -> None:
        """Delete all WebP files under the thumbnail cache dir and clear in-memory decoded images."""
        self._pending.clear()
        self._ready_images.clear()
        if self._cache_dir.is_dir():
            for f in self._cache_dir.iterdir():
                if f.is_file():
                    try:
                        f.unlink()
                    except OSError:
                        pass
