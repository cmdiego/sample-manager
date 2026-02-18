"""Scanner module for Sample Manager.

Walks a library root directory, collects audio sample metadata,
and persists results to SQLite via the repository layer.

Per docs/03-cli.md:
  - `sample scan <path> [--rescan] [--fast]`
  - `sample status`

Per docs/01-data-model.md:
  - Sample identity: (library_root_id, rel_path_norm)
  - Metadata captured: filename, ext, size_bytes, mtime_epoch

Design:
  - collect_samples() is a pure function (no DB, no side effects).
  - scan_library() orchestrates collection + persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .db import Db
from .normalize import norm_rel_path
from .repos.library_root_repo import LibraryRootRepo
from .repos.sample_repo import SampleRepo


# Common audio sample extensions (lowercase, with leading dot).
# Users can override via the extensions parameter.
DEFAULT_SAMPLE_EXTENSIONS: frozenset[str] = frozenset(
    {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg", ".mp4", ".wv"}
)


@dataclass
class ScanResult:
    """Summary of a scan operation."""

    library_root_id: int
    total_on_disk: int
    inserted: int
    updated: int
    skipped: int
    pruned: int


def collect_samples(
    root: Path,
    extensions: frozenset[str] = DEFAULT_SAMPLE_EXTENSIONS,
) -> list[dict]:
    """Walk *root* recursively and collect metadata for audio files.

    This is a **pure** function — no database access, no side effects beyond
    reading the filesystem.

    Args:
        root: Absolute path to the library root directory.
        extensions: Set of lowercase extensions (with leading dot) to include.

    Returns:
        List of dicts, each with keys:
          rel_path, filename, ext, size_bytes, mtime_epoch
    """
    results: list[dict] = []

    for entry in sorted(root.rglob("*")):
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        if ext not in extensions:
            continue

        stat = entry.stat()
        rel = entry.relative_to(root)

        results.append(
            {
                "rel_path": str(rel),
                "filename": entry.name,
                "ext": ext,
                "size_bytes": stat.st_size,
                "mtime_epoch": int(stat.st_mtime),
            }
        )

    return results


def scan_library(
    db: Db,
    path: str | Path,
    *,
    rescan: bool = False,
    fast: bool = False,
    extensions: frozenset[str] | None = None,
) -> ScanResult:
    """Scan a library root directory and persist results to the database.

    Args:
        db: Connected database instance (with migrations applied).
        path: Path to the library root directory.
        rescan: If True, prune samples that no longer exist on disk.
        fast: If True, skip files whose (mtime_epoch, size_bytes) haven't
              changed since the last scan.
        extensions: Override the default audio extensions filter.

    Returns:
        ScanResult with counts of what happened.

    Raises:
        FileNotFoundError: If *path* does not exist.
        NotADirectoryError: If *path* is not a directory.
    """
    root = Path(path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")

    exts = extensions if extensions is not None else DEFAULT_SAMPLE_EXTENSIONS

    # Ensure library root row exists
    root_repo = LibraryRootRepo(db)
    root_row = root_repo.get_or_create(str(root))
    library_root_id: int = root_row["id"]

    # Collect files from disk
    on_disk = collect_samples(root, exts)
    total_on_disk = len(on_disk)

    # Build lookup of existing samples for insert/update tracking (and fast-skip)
    sample_repo = SampleRepo(db)
    existing_lookup: dict[str, tuple[int | None, int | None]] = {}
    for row in sample_repo.list_by_root(library_root_id):
        existing_lookup[row["rel_path_norm"]] = (
            row["size_bytes"],
            row["mtime_epoch"],
        )

    # Upsert samples inside a single transaction for performance
    inserted = 0
    updated = 0
    skipped = 0
    scanned_norms: set[str] = set()

    with db.transaction():
        for entry in on_disk:
            rel_norm = norm_rel_path(entry["rel_path"])
            scanned_norms.add(rel_norm)

            # Fast mode: skip if mtime+size unchanged
            if fast and rel_norm in existing_lookup:
                existing_size, existing_mtime = existing_lookup[rel_norm]
                if (
                    existing_size == entry["size_bytes"]
                    and existing_mtime == entry["mtime_epoch"]
                ):
                    skipped += 1
                    continue

            # Check if row exists to distinguish insert vs update
            is_new = rel_norm not in existing_lookup

            # Upsert — use raw execute to stay inside the open transaction
            # (SampleRepo.upsert commits individually, so we inline the SQL)
            db.execute(
                "INSERT INTO sample "
                "  (library_root_id, rel_path, rel_path_norm, filename, ext, "
                "   size_bytes, mtime_epoch) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(library_root_id, rel_path_norm) DO UPDATE SET "
                "  filename = excluded.filename, "
                "  ext = excluded.ext, "
                "  size_bytes = excluded.size_bytes, "
                "  mtime_epoch = excluded.mtime_epoch, "
                "  updated_at = datetime('now')",
                (
                    library_root_id,
                    entry["rel_path"],
                    rel_norm,
                    entry["filename"],
                    entry["ext"],
                    entry["size_bytes"],
                    entry["mtime_epoch"],
                ),
            )

            if is_new:
                inserted += 1
            else:
                updated += 1

    # Prune deleted files if rescan requested
    pruned = 0
    if rescan:
        pruned = sample_repo.delete_stale(library_root_id, scanned_norms)

    return ScanResult(
        library_root_id=library_root_id,
        total_on_disk=total_on_disk,
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        pruned=pruned,
    )
