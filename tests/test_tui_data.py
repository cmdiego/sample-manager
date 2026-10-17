"""Unit tests for tui/data.py — TuiDataSource query methods.

Tests the two methods added in the 4-zone layout redesign:
  - get_selection_total_size()
  - get_active_destination()

Uses the shared `db` fixture (in-memory SQLite with all migrations applied).
get_active_destination() reads DEFAULT_CONFIG_PATH, which is monkeypatched
using the same three-patch isolation pattern established in test_e2e_lifecycle.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sample_manager import config as config_module
from sample_manager.tui.data import TuiDataSource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_sample(db, root_id: int, filename: str, size_bytes: int) -> int:
    """Insert a minimal sample row and return its id."""
    rel = filename
    db.execute(
        "INSERT INTO sample (library_root_id, rel_path, rel_path_norm, filename, size_bytes)"
        " VALUES (?, ?, ?, ?, ?)",
        (root_id, rel, rel.lower(), filename, size_bytes),
    )
    return db.fetchval("SELECT last_insert_rowid()")


def _insert_root(db, path: str = "/lib") -> int:
    """Insert a library_root row and return its id."""
    db.execute(
        "INSERT INTO library_root (path, path_norm) VALUES (?, ?)",
        (path, path.lower()),
    )
    return db.fetchval("SELECT last_insert_rowid()")


def _add_to_selection(db, sample_id: int) -> None:
    db.execute("INSERT INTO selection_sample (sample_id) VALUES (?)", (sample_id,))


# ---------------------------------------------------------------------------
# get_selection_total_size()
# ---------------------------------------------------------------------------


class TestGetSelectionTotalSize:
    def test_returns_zero_when_selection_is_empty(self, db):
        ds = TuiDataSource(db)
        assert ds.get_selection_total_size() == 0

    def test_returns_zero_when_samples_exist_but_none_selected(self, db):
        root_id = _insert_root(db)
        _insert_sample(db, root_id, "kick.wav", 1000)
        # nothing added to selection_sample
        ds = TuiDataSource(db)
        assert ds.get_selection_total_size() == 0

    def test_returns_size_for_single_selected_sample(self, db):
        root_id = _insert_root(db)
        s1 = _insert_sample(db, root_id, "kick.wav", 4096)
        _add_to_selection(db, s1)
        ds = TuiDataSource(db)
        assert ds.get_selection_total_size() == 4096

    def test_returns_sum_for_multiple_selected_samples(self, db):
        root_id = _insert_root(db)
        s1 = _insert_sample(db, root_id, "kick.wav", 1000)
        s2 = _insert_sample(db, root_id, "snare.wav", 2000)
        _add_to_selection(db, s1)
        _add_to_selection(db, s2)
        ds = TuiDataSource(db)
        assert ds.get_selection_total_size() == 3000

    def test_only_counts_selected_samples_not_all_samples(self, db):
        root_id = _insert_root(db)
        s1 = _insert_sample(db, root_id, "kick.wav", 500)
        _insert_sample(db, root_id, "snare.wav", 9999)  # NOT selected
        _add_to_selection(db, s1)
        ds = TuiDataSource(db)
        assert ds.get_selection_total_size() == 500

    def test_returns_int_not_none(self, db):
        ds = TuiDataSource(db)
        result = ds.get_selection_total_size()
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# get_active_destination()
# ---------------------------------------------------------------------------


class TestGetActiveDestination:
    def test_returns_none_when_config_file_does_not_exist(
        self, db, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            config_module, "DEFAULT_CONFIG_PATH", tmp_path / "no_config.yaml"
        )
        ds = TuiDataSource(db)
        assert ds.get_active_destination() is None

    def test_returns_none_when_export_profiles_file_is_absent(
        self, db, tmp_path, monkeypatch
    ):
        """Config exists and profiles_dir exists, but export_profiles.yaml is missing."""
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

        monkeypatch.setenv("HOME", str(tmp_path))
        # Windows expands ~ from USERPROFILE rather than HOME.
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

        ds = TuiDataSource(db)
        assert ds.get_active_destination() is None

    def test_returns_destination_from_first_export_profile(
        self, db, tmp_path, monkeypatch
    ):
        """Config + export_profiles.yaml present with default_dest → returns the dest."""
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

        ep_file = profiles_dir / "export_profiles.yaml"
        with open(ep_file, "w") as f:
            yaml.safe_dump(
                [
                    {
                        "name": "default-export",
                        "default_dest": str(tmp_path / "exports"),
                    }
                ],
                f,
            )

        monkeypatch.setenv("HOME", str(tmp_path))
        # Windows expands ~ from USERPROFILE rather than HOME.
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

        ds = TuiDataSource(db)
        result = ds.get_active_destination()
        assert result == str(tmp_path / "exports")
