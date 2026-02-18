"""Tests for sample_manager.db — SQLite connection wrapper."""

import sqlite3

import pytest

from sample_manager.db import Db


class TestDbConnection:
    def test_connect_creates_file(self, tmp_path):
        db_path = tmp_path / "test.sqlite3"
        db = Db(db_path)
        db.connect()
        assert db_path.exists()
        db.close()

    def test_connect_creates_parent_dirs(self, tmp_path):
        db_path = tmp_path / "sub" / "dir" / "test.sqlite3"
        db = Db(db_path)
        db.connect()
        assert db_path.exists()
        db.close()

    def test_connect_idempotent(self, tmp_path):
        db = Db(tmp_path / "test.sqlite3")
        conn1 = db.connect()
        conn2 = db.connect()
        assert conn1 is conn2
        db.close()

    def test_close_and_reconnect(self, tmp_path):
        db = Db(tmp_path / "test.sqlite3")
        conn1 = db.connect()
        db.close()
        conn2 = db.connect()
        assert conn1 is not conn2
        db.close()

    def test_context_manager(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            row = db.fetchone("SELECT 1")
            assert row[0] == 1
        # Connection should be closed after with block
        assert db._conn is None


class TestDbPragmas:
    """Verify that per-connection PRAGMAs are applied (docs/02 §2.3)."""

    def test_foreign_keys_on(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            val = db.fetchval("PRAGMA foreign_keys")
            assert val == 1

    def test_journal_mode_wal(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            val = db.fetchval("PRAGMA journal_mode")
            assert val == "wal"

    def test_synchronous_normal(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            val = db.fetchval("PRAGMA synchronous")
            # NORMAL = 1
            assert val == 1

    def test_temp_store_memory(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            val = db.fetchval("PRAGMA temp_store")
            # MEMORY = 2
            assert val == 2


class TestDbHelpers:
    def test_fetchone_returns_row(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            row = db.fetchone("SELECT 42 AS answer")
            assert row is not None
            assert row["answer"] == 42

    def test_fetchone_returns_none(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
            row = db.fetchone("SELECT * FROM t WHERE id = 999")
            assert row is None

    def test_fetchall(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            db.execute("CREATE TABLE t (v INTEGER)")
            db.execute("INSERT INTO t VALUES (1)")
            db.execute("INSERT INTO t VALUES (2)")
            db.execute("INSERT INTO t VALUES (3)")
            rows = db.fetchall("SELECT v FROM t ORDER BY v")
            assert [r["v"] for r in rows] == [1, 2, 3]

    def test_fetchval(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            assert db.fetchval("SELECT 99") == 99

    def test_fetchval_none(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
            assert db.fetchval("SELECT id FROM t") is None

    def test_row_factory_dict_access(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            row = db.fetchone("SELECT 1 AS a, 'hello' AS b")
            assert row["a"] == 1
            assert row["b"] == "hello"


class TestDbTransaction:
    def test_commit_on_success(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            db.execute("CREATE TABLE t (v INTEGER)")
            with db.transaction():
                db.execute("INSERT INTO t VALUES (1)")
                db.execute("INSERT INTO t VALUES (2)")
            rows = db.fetchall("SELECT v FROM t")
            assert len(rows) == 2

    def test_rollback_on_exception(self, tmp_path):
        with Db(tmp_path / "test.sqlite3") as db:
            db.execute("CREATE TABLE t (v INTEGER)")
            db.conn.commit()
            with pytest.raises(ValueError):
                with db.transaction():
                    db.execute("INSERT INTO t VALUES (1)")
                    raise ValueError("boom")
            rows = db.fetchall("SELECT v FROM t")
            assert len(rows) == 0

    def test_foreign_key_enforced_in_transaction(self, tmp_path):
        """FK constraints must work inside transactions (PRAGMAs active)."""
        with Db(tmp_path / "test.sqlite3") as db:
            db.execute(
                "CREATE TABLE parent (id INTEGER PRIMARY KEY)"
            )
            db.execute(
                "CREATE TABLE child ("
                "  id INTEGER PRIMARY KEY,"
                "  pid INTEGER REFERENCES parent(id)"
                ")"
            )
            db.conn.commit()
            with pytest.raises(sqlite3.IntegrityError):
                with db.transaction():
                    db.execute("INSERT INTO child (pid) VALUES (999)")
