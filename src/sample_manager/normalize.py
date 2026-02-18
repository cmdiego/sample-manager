"""Normalization functions for Sample Manager.

Pure functions for case-insensitive text and path normalization.
Used to compute *_norm columns stored in SQLite for uniqueness constraints.

Per docs/01-data-model.md §5:
- Tag-like strings: strip, lowercase, collapse internal whitespace.
- Paths: platform-safe canonicalization with forward slashes.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath


_WHITESPACE_RUN = re.compile(r"\s+")


def norm_text(s: str) -> str:
    """Normalize tag-like text for case-insensitive uniqueness.

    Rules:
      1. Strip leading/trailing whitespace.
      2. Lowercase.
      3. Collapse internal runs of whitespace to a single space.

    Examples:
        "  Kick  Drum " -> "kick drum"
        "HI-HAT" -> "hi-hat"
    """
    return _WHITESPACE_RUN.sub(" ", s.strip()).lower()


def norm_rel_path(p: str | Path) -> str:
    """Normalize a relative path for stable storage in sample.rel_path_norm.

    Rules:
      1. Convert to forward slashes (POSIX separators) for cross-platform consistency.
      2. Lowercase for case-insensitive matching.
      3. Strip trailing separators.
      4. Collapse redundant separators / resolve . and .. segments.

    The input must be a relative path; absolute paths are rejected.
    """
    path = Path(p)
    if path.is_absolute():
        raise ValueError(f"Expected relative path, got absolute: {p}")
    # os.path.normpath resolves . and .. segments without requiring absolute path
    normed = os.path.normpath(str(path))
    # Rebuild with PurePosixPath for forward slashes on all platforms
    parts = Path(normed).parts
    posix = "/".join(parts)
    return posix.lower()


def norm_abs_path(p: str | Path) -> str:
    """Normalize an absolute path for library_root.path_norm.

    Rules:
      1. Expand ~ and environment variables.
      2. Resolve to absolute (resolve symlinks where possible).
      3. Lowercase for case-insensitive matching.
      4. Convert to forward slashes (POSIX separators).

    Returns a string suitable for unique constraint comparison.
    """
    expanded = os.path.expanduser(os.path.expandvars(str(p)))
    resolved = Path(expanded).resolve()
    # Convert to forward-slash string and lowercase
    posix = resolved.as_posix()
    return posix.lower()
