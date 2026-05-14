"""Read and write image tags (keywords) in file metadata.

Strategy
--------
* **JPEG** (``.jpg`` / ``.jpeg``): keywords in APP13 / Photoshop IPTC
  (Record 2 / Dataset 25). Only the metadata segment is replaced — no image
  re-encode. After an atomic replace, **last access**, **last modified**, and
  on **Windows** **creation** time are restored so tagging does not refresh
  Explorer timestamps.
* **WebP** (``.webp``): keywords in EXIF **XPKeywords** (0x9C9E, UTF-16 LE),
  which Windows shows in the file **Tags** field. Pillow re-encodes the WebP
  payload (``lossless`` / ``quality`` are chosen from the opened image when
  possible). **Animated** WebP is skipped (metadata write would drop frames).
* Other formats: Mason stores tags in SQLite only.

Interoperability
----------------
JPEG IPTC keywords match Adobe Bridge, Lightroom, digiKam, and Windows
Explorer for JPEG. WebP uses the same EXIF field Windows uses for “Tags” on
JPEG/TIFF where applicable.
"""

from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

_IPTC_JPEG_EXTS = frozenset({".jpg", ".jpeg"})
_WEBP_EXTS = frozenset({".webp"})

# EXIF tag 0x9C9E — Windows XPKeywords / Explorer “Tags” (UTF-16 LE, ;-separated).
_EXIF_XP_KEYWORDS = 0x9C9E


# ---------------------------------------------------------------------------
# File times (preserve across atomic replace / Pillow re-save)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FileTimes:
    atime: float
    mtime: float
    # Windows file creation time, or macOS st_birthtime when present (restore on Windows only).
    birthtime: float | None


def _capture_file_times(path: Path) -> _FileTimes:
    st = path.stat()
    atime = float(st.st_atime)
    mtime = float(st.st_mtime)
    birth: float | None = None
    if sys.platform == "win32":
        birth = float(st.st_ctime)  # on Windows, st_ctime is creation time
    else:
        bt = getattr(st, "st_birthtime", None)
        if bt is not None and float(bt) > 0:
            birth = float(bt)
    return _FileTimes(atime, mtime, birth)


def _restore_file_times(path: Path, times: _FileTimes) -> None:
    try:
        os.utime(path, (times.atime, times.mtime))
    except OSError:
        pass
    if times.birthtime is not None and sys.platform == "win32":
        _win_set_creation_time(path, times.birthtime)


def _win_set_creation_time(path: Path, creation: float) -> None:
    """Restore Windows *creation* time only (does not change last-write time)."""
    import ctypes
    from ctypes import wintypes

    EPOCH_AS_FILETIME = 116444736000000000  # 100-ns intervals from 1601-01-01 to 1970-01-01
    t = int((creation * 10_000_000) + EPOCH_AS_FILETIME)
    ft = wintypes.FILETIME()
    ft.dwLowDateTime = t & 0xFFFFFFFF
    ft.dwHighDateTime = t >> 32

    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    FILE_SHARE_READ = 1
    FILE_SHARE_WRITE = 2
    FILE_SHARE_DELETE = 4
    FILE_ATTRIBUTE_NORMAL = 0x80

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    CreateFileW = kernel32.CreateFileW
    CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    CreateFileW.restype = wintypes.HANDLE
    kernel32.SetFileTime.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.SetFileTime.restype = wintypes.BOOL

    h = CreateFileW(
        str(path.resolve()),
        GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    invalid = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    hv = int(h) if isinstance(h, int) else int(ctypes.cast(h, ctypes.c_void_p).value or 0)
    if hv == invalid or hv == -1:
        return
    try:
        kernel32.SetFileTime(h, ctypes.byref(ft), None, None)
    finally:
        kernel32.CloseHandle(h)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_tags(image_path: str | Path, tags: list[str]) -> None:
    """Write *tags* into embedded metadata when the format supports it."""
    p = Path(image_path)
    suf = p.suffix.lower()
    try:
        if suf in _IPTC_JPEG_EXTS:
            _write_jpeg_iptc(p, tags)
        elif suf in _WEBP_EXTS:
            _write_webp_xp_keywords(p, tags)
    except Exception:
        pass  # never crash the UI over a metadata write failure


def read_tags(image_path: str | Path) -> list[str]:
    """Return tags from embedded metadata, or ``[]`` if none / unsupported."""
    p = Path(image_path)
    suf = p.suffix.lower()
    try:
        if suf in _IPTC_JPEG_EXTS:
            return _read_jpeg_iptc(p)
        if suf in _WEBP_EXTS:
            return _read_webp_xp_keywords(p)
    except Exception:
        return []
    return []


# ---------------------------------------------------------------------------
# IPTC reading (via Pillow)
# ---------------------------------------------------------------------------


def _read_jpeg_iptc(path: Path) -> list[str]:
    from PIL import Image, IptcImagePlugin  # type: ignore[import-untyped]

    with Image.open(path) as img:
        iptc = IptcImagePlugin.getiptcinfo(img)
    if not iptc:
        return []
    raw = iptc.get((2, 25), [])
    if isinstance(raw, (bytes, str)):
        raw = [raw]
    result: list[str] = []
    for item in raw:
        if isinstance(item, bytes):
            result.append(item.decode("utf-8", errors="replace"))
        elif isinstance(item, str):
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# WebP (EXIF XPKeywords via Pillow)
# ---------------------------------------------------------------------------


def _decode_xp_keywords(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        blob = raw.encode("utf-16le", errors="replace")
    elif isinstance(raw, bytes):
        blob = raw
    else:
        return []
    if not blob:
        return []
    try:
        s = blob.decode("utf-16le").rstrip("\x00")
    except UnicodeDecodeError:
        return []
    parts = [p.strip() for p in s.replace("\x00", ";").split(";") if p.strip()]
    return parts


def _read_webp_xp_keywords(path: Path) -> list[str]:
    from PIL import Image  # type: ignore[import-untyped]

    with Image.open(path) as img:
        exif = img.getexif()
        raw = exif.get(_EXIF_XP_KEYWORDS)
    return _decode_xp_keywords(raw)


def _webp_save_kwargs(im) -> dict:  # type: ignore[no-untyped-def]
    """Pick WebP encoder options that best match the opened image."""
    kw: dict = {}
    icc = im.info.get("icc_profile")
    if icc:
        kw["icc_profile"] = icc
    if im.info.get("lossless"):
        kw["lossless"] = True
    else:
        q = im.info.get("quality")
        kw["quality"] = int(q) if isinstance(q, (int, float)) and q > 0 else 100
        kw["method"] = 6
    return kw


def _write_webp_xp_keywords(path: Path, tags: list[str]) -> None:
    from PIL import Image  # type: ignore[import-untyped]

    ordered = sorted({t.strip() for t in tags if t.strip()})
    times = _capture_file_times(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with Image.open(path) as im:
            if getattr(im, "n_frames", 1) != 1:
                return
            im.load()
            exif = im.getexif()
            if ordered:
                exif[_EXIF_XP_KEYWORDS] = ";".join(ordered).encode("utf-16le")
            elif _EXIF_XP_KEYWORDS in exif:
                del exif[_EXIF_XP_KEYWORDS]

            save_kw = _webp_save_kwargs(im)
            save_kw["format"] = "WEBP"
            if len(exif) > 0:
                save_kw["exif"] = exif.tobytes()
            im.save(tmp, **save_kw)
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        try:
            _restore_file_times(path, times)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# IPTC writing (pure stdlib — no re-encoding of image data)
# ---------------------------------------------------------------------------


def _build_iptc_records(tags: list[str]) -> bytes:
    """Encode tags as IPTC IIM Record 2 / Dataset 25 entries."""
    out = b""
    for tag in sorted({t.strip() for t in tags if t.strip()}):
        encoded = tag.encode("utf-8")
        out += b"\x1c\x02\x19"                      # marker, record 2, dataset 25
        out += struct.pack(">H", len(encoded))
        out += encoded
    return out


def _build_app13(iptc_data: bytes) -> bytes:
    """Wrap IPTC data in a Photoshop 3.0 IRB and return a full APP13 segment."""
    if len(iptc_data) % 2:
        iptc_data += b"\x00"                         # pad to even length

    irb = b"8BIM"
    irb += b"\x04\x04"                              # resource ID: IPTC-NAA
    irb += b"\x00\x00"                              # empty Pascal name
    irb += struct.pack(">I", len(iptc_data))
    irb += iptc_data

    content = b"Photoshop 3.0\x00" + irb
    seg_len = len(content) + 2                       # length field includes itself
    return b"\xff\xed" + struct.pack(">H", seg_len) + content


def _inject_app13(jpeg_bytes: bytes, new_app13: bytes | None) -> bytes:
    """Return a new JPEG byte string with APP13 replaced / removed.

    * Existing APP13 (0xFFED) segments are stripped.
    * *new_app13* is inserted immediately after the first APPn segment
      (e.g. APP0/JFIF or APP1/EXIF), or right after SOI if there are none.
    * Everything after SOS (compressed image data) is copied verbatim.
    """
    if not jpeg_bytes.startswith(b"\xff\xd8"):
        return jpeg_bytes                            # not a JPEG — return as-is

    result = bytearray(b"\xff\xd8")                 # start with SOI
    inject_done = False
    pos = 2

    while pos < len(jpeg_bytes) - 1:
        if jpeg_bytes[pos] != 0xFF:
            result.extend(jpeg_bytes[pos:])          # raw / entropy data
            break

        marker = jpeg_bytes[pos + 1]

        # Two-byte standalone markers (SOI, EOI, restart markers)
        if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7):
            result.extend(jpeg_bytes[pos : pos + 2])
            pos += 2
            continue

        # SOS: compressed image data follows — copy rest unchanged
        if marker == 0xDA:
            if new_app13 and not inject_done:
                result.extend(new_app13)
                inject_done = True
            result.extend(jpeg_bytes[pos:])
            break

        # Segments with length field
        if pos + 4 > len(jpeg_bytes):
            result.extend(jpeg_bytes[pos:])
            break

        seg_len = struct.unpack(">H", jpeg_bytes[pos + 2 : pos + 4])[0]
        end = pos + 2 + seg_len

        if marker == 0xED:
            # Skip existing APP13 — we'll replace it
            pos = end
            continue

        # Copy segment
        result.extend(jpeg_bytes[pos:end])
        pos = end

        # Inject new APP13 after the first APPn segment
        if new_app13 and not inject_done and 0xE0 <= marker <= 0xEF:
            result.extend(new_app13)
            inject_done = True

    # Edge case: no APPn markers at all — insert right after SOI
    if new_app13 and not inject_done:
        raw = bytes(result)
        result = bytearray(raw[:2]) + bytearray(new_app13) + bytearray(raw[2:])

    return bytes(result)


def _write_jpeg_iptc(path: Path, tags: list[str]) -> None:
    """Replace IPTC keywords in a JPEG file without re-encoding image data."""
    times = _capture_file_times(path)
    jpeg_bytes = path.read_bytes()
    iptc_data = _build_iptc_records(tags)
    new_app13 = _build_app13(iptc_data) if iptc_data else None
    new_bytes = _inject_app13(jpeg_bytes, new_app13)

    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_bytes(new_bytes)
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        try:
            _restore_file_times(path, times)
        except Exception:
            pass
