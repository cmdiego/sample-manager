"""SQLite database wrapper for Sample Manager.

Provides connection management with required PRAGMAs (per docs/02-persistence.md §2.3),
execute/fetch helpers, and a transaction context manager.

Uses a single persistent connection per Db instance (single-user CLI model).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator


# PRAGMAs applied on every new connection (docs/02-persistence.md §2.3)
_CONNECTION_PRAGMAS = [
    "PRAGMA foreign_keys = ON",
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA temp_store = MEMORY",
]


class Db:
    """Thin wrapper around a single sqlite3 connection.

    Usage::

        db = Db("/path/to/db.sqlite3")
        db.connect()
        row = db.fetchone("SELECT 1")
        db.close()

    Or as a context manager::

        with Db("/path/to/db.sqlite3") as db:
            db.fetchone("SELECT 1")
    """

    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle --

    def connect(self) -> sqlite3.Connection:
        """Open the connection and apply required PRAGMAs.

        Safe to call multiple times; returns existing connection if already open.
        """
        if self._conn is not None:
            return self._conn

        # Create parent directory if needed (mirrors config.py behavior)
        parent = Path(self._path).parent
        parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row  # dict-like row access

        # Apply per-connection PRAGMAs
        for pragma in _CONNECTION_PRAGMAS:
            self._conn.execute(pragma)

        return self._conn

    def close(self) -> None:
        """Close the connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Db:
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # -- properties --

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the active connection, opening if needed."""
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    # -- execute / fetch helpers --

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        """Execute a single SQL statement."""
        return self.conn.execute(sql, params)

    def executescript(self, sql: str) -> None:
        """Execute multiple SQL statements (no parameter binding).

        NOTE: executescript issues an implicit COMMIT before executing,
        so it should not be used inside a transaction() block.
        """
        self.conn.executescript(sql)

    def fetchone(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        """Execute and return the first row, or None."""
        return self.conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        """Execute and return all rows."""
        return self.conn.execute(sql, params).fetchall()

    def fetchval(self, sql: str, params: tuple | dict = ()) -> Any:
        """Execute and return the first column of the first row, or None."""
        row = self.fetchone(sql, params)
        if row is None:
            return None
        return row[0]

    # -- transaction context manager --

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Explicit transaction block with BEGIN IMMEDIATE / COMMIT / ROLLBACK.

        Usage::

            with db.transaction():
                db.execute("INSERT ...")
                db.execute("INSERT ...")
            # auto-commits on success, auto-rolls back on exception

        Uses BEGIN IMMEDIATE to acquire a write lock early, avoiding
        SQLITE_BUSY under WAL mode for write transactions.
        """
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
