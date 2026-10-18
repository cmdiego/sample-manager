"""DB queries for the TUI.

The framework-neutral logic now lives in
``sample_manager.services.library_browser.LibraryBrowserService``. ``TuiDataSource``
is a thin Textual-facing adapter that delegates to that service and exposes the
dict/set return shapes the Textual widgets already consume, so the app layer is
unaffected by the extraction.
"""

from __future__ import annotations

from pathlib import Path

from ..db import Db
from ..scanner import ScanResult
from ..services.library_browser import LibraryBrowserService
from ..services.stage_workspace import StageWorkspace
from ..tag_service import list_sample_tags, resolve_tag, tag_sample, untag_sample
from .nav_state import NavItem


class TuiDataSource:
    def __init__(self, db: Db) -> None:
        self._db = db
        self._service = LibraryBrowserService(db)
        self.stage_workspace = StageWorkspace(db)

    def get_library_roots(self) -> list[dict]:
        return self._service.library_root_rows()

    def get_indexed_files(self, library_root_path: Path) -> dict[str, int]:
        """Return {rel_path_norm: sample_id} for all indexed files under a library root.

        The caller holds this dict and uses it to enrich NavItems when building
        the directory listing. Queried once per root and reused across directory changes.
        """
        return self._service.indexed_files(library_root_path)

    def search_samples(self, root_path: Path, query: str) -> tuple[NavItem, ...]:
        """Search indexed names, paths, and tags throughout one library root."""
        root = next(
            (root for root in self._service.library_roots() if root.path == root_path),
            None,
        )
        if root is None:
            return ()
        return tuple(
            NavItem(
                item.name, item.path, False, item.sample_id, item.is_selected,
                context=item.context if item.context != "." else "",
            )
            for item in self._service.search_samples(root, query)
        )

    def scan_directory(self, root_path: Path) -> ScanResult:
        """Reconcile a root using the service's separate worker DB connection."""
        return self._service.scan_directory(root_path)

    def get_selection_ids(self) -> set[int]:
        return self._service.selection_ids()

    def add_to_selection(self, sample_id: int) -> None:
        self._service.add_to_selection(sample_id)

    def remove_from_selection(self, sample_id: int) -> None:
        self._service.remove_from_selection(sample_id)

    def get_sample_details(self, sample_id: int) -> dict | None:
        """Read preview metadata with the sample's actual visible tag names."""
        details = self._service.sample_details_row(sample_id)
        if details is not None:
            try:
                details["tags"] = [tag["name_display"] for tag in self.get_sample_tags(sample_id)]
            except ValueError:
                # A scanner on its own connection can prune the sample between
                # these reads. Treat that as an absent row during refresh.
                return None
        return details

    def get_sample_tags(self, sample_id: int) -> list[dict]:
        """Expose visible attachments while preserving globally hidden tags."""
        return [tag for tag in list_sample_tags(self._db, sample_id) if not tag["is_hidden"]]

    def add_sample_tag(self, sample_id: int, text: str) -> None:
        """Attach a tag name/alias without creating empty or hidden attachments."""
        text = text.strip()
        if not text:
            raise ValueError("Enter a tag name")
        try:
            existing = resolve_tag(self._db, text, include_hidden=True)
        except ValueError:
            existing = None
        if existing is not None and existing["is_hidden"]:
            raise ValueError("This tag is hidden. Restore it before adding it.")
        tag_sample(self._db, sample_id, text)

    def remove_sample_tag(self, sample_id: int, name: str) -> None:
        """Detach a visible tag from one sample without deleting the shared tag."""
        untag_sample(self._db, sample_id, name)

    def get_sample_path(self, sample_id: int) -> Path | None:
        """Resolve a staged sample so pane focus can audition it."""
        return self._service.sample_path(sample_id)

    def get_selection_total_size(self) -> int:
        """Return total size_bytes for all selected samples (0 if none or column missing)."""
        return self._service.selection_total_size()

    def get_active_destination(self) -> str | None:
        """Return the destination path from the first export profile in config, or None."""
        return self._service.active_destination()
