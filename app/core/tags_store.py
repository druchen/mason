"""SQLite-backed tag storage.

After every assign or remove the full tag list for that image is written into
the image's IPTC metadata (JPEG only) so tags are visible to Bridge/Lightroom.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from app.core.settings import app_data_dir


def _db_path() -> Path:
    d = app_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "tags.db"


class TagsStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or _db_path()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS image_tags (
                    image_path TEXT NOT NULL,
                    tag_id     INTEGER NOT NULL,
                    PRIMARY KEY (image_path, tag_id),
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_it_path ON image_tags(image_path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_it_tag  ON image_tags(tag_id)")

    def _sync_iptc(self, image_path: str) -> None:
        """Write current tags for *image_path* into its IPTC metadata."""
        try:
            from app.core.tags_writer import write_tags
            tag_names = [name for _, name in self.get_tags_for_image(image_path)]
            write_tags(image_path, tag_names)
        except Exception:
            pass  # never crash the UI over a metadata write failure

    # ------------------------------------------------------------------
    # Tag library CRUD
    # ------------------------------------------------------------------

    def add_tag(self, name: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("empty tag")
        with self._connect() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
            if cur.rowcount:
                return int(cur.lastrowid)
            row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
            return int(row["id"]) if row else 0

    def delete_tag(self, tag_id: int) -> None:
        affected = self.get_image_paths_with_tag(tag_id)
        with self._connect() as conn:
            conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        for path in affected:
            self._sync_iptc(path)

    def rename_tag(self, tag_id: int, new_name: str) -> None:
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("empty tag name")
        affected = self.get_image_paths_with_tag(tag_id)
        with self._connect() as conn:
            conn.execute("UPDATE tags SET name = ? WHERE id = ?", (new_name, tag_id))
        for path in affected:
            self._sync_iptc(path)

    def get_all_tags(self) -> list[tuple[int, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name FROM tags ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [(int(r["id"]), str(r["name"])) for r in rows]

    # ------------------------------------------------------------------
    # Image ↔ tag assignments
    # ------------------------------------------------------------------

    def assign_tag_to_image(self, image_path: str, tag_id: int) -> None:
        norm = str(Path(image_path).resolve())
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO image_tags(image_path, tag_id) VALUES (?, ?)",
                (norm, tag_id),
            )
        self._sync_iptc(norm)

    def remove_tag_from_image(self, image_path: str, tag_id: int) -> None:
        norm = str(Path(image_path).resolve())
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM image_tags WHERE image_path = ? AND tag_id = ?",
                (norm, tag_id),
            )
        self._sync_iptc(norm)

    def rename_image_path(self, old_path: str, new_path: str) -> None:
        """Move tag assignments when a file is renamed on disk."""
        old_norm = str(Path(old_path).resolve())
        new_norm = str(Path(new_path).resolve())
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tag_id FROM image_tags WHERE image_path = ?",
                (old_norm,),
            ).fetchall()
            conn.execute("DELETE FROM image_tags WHERE image_path = ?", (old_norm,))
            for row in rows:
                conn.execute(
                    "INSERT OR IGNORE INTO image_tags(image_path, tag_id) VALUES (?, ?)",
                    (new_norm, int(row["tag_id"])),
                )
        self._sync_iptc(new_norm)

    def get_tags_for_image(self, image_path: str) -> list[tuple[int, str]]:
        norm = str(Path(image_path).resolve())
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT t.id, t.name FROM tags t
                JOIN image_tags it ON it.tag_id = t.id
                WHERE it.image_path = ?
                ORDER BY t.name COLLATE NOCASE
                """,
                (norm,),
            ).fetchall()
        return [(int(r["id"]), str(r["name"])) for r in rows]

    def get_image_paths_with_tag(self, tag_id: int) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT image_path FROM image_tags WHERE tag_id = ?", (tag_id,)
            ).fetchall()
        return {str(r["image_path"]) for r in rows}

    def get_images_matching_all_tags(self, tag_ids: Iterable[int]) -> set[str] | None:
        """Paths that have ALL given tag IDs. Empty → None (no filter)."""
        ids = list(tag_ids)
        if not ids:
            return None
        with self._connect() as conn:
            placeholders = ",".join("?" * len(ids))
            rows = conn.execute(
                f"""
                SELECT image_path FROM image_tags
                WHERE tag_id IN ({placeholders})
                GROUP BY image_path
                HAVING COUNT(DISTINCT tag_id) = ?
                """,
                (*ids, len(ids)),
            ).fetchall()
        return {str(r["image_path"]) for r in rows}
