"""Persistent Stage hierarchy, migration and arrangement handoff contracts."""

import pytest

from sample_manager.db import Db
from sample_manager import migrations
from sample_manager.repos.arrangement_repo import ArrangementRepo
from sample_manager.repos.library_root_repo import LibraryRootRepo
from sample_manager.repos.sample_repo import SampleRepo
from sample_manager.repos.selection_repo import SelectionRepo
from sample_manager.services.stage_workspace import StageWorkspace
from sample_manager.arrangement_workspace import ArrangementWorkspaceService


def _samples(db, tmp_path):
    """Seed indexed sample rows without modifying a user's filesystem."""
    root = LibraryRootRepo(db).get_or_create(str(tmp_path / "library"))
    return [SampleRepo(db).upsert(root["id"], name, name)["id"] for name in ("kick.wav", "snare.wav")]


def test_upgrade_preserves_flat_selection_and_is_idempotent(tmp_path):
    """Version 6 selections acquire NULL placements without losing IDs or time."""
    with Db(tmp_path / "old.sqlite3") as db:
        migrations.ensure_schema_version(db)
        for version in range(1, 7):
            getattr(migrations, f"_migration_{version:04}")(db)
        sample_ids = _samples(db, tmp_path)
        selection = SelectionRepo(db)
        selection.add_samples(sample_ids)
        before = [dict(row) for row in db.fetchall("SELECT * FROM selection_sample ORDER BY sample_id")]
        assert migrations.apply_migrations(db) == migrations.apply_migrations(db) == 7
        after = [dict(row) for row in db.fetchall("SELECT * FROM selection_sample ORDER BY sample_id")]
        assert [{key: value for key, value in row.items() if key != "folder_id"} for row in after] == before
        assert all(row["folder_id"] is None for row in after)


def test_nested_folders_and_placements_survive_reopening(tmp_path):
    """Stage hierarchy is persisted alongside the existing shared selection IDs."""
    path = tmp_path / "stage.sqlite3"
    with Db(path) as db:
        migrations.apply_migrations(db)
        ids = _samples(db, tmp_path)
        workspace = StageWorkspace(db)
        folder = workspace.create_folder("Drums/Kicks")
        assert workspace.create_folder("drums/kicks") == folder
        workspace.stage_sample(ids[0], folder)
        workspace.stage_sample(ids[1])
        workspace.stage_sample(ids[0])  # Re-adding must not flatten placement.
        assert {row["id"] for row in SelectionRepo(db).list_samples()} == set(ids)
    with Db(path) as db:
        workspace = StageWorkspace(db)
        assert workspace.path(folder) == "/Drums/Kicks"
        assert workspace.placements() == {ids[0]: folder, ids[1]: None}


@pytest.mark.parametrize("path", ["", "/", "Drums/../Kicks", "Drums/CON", "Drums/a:b", "Drums//Kicks", "Drums/Bad\\Name", "Drums/Bad\x1b"])
def test_invalid_paths_leave_no_partial_folders(db, path):
    """Validation and rollback prevent partial nested paths or unsafe export names."""
    workspace = StageWorkspace(db)
    with pytest.raises(ValueError):
        workspace.create_folder(path)
    assert workspace.folders() == []


def test_moves_cycles_conflicts_and_rename_are_atomic(db, tmp_path):
    """Subtree moves preserve IDs and reject cycles/collisions without side effects."""
    workspace = StageWorkspace(db)
    ids = _samples(db, tmp_path)
    kick = workspace.create_folder("Drums/Kicks")
    drums = workspace.folder(kick)["parent_id"]
    workspace.stage_sample(ids[0], kick)
    before = workspace.folders()
    with pytest.raises(ValueError, match="subfolders"):
        workspace.move_folder(drums, "/Drums/Kicks/NewChild")
    assert workspace.folders() == before
    with pytest.raises(ValueError):
        workspace.move_sample(9999, "/Must/RollBack")
    assert workspace.folders() == before
    workspace.move_folder(drums, "/Kits/Kit 1")
    assert workspace.path(kick) == "/Kits/Kit 1/Drums/Kicks"
    workspace.rename_folder(drums, "Percussion")
    assert workspace.path(kick) == "/Kits/Kit 1/Percussion/Kicks"
    assert workspace.placements()[ids[0]] == kick
    workspace.create_folder("/Kits/Kit 1/Percussion/Snares")
    with pytest.raises(ValueError, match="already exists"):
        workspace.rename_folder(kick, "Snares")
    assert workspace.path(kick).endswith("/Kicks")
    with pytest.raises(ValueError, match="not empty"):
        workspace.remove_folder(drums)
    workspace.move_sample(ids[0], "/")
    workspace.remove_folder(kick)
    assert workspace.placements()[ids[0]] is None


def test_clear_stage_removes_folders_and_samples_not_library_records(db, tmp_path):
    """Clear resets the virtual workspace while retaining indexed source samples."""
    workspace = StageWorkspace(db)
    ids = _samples(db, tmp_path)
    folder = workspace.create_folder("Drums/Kicks")
    workspace.stage_sample(ids[0], folder)
    assert SelectionRepo(db).clear() == 1
    assert workspace.folders() == [] and workspace.placements() == {}
    assert SampleRepo(db).get_by_id(ids[0]) is not None


def test_arrangement_handoff_merges_paths_and_preserves_existing_placements(db, tmp_path):
    """Stage-to-arrangement copies hierarchy; repeated adds keep prior user edits."""
    workspace = StageWorkspace(db)
    ids = _samples(db, tmp_path)
    folder = workspace.create_folder("Drums/Kicks")
    workspace.stage_sample(ids[0], folder)
    repo = ArrangementRepo(db)
    arrangement = repo.create("Kit", "default")
    assert workspace.copy_to_arrangement(arrangement["id"], ids) == 2
    saved = ArrangementWorkspaceService(db)
    assert saved.get_sample_folder_paths(arrangement["id"]) == {ids[0]: "Drums/Kicks", ids[1]: ""}
    workspace.move_sample(ids[0], "/Moved")
    workspace.stage_sample(ids[1], folder)
    assert workspace.copy_to_arrangement(arrangement["id"], ids) == 0
    assert saved.get_sample_folder_paths(arrangement["id"])[ids[0]] == "Drums/Kicks"
    assert len([row for row in repo.list_folders(arrangement["id"]) if row["name"] == "Drums"]) == 1
