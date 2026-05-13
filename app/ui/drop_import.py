"""Import images dropped onto the preview panel: convert, save to active folder, collision prompts."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QInputDialog, QMessageBox, QWidget

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None  # type: ignore[misc, assignment]

FORMAT_KEYS = ("webp", "jpeg", "png")
PIL_FORMAT = {"webp": "WEBP", "jpeg": "JPEG", "png": "PNG"}
FILE_EXT = {"webp": ".webp", "jpeg": ".jpg", "png": ".png"}

_MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024


def normalize_drop_format(s: str) -> str:
    k = (s or "webp").lower().strip()
    return k if k in FILE_EXT else "webp"


def _mime_has_raw_image_format(mime: QMimeData) -> bool:
    for fmt in mime.formats():
        if not isinstance(fmt, str):
            continue
        low = fmt.lower()
        if not low.startswith("image/") or "delay" in low:
            continue
        data = mime.data(fmt)
        if data is not None and not data.isEmpty():
            return True
    return False


def _local_existing_file_urls(mime: QMimeData) -> list[QUrl]:
    out: list[QUrl] = []
    for u in _all_candidate_urls(mime):
        if u.isLocalFile():
            p = Path(u.toLocalFile())
            if p.is_file():
                out.append(u)
    return out


def _urls_from_text_uri_list(mime: QMimeData) -> list[QUrl]:
    if not mime.hasFormat("text/uri-list"):
        return []
    blob = mime.data("text/uri-list")
    if blob is None or blob.isEmpty():
        return []
    text = bytes(blob).decode("utf-8", errors="ignore").replace("\r\n", "\n").replace("\r", "\n")
    out: list[QUrl] = []
    seen: set[str] = set()
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        u = QUrl(line)
        if not u.isValid():
            continue
        k = u.toString()
        if k in seen:
            continue
        seen.add(k)
        out.append(u)
    return out


def _all_candidate_urls(mime: QMimeData) -> list[QUrl]:
    seen: set[str] = set()
    merged: list[QUrl] = []
    for u in list(mime.urls()) + _urls_from_text_uri_list(mime):
        if not u.isValid():
            continue
        k = u.toString()
        if k in seen:
            continue
        seen.add(k)
        merged.append(u)
    return merged


def mime_has_importable(mime: QMimeData) -> bool:
    if mime.hasImage():
        return True
    if _mime_has_raw_image_format(mime):
        return True
    for url in _all_candidate_urls(mime):
        if not url.isValid():
            continue
        if url.isLocalFile():
            p = Path(url.toLocalFile())
            if p.is_file():
                return True
        if url.scheme() in ("http", "https"):
            return True
    return False


def _internal_same_folder_file_drag(mime: QMimeData, folder: Path) -> bool:
    """True for typical in-app drag-out: only on-disk paths under ``folder`` (optionally with pixmap)."""
    root = folder.resolve()
    le = _local_existing_file_urls(mime)
    if not le:
        return False
    for u in le:
        try:
            Path(u.toLocalFile()).resolve().relative_to(root)
        except ValueError:
            return False
    if mime.hasImage():
        return True
    if _mime_has_raw_image_format(mime):
        return False
    return True


def mime_looks_external_folder_import(mime: QMimeData, folder: Path) -> bool:
    """Accept drag/drop on preview: browsers (often deferred MIME), HTTP(s), files; block in-app export drags."""
    if not folder.is_dir():
        return False
    if _internal_same_folder_file_drag(mime, folder):
        return False

    if mime.hasImage():
        return True
    if _mime_has_raw_image_format(mime):
        return True

    root = folder.resolve()
    for u in _all_candidate_urls(mime):
        if not u.isValid():
            continue
        if u.scheme() in ("http", "https"):
            return True
        if u.isLocalFile():
            p = Path(u.toLocalFile())
            if p.is_file():
                try:
                    p.resolve().relative_to(root)
                except ValueError:
                    return True

    if mime.hasFormat("text/uri-list"):
        blob = mime.data("text/uri-list")
        if blob is not None and not blob.isEmpty():
            return True

    for fmt in mime.formats():
        if not isinstance(fmt, str):
            continue
        low = fmt.lower()
        if "chromium" in low or low == "downloadurl":
            return True
        if fmt in ("text/x-moz-url", "text/x-moz-url-desc"):
            return True

    if mime.hasUrls():
        return True

    return mime_has_importable(mime)


_WIN_FORBIDDEN = set('<>:"/\\|?*')


def _sanitize_stem(stem: str) -> str:
    stem = (stem or "").strip() or "imported"
    out: list[str] = []
    for ch in stem:
        if ord(ch) < 32 or ch in _WIN_FORBIDDEN:
            out.append("_")
        else:
            out.append(ch)
    stem = "".join(out).strip(" .") or "imported"
    if len(stem) > 120:
        stem = stem[:120]
    return stem


def _pil_from_qimage(qimg: QImage) -> "PILImage.Image":
    buf = BytesIO()
    qimg.save(buf, "PNG")
    buf.seek(0)
    im = PILImage.open(buf)
    im.load()
    return im


def _stem_from_http_url(url: QUrl) -> str:
    try:
        path = urlparse(url.toString()).path or ""
        stem = Path(path).stem
        if stem:
            return stem
    except ValueError:
        pass
    return f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _load_http_image(parent: QWidget, url: QUrl) -> tuple[str, "PILImage.Image"] | None:
    if PILImage is None:
        return None
    if url.scheme() not in ("http", "https"):
        return None
    s = url.toString()
    req = Request(
        s,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=45) as resp:
            chunk = resp.read(_MAX_DOWNLOAD_BYTES + 1)
    except HTTPError as e:
        QMessageBox.warning(
            parent, "Import", f"Could not download image (HTTP {e.code}).\n{s[:300]}"
        )
        return None
    except URLError as e:
        reason = e.reason if isinstance(e.reason, str) else str(e.reason)
        QMessageBox.warning(parent, "Import", f"Could not download image.\n{reason}\n{s[:300]}")
        return None
    except OSError as e:
        QMessageBox.warning(parent, "Import", f"Could not download image.\n{e}\n{s[:300]}")
        return None
    if len(chunk) > _MAX_DOWNLOAD_BYTES:
        QMessageBox.warning(parent, "Import", "Downloaded image is too large to import.")
        return None
    try:
        im = PILImage.open(BytesIO(chunk))
        im.load()
    except OSError:
        QMessageBox.warning(
            parent, "Import", f"Downloaded data is not a recognized image.\n{s[:300]}"
        )
        return None
    return (_stem_from_http_url(url), im)


def _load_from_image_mime_formats(mime: QMimeData) -> tuple[str, "PILImage.Image"] | None:
    if PILImage is None:
        return None
    cand = sorted(
        (f for f in mime.formats() if isinstance(f, str) and f.lower().startswith("image/")),
        key=lambda f: (
            0
            if f.lower()
            in (
                "image/png",
                "image/jpeg",
                "image/jpg",
                "image/webp",
                "image/gif",
                "image/bmp",
                "image/pjpeg",
            )
            else 1,
            f.lower(),
        ),
    )
    for fmt in cand:
        if "delay" in fmt.lower():
            continue
        data = mime.data(fmt)
        if data is None or data.isEmpty():
            continue
        try:
            im = PILImage.open(BytesIO(bytes(data)))
            im.load()
            return (f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}", im)
        except OSError:
            continue
    return None


def _prepare_for_save(im: "PILImage.Image", fmt_key: str) -> "PILImage.Image":
    if fmt_key == "jpeg":
        if im.mode in ("RGBA", "LA"):
            bg = PILImage.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            return bg
        if im.mode == "P":
            im = im.convert("RGBA")
            bg = PILImage.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            return bg
        return im.convert("RGB")
    if im.mode == "P":
        im = im.convert("RGBA")
    return im


def _save_pil(im: "PILImage.Image", dest: Path, fmt_key: str) -> None:
    fmt = PIL_FORMAT[fmt_key]
    im = _prepare_for_save(im, fmt_key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if fmt_key == "jpeg":
        im.save(dest, format=fmt, quality=92, optimize=True)
    elif fmt_key == "webp":
        im.save(dest, format=fmt, quality=90, method=6)
    else:
        im.save(dest, format=fmt, optimize=True)


def _pick_destination_path(parent: QWidget, folder: Path, stem: str, ext: str) -> Path | None:
    """Return a non-existing path, or None if user cancels."""
    base = _sanitize_stem(stem)
    target = folder / f"{base}{ext}"
    if not target.exists():
        return target

    while True:
        mb = QMessageBox(parent)
        mb.setIcon(QMessageBox.Icon.Question)
        mb.setWindowTitle("File exists")
        mb.setText(
            f"A file named \"{target.name}\" already exists in this folder.\n\n"
            "Rename to save with a different name, or cancel this import."
        )
        rename = mb.addButton("Rename…", QMessageBox.ButtonRole.AcceptRole)
        cancel = mb.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        mb.setDefaultButton(rename)
        mb.exec()
        if mb.clickedButton() == cancel:
            return None
        name, ok = QInputDialog.getText(
            parent,
            "Rename import",
            "New file name (without extension):",
            text=base + "_copy",
        )
        if not ok:
            return None
        base = _sanitize_stem(name)
        target = folder / f"{base}{ext}"
        if not target.exists():
            return target


def import_from_mime_data(
    parent: QWidget,
    folder: Path,
    fmt_key: str,
    mime: QMimeData,
) -> list[str]:
    """
    Convert dropped images to the chosen format and save under ``folder``.
    Returns list of saved absolute paths (POSIX str).
    """
    if PILImage is None:
        QMessageBox.warning(parent, "Import", "Pillow is required to import images.")
        return []

    fmt_key = normalize_drop_format(fmt_key)
    ext = FILE_EXT[fmt_key]
    if not folder.is_dir():
        QMessageBox.warning(parent, "Import", "The active folder is not available.")
        return []

    if _internal_same_folder_file_drag(mime, folder):
        return []

    jobs: list[tuple[str, "PILImage.Image"]] = []

    for url in _all_candidate_urls(mime):
        if not url.isLocalFile():
            continue
        p = Path(url.toLocalFile())
        if not p.is_file():
            continue
        try:
            im = PILImage.open(p)
            im.load()
            jobs.append((p.stem, im))
        except OSError:
            continue

    raw_pair = _load_from_image_mime_formats(mime)
    if raw_pair:
        jobs.append(raw_pair)
    else:
        http_seen: set[str] = set()
        for url in _all_candidate_urls(mime):
            if not url.isValid() or url.scheme() not in ("http", "https"):
                continue
            key = url.toString()
            if key in http_seen:
                continue
            http_seen.add(key)
            got = _load_http_image(parent, url)
            if got:
                jobs.append(got)

        if mime.hasImage():
            qimg = mime.imageData()
            if isinstance(qimg, QImage) and not qimg.isNull():
                try:
                    jobs.append(
                        (
                            f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                            _pil_from_qimage(qimg),
                        )
                    )
                except OSError:
                    pass

    if not jobs:
        QMessageBox.information(parent, "Import", "No image could be read from the drop.")
        return []

    saved: list[str] = []
    for stem, im in jobs:
        dest = _pick_destination_path(parent, folder, stem, ext)
        if dest is None:
            continue
        try:
            _save_pil(im, dest, fmt_key)
            saved.append(str(dest))
        except OSError as e:
            QMessageBox.warning(parent, "Import failed", str(e))

    return saved
