"""Repository for sample_tag join table.

Per docs/01-data-model.md: many-to-many between sample and tag.
Primary key is (sample_id, tag_id). Attach is idempotent via INSERT OR IGNORE.
"""

from __future__ import annotations

from ..db import Db


class SampleTagRepo:
    """CRUD operations for the sample_tag join table."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def attach(self, sample_id: int, tag_id: int) -> None:
        """Tag a sample. Idempotent (INSERT OR IGNORE on PK)."""
        self._db.execute(
            "INSERT OR IGNORE INTO sample_tag (sample_id, tag_id) VALUES (?, ?)",
            (sample_id, tag_id),
        )
        self._db.conn.commit()

    def detach(self, sample_id: int, tag_id: int) -> None:
        """Remove a tag from a sample."""
        self._db.execute(
            "DELETE FROM sample_tag WHERE sample_id = ? AND tag_id = ?",
            (sample_id, tag_id),
        )
        self._db.conn.commit()

    def list_tags_for_sample(self, sample_id: int) -> list[dict]:
        """List all tags attached to a sample."""
        rows = self._db.fetchall(
            "SELECT t.* FROM tag t "
            "JOIN sample_tag st ON st.tag_id = t.id "
            "WHERE st.sample_id = ? "
            "ORDER BY t.name_norm",
            (sample_id,),
        )
        return [dict(r) for r in rows]

    def list_samples_for_tag(self, tag_id: int) -> list[dict]:
        """List all samples tagged with a given tag."""
        rows = self._db.fetchall(
            "SELECT s.* FROM sample s "
            "JOIN sample_tag st ON st.sample_id = s.id "
            "WHERE st.tag_id = ? "
            "ORDER BY s.rel_path_norm",
            (tag_id,),
        )
        return [dict(r) for r in rows]
