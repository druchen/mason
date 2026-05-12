"""Persistent image dimension cache.

Avoids the per-image ``Image.open()`` call in every layout reflow by storing
(width, height) keyed on (path, mtime) in a local SQLite database.

Usage
-----
Call ``probe_batch(paths)`` before building a layout; it returns a dict of all
known ``{path: (w, h)}``.  Unknown entries are probed synchronously and saved
so the *next* call is instant.

``store_dims(path, mtime, w, h)`` is called by the thumbnail worker (background
thread) whenever it opens a source image, keeping the cache warm with zero
extra I/O.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Storage path
# ---------------------------------------------------------------------------


def _db_path() -> Path:
    from app.core.settings import app_data_dir
    d = app_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "image_dims.db"


# ---------------------------------------------------------------------------
# Database layer (thread-safe: each call opens its own connection)
# ---------------------------------------------------------------------------


def _init_schema(path: Path) -> None:
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dims (
                path   TEXT    PRIMARY KEY,
                mtime  REAL    NOT NULL,
                width  INTEGER NOT NULL,
                height INTEGER NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dims_path ON dims(path)")
        conn.execute("PRAGMA journal_mode=WAL")


def _db_get_batch(db: Path, paths: list[str]) -> dict[str, tuple[float, int, int]]:
    """Return {path: (mtime, w, h)} for all paths present in DB."""
    if not paths:
        return {}
    placeholders = ",".join("?" * len(paths))
    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            f"SELECT path, mtime, width, height FROM dims WHERE path IN ({placeholders})",
            paths,
        ).fetchall()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def _db_put_batch(db: Path, entries: list[tuple[str, float, int, int]]) -> None:
    """Store (path, mtime, w, h) entries."""
    if not entries:
        return
    with sqlite3.connect(str(db)) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO dims(path, mtime, width, height) VALUES (?,?,?,?)",
            entries,
        )


# ---------------------------------------------------------------------------
# Module-level singleton state (main-thread only for _mem)
# ---------------------------------------------------------------------------

_db: Path | None = None
_mem: dict[str, tuple[float, int, int]] = {}   # {path: (mtime, w, h)}
_lock = threading.Lock()                        # guards _mem for background writes


def _get_db() -> Path:
    global _db
    if _db is None:
        _db = _db_path()
        _init_schema(_db)
    return _db


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def probe_batch(paths: list[str]) -> dict[str, tuple[int, int]]:
    """Return ``{path: (width, height)}`` for all paths.

    * In-memory hits are returned immediately.
    * SQLite is queried once for the remainder.
    * Any still-unknown paths are probed synchronously (first-visit cost).
    Probed results are saved to SQLite so subsequent calls are instant.
    """
    db = _get_db()
    result: dict[str, tuple[int, int]] = {}
    need_sql: list[str] = []

    # 1. In-memory pass
    path_mtimes: dict[str, float] = {}
    for path in paths:
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            continue
        path_mtimes[path] = mtime
        with _lock:
            cached = _mem.get(path)
        if cached and abs(cached[0] - mtime) < 0.001:
            result[path] = (cached[1], cached[2])
        else:
            need_sql.append(path)

    # 2. SQLite batch pass
    need_probe: list[str] = []
    if need_sql:
        db_rows = _db_get_batch(db, need_sql)
        to_mem: list[tuple[str, float, int, int]] = []
        for path in need_sql:
            mtime = path_mtimes.get(path)
            if mtime is None:
                continue
            row = db_rows.get(path)
            if row and abs(row[0] - mtime) < 0.001:
                w, h = row[1], row[2]
                result[path] = (w, h)
                to_mem.append((path, mtime, w, h))
            else:
                need_probe.append(path)
        with _lock:
            for path, mtime, w, h in to_mem:
                _mem[path] = (mtime, w, h)

    # 3. File probe for any remaining cache misses
    if need_probe:
        from app.core.image_probe import probe_dimensions
        new_entries: list[tuple[str, float, int, int]] = []
        for path in need_probe:
            dims = probe_dimensions(path)
            if not dims:
                continue
            w, h = dims
            result[path] = (w, h)
            mtime = path_mtimes.get(path, 0.0)
            with _lock:
                _mem[path] = (mtime, w, h)
            new_entries.append((path, mtime, w, h))
        if new_entries:
            try:
                _db_put_batch(db, new_entries)
            except Exception:
                pass

    return result


def store_dims(path: str, mtime: float, w: int, h: int) -> None:
    """Called by thumbnail workers (background threads) when an image is opened.

    Updates both the in-memory cache and SQLite so future ``probe_batch`` calls
    skip the file probe for this image.
    """
    db = _get_db()
    with _lock:
        _mem[path] = (mtime, w, h)
    try:
        _db_put_batch(db, [(path, mtime, w, h)])
    except Exception:
        pass
