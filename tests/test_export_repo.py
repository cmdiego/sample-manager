"""Tests for export/history repositories."""

from sample_manager.repos.export_repo import ExportRunRepo, HistoryEntryRepo


def test_export_run_and_history_repo(db):
    db.execute(
        "INSERT INTO arrangement (name, name_norm, profile_name) VALUES (?, ?, ?)",
        ("A", "a", "p"),
    )
    arrangement_id = db.fetchval("SELECT id FROM arrangement WHERE name_norm = 'a'")
    db.conn.commit()

    export_repo = ExportRunRepo(db)
    history_repo = HistoryEntryRepo(db)

    run = export_repo.create(
        arrangement_id=arrangement_id,
        export_profile_name="exp",
        export_dir="/tmp/x",
        mode="copy",
        status="planned",
    )
    assert run["id"] is not None
    assert run["status"] == "planned"

    hist = history_repo.create(
        export_id=run["id"],
        plan_json={"operations": []},
        stats_json={"operations": 0},
        errors_json=None,
    )
    assert hist["id"] is not None
    latest = history_repo.get_latest_for_export(run["id"])
    assert latest is not None
