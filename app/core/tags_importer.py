"""Import tags from embedded image metadata into the SQLite tags store.

Called once when a folder is loaded so tags already present in files
(written by Mason, Bridge, Lightroom, etc.) appear in the UI immediately.

Supported in-file sources: JPEG (IPTC keywords), WebP (EXIF XPKeywords).
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.tags_store import TagsStore
from app.core.tags_writer import read_tags


def scan_paths_for_embedded_tags(
    image_paths: list[str],
    should_abort: Callable[[], bool] | None = None,
) -> list[tuple[str, list[str]]]:
    """Read IPTC / EXIF keywords from files (CPU + disk heavy). Safe off the UI thread."""
    out: list[tuple[str, list[str]]] = []
    for path in image_paths:
        if should_abort is not None and should_abort():
            return out
        try:
            tag_names = read_tags(path)
        except Exception:
            continue
        if tag_names:
            out.append((path, list(tag_names)))
    return out


def apply_embedded_tags_to_store(
    store: TagsStore, path_tag_pairs: list[tuple[str, list[str]]]
) -> bool:
    """Apply pre-scanned embedded tags to SQLite (call from the main / store thread)."""
    return store.import_embedded_tags_from_files(path_tag_pairs)


def import_tags_from_folder(image_paths: list[str], store: TagsStore) -> None:
    """Read embedded tags from each supported image and sync them into *store* (blocking)."""
    apply_embedded_tags_to_store(store, scan_paths_for_embedded_tags(image_paths))
