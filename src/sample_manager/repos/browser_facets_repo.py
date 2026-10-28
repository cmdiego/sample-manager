"""Root-scoped tag facets and stored audio summaries for terminal browsing."""

from ..db import Db
from ..audio.analysis import ANALYSIS_VERSION


class BrowserFacetsRepo:
    """Keep facet SQL out of widgets; counts include descendant tags."""

    def __init__(self, db: Db):
        self._db = db

    def tags(self, root_id: int, prefix: str = "") -> list[dict]:
        """Count unique samples per visible ancestor without double counting DAGs."""
        return [dict(row) for row in self._db.fetchall(
            "WITH RECURSIVE descendants(parent, child) AS ("
            " SELECT id, id FROM tag WHERE is_hidden = 0 UNION "
            " SELECT d.parent, tp.child_tag_id FROM descendants d "
            " JOIN tag_parent tp ON tp.parent_tag_id = d.child) "
            "SELECT t.name_display, COUNT(DISTINCT s.id) AS samples FROM tag t "
            "JOIN descendants d ON d.parent = t.id "
            "JOIN sample_tag st ON st.tag_id = d.child "
            "JOIN sample s ON s.id = st.sample_id "
            "WHERE s.library_root_id = ? AND t.is_hidden = 0 "
            "AND substr(s.rel_path_norm, 1, ?) = ? "
            "GROUP BY t.id ORDER BY t.name_norm", (root_id, len(prefix), prefix),
        )]

    def summaries(self, root_id: int, prefix: str = "") -> dict[int, dict]:
        """Fetch one root's summaries in one query, not one query per row."""
        return {row["sample_id"]: dict(row) for row in self._db.fetchall(
            # Never fetch peak BLOBs for a table summary: a large library would
            # otherwise materialize gigabytes just to draw duration/LUFS columns.
            "SELECT a.sample_id, a.duration_seconds, a.loudness_lufs "
            "FROM sample_analysis a JOIN sample s ON s.id = a.sample_id "
            "WHERE s.library_root_id = ? AND substr(s.rel_path_norm, 1, ?) = ? "
            "AND a.analysis_version = ? AND a.size_bytes = s.size_bytes "
            "AND CAST(a.mtime_ns / 1000000000 AS INTEGER) = s.mtime_epoch",
            (root_id, len(prefix), prefix, ANALYSIS_VERSION),
        )}
