"""Repositories for export_run and history_entry tables."""

from __future__ import annotations

import json
from typing import Any

from ..db import Db


class ExportRunRepo:
    """CRUD operations for export_run."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def create(
        self,
        *,
        arrangement_id: int,
        export_profile_name: str,
        export_dir: str,
        mode: str,
        status: str,
    ) -> dict:
        self._db.execute(
            "INSERT INTO export_run "
            "(arrangement_id, export_profile_name, export_dir, mode, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (arrangement_id, export_profile_name, export_dir, mode, status),
        )
        self._db.conn.commit()
        row = self._db.fetchone("SELECT * FROM export_run ORDER BY id DESC LIMIT 1")
        assert row is not None
        return dict(row)

    def list_recent(self, limit: int = 100) -> list[dict]:
        """List recorded runs for explicit history-based revert selection."""
        return [dict(row) for row in self._db.fetchall(
            "SELECT * FROM export_run ORDER BY id DESC LIMIT ?", (limit,),
        )]

    def get_by_id(self, export_id: int) -> dict | None:
        row = self._db.fetchone("SELECT * FROM export_run WHERE id = ?", (export_id,))
        return dict(row) if row else None

    def set_status(self, export_id: int, status: str) -> None:
        self._db.execute(
            "UPDATE export_run SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, export_id),
        )
        self._db.conn.commit()


class HistoryEntryRepo:
    """CRUD operations for history_entry."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def create(
        self,
        *,
        export_id: int,
        plan_json: dict[str, Any],
        stats_json: dict[str, Any],
        errors_json: dict[str, Any] | None = None,
    ) -> dict:
        self._db.execute(
            "INSERT INTO history_entry (export_id, plan_json, stats_json, errors_json) "
            "VALUES (?, ?, ?, ?)",
            (
                export_id,
                json.dumps(plan_json, indent=2, sort_keys=True),
                json.dumps(stats_json, indent=2, sort_keys=True),
                json.dumps(errors_json, indent=2, sort_keys=True)
                if errors_json is not None
                else None,
            ),
        )
        self._db.conn.commit()
        row = self._db.fetchone(
            "SELECT * FROM history_entry WHERE export_id = ? ORDER BY id DESC LIMIT 1",
            (export_id,),
        )
        assert row is not None
        return dict(row)

    def get_latest_for_export(self, export_id: int) -> dict | None:
        row = self._db.fetchone(
            "SELECT * FROM history_entry WHERE export_id = ? ORDER BY id DESC LIMIT 1",
            (export_id,),
        )
        return dict(row) if row else None
