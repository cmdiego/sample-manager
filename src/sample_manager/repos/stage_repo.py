"""Persistence for virtual Stage folders and selection placements.

Writes do not commit: StageWorkspace owns transactional multi-step operations.
"""

from ..db import Db
from ..normalize import norm_text


class StageRepo:
    """SQL boundary for the single persistent Stage workspace."""

    def __init__(self, db: Db) -> None:
        """Share the application's connection and transaction scope."""
        self._db = db

    def folders(self) -> list[dict]:
        """Read all virtual folders in stable sibling name order."""
        return [dict(row) for row in self._db.fetchall("SELECT id, parent_id, name FROM stage_folder ORDER BY name_norm, id")]

    def create(self, parent_id: int | None, name: str) -> int:
        """Insert one folder, with uniqueness enforced by sibling indexes."""
        cursor = self._db.execute("INSERT INTO stage_folder(parent_id, name, name_norm) VALUES (?, ?, ?)", (parent_id, name, norm_text(name)))
        return cursor.lastrowid

    def update(self, folder_id: int, parent_id: int | None, name: str) -> None:
        """Move/rename a service-validated folder without changing its children."""
        self._db.execute("UPDATE stage_folder SET parent_id = ?, name = ?, name_norm = ? WHERE id = ?", (parent_id, name, norm_text(name), folder_id))

    def is_empty(self, folder_id: int) -> bool:
        """Require both sample and folder children to be absent before removal."""
        return not self._db.fetchval("SELECT EXISTS(SELECT 1 FROM stage_folder WHERE parent_id = ?) OR EXISTS(SELECT 1 FROM selection_sample WHERE folder_id = ?)", (folder_id, folder_id))

    def remove(self, folder_id: int) -> None:
        """Remove a folder after the service checks that it is empty."""
        self._db.execute("DELETE FROM stage_folder WHERE id = ?", (folder_id,))

    def placements(self) -> dict[int, int | None]:
        """Read placements without changing legacy flat selection DTOs."""
        return {row["sample_id"]: row["folder_id"] for row in self._db.fetchall("SELECT sample_id, folder_id FROM selection_sample")}

    def stage_sample(self, sample_id: int, folder_id: int | None) -> bool:
        """Stage once; repeated adds preserve an existing placement."""
        cursor = self._db.execute("INSERT OR IGNORE INTO selection_sample(sample_id, folder_id) VALUES (?, ?)", (sample_id, folder_id))
        return bool(cursor.rowcount)

    def move_sample(self, sample_id: int, folder_id: int | None) -> None:
        """Move only an existing selection, rejecting stale UI actions."""
        cursor = self._db.execute("UPDATE selection_sample SET folder_id = ? WHERE sample_id = ?", (folder_id, sample_id))
        if not cursor.rowcount:
            raise ValueError("This sample is no longer in Stage")
