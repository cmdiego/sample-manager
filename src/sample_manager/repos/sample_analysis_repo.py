"""Repository for the sample_analysis table (v2 milestone 2).

One row per sample. A row is only valid while its ``size_bytes``/``mtime_ns``
match the file on disk and its ``analysis_version`` matches the current
algorithm; callers pass those values and get ``None`` for a stale row.
"""

from __future__ import annotations

from ..db import Db


class SampleAnalysisRepo:
    """Read and write stored peak pyramids and loudness."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def get_valid(
        self, sample_id: int, *, size_bytes: int, mtime_ns: int, analysis_version: int
    ) -> dict | None:
        row = self._db.fetchone(
            "SELECT * FROM sample_analysis "
            "WHERE sample_id = ? AND size_bytes = ? AND mtime_ns = ? AND analysis_version = ?",
            (sample_id, size_bytes, mtime_ns, analysis_version),
        )
        return dict(row) if row is not None else None

    def upsert(self, sample_id: int, values: dict) -> None:
        """Insert or replace the row for *sample_id* and commit."""
        columns = ["sample_id", *values]
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{name} = excluded.{name}" for name in values)
        self._db.execute(
            f"INSERT INTO sample_analysis ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(sample_id) DO UPDATE SET {updates}, analyzed_at = datetime('now')",
            (sample_id, *values.values()),
        )
        self._db.conn.commit()

    def list_candidates(self, library_root_id: int | None, analysis_version: int) -> list[dict]:
        """Samples without a current-version row, cheapest check first.

        Rows of the current version are still re-checked against the file's
        size and mtime by the caller, since the table stores nanosecond mtimes
        that the scanner does not track.
        """
        where = "WHERE s.library_root_id = ?" if library_root_id is not None else ""
        params: tuple = (analysis_version,)
        if library_root_id is not None:
            params = (analysis_version, library_root_id)
        rows = self._db.fetchall(
            "SELECT s.id AS sample_id, lr.path AS root_path, s.rel_path, "
            "       a.size_bytes AS analyzed_size, a.mtime_ns AS analyzed_mtime_ns "
            "FROM sample s "
            "JOIN library_root lr ON lr.id = s.library_root_id "
            "LEFT JOIN sample_analysis a "
            "  ON a.sample_id = s.id AND a.analysis_version = ? "
            f"{where} ORDER BY s.library_root_id, s.rel_path_norm",
            params,
        )
        return [dict(row) for row in rows]
