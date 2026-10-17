"""Tests for arrangement workspace service and virtual folders."""

import pytest
from pathlib import Path

from sample_manager.arrangement_workspace import (
    ArrangementWorkspaceService,
    Folder,
    RemovalSnapshot,
)
from sample_manager.db import Db
from sample_manager.migrations import apply_migrations
from sample_manager.repos.arrangement_repo import ArrangementRepo


@pytest.fixture
def db(tmp_path):
    """Fresh in-memory DB with migrations applied."""
    db_path = tmp_path / "test.sqlite3"
    db = Db(db_path)
    db.connect()
    apply_migrations(db)
    yield db
    db.close()


@pytest.fixture
def workspace(db):
    """Arrangement workspace service."""
    return ArrangementWorkspaceService(db)


@pytest.fixture
def arrangement(db):
    """Create a test arrangement."""
    repo = ArrangementRepo(db)
    return repo.create("Test Arrangement", "default")


@pytest.fixture
def library_and_samples(db):
    """Create library root and sample fixtures."""
    db.execute(
        "INSERT INTO library_root (path, path_norm) VALUES (?, ?)",
        ("/lib", "/lib"),
    )
    lib_id = db.fetchval("SELECT id FROM library_root WHERE path_norm = '/lib'")

    samples = []
    for i in range(5):
        db.execute(
            "INSERT INTO sample (library_root_id, rel_path, rel_path_norm, filename, ext) "
            "VALUES (?, ?, ?, ?, ?)",
            (lib_id, f"kick{i}.wav", f"kick{i}.wav", f"kick{i}.wav", ".wav"),
        )
        sample_id = db.fetchval("SELECT last_insert_rowid()")
        samples.append(sample_id)

    db.conn.commit()
    return lib_id, samples


class TestFolderCreation:
    def test_create_root_folder(self, workspace, arrangement):
        folder = workspace.create_folder(arrangement["id"], None, "Kicks")
        assert folder.name == "Kicks"
        assert folder.name_norm == "kicks"
        assert folder.parent_id is None
        assert folder.arrangement_id == arrangement["id"]
        assert folder.sort_order > 0

    def test_create_nested_folder(self, workspace, arrangement):
        parent = workspace.create_folder(arrangement["id"], None, "Drums")
        child = workspace.create_folder(arrangement["id"], parent.id, "Kicks")

        assert child.parent_id == parent.id
        assert child.name == "Kicks"

    def test_duplicate_sibling_rejected(self, workspace, arrangement):
        workspace.create_folder(arrangement["id"], None, "Kicks")

        with pytest.raises(ValueError, match="already exists"):
            workspace.create_folder(arrangement["id"], None, "kicks")

    def test_duplicate_in_different_parent_allowed(self, workspace, arrangement):
        parent1 = workspace.create_folder(arrangement["id"], None, "Set1")
        parent2 = workspace.create_folder(arrangement["id"], None, "Set2")

        folder1 = workspace.create_folder(arrangement["id"], parent1.id, "Kicks")
        folder2 = workspace.create_folder(arrangement["id"], parent2.id, "Kicks")

        assert folder1.id != folder2.id
        assert folder1.name == folder2.name

    def test_empty_name_rejected(self, workspace, arrangement):
        with pytest.raises(ValueError, match="empty"):
            workspace.create_folder(arrangement["id"], None, "")

    def test_path_separator_rejected(self, workspace, arrangement):
        with pytest.raises(ValueError, match="separator"):
            workspace.create_folder(arrangement["id"], None, "sub/folder")

        with pytest.raises(ValueError, match="separator"):
            workspace.create_folder(arrangement["id"], None, "sub\\folder")

    def test_dot_names_rejected(self, workspace, arrangement):
        with pytest.raises(ValueError, match="cannot be"):
            workspace.create_folder(arrangement["id"], None, ".")

        with pytest.raises(ValueError, match="cannot be"):
            workspace.create_folder(arrangement["id"], None, "..")

    def test_invalid_parent_rejected(self, workspace, arrangement):
        with pytest.raises(ValueError, match="not found"):
            workspace.create_folder(arrangement["id"], 9999, "Kicks")

    def test_cross_arrangement_parent_rejected(self, workspace, arrangement, db):
        # Create second arrangement
        repo = ArrangementRepo(db)
        arr2 = repo.create("Other", "default")

        folder = workspace.create_folder(arrangement["id"], None, "Drums")

        with pytest.raises(ValueError, match="different arrangement"):
            workspace.create_folder(arr2["id"], folder.id, "Kicks")


class TestFolderRename:
    def test_rename_folder(self, workspace, arrangement):
        folder = workspace.create_folder(arrangement["id"], None, "Kicks")
        renamed = workspace.rename_folder(folder.id, "Kick Drums")

        assert renamed.id == folder.id
        assert renamed.name == "Kick Drums"
        assert renamed.name_norm == "kick drums"

    def test_rename_duplicate_sibling_rejected(self, workspace, arrangement):
        folder1 = workspace.create_folder(arrangement["id"], None, "Kicks")
        folder2 = workspace.create_folder(arrangement["id"], None, "Snares")

        with pytest.raises(ValueError, match="already exists"):
            workspace.rename_folder(folder2.id, "Kicks")

    def test_rename_empty_rejected(self, workspace, arrangement):
        folder = workspace.create_folder(arrangement["id"], None, "Kicks")

        with pytest.raises(ValueError, match="empty"):
            workspace.rename_folder(folder.id, "")

    def test_rename_invalid_chars_rejected(self, workspace, arrangement):
        folder = workspace.create_folder(arrangement["id"], None, "Kicks")

        with pytest.raises(ValueError, match="separator"):
            workspace.rename_folder(folder.id, "sub/folder")


class TestFolderMove:
    def test_move_folder_to_root(self, workspace, arrangement):
        parent = workspace.create_folder(arrangement["id"], None, "Drums")
        child = workspace.create_folder(arrangement["id"], parent.id, "Kicks")

        workspace.move_folders((child.id,), None)

        # Verify move
        moved = workspace._repo.get_folder(child.id)
        assert moved["parent_id"] is None

    def test_move_folder_to_parent(self, workspace, arrangement):
        folder1 = workspace.create_folder(arrangement["id"], None, "Folder1")
        folder2 = workspace.create_folder(arrangement["id"], None, "Folder2")

        workspace.move_folders((folder1.id,), folder2.id)

        moved = workspace._repo.get_folder(folder1.id)
        assert moved["parent_id"] == folder2.id

    def test_move_to_self_rejected(self, workspace, arrangement):
        folder = workspace.create_folder(arrangement["id"], None, "Folder")

        with pytest.raises(ValueError, match="to itself"):
            workspace.move_folders((folder.id,), folder.id)

    def test_move_to_descendant_rejected(self, workspace, arrangement):
        parent = workspace.create_folder(arrangement["id"], None, "Parent")
        child = workspace.create_folder(arrangement["id"], parent.id, "Child")
        grandchild = workspace.create_folder(arrangement["id"], child.id, "Grandchild")

        with pytest.raises(ValueError, match="descendant"):
            workspace.move_folders((parent.id,), grandchild.id)

    def test_move_multiple_folders(self, workspace, arrangement):
        target = workspace.create_folder(arrangement["id"], None, "Target")
        folder1 = workspace.create_folder(arrangement["id"], None, "Folder1")
        folder2 = workspace.create_folder(arrangement["id"], None, "Folder2")

        workspace.move_folders((folder1.id, folder2.id), target.id)

        moved1 = workspace._repo.get_folder(folder1.id)
        moved2 = workspace._repo.get_folder(folder2.id)
        assert moved1["parent_id"] == target.id
        assert moved2["parent_id"] == target.id


class TestSamplePlacement:
    def test_add_samples_to_root(self, workspace, arrangement, library_and_samples):
        _, samples = library_and_samples

        added = workspace.add_samples(arrangement["id"], tuple(samples[:3]))
        assert added == 3

        # Verify placement
        arr_samples = workspace._repo.list_sample_ids(arrangement["id"])
        assert len(arr_samples) == 3

    def test_add_samples_to_folder(self, workspace, arrangement, library_and_samples):
        _, samples = library_and_samples
        folder = workspace.create_folder(arrangement["id"], None, "Kicks")

        added = workspace.add_samples(arrangement["id"], tuple(samples[:3]), folder.id)
        assert added == 3

        # Verify placement
        folder_samples = workspace._repo.list_folder_samples(folder.id)
        assert len(folder_samples) == 3
        assert all(s["folder_id"] == folder.id for s in folder_samples)

    def test_add_duplicate_samples_idempotent(self, workspace, arrangement, library_and_samples):
        _, samples = library_and_samples

        added1 = workspace.add_samples(arrangement["id"], tuple(samples[:3]))
        added2 = workspace.add_samples(arrangement["id"], tuple(samples[:3]))

        assert added1 == 3
        assert added2 == 0  # Already present

    def test_move_samples_to_folder(self, workspace, arrangement, library_and_samples):
        _, samples = library_and_samples

        # Add to root
        workspace.add_samples(arrangement["id"], tuple(samples[:3]))

        # Create folder and move
        folder = workspace.create_folder(arrangement["id"], None, "Kicks")
        workspace.move_samples(arrangement["id"], tuple(samples[:2]), folder.id)

        # Verify
        folder_samples = workspace._repo.list_folder_samples(folder.id)
        root_samples = workspace._repo.list_folder_samples(None)

        assert len(folder_samples) == 2
        assert len(root_samples) == 1

    def test_remove_samples(self, workspace, arrangement, library_and_samples):
        _, samples = library_and_samples
        workspace.add_samples(arrangement["id"], tuple(samples[:3]))

        removed = workspace.remove_samples(arrangement["id"], tuple(samples[:2]))
        assert removed == 2

        remaining = workspace._repo.list_sample_ids(arrangement["id"])
        assert len(remaining) == 1


class TestFolderRemoval:
    def test_remove_empty_folder(self, workspace, arrangement):
        folder = workspace.create_folder(arrangement["id"], None, "Empty")

        snapshot = workspace.remove_folder_tree(folder.id)

        assert len(snapshot.folder_rows) == 1
        assert len(snapshot.sample_placements) == 0

        # Verify removal
        assert workspace._repo.get_folder(folder.id) is None

    def test_remove_folder_with_samples(self, workspace, arrangement, library_and_samples):
        _, samples = library_and_samples
        folder = workspace.create_folder(arrangement["id"], None, "Kicks")
        workspace.add_samples(arrangement["id"], tuple(samples[:3]), folder.id)

        snapshot = workspace.remove_folder_tree(folder.id)

        assert len(snapshot.folder_rows) == 1
        assert len(snapshot.sample_placements) == 3

        # Verify samples removed from arrangement
        arr_samples = workspace._repo.list_sample_ids(arrangement["id"])
        assert len(arr_samples) == 0

    def test_remove_folder_with_descendants(self, workspace, arrangement, library_and_samples):
        _, samples = library_and_samples

        parent = workspace.create_folder(arrangement["id"], None, "Parent")
        child1 = workspace.create_folder(arrangement["id"], parent.id, "Child1")
        child2 = workspace.create_folder(arrangement["id"], parent.id, "Child2")
        grandchild = workspace.create_folder(arrangement["id"], child1.id, "Grandchild")

        # Add samples to various folders
        workspace.add_samples(arrangement["id"], tuple(samples[:2]), child1.id)
        workspace.add_samples(arrangement["id"], tuple(samples[2:4]), grandchild.id)

        snapshot = workspace.remove_folder_tree(parent.id)

        # Should remove parent + 3 descendants
        assert len(snapshot.folder_rows) == 4
        assert len(snapshot.sample_placements) == 4

        # Verify all removed
        assert workspace._repo.get_folder(parent.id) is None
        assert workspace._repo.get_folder(child1.id) is None
        assert workspace._repo.get_folder(child2.id) is None
        assert workspace._repo.get_folder(grandchild.id) is None

    def test_restore_removal_snapshot(self, workspace, arrangement, library_and_samples):
        _, samples = library_and_samples

        parent = workspace.create_folder(arrangement["id"], None, "Parent")
        child = workspace.create_folder(arrangement["id"], parent.id, "Child")
        workspace.add_samples(arrangement["id"], tuple(samples[:3]), child.id)

        # Remove and capture snapshot
        snapshot = workspace.remove_folder_tree(parent.id)

        # Restore
        workspace.restore_removal_snapshot(snapshot)

        # Verify restoration
        restored_parent = workspace._repo.get_folder(parent.id)
        restored_child = workspace._repo.get_folder(child.id)
        restored_samples = workspace._repo.list_folder_samples(child.id)

        assert restored_parent is not None
        assert restored_child is not None
        assert len(restored_samples) == 3


class TestTree:
    def test_empty_tree(self, workspace, arrangement):
        tree = workspace.tree(arrangement["id"])

        assert tree.arrangement_id == arrangement["id"]
        assert len(tree.root_folders) == 0
        assert len(tree.root_samples) == 0

    def test_tree_with_folders_and_samples(self, workspace, arrangement, library_and_samples):
        _, samples = library_and_samples

        # Create folder structure
        drums = workspace.create_folder(arrangement["id"], None, "Drums")
        kicks = workspace.create_folder(arrangement["id"], drums.id, "Kicks")
        snares = workspace.create_folder(arrangement["id"], drums.id, "Snares")

        # Add samples
        workspace.add_samples(arrangement["id"], tuple(samples[:2]), kicks.id)
        workspace.add_samples(arrangement["id"], tuple(samples[2:4]), snares.id)
        workspace.add_samples(arrangement["id"], tuple(samples[4:5]))  # Root

        tree = workspace.tree(arrangement["id"])

        assert len(tree.root_folders) == 1
        assert len(tree.root_samples) == 1
        assert tree.root_folders[0].folder.name == "Drums"
        assert len(tree.root_folders[0].children) == 2

    def test_get_folder_path(self, workspace, arrangement):
        parent = workspace.create_folder(arrangement["id"], None, "Parent")
        child = workspace.create_folder(arrangement["id"], parent.id, "Child")
        grandchild = workspace.create_folder(arrangement["id"], child.id, "Grandchild")

        path = workspace.get_folder_path(grandchild.id)
        assert path == "Parent/Child/Grandchild"

    def test_get_sample_folder_paths(self, workspace, arrangement, library_and_samples):
        _, samples = library_and_samples

        parent = workspace.create_folder(arrangement["id"], None, "Parent")
        child = workspace.create_folder(arrangement["id"], parent.id, "Child")

        workspace.add_samples(arrangement["id"], tuple(samples[:2]), child.id)
        workspace.add_samples(arrangement["id"], tuple(samples[2:4]))  # Root

        paths = workspace.get_sample_folder_paths(arrangement["id"])

        assert paths[samples[0]] == "Parent/Child"
        assert paths[samples[1]] == "Parent/Child"
        assert paths[samples[2]] == ""
        assert paths[samples[3]] == ""


class TestExportPlanningIntegration:
    def test_plan_without_folders_unchanged(self, workspace, arrangement, library_and_samples):
        """Existing arrangements without folders should produce unchanged plans."""
        from sample_manager.arrangement_service import build_plan
        from sample_manager.profiles import ArrangementProfile, ExportProfile

        _, samples = library_and_samples
        workspace.add_samples(arrangement["id"], tuple(samples[:3]))

        # Get samples with library root path
        sample_rows = workspace._repo.list_samples(arrangement["id"])

        arr_profile = ArrangementProfile(
            name="default",
            layout_mode="flat",
            naming_template="{index}_{name}",
            collision_policy="fail",
        )
        exp_profile = ExportProfile(
            name="default",
            max_depth=3,
            max_filename_len=255,
            illegal_chars="",
            on_violation="fail",
        )

        # Plan without folder_paths
        plan = build_plan(
            arrangement=arrangement,
            samples=sample_rows,
            arrangement_profile=arr_profile,
            export_profile=exp_profile,
        )

        # Paths should not have folder prefixes
        assert all("/" not in op["dst_rel_path"].split("_")[0] for op in plan["operations"])

    def test_plan_with_folders(self, workspace, arrangement, library_and_samples):
        """Plans should prepend virtual folder paths."""
        from sample_manager.arrangement_service import build_plan
        from sample_manager.profiles import ArrangementProfile, ExportProfile

        _, samples = library_and_samples

        drums = workspace.create_folder(arrangement["id"], None, "Drums")
        kicks = workspace.create_folder(arrangement["id"], drums.id, "Kicks")

        workspace.add_samples(arrangement["id"], tuple(samples[:2]), kicks.id)
        workspace.add_samples(arrangement["id"], tuple(samples[2:3]))  # Root

        # Get samples and folder paths
        sample_rows = workspace._repo.list_samples(arrangement["id"])
        folder_paths = workspace.get_sample_folder_paths(arrangement["id"])

        arr_profile = ArrangementProfile(
            name="default",
            layout_mode="flat",
            naming_template="{index}_{name}",
            collision_policy="fail",
        )
        exp_profile = ExportProfile(
            name="default",
            max_depth=5,
            max_filename_len=255,
            illegal_chars="",
            on_violation="fail",
        )

        plan = build_plan(
            arrangement=arrangement,
            samples=sample_rows,
            arrangement_profile=arr_profile,
            export_profile=exp_profile,
            folder_paths=folder_paths,
        )

        # Samples in kicks folder should have "Drums/Kicks/" prefix
        ops_by_id = {op["sample_id"]: op for op in plan["operations"]}

        # Export paths use the host separator unless the profile requests POSIX.
        assert Path(ops_by_id[samples[0]]["dst_rel_path"]).parts[:2] == ("Drums", "Kicks")
        assert Path(ops_by_id[samples[1]]["dst_rel_path"]).parts[:2] == ("Drums", "Kicks")
        assert not ops_by_id[samples[2]]["dst_rel_path"].startswith("Drums")
