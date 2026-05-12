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


def read_metadata(path: str | Path) -> dict[str, str]:
    """Return human-readable metadata key/value pairs for display."""
    p = Path(path)
    result: dict[str, str] = {}
    st = p.stat()
    result["File name"] = p.name
    result["Path"] = str(p.resolve())
    result["Size"] = f"{st.st_size:,} bytes"
    result["Modified"] = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    try:
        with Image.open(p) as img:
            result["Format"] = img.format or "?"
            result["Mode"] = img.mode
            w, h = img.size
            result["Dimensions"] = f"{w} × {h}"
            try:
                dpi = img.info.get("dpi")
                if dpi and isinstance(dpi, tuple) and len(dpi) >= 2:
                    result["Resolution"] = f"{dpi[0]:.0f} × {dpi[1]:.0f} DPI"
            except Exception:
                pass
            exif = getattr(img, "getexif", lambda: None)()
            if exif:
                ed = _exif_to_dict(exif)
                # Surface common fields first
                for key in ("DateTime", "DateTimeOriginal", "Make", "Model", "LensModel", "FNumber", "ExposureTime", "ISOSpeedRatings"):
                    if key in ed:
                        result[key] = ed[key]
                for k, v in sorted(ed.items()):
                    if k not in result and len(result) < 80:
                        result[k] = v
    except OSError as e:
        result["Error"] = str(e)

    return result
