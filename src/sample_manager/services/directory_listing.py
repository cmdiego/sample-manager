"""Read-only, framework-neutral directory inspection without audio indexing."""

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class DirectoryItem:
    """One filesystem entry; symlinks are visible but never traversed."""

    path: Path
    is_dir: bool
    is_symlink: bool = False


def list_directory(path: Path) -> tuple[DirectoryItem, ...]:
    """Read one directory, listing subfolders before files in stable name order.

    Leave OSError reporting to the caller so inaccessible/disappearing folders
    are distinguishable from genuinely empty directories. Loading one level at
    a time lets inspectors handle large libraries without recursive scans.
    """
    with os.scandir(path) as entries:
        items = [
            DirectoryItem(Path(entry.path), entry.is_dir(follow_symlinks=False), entry.is_symlink())
            for entry in entries
        ]
    return tuple(sorted(items, key=lambda item: (not item.is_dir, item.path.name.casefold(), item.path.name)))
