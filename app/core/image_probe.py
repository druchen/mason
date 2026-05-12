"""Fast image dimension probing for layout algorithms."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def probe_dimensions(path: str | Path) -> tuple[int, int] | None:
    """Return (width, height) without fully decoding the image."""
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None
