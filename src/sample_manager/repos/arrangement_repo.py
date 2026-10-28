"""Repository for arrangement and arrangement_sample tables."""

from __future__ import annotations

from ..db import Db
from ..normalize import norm_text


class ArrangementRepo:
    """CRUD operations for arrangements."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def create(self, name: str, profile_name: str, *, commit: bool = True) -> dict:
        """Create a new arrangement."""
        name_norm = norm_text(name)
        self._db.execute(
            "INSERT INTO arrangement (name, name_norm, profile_name) VALUES (?, ?, ?)",
            (name, name_norm, profile_name),
        )
        # A workflow may own an outer transaction covering initial membership.
        if commit:
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

    def add_samples(
        self, arrangement_id: int, sample_ids: list[int], folder_id: int | None = None
    ) -> int:
        """Attach samples to an arrangement idempotently. Does not commit.

        Args:
            arrangement_id: Target arrangement
            sample_ids: Sample IDs to add
            folder_id: Optional folder to place samples in

        Returns:
            Number of newly inserted attachments.
        """
        if not sample_ids:
            return 0

        # Get next sort_order
        if folder_id is None:
            max_order = self._db.fetchval(
                "SELECT MAX(sort_order) FROM arrangement_sample "
                "WHERE arrangement_id = ? AND folder_id IS NULL",
                (arrangement_id,),
            )
        else:
            max_order = self._db.fetchval(
                "SELECT MAX(sort_order) FROM arrangement_sample "
                "WHERE arrangement_id = ? AND folder_id = ?",
                (arrangement_id, folder_id),
            )
        sort_order = max_order or 0

        inserted = 0
        for sample_id in sample_ids:
            sort_order += 1
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO arrangement_sample "
                "(arrangement_id, sample_id, folder_id, sort_order) "
                "VALUES (?, ?, ?, ?)",
                (arrangement_id, sample_id, folder_id, sort_order),
            )
            inserted += cursor.rowcount
        return inserted

    def remove_samples(self, arrangement_id: int, sample_ids: list[int]) -> int:
        """Detach samples from an arrangement. Does not commit."""
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

    # -- Virtual folder operations --

    def create_folder(
        self, arrangement_id: int, parent_id: int | None, name: str, name_norm: str
    ) -> dict:
        """Create a new virtual folder.

        Args:
            arrangement_id: Arrangement to add folder to
            parent_id: Parent folder ID (None for root)
            name: Display name
            name_norm: Normalized name for uniqueness

        Returns:
            Folder row dict with id, arrangement_id, parent_id, name, name_norm,
            sort_order, created_at, updated_at

        Note:
            Does not commit. Caller should manage transactions.
        """
        # Get next sort_order
        if parent_id is None:
            max_order = self._db.fetchval(
                "SELECT MAX(sort_order) FROM arrangement_folder "
                "WHERE arrangement_id = ? AND parent_id IS NULL",
                (arrangement_id,),
            )
        else:
            max_order = self._db.fetchval(
                "SELECT MAX(sort_order) FROM arrangement_folder "
                "WHERE arrangement_id = ? AND parent_id = ?",
                (arrangement_id, parent_id),
            )
        sort_order = (max_order or 0) + 1

        self._db.execute(
            "INSERT INTO arrangement_folder "
            "(arrangement_id, parent_id, name, name_norm, sort_order) "
            "VALUES (?, ?, ?, ?, ?)",
            (arrangement_id, parent_id, name, name_norm, sort_order),
        )

        row = self._db.fetchone(
            "SELECT id, arrangement_id, parent_id, name, name_norm, sort_order, "
            "created_at, updated_at FROM arrangement_folder WHERE id = last_insert_rowid()"
        )
        assert row is not None
        return dict(row)

    def get_folder(self, folder_id: int) -> dict | None:
        """Fetch a single folder by ID."""
        row = self._db.fetchone(
            "SELECT id, arrangement_id, parent_id, name, name_norm, sort_order, "
            "created_at, updated_at FROM arrangement_folder WHERE id = ?",
            (folder_id,),
        )
        return dict(row) if row else None

    def list_folders(self, arrangement_id: int) -> list[dict]:
        """List all folders in an arrangement, ordered for tree loading."""
        rows = self._db.fetchall(
            "SELECT id, arrangement_id, parent_id, name, name_norm, sort_order, "
            "created_at, updated_at FROM arrangement_folder "
            "WHERE arrangement_id = ? "
            "ORDER BY parent_id NULLS FIRST, sort_order, name_norm",
            (arrangement_id,),
        )
        return [dict(r) for r in rows]

    def rename_folder(self, folder_id: int, name: str, name_norm: str) -> dict:
        """Rename a folder. Does not commit."""
        self._db.execute(
            "UPDATE arrangement_folder SET name = ?, name_norm = ?, "
            "updated_at = datetime('now') WHERE id = ?",
            (name, name_norm, folder_id),
        )
        row = self._db.fetchone(
            "SELECT id, arrangement_id, parent_id, name, name_norm, sort_order, "
            "created_at, updated_at FROM arrangement_folder WHERE id = ?",
            (folder_id,),
        )
        assert row is not None
        return dict(row)

    def move_folder(self, folder_id: int, new_parent_id: int | None) -> None:
        """Move a folder to a new parent. Does not commit."""
        self._db.execute(
            "UPDATE arrangement_folder SET parent_id = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (new_parent_id, folder_id),
        )

    def remove_folder(self, folder_id: int) -> None:
        """Remove a single folder (CASCADE will remove descendants). Does not commit."""
        self._db.execute("DELETE FROM arrangement_folder WHERE id = ?", (folder_id,))

    def get_folder_descendants(self, folder_id: int) -> list[dict]:
        """Get all descendant folders recursively using CTE."""
        rows = self._db.fetchall(
            """
            WITH RECURSIVE descendants(id) AS (
                SELECT id FROM arrangement_folder WHERE id = ?
                UNION ALL
                SELECT af.id FROM arrangement_folder af
                JOIN descendants d ON af.parent_id = d.id
            )
            SELECT af.id, af.arrangement_id, af.parent_id, af.name, af.name_norm,
                   af.sort_order, af.created_at, af.updated_at
            FROM arrangement_folder af
            JOIN descendants d ON af.id = d.id
            WHERE af.id != ?
            """,
            (folder_id, folder_id),
        )
        return [dict(r) for r in rows]

    def get_folder_sample_count(self, folder_id: int) -> int:
        """Count samples directly in a folder."""
        return self._db.fetchval(
            "SELECT COUNT(*) FROM arrangement_sample WHERE folder_id = ?",
            (folder_id,),
        ) or 0

    def get_folder_tree_sample_count(self, folder_id: int) -> int:
        """Count all samples in a folder and its descendants."""
        count = self._db.fetchval(
            """
            WITH RECURSIVE descendants(id) AS (
                SELECT id FROM arrangement_folder WHERE id = ?
                UNION ALL
                SELECT af.id FROM arrangement_folder af
                JOIN descendants d ON af.parent_id = d.id
            )
            SELECT COUNT(*)
            FROM arrangement_sample ars
            WHERE ars.folder_id IN (SELECT id FROM descendants)
            """,
            (folder_id,),
        )
        return count or 0

    def list_folder_samples(self, folder_id: int | None) -> list[dict]:
        """List samples in a specific folder (or root if folder_id is None)."""
        if folder_id is None:
            rows = self._db.fetchall(
                "SELECT s.id, s.filename, s.rel_path, s.ext, s.size_bytes, s.mtime_epoch, "
                "lr.path AS library_root_path, ars.folder_id, ars.sort_order "
                "FROM arrangement_sample ars "
                "JOIN sample s ON s.id = ars.sample_id "
                "JOIN library_root lr ON lr.id = s.library_root_id "
                "WHERE ars.folder_id IS NULL "
                "ORDER BY ars.sort_order, s.filename",
            )
        else:
            rows = self._db.fetchall(
                "SELECT s.id, s.filename, s.rel_path, s.ext, s.size_bytes, s.mtime_epoch, "
                "lr.path AS library_root_path, ars.folder_id, ars.sort_order "
                "FROM arrangement_sample ars "
                "JOIN sample s ON s.id = ars.sample_id "
                "JOIN library_root lr ON lr.id = s.library_root_id "
                "WHERE ars.folder_id = ? "
                "ORDER BY ars.sort_order, s.filename",
                (folder_id,),
            )
        return [dict(r) for r in rows]

    def update_sample_placement(
        self, arrangement_id: int, sample_id: int, folder_id: int | None
    ) -> None:
        """Update a sample's folder placement. Does not commit."""
        self._db.execute(
            "UPDATE arrangement_sample SET folder_id = ? "
            "WHERE arrangement_id = ? AND sample_id = ?",
            (folder_id, arrangement_id, sample_id),
        )

    def remove_samples_in_folder_tree(self, folder_id: int) -> int:
        """Remove all samples in a folder and its descendants. Does not commit.

        Returns:
            Number of samples removed
        """
        removed = self._db.execute(
            """
            WITH RECURSIVE descendants(id) AS (
                SELECT id FROM arrangement_folder WHERE id = ?
                UNION ALL
                SELECT af.id FROM arrangement_folder af
                JOIN descendants d ON af.parent_id = d.id
            )
            DELETE FROM arrangement_sample
            WHERE folder_id IN (SELECT id FROM descendants)
            """,
            (folder_id,),
        ).rowcount
        return removed
