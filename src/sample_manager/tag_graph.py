"""Tag graph service for recursive CTE queries on the tag DAG.

Provides descendants_including_self and expand_for_search using the
canonical CTEs from docs/appendix-phase2-ddl-and-ctes.md (Appendix B).
"""

from __future__ import annotations

from .db import Db


# Appendix B.1 — descendants of a tag (including itself)
_DESCENDANTS_SQL = """\
WITH RECURSIVE
  descendants(tag_id) AS (
    SELECT :root_tag_id
    UNION
    SELECT tp.child_tag_id
    FROM tag_parent tp
    JOIN descendants d ON d.tag_id = tp.parent_tag_id
  )
SELECT tag_id FROM descendants
"""


class TagGraphService:
    """Query the tag inheritance DAG using recursive CTEs."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def descendants_including_self(self, root_tag_id: int) -> set[int]:
        """Return the set of tag IDs reachable from root_tag_id (including itself).

        Uses the recursive CTE from Appendix B.1:
        - Anchor: the root tag itself
        - Recursive step: find children via tag_parent edges

        Returns:
            Set of tag IDs including root_tag_id and all its descendants.
        """
        rows = self._db.fetchall(
            _DESCENDANTS_SQL, {"root_tag_id": root_tag_id}
        )
        return {row["tag_id"] for row in rows}

    def expand_for_search(self, tag_ids: list[int] | set[int]) -> set[int]:
        """Expand a collection of tag IDs to include all their descendants.

        Per docs/01-data-model.md: "Searching/filtering for a tag expands to
        include descendants (parent matches descendants only)."

        This is the union of descendants_including_self for each input tag_id.

        Args:
            tag_ids: Collection of tag IDs to expand.

        Returns:
            Set of all tag IDs (inputs + all their descendants).
        """
        if not tag_ids:
            return set()

        result: set[int] = set()
        for tag_id in tag_ids:
            result |= self.descendants_including_self(tag_id)
        return result
