"""Repository for arrangement and arrangement_sample tables."""

from __future__ import annotations

from ..db import Db
from ..normalize import norm_text


class ArrangementRepo:
    """CRUD operations for arrangements."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def create(self, name: str, profile_name: str) -> dict:
        """Create a new arrangement."""
        name_norm = norm_text(name)
        self._db.execute(
            "INSERT INTO arrangement (name, name_norm, profile_name) VALUES (?, ?, ?)",
            (name, name_norm, profile_name),
        )
        self._db.conn.commit()

        row = self._db.fetchone(
            "SELECT id, name, name_norm, profile_name, created_at, updated_at "
            "FROM arrangement WHERE name_norm = ?",
            (name_norm,),
        )
        assert row is not None
        payload = dict(row)
        payload["sample_count"] = 0
        return payload

    def get_by_name(self, name: str) -> dict | None:
        """Fetch arrangement by name (case-insensitive)."""
        row = self._db.fetchone(
            "SELECT a.id, a.name, a.name_norm, a.profile_name, a.created_at, "
            "a.updated_at, COUNT(asl.sample_id) AS sample_count "
            "FROM arrangement a "
            "LEFT JOIN arrangement_sample asl ON asl.arrangement_id = a.id "
            "WHERE a.name_norm = ? "
            "GROUP BY a.id",
            (norm_text(name),),
        )
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        """List all arrangements with sample counts."""
        rows = self._db.fetchall(
            "SELECT a.id, a.name, a.name_norm, a.profile_name, a.created_at, "
            "a.updated_at, COUNT(asl.sample_id) AS sample_count "
            "FROM arrangement a "
            "LEFT JOIN arrangement_sample asl ON asl.arrangement_id = a.id "
            "GROUP BY a.id "
            "ORDER BY a.name_norm"
        )
        return [dict(r) for r in rows]

    def add_samples(self, arrangement_id: int, sample_ids: list[int]) -> int:
        """Attach samples to an arrangement idempotently.

        Returns:
            Number of newly inserted attachments.
        """
        if not sample_ids:
            return 0

        inserted = 0
        for sample_id in sample_ids:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO arrangement_sample (arrangement_id, sample_id) "
                "VALUES (?, ?)",
                (arrangement_id, sample_id),
            )
            inserted += cursor.rowcount
        self._db.conn.commit()
        return inserted

    def remove_samples(self, arrangement_id: int, sample_ids: list[int]) -> int:
        """Detach samples from an arrangement."""
        if not sample_ids:
            return 0

        removed = 0
        for sample_id in sample_ids:
            cursor = self._db.execute(
                "DELETE FROM arrangement_sample "
                "WHERE arrangement_id = ? AND sample_id = ?",
                (arrangement_id, sample_id),
            )
            removed += cursor.rowcount
        self._db.conn.commit()
        return removed

    def list_sample_ids(self, arrangement_id: int) -> list[int]:
        """List sample IDs in an arrangement."""
        rows = self._db.fetchall(
            "SELECT sample_id FROM arrangement_sample "
            "WHERE arrangement_id = ? "
            "ORDER BY sample_id",
            (arrangement_id,),
        )
        return [int(r["sample_id"]) for r in rows]

    def list_samples(self, arrangement_id: int) -> list[dict]:
        """List detailed samples in an arrangement."""
        rows = self._db.fetchall(
            "SELECT s.id, s.filename, s.rel_path, s.ext, s.size_bytes, s.mtime_epoch, "
            "lr.path AS library_root_path "
            "FROM arrangement_sample ars "
            "JOIN sample s ON s.id = ars.sample_id "
            "JOIN library_root lr ON lr.id = s.library_root_id "
            "WHERE ars.arrangement_id = ? "
            "ORDER BY s.id",
            (arrangement_id,),
        )
        return [dict(r) for r in rows]
