"""Unit tests for services/library_browser.py — LibraryBrowserService + DTOs.

Uses the shared in-memory `db` fixture. Verifies the framework-neutral public
interface returns typed immutable DTOs while preserving directory ordering,
hidden-file handling, sample IDs, and persistent selection behaviour.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from sample_manager import config as config_module
from sample_manager.services.library_browser import (
    BrowserItem,
    LibraryBrowserService,
    LibraryRoot,
    SampleDetails,
    SelectionSummary,
)


def _insert_root(db, path: str) -> int:
    db.execute(
        "INSERT INTO library_root (path, path_norm) VALUES (?, ?)",
        (path, path.lower()),
    )
    return db.fetchval("SELECT last_insert_rowid()")


def _insert_sample(db, root_id: int, rel: str, size_bytes: int = 0) -> int:
    filename = rel.rsplit("/", 1)[-1]
    db.execute(
        "INSERT INTO sample (library_root_id, rel_path, rel_path_norm, filename, size_bytes)"
        " VALUES (?, ?, ?, ?, ?)",
        (root_id, rel, rel.lower(), filename, size_bytes),
    )
    return db.fetchval("SELECT last_insert_rowid()")


def _add_to_selection(db, sample_id: int) -> None:
    db.execute("INSERT INTO selection_sample (sample_id) VALUES (?)", (sample_id,))


class TestLibraryRoots:
    def test_returns_frozen_dtos(self, db, tmp_path):
        _insert_root(db, str(tmp_path))
        roots = LibraryBrowserService(db).library_roots()
        assert len(roots) == 1
        assert isinstance(roots[0], LibraryRoot)
        assert roots[0].path == tmp_path

    def test_empty_when_no_roots(self, db):
        assert LibraryBrowserService(db).library_roots() == ()


class TestListDirectory:
    def test_orders_dirs_before_files_and_hides_dotfiles(self, db, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        _insert_root(db, str(lib))
        (lib / "b_dir").mkdir()
        (lib / "a_file.wav").touch()
        (lib / ".hidden").touch()
        items = LibraryBrowserService(db).list_directory(lib)
        assert all(isinstance(i, BrowserItem) for i in items)
        assert [i.name for i in items] == ["b_dir", "a_file.wav"]

    def test_enriches_indexed_file_with_sample_id_and_selection(self, db, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        root_id = _insert_root(db, str(lib))
        (lib / "kick.wav").touch()
        sid = _insert_sample(db, root_id, "kick.wav")
        _add_to_selection(db, sid)
        (item,) = LibraryBrowserService(db).list_directory(lib)
        assert item.sample_id == sid
        assert item.is_selected is True

    def test_unindexed_file_has_no_sample_id(self, db, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        _insert_root(db, str(lib))
        (lib / "loose.wav").touch()
        (item,) = LibraryBrowserService(db).list_directory(lib)
        assert item.sample_id is None
        assert item.is_selected is False

    def test_path_outside_any_root_still_lists_without_sample_ids(self, db, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        # No library_root inserted → path not under a known root.
        (lib / "x.wav").touch()
        (item,) = LibraryBrowserService(db).list_directory(lib)
        assert item.sample_id is None

    def test_nested_directory_resolves_sample_id(self, db, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        root_id = _insert_root(db, str(lib))
        sub = lib / "drums"
        sub.mkdir()
        (sub / "snare.wav").touch()
        sid = _insert_sample(db, root_id, "drums/snare.wav")
        (item,) = LibraryBrowserService(db).list_directory(sub)
        assert item.sample_id == sid


class TestSampleDetails:
    def test_returns_dto_for_existing_sample(self, db, tmp_path):
        root_id = _insert_root(db, str(tmp_path))
        sid = _insert_sample(db, root_id, "kick.wav", size_bytes=2048)
        details = LibraryBrowserService(db).sample_details(sid)
        assert isinstance(details, SampleDetails)
        assert details.id == sid
        assert details.filename == "kick.wav"
        assert details.size_bytes == 2048
        assert details.library_root_id == root_id

    def test_returns_none_for_missing_sample(self, db):
        assert LibraryBrowserService(db).sample_details(9999) is None


class TestSelection:
    def test_add_and_remove_round_trip(self, db, tmp_path):
        root_id = _insert_root(db, str(tmp_path))
        sid = _insert_sample(db, root_id, "kick.wav")
        svc = LibraryBrowserService(db)

        svc.add_to_selection(sid)
        assert {s.id for s in svc.selected_samples()} == {sid}

        svc.remove_from_selection(sid)
        assert svc.selected_samples() == ()

    def test_add_is_idempotent(self, db, tmp_path):
        root_id = _insert_root(db, str(tmp_path))
        sid = _insert_sample(db, root_id, "kick.wav")
        svc = LibraryBrowserService(db)
        svc.add_to_selection(sid)
        svc.add_to_selection(sid)
        assert len(svc.selected_samples()) == 1

    def test_selected_samples_returns_dtos(self, db, tmp_path):
        root_id = _insert_root(db, str(tmp_path))
        sid = _insert_sample(db, root_id, "kick.wav")
        svc = LibraryBrowserService(db)
        svc.add_to_selection(sid)
        (dto,) = svc.selected_samples()
        assert isinstance(dto, SampleDetails)
        assert dto.filename == "kick.wav"


class TestSelectionSummary:
    def test_empty_summary(self, db, tmp_path, monkeypatch):
        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", tmp_path / "none.yaml")
        summary = LibraryBrowserService(db).selection_summary()
        assert isinstance(summary, SelectionSummary)
        assert summary.count == 0
        assert summary.total_bytes == 0
        assert summary.destination is None

    def test_summary_counts_and_sums_selected(self, db, tmp_path, monkeypatch):
        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", tmp_path / "none.yaml")
        root_id = _insert_root(db, str(tmp_path))
        s1 = _insert_sample(db, root_id, "kick.wav", size_bytes=1000)
        s2 = _insert_sample(db, root_id, "snare.wav", size_bytes=2000)
        _insert_sample(db, root_id, "hat.wav", size_bytes=9999)  # not selected
        _add_to_selection(db, s1)
        _add_to_selection(db, s2)
        summary = LibraryBrowserService(db).selection_summary()
        assert summary.count == 2
        assert summary.total_bytes == 3000

    def test_summary_reports_destination_from_export_profile(self, db, tmp_path, monkeypatch):
        config_dir = tmp_path / ".sample_manager"
        config_dir.mkdir()
        profiles_dir = config_dir / "profiles"
        profiles_dir.mkdir()
        config_path = config_dir / "config.yaml"
        with open(config_path, "w") as f:
            yaml.safe_dump(
                {
                    "db_path": str(config_dir / "sample_manager.sqlite3"),
                    "library_roots": [],
                    "default_library_root": None,
                    "profiles_dir": str(profiles_dir),
                },
                f,
            )
        with open(profiles_dir / "export_profiles.yaml", "w") as f:
            yaml.safe_dump([{"name": "d", "default_dest": str(tmp_path / "exports")}], f)

        monkeypatch.setenv("HOME", str(tmp_path))
        # Windows expands ~ from USERPROFILE rather than HOME.
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

        summary = LibraryBrowserService(db).selection_summary()
        assert summary.destination == str(tmp_path / "exports")
