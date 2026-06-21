"""Tests for ArrangementRepo."""

import sqlite3

import pytest

from sample_manager.repos.arrangement_repo import ArrangementRepo


@pytest.fixture
def arrangement_repo(db):
    return ArrangementRepo(db)


class TestArrangementRepo:
    def test_create(self, arrangement_repo):
        row = arrangement_repo.create("My Set", "default-monolithic")
        assert row["id"] is not None
        assert row["name"] == "My Set"
        assert row["name_norm"] == "my set"
        assert row["profile_name"] == "default-monolithic"
        assert row["sample_count"] == 0

    def test_unique_name_norm(self, arrangement_repo):
        arrangement_repo.create("My Set", "default-monolithic")
        with pytest.raises(sqlite3.IntegrityError):
            arrangement_repo.create("my set", "another-profile")

    def test_get_by_name_case_insensitive(self, arrangement_repo):
        arrangement_repo.create("Drum Batch", "default-monolithic")
        row = arrangement_repo.get_by_name("drum batch")
        assert row is not None
        assert row["name"] == "Drum Batch"

    def test_list_all_sorted_by_name_norm(self, arrangement_repo):
        arrangement_repo.create("ZZZ", "p1")
        arrangement_repo.create("AAA", "p1")
        names = [r["name"] for r in arrangement_repo.list_all()]
        assert names == ["AAA", "ZZZ"]

    def test_add_samples_idempotent(self, arrangement_repo, db, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        db.execute(
            "INSERT INTO library_root (path, path_norm) VALUES (?, ?)",
            (str(lib), str(lib).lower()),
        )
        root_id = db.fetchval("SELECT id FROM library_root")
        db.execute(
            "INSERT INTO sample (library_root_id, rel_path, rel_path_norm, filename) "
            "VALUES (?, ?, ?, ?)",
            (root_id, "a.wav", "a.wav", "a.wav"),
        )
        sample_id = db.fetchval("SELECT id FROM sample")
        db.conn.commit()

        arr = arrangement_repo.create("Attach Test", "p1")
        inserted_first = arrangement_repo.add_samples(arr["id"], [sample_id])
        inserted_second = arrangement_repo.add_samples(arr["id"], [sample_id])

        assert inserted_first == 1
        assert inserted_second == 0

    def test_remove_samples(self, arrangement_repo, db, tmp_path):
        lib = tmp_path / "lib2"
        lib.mkdir()
        db.execute(
            "INSERT INTO library_root (path, path_norm) VALUES (?, ?)",
            (str(lib), str(lib).lower()),
        )
        root_id = db.fetchval("SELECT id FROM library_root")
        db.execute(
            "INSERT INTO sample (library_root_id, rel_path, rel_path_norm, filename) "
            "VALUES (?, ?, ?, ?)",
            (root_id, "b.wav", "b.wav", "b.wav"),
        )
        sample_id = db.fetchval("SELECT id FROM sample")
        db.conn.commit()

        arr = arrangement_repo.create("Detach Test", "p1")
        arrangement_repo.add_samples(arr["id"], [sample_id])
        removed = arrangement_repo.remove_samples(arr["id"], [sample_id])
        assert removed == 1
        assert arrangement_repo.list_sample_ids(arr["id"]) == []

    def test_list_samples(self, arrangement_repo, db, tmp_path):
        lib = tmp_path / "lib3"
        lib.mkdir()
        db.execute(
            "INSERT INTO library_root (path, path_norm) VALUES (?, ?)",
            (str(lib), str(lib).lower()),
        )
        root_id = db.fetchval("SELECT id FROM library_root")
        db.execute(
            "INSERT INTO sample (library_root_id, rel_path, rel_path_norm, filename, ext) "
            "VALUES (?, ?, ?, ?, ?)",
            (root_id, "c.wav", "c.wav", "c.wav", ".wav"),
        )
        sample_id = db.fetchval("SELECT id FROM sample")
        db.conn.commit()

        arr = arrangement_repo.create("List Test", "p1")
        arrangement_repo.add_samples(arr["id"], [sample_id])
        rows = arrangement_repo.list_samples(arr["id"])
        assert len(rows) == 1
        assert rows[0]["id"] == sample_id
        assert "library_root_path" in rows[0]
