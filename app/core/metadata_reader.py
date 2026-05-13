"""Read image metadata using Pillow (and optional EXIF)."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image
from PIL.ExifTags import TAGS


def _exif_to_dict(exif: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if exif is None:
        return out
    for tag_id, value in exif.items():
        tag = TAGS.get(tag_id, tag_id)
        try:
            if isinstance(value, bytes):
                s = f"<{len(value)} bytes>"
            else:
                s = str(value)
            out[str(tag)] = s
        except Exception:
            pass
    return out


def _format_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _creation_timestamp(st: os.stat_result) -> float:
    """Best-effort file creation time (OS-dependent)."""
    bt = getattr(st, "st_birthtime", None)
    if bt is not None and bt > 0:
        return float(bt)
    if os.name == "nt":
        return float(st.st_ctime)
    return float(st.st_mtime)


def _format_file_size(n: int) -> str:
    if n < 1024:
        return f"{n} bytes"
    if n < 1024 * 1024:
        kb = n / 1024.0
        if abs(kb - round(kb)) < 0.05:
            return f"{int(round(kb))} KB"
        return f"{kb:.1f} KB"
    mb = n / (1024 * 1024)
    if abs(mb - round(mb)) < 0.05:
        return f"{int(round(mb))} MB"
    return f"{mb:.1f} MB"


def read_metadata_summary(path: str | Path) -> dict[str, str]:
    """Ordered metadata fields for the Metadata panel (no tags — UI adds those)."""
    p = Path(path)
    dash = "—"
    keys = (
        "filename",
        "dimensions",
        "file_size",
        "date_created",
        "date_modified",
        "file_format",
        "color_mode",
    )
    out: dict[str, str] = {k: dash for k in keys}
    if not p.is_file():
        return out
    try:
        st = p.stat()
    except OSError:
        return out
    out["filename"] = p.name
    out["file_size"] = _format_file_size(st.st_size)
    out["date_modified"] = _format_ts(st.st_mtime)
    out["date_created"] = _format_ts(_creation_timestamp(st))
    try:
        with Image.open(p) as img:
            fmt = img.format
            out["file_format"] = str(fmt) if fmt else dash
            out["color_mode"] = str(img.mode)
            w, h = img.size
            out["dimensions"] = f"{w} × {h}"
    except OSError:
        pass
    return out


def read_metadata(path: str | Path) -> dict[str, str]:
    """Return human-readable metadata key/value pairs for display (legacy / extended)."""
    p = Path(path)
    result: dict[str, str] = {}
    summary = read_metadata_summary(p)
    result["File name"] = summary["filename"]
    result["Path"] = str(p.resolve())
    result["Size"] = summary["file_size"]
    result["Modified"] = summary["date_modified"]
    result["Created"] = summary["date_created"]
    result["Format"] = summary["file_format"]
    result["Mode"] = summary["color_mode"]
    result["Dimensions"] = summary["dimensions"]

    try:
        with Image.open(p) as img:
            try:
                dpi = img.info.get("dpi")
                if dpi and isinstance(dpi, tuple) and len(dpi) >= 2:
                    result["Resolution"] = f"{dpi[0]:.0f} × {dpi[1]:.0f} DPI"
            except Exception:
                pass
            exif = getattr(img, "getexif", lambda: None)()
            if exif:
                ed = _exif_to_dict(exif)
                for key in (
                    "DateTime",
                    "DateTimeOriginal",
                    "Make",
                    "Model",
                    "LensModel",
                    "FNumber",
                    "ExposureTime",
                    "ISOSpeedRatings",
                ):
                    if key in ed:
                        result[key] = ed[key]
                for k, v in sorted(ed.items()):
                    if k not in result and len(result) < 80:
                        result[k] = v
    except OSError as e:
        result["Error"] = str(e)

    return result
