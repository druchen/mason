"""Scan folders for supported image files."""

from __future__ import annotations

import os
from pathlib import Path

IMAGE_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".webp",
        ".tiff",
        ".tif",
        ".svg",
    }
)


def scan_folder(folder: str | Path, recursive: bool = False) -> list[str]:
    """Return sorted list of absolute paths to image files in `folder`."""
    root = Path(folder).resolve()
    if not root.is_dir():
        return []

    paths: list[str] = []
    if recursive:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                p = Path(dirpath) / name
                if p.suffix.lower() in IMAGE_EXTENSIONS:
                    paths.append(str(p))
    else:
        try:
            for p in root.iterdir():
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
                    paths.append(str(p))
        except OSError:
            return []

    paths.sort(key=lambda s: s.lower())
    return paths


def snapshot_mtimes(paths: list[str]) -> dict[str, float]:
    """Last-known ``st_mtime`` per path (for detecting in-place file edits)."""
    out: dict[str, float] = {}
    for path in paths:
        try:
            out[path] = os.path.getmtime(path)
        except OSError:
            continue
    return out


def paths_with_changed_mtime(paths: list[str], stored: dict[str, float]) -> set[str]:
    """Paths whose modification time differs from *stored* (or are newly seen)."""
    changed: set[str] = set()
    for path in paths:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            if path in stored:
                changed.add(path)
            continue
        if stored.get(path) != mtime:
            changed.add(path)
    return changed
