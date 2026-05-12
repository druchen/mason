"""Import tags from JPEG IPTC metadata into the SQLite tags store.

Called once when a folder is loaded so tags already present in the image files
(written by Mason, Bridge, Lightroom, etc.) appear in the UI immediately.
"""

from __future__ import annotations

from app.core.tags_store import TagsStore
from app.core.tags_writer import read_tags


def import_tags_from_folder(image_paths: list[str], store: TagsStore) -> None:
    """Read IPTC tags from each JPEG and sync them into *store*."""
    for path in image_paths:
        try:
            tag_names = read_tags(path)
        except Exception:
            continue
        for name in tag_names:
            name = name.strip()
            if not name:
                continue
            try:
                tid = store.add_tag(name)
                store.assign_tag_to_image(path, tid)
            except Exception:
                continue
