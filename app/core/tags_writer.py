"""Read and write image tags (keywords) directly into JPEG IPTC metadata.

Strategy
--------
* JPEG files (.jpg / .jpeg): tags are written into the APP13 segment as IPTC
  Record 2 / Dataset 25 (Keywords).  No re-encoding of image data occurs —
  only the metadata segment is replaced, so there is zero quality loss.
* All other formats (PNG, WEBP, GIF, TIFF, …): tags are stored in Mason's
  SQLite database only.  Those formats either require full re-save (lossy for
  JPEG-encoded WEBPs) or lack a universally supported keyword field.
* No third-party packages needed — only stdlib ``struct`` and Pillow (already
  a dependency) for reading.

Interoperability
----------------
IPTC Record 2 / Dataset 25 is the field used by Adobe Bridge, Lightroom,
digiKam, Windows Explorer (Details pane) and most photo management tools.
"""

from __future__ import annotations

import struct
from pathlib import Path

_IPTC_JPEG_EXTS = frozenset({".jpg", ".jpeg"})

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_tags(image_path: str | Path, tags: list[str]) -> None:
    """Write *tags* into the IPTC metadata of a JPEG file.

    For non-JPEG formats this is a no-op; tags are stored in SQLite only.
    If *tags* is empty the IPTC segment is removed from the file.
    """
    p = Path(image_path)
    if p.suffix.lower() not in _IPTC_JPEG_EXTS:
        return
    try:
        _write_jpeg_iptc(p, tags)
    except Exception:
        pass  # never crash the UI over a metadata write failure


def read_tags(image_path: str | Path) -> list[str]:
    """Return tags from IPTC metadata, or ``[]`` if none / unsupported format."""
    p = Path(image_path)
    if p.suffix.lower() not in _IPTC_JPEG_EXTS:
        return []
    try:
        return _read_jpeg_iptc(p)
    except Exception:
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
    jpeg_bytes = path.read_bytes()
    iptc_data = _build_iptc_records(tags)
    new_app13 = _build_app13(iptc_data) if iptc_data else None
    new_bytes = _inject_app13(jpeg_bytes, new_app13)

    # Atomic write
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_bytes(new_bytes)
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
