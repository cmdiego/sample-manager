"""Framework-neutral library browsing service.

``LibraryBrowserService`` wraps the repository/DB layer and returns typed,
immutable DTOs so any front-end (the terminal UI today, Qt tomorrow) can browse
library roots, list directories, inspect samples, and drive the persistent
selection buffer without ever writing SQL or importing a UI framework.

No UI-framework imports live here — this module is pure application logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import get_config_path, load_config, normalize_config
from ..db import Db
from ..repos.library_root_repo import LibraryRootRepo
from ..repos.sample_repo import SampleRepo
from ..repos.selection_repo import SelectionRepo
from ..scanner import ScanResult, scan_library
from .navigation import build_items


# ---------------------------------------------------------------------------
# Immutable DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LibraryRoot:
    """A configured library root directory."""

    id: int
    path: Path
    path_norm: str


@dataclass(frozen=True)
class BrowserItem:
    """A single entry in a directory listing (a subdirectory or a file)."""

    name: str
    path: Path
    is_dir: bool
    sample_id: int | None  # None = not indexed in the DB
    is_selected: bool
    context: str | None = None  # Search-result folder, hidden in directory listings.


@dataclass(frozen=True)
class SampleDetails:
    """A sample row. Optional fields default to None so this DTO can be built
    from either a full ``SELECT *`` row or the narrower selection listing row."""

    id: int
    filename: str
    rel_path: str | None = None
    rel_path_norm: str | None = None
    ext: str | None = None
    size_bytes: int | None = None
    mtime_epoch: int | None = None
    library_root_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_row(cls, row: dict) -> SampleDetails:
        return cls(
            id=row["id"],
            filename=row["filename"],
            rel_path=row.get("rel_path"),
            rel_path_norm=row.get("rel_path_norm"),
            ext=row.get("ext"),
            size_bytes=row.get("size_bytes"),
            mtime_epoch=row.get("mtime_epoch"),
            library_root_id=row.get("library_root_id"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


@dataclass(frozen=True)
class SelectionSummary:
    """Aggregate view of the persistent selection buffer."""

    count: int
    total_bytes: int
    destination: str | None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class LibraryBrowserService:
    """Framework-neutral facade over library roots, samples, and selection."""

    def __init__(self, db: Db) -> None:
        self._db = db
        self._root_repo = LibraryRootRepo(db)
        self._sample_repo = SampleRepo(db)
        self._selection_repo = SelectionRepo(db)

    # -- public DTO interface -------------------------------------------------

    def library_roots(self) -> tuple[LibraryRoot, ...]:
        return tuple(
            LibraryRoot(id=row["id"], path=Path(row["path"]), path_norm=row["path_norm"])
            for row in self._root_repo.list_all()
        )

    def scan_directory(self, path: Path) -> ScanResult:
        """Index a folder on a separate SQLite connection for background jobs.

        The GUI's service connection belongs to the main thread. A scan can
        take seconds, so a worker must own its own connection instead of
        sharing that SQLite object across Qt threads.
        """
        with Db(self._db.path) as worker_db:
            return scan_library(worker_db, path, rescan=True, fast=True)

    def list_directory(self, path: Path) -> tuple[BrowserItem, ...]:
        """List a directory as ordered, selection-aware browser items.

        Directories come first (alphabetical), then files (alphabetical);
        dotfiles are hidden. Files are enriched with their sample_id and
        selection state when the path falls under a known library root.
        """
        root = self._root_for_path(path)
        indexed = self.indexed_files(root.path) if root is not None else {}
        selection = self.selection_ids()
        return tuple(
            BrowserItem(
                name=item.name,
                path=item.path,
                is_dir=item.is_dir,
                sample_id=item.sample_id,
                is_selected=item.is_selected,
            )
            for item in build_items(path, indexed, selection)
        )

    def search_samples(self, root: LibraryRoot, query: str) -> tuple[BrowserItem, ...]:
        """Return root-wide indexed search hits as selection-aware browser rows."""
        rows = self._sample_repo.search_by_text(root.id, query)
        selected = self.selection_ids()
        return tuple(
            BrowserItem(
                name=row["filename"],
                path=root.path / row["rel_path"],
                is_dir=False,
                sample_id=row["id"],
                is_selected=row["id"] in selected,
                context=str(Path(row["rel_path"]).parent),
            )
            for row in rows
        )

    def sample_details(self, sample_id: int) -> SampleDetails | None:
        row = self._sample_repo.get_by_id(sample_id)
        return SampleDetails.from_row(row) if row is not None else None

    def sample_path(self, sample_id: int) -> Path | None:
        """Absolute filesystem path for a sample (root path + rel_path).

        Returns ``None`` when the sample or its library root is unknown. Used by
        front-ends that need to hand a real path to the audio engine.
        """
        row = self._sample_repo.get_by_id(sample_id)
        if row is None:
            return None
        root = self._root_repo.get_by_id(row["library_root_id"])
        if root is None:
            return None
        rel = row.get("rel_path")
        if not rel:
            return None
        return Path(root["path"]) / rel

    def selected_samples(self) -> tuple[SampleDetails, ...]:
        return tuple(SampleDetails.from_row(row) for row in self._selection_repo.list_samples())

    def add_to_selection(self, sample_id: int) -> None:
        self._selection_repo.add_samples([sample_id])

    def remove_from_selection(self, sample_id: int) -> None:
        self._selection_repo.remove_samples([sample_id])

    def selection_summary(self) -> SelectionSummary:
        return SelectionSummary(
            count=self._selection_repo.count(),
            total_bytes=self.selection_total_size(),
            destination=self.active_destination(),
        )

    # -- lower-level helpers (framework-neutral, shared with the TUI adapter) --

    def library_root_rows(self) -> list[dict]:
        """Raw library_root rows (used by the terminal-UI adapter that needs dicts)."""
        return self._root_repo.list_all()

    def indexed_files(self, library_root_path: Path) -> dict[str, int]:
        """Return {rel_path_norm: sample_id} for all indexed files under a root.

        Queried once per root and reused across directory changes by callers.
        """
        root_row = self._db.fetchone(
            "SELECT id FROM library_root WHERE path_norm = ?",
            (str(library_root_path).lower(),),
        )
        if root_row is None:
            # Try un-lowercased path (path_norm may vary)
            root_row = self._db.fetchone(
                "SELECT id FROM library_root WHERE path = ? OR path_norm = ?",
                (str(library_root_path), str(library_root_path)),
            )
        if root_row is None:
            return {}

        rows = self._sample_repo.list_by_root(root_row["id"])
        return {row["rel_path_norm"]: row["id"] for row in rows}

    def selection_ids(self) -> set[int]:
        return {row["id"] for row in self._selection_repo.list_samples()}

    def sample_details_row(self, sample_id: int) -> dict | None:
        """Raw sample row (used by the terminal-UI adapter that needs dicts)."""
        return self._sample_repo.get_by_id(sample_id)

    def selection_total_size(self) -> int:
        """Total size_bytes across all selected samples (0 if none)."""
        result = self._db.fetchval(
            "SELECT COALESCE(SUM(s.size_bytes), 0) "
            "FROM selection_sample ss JOIN sample s ON s.id = ss.sample_id",
        )
        return int(result) if result is not None else 0

    def active_destination(self) -> str | None:
        """Destination path from the first export profile in config, or None."""
        try:
            cfg_path = get_config_path()
            if not cfg_path.exists():
                return None
            cfg = load_config(cfg_path)
            normalized = normalize_config(cfg)
            profiles_dir = normalized.get("profiles_dir")
            if not profiles_dir:
                return None
            import yaml
            ep_file = Path(profiles_dir) / "export_profiles.yaml"
            if not ep_file.exists():
                return None
            with open(ep_file) as f:
                profiles = yaml.safe_load(f) or []
            if profiles and isinstance(profiles, list):
                dest = profiles[0].get("default_dest") or profiles[0].get("destination")
                return str(dest) if dest else None
        except Exception:
            pass
        return None

    # -- internal -------------------------------------------------------------

    def _root_for_path(self, path: Path) -> LibraryRoot | None:
        """Return the library root that contains *path* (deepest match wins)."""
        best: LibraryRoot | None = None
        best_len = -1
        for root in self.library_roots():
            try:
                path.relative_to(root.path)
            except ValueError:
                continue
            depth = len(root.path.parts)
            if depth > best_len:
                best = root
                best_len = depth
        return best
