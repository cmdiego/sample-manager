"""Repository for tag table.

Per docs/01-data-model.md: tag has display + normalized columns, soft delete via is_hidden.
Case-insensitive uniqueness enforced via name_norm and shorthand_norm columns.
"""

from __future__ import annotations

import sqlite3

from ..db import Db
from ..normalize import norm_text


class TagRepo:
    """CRUD operations for the tag table."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def create(
        self,
        name_display: str,
        *,
        is_category: bool = False,
    ) -> dict:
        """Create a new tag.

        Args:
            name_display: Human-readable tag name.
            is_category: Whether this tag represents a category.

        Returns:
            Dict with full tag row.

        Raises:
            sqlite3.IntegrityError: If name_norm already exists.
        """
        name_normalized = norm_text(name_display)
        self._db.execute(
            "INSERT INTO tag (name_display, name_norm, is_category) VALUES (?, ?, ?)",
            (name_display, name_normalized, int(is_category)),
        )
        self._db.conn.commit()

        row = self._db.fetchone(
            "SELECT * FROM tag WHERE name_norm = ?", (name_normalized,)
        )
        assert row is not None
        return dict(row)

    def get_by_name(self, name: str) -> dict | None:
        """Lookup tag by name (case-insensitive via norm)."""
        row = self._db.fetchone(
            "SELECT * FROM tag WHERE name_norm = ?", (norm_text(name),)
        )
        return dict(row) if row else None

    def get_by_id(self, tag_id: int) -> dict | None:
        """Lookup tag by ID."""
        row = self._db.fetchone("SELECT * FROM tag WHERE id = ?", (tag_id,))
        return dict(row) if row else None

    def get_or_create(self, name_display: str) -> dict:
        """Get existing tag by name_norm or create a new one."""
        existing = self.get_by_name(name_display)
        if existing is not None:
            return existing
        return self.create(name_display)

    def set_shorthand(self, tag_id: int, shorthand_display: str) -> None:
        """Set shorthand for a tag (unique when not null).

        Raises:
            sqlite3.IntegrityError: If shorthand_norm conflicts with another tag.
        """
        shorthand_normalized = norm_text(shorthand_display)
        self._db.execute(
            "UPDATE tag SET shorthand_display = ?, shorthand_norm = ?, "
            "  updated_at = datetime('now') "
            "WHERE id = ?",
            (shorthand_display, shorthand_normalized, tag_id),
        )
        self._db.conn.commit()

    def clear_shorthand(self, tag_id: int) -> None:
        """Remove shorthand from a tag."""
        self._db.execute(
            "UPDATE tag SET shorthand_display = NULL, shorthand_norm = NULL, "
            "  updated_at = datetime('now') "
            "WHERE id = ?",
            (tag_id,),
        )
        self._db.conn.commit()

    def hide(self, tag_id: int) -> None:
        """Soft-delete a tag (is_hidden = 1)."""
        self._db.execute(
            "UPDATE tag SET is_hidden = 1, updated_at = datetime('now') WHERE id = ?",
            (tag_id,),
        )
        self._db.conn.commit()

    def unhide(self, tag_id: int) -> None:
        """Restore a soft-deleted tag (is_hidden = 0)."""
        self._db.execute(
            "UPDATE tag SET is_hidden = 0, updated_at = datetime('now') WHERE id = ?",
            (tag_id,),
        )
        self._db.conn.commit()

    def list(self, *, include_hidden: bool = False) -> list[dict]:
        """List tags, optionally including hidden ones.

        Default: exclude hidden tags (is_hidden = 0 only).
        """
        if include_hidden:
            rows = self._db.fetchall("SELECT * FROM tag ORDER BY name_norm")
        else:
            rows = self._db.fetchall(
                "SELECT * FROM tag WHERE is_hidden = 0 ORDER BY name_norm"
            )
        return [dict(r) for r in rows]
