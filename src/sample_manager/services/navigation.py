"""Navigation state model for the file browser.

Pure Python — no UI-framework imports (no TUI, no Qt). Fully unit-testable
without a terminal or a GUI event loop. Extracted from ``tui/nav_state.py`` so
both the terminal UI and the future Qt GUI can share the same navigation logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class NavItem:
    name: str
    path: Path
    is_dir: bool
    sample_id: int | None  # None = file not indexed in DB
    is_selected: bool


@dataclass(frozen=True)
class NavState:
    library_roots: tuple[Path, ...]
    current_root: Path
    current_dir: Path
    dir_stack: tuple[Path, ...]  # history for go_back()
    items: tuple[NavItem, ...]
    focused_index: int
    selection_ids: frozenset[int]

    # -- factories --

    @classmethod
    def initial(
        cls,
        root: Path,
        items: list[NavItem],
        selection_ids: set[int] | None = None,
        library_roots: list[Path] | None = None,
    ) -> NavState:
        roots = tuple(library_roots or [root])
        return cls(
            library_roots=roots,
            current_root=root,
            current_dir=root,
            dir_stack=(),
            items=tuple(items),
            focused_index=0 if items else -1,
            selection_ids=frozenset(selection_ids or []),
        )

    # -- focused item --

    @property
    def focused_item(self) -> NavItem | None:
        if not self.items or self.focused_index < 0:
            return None
        return self.items[self.focused_index]

    # -- movement --

    def move_up(self) -> NavState:
        if not self.items or self.focused_index <= 0:
            return self
        return replace(self, focused_index=self.focused_index - 1)

    def move_down(self) -> NavState:
        if not self.items or self.focused_index >= len(self.items) - 1:
            return self
        return replace(self, focused_index=self.focused_index + 1)

    def enter_dir(self, new_dir: Path, new_items: list[NavItem]) -> NavState:
        """Descend into a subdirectory, pushing current_dir onto the stack."""
        return replace(
            self,
            current_dir=new_dir,
            dir_stack=self.dir_stack + (self.current_dir,),
            items=tuple(new_items),
            focused_index=0 if new_items else -1,
        )

    def go_back(self, parent_items: list[NavItem], restore_focus_name: str | None = None) -> NavState:
        """Ascend to the parent directory (pop dir_stack)."""
        if not self.dir_stack:
            return self
        parent_dir = self.dir_stack[-1]
        new_stack = self.dir_stack[:-1]

        # Try to restore focus to the directory we just came from
        target_name = restore_focus_name or self.current_dir.name
        new_index = 0
        for i, item in enumerate(parent_items):
            if item.name == target_name:
                new_index = i
                break

        return replace(
            self,
            current_dir=parent_dir,
            dir_stack=new_stack,
            items=tuple(parent_items),
            focused_index=new_index if parent_items else -1,
        )

    # -- selection --

    def with_selection(self, selection_ids: set[int]) -> NavState:
        """Return a new state with updated selection, refreshing item.is_selected flags."""
        frozen = frozenset(selection_ids)
        new_items = tuple(
            replace(item, is_selected=(item.sample_id in frozen) if item.sample_id is not None else False)
            for item in self.items
        )
        return replace(self, selection_ids=frozen, items=new_items)


def build_items(
    directory: Path,
    indexed: dict[str, int],
    selection_ids: set[int],
) -> list[NavItem]:
    """Build the NavItem list for a directory.

    Args:
        directory: The filesystem directory to list.
        indexed: Mapping of rel_path_norm -> sample_id for all indexed files
                 under the current library root. The caller pre-computes this.
        selection_ids: Set of currently selected sample IDs.

    Returns:
        Sorted list: directories first (alphabetical), then files (alphabetical).
    """
    dirs: list[NavItem] = []
    files: list[NavItem] = []

    try:
        entries = sorted(os.scandir(directory), key=lambda e: e.name.lower())
    except PermissionError:
        return []

    for entry in entries:
        if entry.name.startswith("."):
            continue
        path = Path(entry.path)
        if entry.is_dir(follow_symlinks=False):
            dirs.append(NavItem(name=entry.name, path=path, is_dir=True, sample_id=None, is_selected=False))
        elif entry.is_file(follow_symlinks=False):
            # Compute the rel_path_norm key used by the DB
            rel_norm = _to_rel_norm(path, indexed)
            sid = indexed.get(rel_norm)
            files.append(NavItem(
                name=entry.name,
                path=path,
                is_dir=False,
                sample_id=sid,
                is_selected=(sid in selection_ids) if sid is not None else False,
            ))

    return dirs + files


def _to_rel_norm(file_path: Path, indexed: dict[str, int]) -> str:
    """Convert an absolute file path to the rel_path_norm key format used by the DB.

    rel_path_norm is lowercase with forward slashes (see normalize.norm_rel_path).
    We try to find a key in `indexed` whose suffix matches the file's name,
    to avoid needing to know the library root here.
    """
    name_lower = file_path.name.lower()
    for key in indexed:
        if key.endswith("/" + name_lower) or key == name_lower:
            # Verify the full path matches (last N components)
            key_parts = key.replace("\\", "/").split("/")
            file_parts = [p.lower() for p in file_path.parts]
            if file_parts[-len(key_parts):] == key_parts:
                return key
    return name_lower
