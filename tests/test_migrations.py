"""Tests for sample_manager.migrations — schema versioning and Migration 0001."""

import pytest

from sample_manager.db import Db
from sample_manager.migrations import ensure_schema_version, apply_migrations


class TestEnsureSchemaVersion:
    def test_creates_table_and_seeds_zero(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            version = ensure_schema_version(db)
            assert version == 0

    def test_idempotent(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            v1 = ensure_schema_version(db)
            v2 = ensure_schema_version(db)
            assert v1 == v2 == 0

    def test_preserves_existing_version(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            ensure_schema_version(db)
            db.execute("UPDATE schema_version SET version = 5")
            db.conn.commit()
            v = ensure_schema_version(db)
            assert v == 5


class TestApplyMigrations:
    def test_fresh_db_reaches_version_4(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            final = apply_migrations(db)
            assert final == 4
            stored = db.fetchval("SELECT version FROM schema_version")
            assert stored == 4

    def test_idempotent_double_apply(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            apply_migrations(db)
            final = apply_migrations(db)
            assert final == 4

    def test_all_tables_exist(self, tmp_path):
        expected_tables = {
            "schema_version",
            "library_root",
            "sample",
            "tag",
            "tag_alias",
            "sample_tag",
            "tag_parent",
            "arrangement",
            "arrangement_sample",
            "selection_sample",
            "export_run",
            "history_entry",
        }
        with Db(tmp_path / "test.sqlite3") as db:
            apply_migrations(db)
            rows = db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
            actual_tables = {r["name"] for r in rows}
            assert expected_tables == actual_tables

    def test_all_indexes_exist(self, tmp_path):
        expected_indexes = {
            # sample indexes
            "idx_sample_library_root",
            "idx_sample_rel_path_norm",
            "idx_sample_filename",
            # tag indexes
            "idx_tag_is_hidden",
            "idx_tag_name_norm",
            "idx_tag_shorthand_norm",
            # tag_alias indexes
            "idx_tag_alias_tag_id",
            "idx_tag_alias_norm",
            # sample_tag indexes
            "idx_sample_tag_tag_id",
            "idx_sample_tag_sample_id",
            # tag_parent indexes
            "idx_tag_parent_parent",
            "idx_tag_parent_child",
            # arrangement indexes
            "idx_arrangement_name_norm",
            "idx_arrangement_sample_arrangement_id",
            "idx_arrangement_sample_sample_id",
            # selection indexes
            "idx_selection_sample_created_at",
            # export/history indexes
            "idx_export_run_arrangement_id",
            "idx_export_run_status",
            "idx_history_entry_export_id",
        }
        with Db(tmp_path / "test.sqlite3") as db:
            apply_migrations(db)
            rows = db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name NOT LIKE 'sqlite_%'"
            )
            actual_indexes = {r["name"] for r in rows}
            # actual_indexes may include auto-created unique constraint indexes;
            # we just check that all expected indexes are present
            assert expected_indexes.issubset(actual_indexes), (
                f"Missing indexes: {expected_indexes - actual_indexes}"
            )

    def test_schema_version_starts_zero_then_four(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            v0 = ensure_schema_version(db)
            assert v0 == 0
            apply_migrations(db)
            v4 = db.fetchval("SELECT version FROM schema_version")
            assert v4 == 4


class TestMigration0001Constraints:
    """Verify key constraints from the DDL are active."""

    def test_library_root_path_norm_unique(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            apply_migrations(db)
            db.execute(
                "INSERT INTO library_root (path, path_norm) VALUES (?, ?)",
                ("/a", "/a"),
            )
            db.conn.commit()
            with pytest.raises(Exception):  # IntegrityError
                db.execute(
                    "INSERT INTO library_root (path, path_norm) VALUES (?, ?)",
                    ("/A", "/a"),
                )

    def test_sample_unique_composite(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            apply_migrations(db)
            db.execute(
                "INSERT INTO library_root (path, path_norm) VALUES (?, ?)",
                ("/lib", "/lib"),
            )
            root_id = db.fetchval("SELECT id FROM library_root WHERE path_norm = '/lib'")
            db.execute(
                "INSERT INTO sample (library_root_id, rel_path, rel_path_norm, filename) "
                "VALUES (?, ?, ?, ?)",
                (root_id, "kick.wav", "kick.wav", "kick.wav"),
            )
            db.conn.commit()
            with pytest.raises(Exception):
                db.execute(
                    "INSERT INTO sample (library_root_id, rel_path, rel_path_norm, filename) "
                    "VALUES (?, ?, ?, ?)",
                    (root_id, "Kick.wav", "kick.wav", "Kick.wav"),
                )

    def test_tag_parent_self_edge_rejected(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            apply_migrations(db)
            db.execute(
                "INSERT INTO tag (name_display, name_norm) VALUES (?, ?)",
                ("Drums", "drums"),
            )
            tag_id = db.fetchval("SELECT id FROM tag WHERE name_norm = 'drums'")
            db.conn.commit()
            with pytest.raises(Exception):  # CHECK constraint
                db.execute(
                    "INSERT INTO tag_parent (child_tag_id, parent_tag_id) VALUES (?, ?)",
                    (tag_id, tag_id),
                )

    def test_foreign_key_sample_to_library_root(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            apply_migrations(db)
            with pytest.raises(Exception):  # FK violation
                db.execute(
                    "INSERT INTO sample (library_root_id, rel_path, rel_path_norm, filename) "
                    "VALUES (?, ?, ?, ?)",
                    (9999, "kick.wav", "kick.wav", "kick.wav"),
                )

    def test_tag_is_hidden_check_constraint(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            apply_migrations(db)
            with pytest.raises(Exception):
                db.execute(
                    "INSERT INTO tag (name_display, name_norm, is_hidden) VALUES (?, ?, ?)",
                    ("x", "x", 2),
                )
