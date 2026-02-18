"""Repository for tag_parent table (inheritance DAG edges: child -> parent).

Per docs/01-data-model.md and Appendix B:
- child_tag_id != parent_tag_id (CHECK constraint in DDL)
- Cycles forbidden via recursive CTE check (app-level, within same transaction)
"""

from __future__ import annotations

from ..db import Db


# Cycle-check CTE from docs/appendix-phase2-ddl-and-ctes.md Appendix B.2
# Returns a row if adding edge child->parent would create a cycle.
_CYCLE_CHECK_SQL = """\
WITH RECURSIVE
  descendants(tag_id) AS (
    SELECT :child_tag_id
    UNION
    SELECT tp.child_tag_id
    FROM tag_parent tp
    JOIN descendants d ON d.tag_id = tp.parent_tag_id
  )
SELECT 1
FROM descendants
WHERE tag_id = :parent_tag_id
LIMIT 1
"""


class TagParentRepo:
    """CRUD operations for the tag_parent DAG edge table."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def add_parent(self, child_tag_id: int, parent_tag_id: int) -> None:
        """Add an inheritance edge (child -> parent).

        Validates:
          1. child != parent (also enforced by CHECK constraint)
          2. No cycle would be created (recursive CTE reachability check)

        Both checks + insert run inside a single transaction.

        Raises:
            ValueError: If self-edge or cycle detected.
        """
        if child_tag_id == parent_tag_id:
            raise ValueError(
                f"Self-edge rejected: child_tag_id == parent_tag_id == {child_tag_id}"
            )

        with self._db.transaction():
            # Cycle check: would 'parent' become reachable as a descendant of 'child'?
            row = self._db.fetchone(
                _CYCLE_CHECK_SQL,
                {"child_tag_id": child_tag_id, "parent_tag_id": parent_tag_id},
            )
            if row is not None:
                raise ValueError(
                    f"Cycle detected: adding edge {child_tag_id} -> {parent_tag_id} "
                    f"would create a cycle in the tag DAG"
                )

            self._db.execute(
                "INSERT INTO tag_parent (child_tag_id, parent_tag_id) VALUES (?, ?)",
                (child_tag_id, parent_tag_id),
            )

    def remove(self, child_tag_id: int, parent_tag_id: int) -> None:
        """Remove an inheritance edge."""
        self._db.execute(
            "DELETE FROM tag_parent WHERE child_tag_id = ? AND parent_tag_id = ?",
            (child_tag_id, parent_tag_id),
        )
        self._db.conn.commit()

    def list_parents(self, tag_id: int) -> list[dict]:
        """List all direct parents of a tag."""
        rows = self._db.fetchall(
            "SELECT t.* FROM tag t "
            "JOIN tag_parent tp ON tp.parent_tag_id = t.id "
            "WHERE tp.child_tag_id = ? "
            "ORDER BY t.name_norm",
            (tag_id,),
        )
        return [dict(r) for r in rows]

    def list_children(self, tag_id: int) -> list[dict]:
        """List all direct children of a tag."""
        rows = self._db.fetchall(
            "SELECT t.* FROM tag t "
            "JOIN tag_parent tp ON tp.child_tag_id = t.id "
            "WHERE tp.parent_tag_id = ? "
            "ORDER BY t.name_norm",
            (tag_id,),
        )
        return [dict(r) for r in rows]
