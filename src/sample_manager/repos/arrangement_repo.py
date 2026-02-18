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
            "SELECT id, name, name_norm, profile_name, created_at, updated_at "
            "FROM arrangement WHERE name_norm = ?",
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
