"""Arrangement workspace service and DTOs for virtual folder management.

Provides a framework-neutral service for managing arrangement virtual folders,
sample placement, and tree operations. All DTOs are immutable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .db import Db
from .normalize import norm_text
from .repos.arrangement_repo import ArrangementRepo


# -- Immutable DTOs --


@dataclass(frozen=True)
class Folder:
    """Virtual folder in an arrangement."""

    id: int
    arrangement_id: int
    parent_id: int | None
    name: str
    name_norm: str
    sort_order: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ArrangementSample:
    """Sample membership in an arrangement with placement."""

    sample_id: int
    filename: str
    rel_path: str
    ext: str | None
    size_bytes: int | None
    mtime_epoch: int | None
    library_root_path: str
    folder_id: int | None
    sort_order: int


@dataclass(frozen=True)
class ArrangementSummary:
    """Summary of an arrangement."""

    id: int
    name: str
    name_norm: str
    profile_name: str
    created_at: str
    updated_at: str
    sample_count: int


@dataclass(frozen=True)
class TreeNode:
    """Node in an arrangement tree (folder or sample)."""

    node_type: str  # "folder" or "sample"
    folder: Folder | None
    sample: ArrangementSample | None
    children: tuple[TreeNode, ...]


@dataclass(frozen=True)
class ArrangementTree:
    """Complete tree structure of an arrangement."""

    arrangement_id: int
    root_folders: tuple[TreeNode, ...]
    root_samples: tuple[ArrangementSample, ...]


@dataclass(frozen=True)
class RemovalSnapshot:
    """Snapshot of removed folders and samples for undo/restore."""

    folder_rows: tuple[dict, ...]
    sample_placements: tuple[dict, ...]  # (arrangement_id, sample_id, folder_id, sort_order)


# -- Service --


class ArrangementWorkspaceService:
    """Framework-neutral service for arrangement workspace operations.

    Handles virtual folder creation, renaming, moving, removal, and sample placement.
    All operations validate constraints and run in transactions.
    """

    def __init__(self, db: Db) -> None:
        self._db = db
        self._repo = ArrangementRepo(db)

    def list_arrangements(self) -> tuple[ArrangementSummary, ...]:
        """List all arrangements with sample counts."""
        rows = self._repo.list_all()
        return tuple(
            ArrangementSummary(
                id=r["id"],
                name=r["name"],
                name_norm=r["name_norm"],
                profile_name=r["profile_name"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                sample_count=r["sample_count"],
            )
            for r in rows
        )

    def get_arrangement(self, arrangement_id: int) -> ArrangementSummary | None:
        """Get arrangement summary by ID."""
        row = self._db.fetchone(
            "SELECT a.id, a.name, a.name_norm, a.profile_name, a.created_at, "
            "a.updated_at, COUNT(asl.sample_id) AS sample_count "
            "FROM arrangement a "
            "LEFT JOIN arrangement_sample asl ON asl.arrangement_id = a.id "
            "WHERE a.id = ? "
            "GROUP BY a.id",
            (arrangement_id,),
        )
        if not row:
            return None
        return ArrangementSummary(
            id=row["id"],
            name=row["name"],
            name_norm=row["name_norm"],
            profile_name=row["profile_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            sample_count=row["sample_count"],
        )

    def tree(self, arrangement_id: int) -> ArrangementTree:
        """Build complete tree structure for an arrangement."""
        # Load all folders
        folder_rows = self._repo.list_folders(arrangement_id)
        folders_by_id = {r["id"]: Folder(**r) for r in folder_rows}

        # Build tree structure
        children_by_parent: dict[int | None, list[TreeNode]] = {}

        # Add folders to tree
        for folder in folders_by_id.values():
            node = TreeNode(
                node_type="folder",
                folder=folder,
                sample=None,
                children=(),  # Will be filled recursively
            )
            children_by_parent.setdefault(folder.parent_id, []).append(node)

        # Recursively build folder subtrees
        def build_subtree(folder_id: int) -> TreeNode:
            folder = folders_by_id[folder_id]
            child_nodes = []

            # Add child folders
            for child in children_by_parent.get(folder_id, []):
                if child.node_type == "folder" and child.folder:
                    child_nodes.append(build_subtree(child.folder.id))

            # Add samples in this folder
            sample_rows = self._repo.list_folder_samples(folder_id)
            for s_row in sample_rows:
                sample = ArrangementSample(
                    sample_id=s_row["id"],
                    filename=s_row["filename"],
                    rel_path=s_row["rel_path"],
                    ext=s_row["ext"],
                    size_bytes=s_row["size_bytes"],
                    mtime_epoch=s_row["mtime_epoch"],
                    library_root_path=s_row["library_root_path"],
                    folder_id=s_row["folder_id"],
                    sort_order=s_row["sort_order"],
                )
                child_nodes.append(
                    TreeNode(node_type="sample", folder=None, sample=sample, children=())
                )

            return TreeNode(
                node_type="folder",
                folder=folder,
                sample=None,
                children=tuple(child_nodes),
            )

        # Build root-level nodes
        root_folder_nodes = []
        for node in children_by_parent.get(None, []):
            if node.node_type == "folder" and node.folder:
                root_folder_nodes.append(build_subtree(node.folder.id))

        # Get root-level samples
        root_sample_rows = self._repo.list_folder_samples(None)
        root_samples = tuple(
            ArrangementSample(
                sample_id=s["id"],
                filename=s["filename"],
                rel_path=s["rel_path"],
                ext=s["ext"],
                size_bytes=s["size_bytes"],
                mtime_epoch=s["mtime_epoch"],
                library_root_path=s["library_root_path"],
                folder_id=s["folder_id"],
                sort_order=s["sort_order"],
            )
            for s in root_sample_rows
        )

        return ArrangementTree(
            arrangement_id=arrangement_id,
            root_folders=tuple(root_folder_nodes),
            root_samples=root_samples,
        )

    def create_folder(
        self, arrangement_id: int, parent_id: int | None, name: str
    ) -> Folder:
        """Create a new virtual folder.

        Args:
            arrangement_id: Target arrangement
            parent_id: Parent folder ID (None for root)
            name: Display name

        Raises:
            ValueError: If name is invalid or would create a duplicate

        Returns:
            Created folder
        """
        # Validate name
        name = name.strip()
        if not name:
            raise ValueError("Folder name cannot be empty")
        if "/" in name or "\\" in name:
            raise ValueError("Folder name cannot contain path separators")
        if name in (".", ".."):
            raise ValueError("Folder name cannot be . or ..")

        name_norm = norm_text(name)

        # Check for duplicate siblings
        if parent_id is None:
            existing = self._db.fetchone(
                "SELECT 1 FROM arrangement_folder "
                "WHERE arrangement_id = ? AND parent_id IS NULL AND name_norm = ?",
                (arrangement_id, name_norm),
            )
        else:
            existing = self._db.fetchone(
                "SELECT 1 FROM arrangement_folder "
                "WHERE arrangement_id = ? AND parent_id = ? AND name_norm = ?",
                (arrangement_id, parent_id, name_norm),
            )

        if existing:
            raise ValueError(f"Folder '{name}' already exists at this level")

        # Validate parent exists if specified
        if parent_id is not None:
            parent = self._repo.get_folder(parent_id)
            if not parent:
                raise ValueError(f"Parent folder {parent_id} not found")
            if parent["arrangement_id"] != arrangement_id:
                raise ValueError("Cannot use parent from different arrangement")

        with self._db.transaction():
            row = self._repo.create_folder(arrangement_id, parent_id, name, name_norm)

        return Folder(**row)

    def rename_folder(self, folder_id: int, name: str) -> Folder:
        """Rename a folder.

        Args:
            folder_id: Folder to rename
            name: New display name

        Raises:
            ValueError: If name is invalid or would create a duplicate

        Returns:
            Updated folder
        """
        # Validate name
        name = name.strip()
        if not name:
            raise ValueError("Folder name cannot be empty")
        if "/" in name or "\\" in name:
            raise ValueError("Folder name cannot contain path separators")
        if name in (".", ".."):
            raise ValueError("Folder name cannot be . or ..")

        name_norm = norm_text(name)

        # Get current folder
        folder = self._repo.get_folder(folder_id)
        if not folder:
            raise ValueError(f"Folder {folder_id} not found")

        # Check for duplicate siblings (excluding self)
        if folder["parent_id"] is None:
            existing = self._db.fetchone(
                "SELECT 1 FROM arrangement_folder "
                "WHERE arrangement_id = ? AND parent_id IS NULL AND name_norm = ? AND id != ?",
                (folder["arrangement_id"], name_norm, folder_id),
            )
        else:
            existing = self._db.fetchone(
                "SELECT 1 FROM arrangement_folder "
                "WHERE arrangement_id = ? AND parent_id = ? AND name_norm = ? AND id != ?",
                (folder["arrangement_id"], folder["parent_id"], name_norm, folder_id),
            )

        if existing:
            raise ValueError(f"Folder '{name}' already exists at this level")

        with self._db.transaction():
            row = self._repo.rename_folder(folder_id, name, name_norm)

        return Folder(**row)

    def move_folders(
        self, folder_ids: tuple[int, ...], parent_id: int | None
    ) -> None:
        """Move folders to a new parent.

        Args:
            folder_ids: Folders to move
            parent_id: New parent folder ID (None for root)

        Raises:
            ValueError: If move would create a cycle or cross-arrangement move
        """
        if not folder_ids:
            return

        with self._db.transaction():
            # Validate all folders exist and belong to same arrangement
            arrangement_id = None
            for folder_id in folder_ids:
                folder = self._repo.get_folder(folder_id)
                if not folder:
                    raise ValueError(f"Folder {folder_id} not found")

                if arrangement_id is None:
                    arrangement_id = folder["arrangement_id"]
                elif folder["arrangement_id"] != arrangement_id:
                    raise ValueError("Cannot move folders from different arrangements")

                # Check for cycle: parent_id cannot be folder_id or any descendant
                if parent_id is not None:
                    if parent_id == folder_id:
                        raise ValueError("Cannot move folder to itself")

                    descendants = self._repo.get_folder_descendants(folder_id)
                    descendant_ids = {d["id"] for d in descendants}
                    if parent_id in descendant_ids:
                        raise ValueError("Cannot move folder to its own descendant")

            # Validate parent exists and belongs to same arrangement
            if parent_id is not None:
                parent = self._repo.get_folder(parent_id)
                if not parent:
                    raise ValueError(f"Parent folder {parent_id} not found")
                if parent["arrangement_id"] != arrangement_id:
                    raise ValueError("Cannot move to parent from different arrangement")

            # Perform moves
            for folder_id in folder_ids:
                self._repo.move_folder(folder_id, parent_id)

    def add_samples(
        self,
        arrangement_id: int,
        sample_ids: tuple[int, ...],
        folder_id: int | None = None,
    ) -> int:
        """Add samples to an arrangement.

        Args:
            arrangement_id: Target arrangement
            sample_ids: Samples to add
            folder_id: Optional folder to place samples in

        Returns:
            Number of newly added samples
        """
        if not sample_ids:
            return 0

        with self._db.transaction():
            # Validate folder if specified
            if folder_id is not None:
                folder = self._repo.get_folder(folder_id)
                if not folder:
                    raise ValueError(f"Folder {folder_id} not found")
                if folder["arrangement_id"] != arrangement_id:
                    raise ValueError("Folder does not belong to this arrangement")

            return self._repo.add_samples(arrangement_id, list(sample_ids), folder_id)

    def move_samples(
        self, arrangement_id: int, sample_ids: tuple[int, ...], folder_id: int | None
    ) -> None:
        """Move samples to a different folder.

        Args:
            arrangement_id: Target arrangement
            sample_ids: Samples to move
            folder_id: Target folder ID (None for root)
        """
        if not sample_ids:
            return

        with self._db.transaction():
            # Validate folder if specified
            if folder_id is not None:
                folder = self._repo.get_folder(folder_id)
                if not folder:
                    raise ValueError(f"Folder {folder_id} not found")
                if folder["arrangement_id"] != arrangement_id:
                    raise ValueError("Folder does not belong to this arrangement")

            for sample_id in sample_ids:
                self._repo.update_sample_placement(arrangement_id, sample_id, folder_id)

    def remove_samples(
        self, arrangement_id: int, sample_ids: tuple[int, ...]
    ) -> int:
        """Remove samples from an arrangement.

        Args:
            arrangement_id: Target arrangement
            sample_ids: Samples to remove

        Returns:
            Number of samples removed
        """
        if not sample_ids:
            return 0

        with self._db.transaction():
            return self._repo.remove_samples(arrangement_id, list(sample_ids))

    def remove_folder_tree(self, folder_id: int) -> RemovalSnapshot:
        """Remove a folder and all its descendants.

        Args:
            folder_id: Root folder to remove

        Returns:
            Snapshot for undo/restore
        """
        with self._db.transaction():
            # Collect all descendant folders
            descendants = self._repo.get_folder_descendants(folder_id)
            folder = self._repo.get_folder(folder_id)
            if not folder:
                raise ValueError(f"Folder {folder_id} not found")

            all_folder_ids = [folder_id] + [d["id"] for d in descendants]
            folder_rows = [folder] + descendants

            # Collect all sample placements in these folders
            sample_placements = []
            for fid in all_folder_ids:
                samples = self._repo.list_folder_samples(fid)
                for s in samples:
                    sample_placements.append(
                        {
                            "arrangement_id": folder["arrangement_id"],
                            "sample_id": s["id"],
                            "folder_id": s["folder_id"],
                            "sort_order": s["sort_order"],
                        }
                    )

            # Remove samples in folder tree first
            self._repo.remove_samples_in_folder_tree(folder_id)

            # Remove the folder (CASCADE removes descendants)
            self._repo.remove_folder(folder_id)

        return RemovalSnapshot(
            folder_rows=tuple(folder_rows), sample_placements=tuple(sample_placements)
        )

    def restore_removal_snapshot(self, snapshot: RemovalSnapshot) -> None:
        """Restore folders and samples from a removal snapshot.

        Args:
            snapshot: Snapshot to restore
        """
        with self._db.transaction():
            # Restore folders in order (root first, then descendants)
            for folder_row in snapshot.folder_rows:
                self._db.execute(
                    "INSERT INTO arrangement_folder "
                    "(id, arrangement_id, parent_id, name, name_norm, sort_order, "
                    "created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        folder_row["id"],
                        folder_row["arrangement_id"],
                        folder_row["parent_id"],
                        folder_row["name"],
                        folder_row["name_norm"],
                        folder_row["sort_order"],
                        folder_row["created_at"],
                        folder_row["updated_at"],
                    ),
                )

            # Restore sample placements
            for placement in snapshot.sample_placements:
                self._db.execute(
                    "INSERT OR REPLACE INTO arrangement_sample "
                    "(arrangement_id, sample_id, folder_id, sort_order) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        placement["arrangement_id"],
                        placement["sample_id"],
                        placement["folder_id"],
                        placement["sort_order"],
                    ),
                )

    def get_folder_path(self, folder_id: int) -> str:
        """Get the full virtual path for a folder.

        Args:
            folder_id: Folder ID

        Returns:
            Path string like "parent/child" (no leading slash)
        """
        folder = self._repo.get_folder(folder_id)
        if not folder:
            raise ValueError(f"Folder {folder_id} not found")

        parts = [folder["name"]]
        current_id = folder["parent_id"]

        while current_id is not None:
            parent = self._repo.get_folder(current_id)
            if not parent:
                break
            parts.insert(0, parent["name"])
            current_id = parent["parent_id"]

        return "/".join(parts)

    def get_sample_folder_paths(self, arrangement_id: int) -> dict[int, str]:
        """Build a mapping of sample_id -> virtual folder path for all samples.

        Args:
            arrangement_id: Arrangement ID

        Returns:
            Dict mapping sample_id to folder path (empty string for root)
        """
        # Get all samples with their folder_id
        samples = self._db.fetchall(
            "SELECT sample_id, folder_id FROM arrangement_sample "
            "WHERE arrangement_id = ?",
            (arrangement_id,),
        )

        # Build folder_id -> path cache
        folder_paths_cache: dict[int | None, str] = {None: ""}

        def get_cached_folder_path(fid: int | None) -> str:
            if fid in folder_paths_cache:
                return folder_paths_cache[fid]
            path = self.get_folder_path(fid) if fid is not None else ""
            folder_paths_cache[fid] = path
            return path

        # Map sample_id -> folder path
        result = {}
        for row in samples:
            sample_id = row["sample_id"]
            folder_id = row["folder_id"]
            result[sample_id] = get_cached_folder_path(folder_id)

        return result
