"""Repository for tag_alias table.

Per docs/01-data-model.md: alias_norm is globally unique (case-insensitive).
Resolve searches tag name_norm -> shorthand_norm -> alias_norm in order.
"""

from __future__ import annotations

from ..db import Db
from ..normalize import norm_text


class TagAliasRepo:
    """CRUD operations for tag_alias + cross-table resolve logic."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def add(self, tag_id: int, alias_display: str) -> dict:
        """Add an alias for a tag.

        Args:
            tag_id: ID of the tag to alias.
            alias_display: Human-readable alias string.

        Returns:
            Dict with full tag_alias row.

        Raises:
            sqlite3.IntegrityError: If alias_norm conflicts globally.
        """
        alias_normalized = norm_text(alias_display)
        self._db.execute(
            "INSERT INTO tag_alias (tag_id, alias_display, alias_norm) VALUES (?, ?, ?)",
            (tag_id, alias_display, alias_normalized),
        )
        self._db.conn.commit()

        row = self._db.fetchone(
            "SELECT * FROM tag_alias WHERE alias_norm = ?", (alias_normalized,)
        )
        assert row is not None
        return dict(row)

    def remove_by_id(self, alias_id: int) -> None:
        """Remove an alias by its ID."""
        self._db.execute("DELETE FROM tag_alias WHERE id = ?", (alias_id,))
        self._db.conn.commit()

    def remove_by_alias(self, alias: str) -> None:
        """Remove an alias by its display/norm text."""
        self._db.execute(
            "DELETE FROM tag_alias WHERE alias_norm = ?", (norm_text(alias),)
        )
        self._db.conn.commit()

    def list_for_tag(self, tag_id: int) -> list[dict]:
        """List all aliases for a given tag."""
        rows = self._db.fetchall(
            "SELECT * FROM tag_alias WHERE tag_id = ? ORDER BY alias_norm",
            (tag_id,),
        )
        return [dict(r) for r in rows]

    def resolve(self, text: str, *, include_hidden: bool = False) -> int | None:
        """Resolve a name/shorthand/alias to a tag_id (case-insensitive).

        Search order:
          1. tag.name_norm
          2. tag.shorthand_norm
          3. tag_alias.alias_norm

        Hidden tags are excluded from resolution unless include_hidden=True.

        Returns:
            tag_id if found, else None.
        """
        normalized = norm_text(text)
        hidden_filter = "" if include_hidden else " AND t.is_hidden = 0"

        # 1. Check tag name
        row = self._db.fetchone(
            f"SELECT t.id FROM tag t WHERE t.name_norm = ?{hidden_filter}",
            (normalized,),
        )
        if row is not None:
            return row["id"]

        # 2. Check tag shorthand
        row = self._db.fetchone(
            f"SELECT t.id FROM tag t WHERE t.shorthand_norm = ?{hidden_filter}",
            (normalized,),
        )
        if row is not None:
            return row["id"]

        # 3. Check alias
        row = self._db.fetchone(
            "SELECT ta.tag_id FROM tag_alias ta "
            f"JOIN tag t ON t.id = ta.tag_id WHERE ta.alias_norm = ?{hidden_filter}",
            (normalized,),
        )
        if row is not None:
            return row["tag_id"]

        return None
