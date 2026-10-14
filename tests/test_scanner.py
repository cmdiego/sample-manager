"""Tests for Phase 3: Scanner + scan/status CLI commands.

Covers:
  - collect_samples (pure function)
  - scan_library (integration with DB)
  - CLI: `sample scan` and `sample status`
"""

import os
import time
from pathlib import Path

import pytest

from sample_manager.db import Db
from sample_manager.migrations import apply_migrations
from sample_manager.scanner import (
    DEFAULT_SAMPLE_EXTENSIONS,
    ScanResult,
    collect_samples,
    scan_library,
)
from sample_manager.repos.sample_repo import SampleRepo
from sample_manager.repos.library_root_repo import LibraryRootRepo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def library_dir(tmp_path):
    """Create a temp library root with a mix of audio and non-audio files."""
    # Audio files in subdirectories
    kicks = tmp_path / "kicks"
    kicks.mkdir()
    (kicks / "kick01.wav").write_bytes(b"\x00" * 1024)
    (kicks / "kick02.wav").write_bytes(b"\x00" * 2048)

    snares = tmp_path / "snares"
    snares.mkdir()
    (snares / "snare01.aif").write_bytes(b"\x00" * 1024)

    loops = tmp_path / "loops"
    loops.mkdir()
    (loops / "beat.flac").write_bytes(b"\x00" * 4096)

    # Non-audio files (should be excluded)
    (tmp_path / "README.txt").write_text("not a sample")
    (tmp_path / "notes.pdf").write_bytes(b"%PDF")

    return tmp_path


@pytest.fixture
def scan_db(tmp_path):
    """Fresh SQLite DB with schema applied, separate from library_dir."""
    db_path = tmp_path / "db" / "test.sqlite3"
    database = Db(db_path)
    database.connect()
    apply_migrations(database)
    yield database
    database.close()


# ---------------------------------------------------------------------------
# collect_samples (pure function)
# ---------------------------------------------------------------------------

class TestCollectSamples:
    """Tests for the pure collect_samples function."""

    def test_finds_audio_files(self, library_dir):
        results = collect_samples(library_dir)
        assert len(results) == 4  # kick01, kick02, snare01, beat

    def test_excludes_non_audio_files(self, library_dir):
        results = collect_samples(library_dir)
        filenames = {r["filename"] for r in results}
        assert "README.txt" not in filenames
        assert "notes.pdf" not in filenames

    def test_indexes_wave_extension_supported_by_decoder(self, library_dir):
        """The long WAV extension must not disappear from GUI search."""
        sample = library_dir / "FL_FDS_09_Drum_Loop_Full_98.wave"
        sample.write_bytes(b"RIFF")

        names = {entry["filename"] for entry in collect_samples(library_dir)}

        assert sample.name in names

    def test_returns_correct_metadata(self, library_dir):
        results = collect_samples(library_dir)
        by_name = {r["filename"]: r for r in results}

        kick01 = by_name["kick01.wav"]
        assert kick01["ext"] == ".wav"
        assert kick01["size_bytes"] == 1024
        assert kick01["mtime_epoch"] > 0
        # rel_path should be relative to root, using OS separator
        assert kick01["rel_path"] == str(Path("kicks") / "kick01.wav")

        beat = by_name["beat.flac"]
        assert beat["ext"] == ".flac"
        assert beat["size_bytes"] == 4096

    def test_ext_is_lowercase(self, library_dir):
        """Extension should be normalized to lowercase."""
        # Create a file with uppercase extension
        (library_dir / "HI.WAV").write_bytes(b"\x00" * 512)
        results = collect_samples(library_dir)
        by_name = {r["filename"]: r for r in results}
        assert by_name["HI.WAV"]["ext"] == ".wav"

    def test_custom_extensions(self, library_dir):
        """Custom extension set should filter accordingly."""
        results = collect_samples(library_dir, extensions=frozenset({".wav"}))
        assert len(results) == 2  # only kick01.wav and kick02.wav
        for r in results:
            assert r["ext"] == ".wav"

    def test_empty_directory(self, tmp_path):
        results = collect_samples(tmp_path)
        assert results == []

    def test_nested_subdirectories(self, tmp_path):
        """Deeply nested files should be found."""
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.wav").write_bytes(b"\x00" * 100)
        results = collect_samples(tmp_path)
        assert len(results) == 1
        assert results[0]["filename"] == "deep.wav"
        expected_rel = str(Path("a") / "b" / "c" / "deep.wav")
        assert results[0]["rel_path"] == expected_rel


# ---------------------------------------------------------------------------
# scan_library (integration with DB)
# ---------------------------------------------------------------------------

class TestScanLibrary:
    """Integration tests: scan_library persists to SQLite."""

    def test_scan_inserts_expected_count(self, library_dir, scan_db):
        result = scan_library(scan_db, str(library_dir))
        assert isinstance(result, ScanResult)
        assert result.total_on_disk == 4
        assert result.inserted == 4
        assert result.updated == 0
        assert result.skipped == 0
        assert result.pruned == 0

        # Verify DB state
        sample_repo = SampleRepo(scan_db)
        assert sample_repo.count_by_root(result.library_root_id) == 4

    def test_scan_creates_library_root(self, library_dir, scan_db):
        result = scan_library(scan_db, str(library_dir))
        root_repo = LibraryRootRepo(scan_db)
        root = root_repo.get_by_id(result.library_root_id)
        assert root is not None
        assert Path(root["path"]) == library_dir.resolve()

    def test_scan_idempotent(self, library_dir, scan_db):
        """Scanning the same directory twice without --rescan keeps the count."""
        r1 = scan_library(scan_db, str(library_dir))
        assert r1.inserted == 4

        r2 = scan_library(scan_db, str(library_dir))
        # Second scan: all rows exist already, so they're updates
        assert r2.inserted == 0
        assert r2.updated == 4
        assert r2.skipped == 0

        sample_repo = SampleRepo(scan_db)
        assert sample_repo.count_by_root(r1.library_root_id) == 4

    def test_rescan_updates_mtime_size(self, library_dir, scan_db):
        """Modify a file's content (change size), rescan, verify updated values."""
        scan_library(scan_db, str(library_dir))

        # Modify kick01.wav — change size
        kick = library_dir / "kicks" / "kick01.wav"
        kick.write_bytes(b"\xff" * 9999)

        result = scan_library(scan_db, str(library_dir), rescan=True)
        assert result.updated >= 1

        # Verify updated metadata in DB
        sample_repo = SampleRepo(scan_db)
        samples = sample_repo.list_by_root(result.library_root_id)
        by_name = {s["filename"]: s for s in samples}
        assert by_name["kick01.wav"]["size_bytes"] == 9999

    def test_rescan_prunes_deleted_files(self, library_dir, scan_db):
        """Scan, delete a file, rescan with --rescan, verify pruned."""
        scan_library(scan_db, str(library_dir))

        # Delete one file from disk
        (library_dir / "snares" / "snare01.aif").unlink()

        result = scan_library(scan_db, str(library_dir), rescan=True)
        assert result.pruned == 1
        assert result.total_on_disk == 3

        sample_repo = SampleRepo(scan_db)
        assert sample_repo.count_by_root(result.library_root_id) == 3

    def test_rescan_prunes_multiple(self, library_dir, scan_db):
        """Delete multiple files, rescan prunes all of them."""
        scan_library(scan_db, str(library_dir))

        (library_dir / "kicks" / "kick01.wav").unlink()
        (library_dir / "kicks" / "kick02.wav").unlink()
        (library_dir / "snares" / "snare01.aif").unlink()

        result = scan_library(scan_db, str(library_dir), rescan=True)
        assert result.pruned == 3
        assert result.total_on_disk == 1

        sample_repo = SampleRepo(scan_db)
        assert sample_repo.count_by_root(result.library_root_id) == 1

    def test_scan_without_rescan_does_not_prune(self, library_dir, scan_db):
        """Without --rescan, deleted files remain in DB."""
        scan_library(scan_db, str(library_dir))
        (library_dir / "snares" / "snare01.aif").unlink()

        result = scan_library(scan_db, str(library_dir))
        assert result.pruned == 0

        sample_repo = SampleRepo(scan_db)
        # Still 4 in DB even though only 3 on disk
        assert sample_repo.count_by_root(result.library_root_id) == 4

    def test_fast_skips_unchanged(self, library_dir, scan_db):
        """Fast mode skips all files when nothing changed."""
        scan_library(scan_db, str(library_dir))

        result = scan_library(scan_db, str(library_dir), fast=True)
        assert result.skipped == 4
        assert result.inserted == 0
        assert result.updated == 0

    def test_fast_detects_changed(self, library_dir, scan_db):
        """Fast mode detects a changed file and re-upserts it."""
        scan_library(scan_db, str(library_dir))

        # Modify one file (change size to force a difference)
        kick = library_dir / "kicks" / "kick01.wav"
        kick.write_bytes(b"\xff" * 7777)

        result = scan_library(scan_db, str(library_dir), fast=True)
        assert result.skipped == 3
        assert result.updated == 1  # kick01.wav existed, now updated

        sample_repo = SampleRepo(scan_db)
        samples = sample_repo.list_by_root(result.library_root_id)
        by_name = {s["filename"]: s for s in samples}
        assert by_name["kick01.wav"]["size_bytes"] == 7777

    def test_fast_detects_new_file(self, library_dir, scan_db):
        """Fast mode inserts a new file that wasn't in the DB before."""
        scan_library(scan_db, str(library_dir))

        # Add a new file
        (library_dir / "kicks" / "kick03.wav").write_bytes(b"\x00" * 500)

        result = scan_library(scan_db, str(library_dir), fast=True)
        assert result.skipped == 4
        assert result.inserted == 1

        sample_repo = SampleRepo(scan_db)
        assert sample_repo.count_by_root(result.library_root_id) == 5

    def test_path_not_found_raises(self, scan_db):
        with pytest.raises(FileNotFoundError):
            scan_library(scan_db, "/nonexistent/path/xyz")

    def test_path_not_directory_raises(self, tmp_path, scan_db):
        f = tmp_path / "afile.txt"
        f.write_text("hi")
        with pytest.raises(NotADirectoryError):
            scan_library(scan_db, str(f))

    def test_sample_metadata_columns(self, library_dir, scan_db):
        """Verify all expected columns are stored correctly."""
        result = scan_library(scan_db, str(library_dir))
        sample_repo = SampleRepo(scan_db)
        samples = sample_repo.list_by_root(result.library_root_id)

        for s in samples:
            assert s["library_root_id"] == result.library_root_id
            assert s["filename"] is not None
            assert s["rel_path"] is not None
            assert s["rel_path_norm"] is not None
            assert s["ext"] is not None
            assert s["size_bytes"] is not None
            assert s["size_bytes"] >= 0
            assert s["mtime_epoch"] is not None
            assert s["mtime_epoch"] > 0
            # ext should be lowercase
            assert s["ext"] == s["ext"].lower()


# ---------------------------------------------------------------------------
# Repo additions (delete_stale, count_by_root, count_all, count)
# ---------------------------------------------------------------------------

class TestRepoAdditions:
    """Tests for the new repo methods added in Phase 3."""

    def test_count_by_root(self, library_dir, scan_db):
        result = scan_library(scan_db, str(library_dir))
        sample_repo = SampleRepo(scan_db)
        assert sample_repo.count_by_root(result.library_root_id) == 4

    def test_count_by_root_empty(self, scan_db):
        sample_repo = SampleRepo(scan_db)
        root_repo = LibraryRootRepo(scan_db)
        # count_by_root for a non-existent root should return 0
        assert sample_repo.count_by_root(9999) == 0

    def test_count_all(self, library_dir, scan_db):
        scan_library(scan_db, str(library_dir))
        sample_repo = SampleRepo(scan_db)
        assert sample_repo.count_all() == 4

    def test_count_all_empty(self, scan_db):
        sample_repo = SampleRepo(scan_db)
        assert sample_repo.count_all() == 0

    def test_library_root_count(self, library_dir, scan_db):
        root_repo = LibraryRootRepo(scan_db)
        assert root_repo.count() == 0
        scan_library(scan_db, str(library_dir))
        assert root_repo.count() == 1

    def test_delete_stale_empty_valid_set(self, library_dir, scan_db):
        """When valid_norms is empty, all samples for the root are deleted."""
        result = scan_library(scan_db, str(library_dir))
        sample_repo = SampleRepo(scan_db)
        deleted = sample_repo.delete_stale(result.library_root_id, set())
        assert deleted == 4
        assert sample_repo.count_by_root(result.library_root_id) == 0

    def test_delete_stale_no_stale(self, library_dir, scan_db):
        """When all norms are valid, nothing is deleted."""
        result = scan_library(scan_db, str(library_dir))
        sample_repo = SampleRepo(scan_db)
        samples = sample_repo.list_by_root(result.library_root_id)
        all_norms = {s["rel_path_norm"] for s in samples}
        deleted = sample_repo.delete_stale(result.library_root_id, all_norms)
        assert deleted == 0
        assert sample_repo.count_by_root(result.library_root_id) == 4


# ---------------------------------------------------------------------------
# CLI commands (end-to-end via CliRunner)
# ---------------------------------------------------------------------------

class TestCLIScan:
    """End-to-end CLI tests for `sample scan` and `sample status`."""

    @pytest.fixture(autouse=True)
    def _patch_config(self, tmp_path, monkeypatch):
        """Redirect config path for all CLI tests in this class."""
        from sample_manager import config as config_module

        self._config_dir = tmp_path / "cli_home" / ".sample_manager"
        self._config_path = self._config_dir / "config.yaml"
        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", self._config_path)
        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_DIR", self._config_dir)

    def _setup_config(self, db_path):
        """Write a minimal config.yaml pointing at the given db_path."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        import yaml
        config = {
            "db_path": str(db_path),
            "library_roots": [],
            "default_library_root": None,
            "defaults": {
                "export_mode": "copy",
                "collision_policy": "suffix",
                "on_violation": "autofix",
                "preview_format": "table",
                "confirmations": True,
            },
        }
        self._config_path.write_text(yaml.safe_dump(config))

    def test_scan_success(self, tmp_path, cli_runner, library_dir):
        from sample_manager.cli import app

        db_path = tmp_path / "db" / "test.sqlite3"
        self._setup_config(db_path)

        result = cli_runner.invoke(app, ["scan", str(library_dir)])
        assert result.exit_code == 0
        assert "Scanned 4 files" in result.output
        assert "inserted: 4" in result.output

    def test_scan_nonexistent_path(self, tmp_path, cli_runner):
        from sample_manager.cli import app

        db_path = tmp_path / "db" / "test.sqlite3"
        self._setup_config(db_path)

        result = cli_runner.invoke(app, ["scan", "/nonexistent/path/xyz"])
        assert result.exit_code != 0

    def test_scan_rescan(self, tmp_path, cli_runner, library_dir):
        from sample_manager.cli import app

        db_path = tmp_path / "db" / "test.sqlite3"
        self._setup_config(db_path)

        # Initial scan
        cli_runner.invoke(app, ["scan", str(library_dir)])

        # Delete a file, rescan
        (library_dir / "loops" / "beat.flac").unlink()
        result = cli_runner.invoke(app, ["scan", str(library_dir), "--rescan"])
        assert result.exit_code == 0
        assert "pruned: 1" in result.output

    def test_scan_fast(self, tmp_path, cli_runner, library_dir):
        from sample_manager.cli import app

        db_path = tmp_path / "db" / "test.sqlite3"
        self._setup_config(db_path)

        # Initial scan
        cli_runner.invoke(app, ["scan", str(library_dir)])

        # Fast rescan — all unchanged
        result = cli_runner.invoke(app, ["scan", str(library_dir), "--fast"])
        assert result.exit_code == 0
        assert "skipped: 4" in result.output

    def test_status(self, tmp_path, cli_runner, library_dir):
        from sample_manager.cli import app

        db_path = tmp_path / "db" / "test.sqlite3"
        self._setup_config(db_path)

        # Scan first
        cli_runner.invoke(app, ["scan", str(library_dir)])

        result = cli_runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Library roots: 1" in result.output
        assert "Total samples: 4" in result.output
        assert "4 samples" in result.output  # per-root breakdown

    def test_status_empty(self, tmp_path, cli_runner):
        from sample_manager.cli import app

        db_path = tmp_path / "db" / "test.sqlite3"
        self._setup_config(db_path)

        result = cli_runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Library roots: 0" in result.output
        assert "Total samples: 0" in result.output

    def test_status_no_config(self, cli_runner):
        """Status without config should fail gracefully."""
        from sample_manager.cli import app

        # _patch_config already redirected to nonexistent path, no _setup_config called
        result = cli_runner.invoke(app, ["status"])
        assert result.exit_code != 0

    def test_scan_no_config(self, cli_runner, library_dir):
        """Scan without config should fail gracefully."""
        from sample_manager.cli import app

        # _patch_config already redirected to nonexistent path, no _setup_config called
        result = cli_runner.invoke(app, ["scan", str(library_dir)])
        assert result.exit_code != 0
