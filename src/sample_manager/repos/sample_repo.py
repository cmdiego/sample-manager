"""Repository for sample table.

Per docs/01-data-model.md: Sample identity is (library_root_id, rel_path_norm).
Upsert updates metadata columns (size_bytes, mtime_epoch, filename, ext, updated_at).
"""

from __future__ import annotations

from ..db import Db
from ..normalize import norm_rel_path


class SampleRepo:
    """CRUD operations for the sample table."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def upsert(
        self,
        library_root_id: int,
        rel_path: str,
        filename: str,
        ext: str | None = None,
        size_bytes: int | None = None,
        mtime_epoch: int | None = None,
    ) -> dict:
        """Insert or update a sample by (library_root_id, rel_path_norm).

        On conflict, updates: filename, ext, size_bytes, mtime_epoch, updated_at.

        Returns:
            Dict with full sample row.
        """
        rel_path_normalized = norm_rel_path(rel_path)

        self._db.execute(
            "INSERT INTO sample "
            "  (library_root_id, rel_path, rel_path_norm, filename, ext, size_bytes, mtime_epoch) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(library_root_id, rel_path_norm) DO UPDATE SET "
            "  filename = excluded.filename, "
            "  ext = excluded.ext, "
            "  size_bytes = excluded.size_bytes, "
            "  mtime_epoch = excluded.mtime_epoch, "
            "  updated_at = datetime('now')",
            (library_root_id, rel_path, rel_path_normalized, filename, ext, size_bytes, mtime_epoch),
        )
        self._db.conn.commit()

        row = self._db.fetchone(
            "SELECT * FROM sample WHERE library_root_id = ? AND rel_path_norm = ?",
            (library_root_id, rel_path_normalized),
        )
        assert row is not None
        return dict(row)

    def get_by_id(self, sample_id: int) -> dict | None:
        """Fetch a sample by its integer ID."""
        row = self._db.fetchone("SELECT * FROM sample WHERE id = ?", (sample_id,))
        return dict(row) if row else None

    def list_by_root(self, library_root_id: int) -> list[dict]:
        """List all samples belonging to a library root."""
        rows = self._db.fetchall(
            "SELECT * FROM sample WHERE library_root_id = ? ORDER BY rel_path_norm",
            (library_root_id,),
        )
        return [dict(r) for r in rows]

    def search_by_text(
        self, library_root_id: int, query: str, *, limit: int = 500
    ) -> list[dict]:
        """Find indexed samples in one root using every whitespace-separated term.

        Each term may occur anywhere in the filename, relative path, tag name,
        shorthand, or tag alias. ``instr`` treats punctuation literally, so a
        sample name containing underscores or percent signs needs no SQL escaping.
        """
        terms = query.lower().split()
        if not terms:
            return []

        # Correlated tag lookup avoids duplicate sample rows when several tags
        # match. Independent term clauses let ``drum loop`` match across fields.
        term_sql = (
            "(instr(lower(s.filename), ?) > 0 OR instr(s.rel_path_norm, ?) > 0 "
            "OR EXISTS (SELECT 1 FROM sample_tag st "
            "JOIN tag t ON t.id = st.tag_id "
            "LEFT JOIN tag_alias ta ON ta.tag_id = t.id "
            "WHERE st.sample_id = s.id AND t.is_hidden = 0 AND "
            "(instr(t.name_norm, ?) > 0 OR instr(t.shorthand_norm, ?) > 0 "
            "OR instr(ta.alias_norm, ?) > 0)))"
        )
        clauses = " AND ".join(term_sql for _ in terms)
        params: list[str | int] = [library_root_id]
        for term in terms:
            params.extend((term, term, term, term, term))
        # Prefer filename hits to path/tag-only hits, then keep the list stable.
        params.extend((query.lower().strip(), max(1, limit)))
        rows = self._db.fetchall(
            "SELECT s.* FROM sample s WHERE s.library_root_id = ? AND "
            + clauses
            + " ORDER BY CASE WHEN instr(lower(s.filename), ?) > 0 "
            "THEN 0 ELSE 1 END, lower(s.filename), s.rel_path_norm LIMIT ?",
            tuple(params),
        )
        return [dict(row) for row in rows]

    def count_by_root(self, library_root_id: int) -> int:
        """Return the number of samples belonging to a library root."""
        val = self._db.fetchval(
            "SELECT COUNT(*) FROM sample WHERE library_root_id = ?",
            (library_root_id,),
        )
        return val or 0

    def count_all(self) -> int:
        """Return the total number of samples across all roots."""
        val = self._db.fetchval("SELECT COUNT(*) FROM sample")
        return val or 0

    def delete_stale(
        self, library_root_id: int, valid_norms: set[str]
    ) -> int:
        """Delete samples for a root whose rel_path_norm is NOT in *valid_norms*.

        Used during rescan to prune files that no longer exist on disk.

        Returns:
            Number of rows deleted.
        """
        if not valid_norms:
            # Everything is stale — delete all for this root
            cursor = self._db.execute(
                "DELETE FROM sample WHERE library_root_id = ?",
                (library_root_id,),
            )
            self._db.conn.commit()
            return cursor.rowcount

        # Fetch all rel_path_norms for this root, compute stale set in Python
        # (avoids building a huge SQL IN clause)
        rows = self._db.fetchall(
            "SELECT id, rel_path_norm FROM sample WHERE library_root_id = ?",
            (library_root_id,),
        )
        stale_ids = [
            row["id"] for row in rows if row["rel_path_norm"] not in valid_norms
        ]
        if not stale_ids:
            return 0

        # Delete in chunks to stay within SQLite variable limits
        chunk_size = 500
        deleted = 0
        for i in range(0, len(stale_ids), chunk_size):
            chunk = stale_ids[i : i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            cursor = self._db.execute(
                f"DELETE FROM sample WHERE id IN ({placeholders})",
                tuple(chunk),
            )
            deleted += cursor.rowcount
        self._db.conn.commit()
        return deleted
