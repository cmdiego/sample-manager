"""Repository for library_root table.

Per docs/01-data-model.md: LibraryRoot has id, path, path_norm (unique), created_at.
"""

from __future__ import annotations

from ..db import Db
from ..normalize import norm_abs_path


class LibraryRootRepo:
    """CRUD operations for the library_root table."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def get_or_create(self, path: str) -> dict:
        """Get existing library root by normalized path, or create a new one.

        Args:
            path: Absolute path to the library root directory.

        Returns:
            Dict with id, path, path_norm, created_at.
        """
        path_normalized = norm_abs_path(path)

        # Try to find existing
        row = self._db.fetchone(
            "SELECT id, path, path_norm, created_at "
            "FROM library_root WHERE path_norm = ?",
            (path_normalized,),
        )
        if row is not None:
            return dict(row)

        # Create new
        self._db.execute(
            "INSERT INTO library_root (path, path_norm) VALUES (?, ?)",
            (str(path), path_normalized),
        )
        self._db.conn.commit()

        row = self._db.fetchone(
            "SELECT id, path, path_norm, created_at "
            "FROM library_root WHERE path_norm = ?",
            (path_normalized,),
        )
        assert row is not None
        return dict(row)

    def get_by_id(self, root_id: int) -> dict | None:
        """Fetch a library root by its integer ID."""
        row = self._db.fetchone(
            "SELECT id, path, path_norm, created_at "
            "FROM library_root WHERE id = ?",
            (root_id,),
        )
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        """Return all library roots."""
        rows = self._db.fetchall(
            "SELECT id, path, path_norm, created_at FROM library_root ORDER BY id"
        )
        return [dict(r) for r in rows]

    def count(self) -> int:
        """Return the total number of library roots."""
        val = self._db.fetchval("SELECT COUNT(*) FROM library_root")
        return val or 0
