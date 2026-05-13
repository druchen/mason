"""Sort and filter image path lists."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from typing import Literal

from app.core.tags_store import TagsStore

SortKey = str
TagMatchMode = Literal["all", "any"]


def _stat_tuple(path: str) -> tuple[float, int]:
    try:
        st = os.stat(path)
        return (st.st_mtime, st.st_size)
    except OSError:
        return (0.0, 0)


def _created_mtime(path: str) -> float:
    """Approximate creation time; OS semantics vary."""
    try:
        st = os.stat(path)
        bt = getattr(st, "st_birthtime", None)
        if bt is not None:
            return float(bt)
        if os.name == "nt":
            return float(st.st_ctime)
        return float(st.st_mtime)
    except OSError:
        return 0.0


def _random_rank(path: str) -> bytes:
    """Stable pseudo-random key per path (same order toggling ascending/descending)."""
    return hashlib.blake2b(path.encode("utf-8", errors="surrogateescape"), digest_size=8).digest()


def sort_paths(paths: list[str], sort_by: SortKey, ascending: bool) -> list[str]:
    """Return a new sorted list."""

    if sort_by == "random":

        def key_fn(p: str) -> bytes:
            return _random_rank(p)

        rev = not ascending
        return sorted(paths, key=key_fn, reverse=rev)
    if sort_by == "name":

        def key_fn(p: str) -> str:
            return Path(p).name.lower()

        rev = not ascending
        return sorted(paths, key=key_fn, reverse=rev)
    if sort_by == "date_modified":

        def key_fn(p: str) -> float:
            return _stat_tuple(p)[0]

        rev = not ascending
        return sorted(paths, key=key_fn, reverse=rev)
    if sort_by == "date_created":

        def key_fn(p: str) -> float:
            return _created_mtime(p)

        rev = not ascending
        return sorted(paths, key=key_fn, reverse=rev)
    if sort_by == "size":

        def key_fn(p: str) -> int:
            return _stat_tuple(p)[1]

        rev = not ascending
        return sorted(paths, key=key_fn, reverse=rev)
    if sort_by == "type":

        def key_fn(p: str) -> str:
            return Path(p).suffix.lower()

        rev = not ascending
        return sorted(paths, key=key_fn, reverse=rev)
    return sort_paths(paths, "name", ascending)


def filter_by_search(paths: list[str], query: str) -> list[str]:
    q = query.strip().lower()
    if not q:
        return list(paths)
    return [p for p in paths if q in Path(p).name.lower()]


def filter_by_tags(
    paths: list[str],
    tag_ids: list[int],
    store: TagsStore,
    match_mode: TagMatchMode = "all",
) -> list[str]:
    """Keep paths whose tags match the checked filter (all vs any)."""
    if not tag_ids:
        return list(paths)
    if match_mode == "any":
        matching = store.get_images_matching_any_tags(tag_ids)
    else:
        matching = store.get_images_matching_all_tags(tag_ids)
    if matching is None:
        return list(paths)
    pairs: list[tuple[str, str]] = []
    for p in paths:
        try:
            pairs.append((str(Path(p).resolve()), p))
        except OSError:
            pairs.append((p, p))
    kept = matching & {norm for norm, _ in pairs}
    return [orig for norm, orig in pairs if norm in kept]
