"""SQLite-backed tag storage.

After every assign or remove the full tag list for that image is written into
embedded metadata where supported (JPEG IPTC, WebP EXIF keywords) so tags
can surface in Explorer, Bridge, Lightroom, and similar tools.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
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
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    parent_id INTEGER REFERENCES tags(id) ON DELETE CASCADE
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
            self._ensure_tags_sort_order_column(conn)
            self._ensure_tags_parent_id_column(conn)

    def _ensure_tags_sort_order_column(self, conn: sqlite3.Connection) -> None:
        """Upgrade DBs created before ``sort_order`` existed."""
        cols = [str(r["name"]) for r in conn.execute("PRAGMA table_info(tags)").fetchall()]
        if "sort_order" in cols:
            return
        conn.execute("ALTER TABLE tags ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        rows = conn.execute("SELECT id FROM tags ORDER BY name COLLATE NOCASE").fetchall()
        for i, r in enumerate(rows):
            conn.execute("UPDATE tags SET sort_order = ? WHERE id = ?", (i, int(r["id"])))

    def _ensure_tags_parent_id_column(self, conn: sqlite3.Connection) -> None:
        """Upgrade DBs: hierarchical tags (NULL = top-level / master tag)."""
        cols = [str(r["name"]) for r in conn.execute("PRAGMA table_info(tags)").fetchall()]
        if "parent_id" in cols:
            return
        conn.execute(
            """
            ALTER TABLE tags ADD COLUMN parent_id INTEGER
                REFERENCES tags(id) ON DELETE CASCADE
            """
        )

    def _sync_iptc(self, image_path: str) -> None:
        """Write current tags for *image_path* into embedded metadata when supported."""
        try:
            from app.core.tags_writer import write_tags

            tag_names = [name for _, name in self.get_tags_for_image(image_path)]
            write_tags(image_path, tag_names)
        except Exception:
            pass  # never crash the UI over a metadata write failure

    # ------------------------------------------------------------------
    # Tag library CRUD
    # ------------------------------------------------------------------

    def add_tag(self, name: str, parent_id: int | None = None) -> int:
        name = name.strip()
        if not name:
            raise ValueError("empty tag")
        with self._connect() as conn:
            if parent_id is not None:
                pr = conn.execute("SELECT id FROM tags WHERE id = ?", (parent_id,)).fetchone()
                if not pr:
                    raise ValueError("invalid parent tag")
            cur = conn.execute(
                "INSERT OR IGNORE INTO tags(name, parent_id) VALUES (?, ?)",
                (name, parent_id),
            )
            if cur.rowcount:
                new_id = int(cur.lastrowid)
                if parent_id is None:
                    mx = conn.execute(
                        "SELECT MAX(sort_order) AS m FROM tags WHERE parent_id IS NULL"
                    ).fetchone()["m"]
                else:
                    mx = conn.execute(
                        "SELECT MAX(sort_order) AS m FROM tags WHERE parent_id = ?",
                        (parent_id,),
                    ).fetchone()["m"]
                conn.execute(
                    "UPDATE tags SET sort_order = ? WHERE id = ?",
                    ((mx if mx is not None else -1) + 1, new_id),
                )
                return new_id
            row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
            return int(row["id"]) if row else 0

    def delete_tag(self, tag_id: int) -> None:
        affected: set[str] = set()
        with self._connect() as conn:
            stack = [tag_id]
            subtree: list[int] = []
            while stack:
                tid = stack.pop()
                subtree.append(tid)
                for r in conn.execute("SELECT id FROM tags WHERE parent_id = ?", (tid,)):
                    stack.append(int(r["id"]))
            for tid in subtree:
                rows = conn.execute(
                    "SELECT image_path FROM image_tags WHERE tag_id = ?", (tid,)
                ).fetchall()
                affected.update(str(r["image_path"]) for r in rows)
            conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        for path in affected:
            self._sync_iptc(path)

    def clear_tags_for_image(self, image_path: str) -> None:
        """Remove every tag assignment for *image_path* and refresh embedded metadata."""
        norm = str(Path(image_path).resolve())
        with self._connect() as conn:
            conn.execute("DELETE FROM image_tags WHERE image_path = ?", (norm,))
        self._sync_iptc(norm)

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
        """All tags in tree order (roots first in sort_order, then each subtree DFS)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, parent_id, sort_order
                FROM tags
                """
            ).fetchall()
        by_parent: dict[int | None, list[sqlite3.Row]] = defaultdict(list)
        for r in rows:
            pid = r["parent_id"]
            pid_key: int | None = int(pid) if pid is not None else None
            by_parent[pid_key].append(r)
        for lst in by_parent.values():
            lst.sort(key=lambda x: (int(x["sort_order"]), str(x["name"]).casefold()))

        out: list[tuple[int, str]] = []

        def walk(parent_key: int | None) -> None:
            for r in by_parent.get(parent_key, []):
                tid = int(r["id"])
                out.append((tid, str(r["name"])))
                walk(tid)

        walk(None)
        return out

    def subtree_tag_count_including_root(self, tag_id: int) -> int:
        """How many tag rows (this tag + descendants) a delete would remove."""
        with self._connect() as conn:
            stack = [tag_id]
            c = 0
            while stack:
                t = stack.pop()
                c += 1
                for r in conn.execute("SELECT id FROM tags WHERE parent_id = ?", (t,)):
                    stack.append(int(r["id"]))
        return c

    def get_tag_tree_rows(self) -> list[tuple[int, str, int | None, int]]:
        """(id, name, parent_id, sort_order) for building the tag tree UI."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, parent_id, sort_order FROM tags"
            ).fetchall()
        out: list[tuple[int, str, int | None, int]] = []
        for r in rows:
            pid = r["parent_id"]
            out.append(
                (
                    int(r["id"]),
                    str(r["name"]),
                    int(pid) if pid is not None else None,
                    int(r["sort_order"]),
                )
            )
        return out

    def set_tag_order(self, ordered_ids: list[int]) -> None:
        """Persist tag list order: ``ordered_ids[i]`` gets ``sort_order = i``."""
        with self._connect() as conn:
            for idx, tid in enumerate(ordered_ids):
                conn.execute(
                    "UPDATE tags SET sort_order = ? WHERE id = ?",
                    (idx, tid),
                )

    def apply_tag_tree_layout(self, layout: list[tuple[int, int | None, int]]) -> None:
        """Set ``parent_id`` and sibling ``sort_order`` from the tree widget (drag-drop)."""
        with self._connect() as conn:
            for tid, parent_id, sort_order in layout:
                conn.execute(
                    "UPDATE tags SET parent_id = ?, sort_order = ? WHERE id = ?",
                    (parent_id, sort_order, tid),
                )

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

    def import_embedded_tags_from_files(
        self, path_tag_pairs: list[tuple[str, list[str]]]
    ) -> bool:
        """Merge keywords read from files into SQLite (single transaction, no IPTC rewrite)."""
        if not path_tag_pairs:
            return False
        changed = False
        with self._connect() as conn:
            name_to_id: dict[str, int] = {
                str(row["name"]).casefold(): int(row["id"])
                for row in conn.execute("SELECT id, name FROM tags")
            }

            def ensure_tag(name: str) -> int:
                nonlocal changed
                key = name.casefold()
                tid = name_to_id.get(key)
                if tid is not None:
                    return tid
                cur = conn.execute(
                    "INSERT OR IGNORE INTO tags(name, parent_id) VALUES (?, NULL)",
                    (name,),
                )
                if cur.rowcount:
                    tid = int(cur.lastrowid)
                    mx = conn.execute(
                        "SELECT MAX(sort_order) AS m FROM tags WHERE parent_id IS NULL"
                    ).fetchone()["m"]
                    conn.execute(
                        "UPDATE tags SET sort_order = ? WHERE id = ?",
                        ((mx if mx is not None else -1) + 1, tid),
                    )
                    changed = True
                else:
                    row = conn.execute(
                        "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (name,)
                    ).fetchone()
                    tid = int(row["id"]) if row else 0
                if tid:
                    name_to_id[key] = tid
                return tid

            for path, tag_names in path_tag_pairs:
                norm = str(Path(path).resolve())
                for raw in tag_names:
                    name = raw.strip()
                    if not name:
                        continue
                    tid = ensure_tag(name)
                    if not tid:
                        continue
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO image_tags(image_path, tag_id) VALUES (?, ?)",
                        (norm, tid),
                    )
                    if cur.rowcount:
                        changed = True
        return changed

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
        order_map = {tid: i for i, (tid, _) in enumerate(self.get_all_tags())}
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT t.id, t.name FROM tags t
                JOIN image_tags it ON it.tag_id = t.id
                WHERE it.image_path = ?
                """,
                (norm,),
            ).fetchall()
        pairs = [(int(r["id"]), str(r["name"])) for r in rows]
        pairs.sort(key=lambda x: order_map.get(x[0], 10**9))
        return pairs

    def get_image_paths_with_tag(self, tag_id: int) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT image_path FROM image_tags WHERE tag_id = ?", (tag_id,)
            ).fetchall()
        return {str(r["image_path"]) for r in rows}

    def get_images_matching_any_tags(self, tag_ids: Iterable[int]) -> set[str] | None:
        """Paths that have at least one of the given tag IDs. Empty iterable → None."""
        ids = list(tag_ids)
        if not ids:
            return None
        with self._connect() as conn:
            placeholders = ",".join("?" * len(ids))
            rows = conn.execute(
                f"""
                SELECT DISTINCT image_path FROM image_tags
                WHERE tag_id IN ({placeholders})
                """,
                ids,
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
