"""Fixtures for the offscreen Qt GUI test suite.

Forces the ``offscreen`` Qt platform plugin so the tests run headless in CI and
locally without a display server. This must be set before ``QApplication`` is
constructed, so it is applied at import time.
"""

import os
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

from sample_manager.db import Db
from sample_manager.migrations import apply_migrations
from sample_manager.normalize import norm_abs_path, norm_rel_path
from sample_manager.services.library_browser import LibraryBrowserService


@pytest.fixture
def browser_db():
    """In-memory DB with all migrations applied."""
    db = Db(":memory:")
    db.connect()
    apply_migrations(db)
    yield db
    db.close()


@pytest.fixture
def populated_service(browser_db, tmp_path):
    """A LibraryBrowserService with a library root, some files, and samples.

    Creates a real directory tree so ``list_directory`` (which scandirs the
    filesystem) returns items, and inserts matching ``sample`` rows so files
    are enriched with sample ids.
    """
    root_dir = tmp_path / "library"
    (root_dir / "drums").mkdir(parents=True)
    kick = root_dir / "drums" / "kick.wav"
    snare = root_dir / "drums" / "snare.wav"
    # These files are also read by waveform workers in integration tests, so
    # give the decoder real PCM data instead of an incomplete RIFF header.
    for audio_path in (kick, snare):
        with wave.open(str(audio_path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\x00\x00" * 800)

    browser_db.execute(
        "INSERT INTO library_root (path, path_norm) VALUES (?, ?)",
        (str(root_dir), norm_abs_path(root_dir)),
    )
    root_id = browser_db.fetchval("SELECT id FROM library_root LIMIT 1")

    for f in (kick, snare):
        rel = f.relative_to(root_dir)
        browser_db.execute(
            "INSERT INTO sample "
            "(library_root_id, rel_path, rel_path_norm, filename, ext, size_bytes, mtime_epoch) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                root_id,
                str(rel),
                # Match scanner keys on Windows as well as POSIX hosts.
                norm_rel_path(rel),
                f.name,
                "wav",
                f.stat().st_size,
                0,
            ),
        )
    browser_db.conn.commit()

    service = LibraryBrowserService(browser_db)
    return service, Path(root_dir)
