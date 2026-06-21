"""Repository for selection_sample buffer table."""

from __future__ import annotations

from ..db import Db


class SelectionRepo:
    """CRUD operations for persistent selection buffer."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def add_samples(self, sample_ids: list[int]) -> int:
        """Add sample IDs to the buffer idempotently."""
        inserted = 0
        for sample_id in sample_ids:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO selection_sample (sample_id) VALUES (?)",
                (sample_id,),
            )
            inserted += cursor.rowcount
        self._db.conn.commit()
        return inserted

    def remove_samples(self, sample_ids: list[int]) -> int:
        """Remove sample IDs from the buffer (ignore IDs not present)."""
        removed = 0
        for sample_id in sample_ids:
            cursor = self._db.execute(
                "DELETE FROM selection_sample WHERE sample_id = ?",
                (sample_id,),
            )
            removed += cursor.rowcount
        self._db.conn.commit()
        return removed

    def clear(self) -> int:
        """Clear the entire selection buffer."""
        cursor = self._db.execute("DELETE FROM selection_sample")
        self._db.conn.commit()
        return cursor.rowcount

    def list_samples(self) -> list[dict]:
        """List selected samples with stable sample columns."""
        rows = self._db.fetchall(
            "SELECT s.id, s.filename, s.rel_path, s.ext, s.size_bytes, s.mtime_epoch "
            "FROM selection_sample ss "
            "JOIN sample s ON s.id = ss.sample_id "
            "ORDER BY ss.created_at, ss.sample_id"
        )
        return [dict(r) for r in rows]

    def count(self) -> int:
        """Return number of selected samples."""
        val = self._db.fetchval("SELECT COUNT(*) FROM selection_sample")
        return val or 0
