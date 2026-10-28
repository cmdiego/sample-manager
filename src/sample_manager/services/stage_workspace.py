"""Transactional virtual sample organization, independent of UI and source files."""

import sqlite3

from ..db import Db
from ..normalize import norm_text
from ..repos.stage_repo import StageRepo
from ..repos.arrangement_repo import ArrangementRepo


class StageWorkspace:
    """Manage one persistent folder hierarchy over the shared selection buffer."""

    def __init__(self, db: Db) -> None:
        """Use the shared repository connection; never touch source audio files."""
        self._db = db
        self._repo = StageRepo(db)

    def folders(self) -> list[dict]:
        """Return folders for breadcrumb and child-list rendering."""
        return self._repo.folders()

    def placements(self) -> dict[int, int | None]:
        """Return each selected sample's unique folder placement."""
        return self._repo.placements()

    def folder(self, folder_id: int) -> dict:
        """Reject stale folder IDs instead of silently redirecting a write."""
        folder = next((row for row in self.folders() if row["id"] == folder_id), None)
        if folder is None:
            raise ValueError("Stage folder no longer exists")
        return folder

    def path(self, folder_id: int | None) -> str:
        """Build a root-relative virtual path without filesystem resolution."""
        folders = {row["id"]: row for row in self.folders()}
        parts, seen = [], set()
        while folder_id is not None:
            if folder_id not in folders or folder_id in seen:
                raise ValueError("Stage folder hierarchy is invalid or no longer exists")
            seen.add(folder_id)
            folder = folders[folder_id]
            parts.append(folder["name"])
            folder_id = folder["parent_id"]
        return "/" + "/".join(reversed(parts))

    @staticmethod
    def _name(name: str) -> str:
        """Validate portable folder names that remain safe as export components."""
        name = name.strip()
        reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)}
        if not name or name in (".", "..") or name.endswith((".", " ")):
            raise ValueError("Use a nonempty folder name other than . or ..")
        if any(char in '/\\:*?"<>|' or not char.isprintable() for char in name):
            raise ValueError("Folder names cannot contain path separators or reserved characters")
        if name.split(".")[0].upper() in reserved:
            raise ValueError("This folder name is reserved on Windows")
        return name

    def _ensure_path(self, text: str, base_id: int | None = None) -> int | None:
        """Resolve/create a virtual path inside an already-open transaction."""
        text = text.strip()
        if not text:
            raise ValueError("Enter a Stage folder path, or / for root")
        if text.startswith("/"):
            base_id = None
        parts = [self._name(part) for part in text.strip("/").split("/")] if text.strip("/") else []
        if base_id is not None:
            self.folder(base_id)
        folders = self.folders()
        for name in parts:
            match = next((row for row in folders if row["parent_id"] == base_id and norm_text(row["name"]) == norm_text(name)), None)
            if match is None:
                folder_id = self._repo.create(base_id, name)
                match = {"id": folder_id, "parent_id": base_id, "name": name}
                folders.append(match)
            base_id = match["id"]
        return base_id

    def create_folder(self, text: str, parent_id: int | None = None) -> int:
        """Create nested paths atomically; reuse existing case-insensitive folders."""
        if not text.strip().strip("/"):
            raise ValueError("Enter a folder name")
        with self._db.transaction():
            result = self._ensure_path(text, parent_id)
        return result

    def stage_sample(self, sample_id: int, folder_id: int | None = None) -> None:
        """Place a new selection in the chosen folder, preserving existing ones."""
        with self._db.transaction():
            if folder_id is not None:
                self.folder(folder_id)
            self._repo.stage_sample(sample_id, folder_id)

    def move_sample(self, sample_id: int, destination: str) -> int | None:
        """Move a selection to a root-relative folder, creating missing parents."""
        with self._db.transaction():
            folder_id = self._ensure_path(destination)
            self._repo.move_sample(sample_id, folder_id)
        return folder_id

    def move_folder(self, folder_id: int, destination: str) -> int | None:
        """Move a folder and its subtree, rejecting self/descendant cycles."""
        with self._db.transaction():
            folder = self.folder(folder_id)
            parent_id = self._ensure_path(destination)
            ancestor = parent_id
            while ancestor is not None:
                if ancestor == folder_id:
                    raise ValueError("Cannot move a folder into itself or one of its subfolders")
                ancestor = self.folder(ancestor)["parent_id"]
            try:
                self._repo.update(folder_id, parent_id, folder["name"])
            except sqlite3.IntegrityError as exc:
                raise ValueError("A folder with that name already exists at the destination") from exc
        return parent_id

    def rename_folder(self, folder_id: int, name: str) -> None:
        """Rename within a parent while preserving all nested sample placements."""
        name = self._name(name)
        with self._db.transaction():
            folder = self.folder(folder_id)
            try:
                self._repo.update(folder_id, folder["parent_id"], name)
            except sqlite3.IntegrityError as exc:
                raise ValueError("A folder with that name already exists here") from exc

    def remove_folder(self, folder_id: int) -> None:
        """Remove only empty folders, leaving every staged sample intact."""
        with self._db.transaction():
            self.folder(folder_id)
            if not self._repo.is_empty(folder_id):
                raise ValueError("Folder is not empty. Move its samples and subfolders out first.")
            self._repo.remove(folder_id)

    def copy_to_arrangement(self, arrangement_id: int, sample_ids: list[int]) -> int:
        """Merge Stage paths and newly attached samples into a saved arrangement.

        Existing arrangement placements win when adding Stage to an arrangement;
        duplicate path components merge by normalized sibling name.
        """
        repo = ArrangementRepo(self._db)
        # Join an arrangement-creation transaction when one already owns the
        # write lock; standalone Stage merges still commit as one operation.
        from contextlib import nullcontext
        transaction = nullcontext() if self._db.conn.in_transaction else self._db.transaction()
        with transaction:
            existing_ids = set(repo.list_sample_ids(arrangement_id))
            inserted = repo.add_samples(arrangement_id, sample_ids)
            targets = repo.list_folders(arrangement_id)
            mapping = {None: None}
            # Parents must be copied first, including after reparenting changes IDs.
            for folder in sorted(self.folders(), key=lambda row: self.path(row["id"]).count("/")):
                parent_id = mapping[folder["parent_id"]]
                match = next((row for row in targets if row["parent_id"] == parent_id and norm_text(row["name"]) == norm_text(folder["name"])), None)
                if match is None:
                    match = repo.create_folder(arrangement_id, parent_id, folder["name"], norm_text(folder["name"]))
                    targets.append(match)
                mapping[folder["id"]] = match["id"]
            for sample_id, folder_id in self.placements().items():
                if sample_id in sample_ids and sample_id not in existing_ids:
                    repo.update_sample_placement(arrangement_id, sample_id, mapping[folder_id])
        return inserted
