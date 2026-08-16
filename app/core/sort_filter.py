"""Sort and filter image path lists."""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path


SortKey = str

# Random sort: path-only BLAKE2b until ``bump_random_sort_seed()`` runs (e.g. user picks Random
# in the UI); then a keyed digest so each new pick can reshuffle.
_random_sort_key: bytes | None = None


def bump_random_sort_seed() -> None:
    """New random ordering for the next ``sort_paths(..., "random", ...)`` (8-byte BLAKE2b key)."""
    global _random_sort_key
    _random_sort_key = secrets.token_bytes(8)


def _modified_mtime(path: str) -> float:
    try:
        return float(os.stat(path).st_mtime)
    except OSError:
        return 0.0


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
    """Pseudo-random key per path; order changes when ``bump_random_sort_seed()`` is called."""
    enc = path.encode("utf-8", errors="surrogateescape")
    if _random_sort_key is None:
        return hashlib.blake2b(enc, digest_size=8).digest()
    return hashlib.blake2b(enc, digest_size=8, key=_random_sort_key).digest()


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
            return _modified_mtime(p)

        rev = not ascending
        return sorted(paths, key=key_fn, reverse=rev)
    if sort_by == "date_created":

        def key_fn(p: str) -> float:
            return _created_mtime(p)

        rev = not ascending
        return sorted(paths, key=key_fn, reverse=rev)
    # Matches the first entry of SortControlBar.SORT_LABELS, which is what the
    # combo falls back to for an unknown key.
    return sort_paths(paths, "date_created", ascending)


def filter_by_search(paths: list[str], query: str) -> list[str]:
    q = query.strip().lower()
    if not q:
        return list(paths)
    return [p for p in paths if q in Path(p).name.lower()]

