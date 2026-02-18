"""Tests for tag CLI commands (Phase 5).

End-to-end tests for:
- `sample tag add <sample-id> <tag>`
- `sample tag remove <sample-id> <tag>`
- `sample tag list <sample-id> [--json]`
- `sample tag bulk --from-search "<query>" --add <tag> [--remove <tag>]`
- `sample tag alias add <tag> <alias>`
- `sample tag alias remove <alias>`
- `sample tag parent add <child> <parent>`
- `sample tag parent remove <child> <parent>`

Uses CliRunner + monkeypatched config pointing at a test DB.
"""

import json

import pytest

from sample_manager import config as config_module
from sample_manager.cli import app
from sample_manager.db import Db
from sample_manager.migrations import apply_migrations
from sample_manager.repos.library_root_repo import LibraryRootRepo
from sample_manager.repos.sample_repo import SampleRepo
from sample_manager.repos.sample_tag_repo import SampleTagRepo
from sample_manager.repos.tag_repo import TagRepo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tag_cli_db(tmp_path):
    """Fresh DB with samples for tag CLI tests.

    Creates:
        root = /test/library
        sample 1: kick.wav
        sample 2: snare.wav
        sample 3: hihat.wav

    Returns:
        Dict with db, sample IDs, and db_path.
    """
    db_path = tmp_path / "tag_cli_test.sqlite3"
    db = Db(db_path)
    db.connect()
    apply_migrations(db)

    root_repo = LibraryRootRepo(db)
    sample_repo = SampleRepo(db)

    root = root_repo.get_or_create("/test/library")

    samples = {}
    for name in ("kick.wav", "snare.wav", "hihat.wav"):
        s = sample_repo.upsert(root["id"], name, name, ext=".wav")
        samples[name] = s

    yield {
        "db": db,
        "db_path": db_path,
        "samples": samples,
    }

    db.close()


@pytest.fixture(autouse=True)
def _setup_cli_config(tmp_path, monkeypatch, tag_cli_db):
    """Monkeypatch config to point at the test DB."""
    config_dir = tmp_path / "cli_home" / ".sample_manager"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"

    db_path = tag_cli_db["db_path"]
    config_path.write_text(
        f"db_path: {db_path}\n"
        f"library_roots: []\n"
        f"default_library_root: null\n"
        f"defaults:\n"
        f"  export_mode: copy\n"
    )

    monkeypatch.setattr(config_module, "get_config_path", lambda: config_path)


# ---------------------------------------------------------------------------
# sample tag add
# ---------------------------------------------------------------------------


class TestTagAddCLI:
    def test_add_tag_creates_and_attaches(self, cli_runner, tag_cli_db):
        sid = tag_cli_db["samples"]["kick.wav"]["id"]
        result = cli_runner.invoke(app, ["tag", "add", str(sid), "Drums"])
        assert result.exit_code == 0
        assert "Tagged" in result.output
        assert "Drums" in result.output

    def test_add_tag_idempotent(self, cli_runner, tag_cli_db):
        sid = tag_cli_db["samples"]["kick.wav"]["id"]
        cli_runner.invoke(app, ["tag", "add", str(sid), "Drums"])
        result = cli_runner.invoke(app, ["tag", "add", str(sid), "Drums"])
        assert result.exit_code == 0
        # Verify only one tag attached
        db = tag_cli_db["db"]
        tags = SampleTagRepo(db).list_tags_for_sample(sid)
        assert len(tags) == 1

    def test_add_tag_auto_creates_new_tag(self, cli_runner, tag_cli_db):
        sid = tag_cli_db["samples"]["kick.wav"]["id"]
        result = cli_runner.invoke(app, ["tag", "add", str(sid), "BrandNewTag"])
        assert result.exit_code == 0
        # Verify tag was created
        db = tag_cli_db["db"]
        tag = TagRepo(db).get_by_name("brandnewtag")
        assert tag is not None

    def test_add_tag_invalid_sample_id(self, cli_runner):
        result = cli_runner.invoke(app, ["tag", "add", "99999", "Drums"])
        assert result.exit_code != 0
        assert "Sample not found" in result.output


# ---------------------------------------------------------------------------
# sample tag remove
# ---------------------------------------------------------------------------


class TestTagRemoveCLI:
    def test_remove_tag(self, cli_runner, tag_cli_db):
        sid = tag_cli_db["samples"]["kick.wav"]["id"]
        # First add
        cli_runner.invoke(app, ["tag", "add", str(sid), "Drums"])
        # Then remove
        result = cli_runner.invoke(app, ["tag", "remove", str(sid), "Drums"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_remove_unknown_tag_errors(self, cli_runner, tag_cli_db):
        sid = tag_cli_db["samples"]["kick.wav"]["id"]
        result = cli_runner.invoke(app, ["tag", "remove", str(sid), "nonexistent"])
        assert result.exit_code != 0
        assert "Tag not found" in result.output

    def test_remove_tag_invalid_sample_id(self, cli_runner, tag_cli_db):
        # Create the tag first so it resolves
        db = tag_cli_db["db"]
        TagRepo(db).create("Drums")
        result = cli_runner.invoke(app, ["tag", "remove", "99999", "Drums"])
        assert result.exit_code != 0
        assert "Sample not found" in result.output


# ---------------------------------------------------------------------------
# sample tag list
# ---------------------------------------------------------------------------


class TestTagListCLI:
    def test_list_tags_empty(self, cli_runner, tag_cli_db):
        sid = tag_cli_db["samples"]["kick.wav"]["id"]
        result = cli_runner.invoke(app, ["tag", "list", str(sid)])
        assert result.exit_code == 0
        assert "no tags" in result.output.lower()

    def test_list_tags_with_tags(self, cli_runner, tag_cli_db):
        sid = tag_cli_db["samples"]["kick.wav"]["id"]
        cli_runner.invoke(app, ["tag", "add", str(sid), "Drums"])
        cli_runner.invoke(app, ["tag", "add", str(sid), "Kick"])
        result = cli_runner.invoke(app, ["tag", "list", str(sid)])
        assert result.exit_code == 0
        assert "Drums" in result.output
        assert "Kick" in result.output

    def test_list_tags_json_output(self, cli_runner, tag_cli_db):
        sid = tag_cli_db["samples"]["kick.wav"]["id"]
        cli_runner.invoke(app, ["tag", "add", str(sid), "Drums"])
        result = cli_runner.invoke(app, ["tag", "list", str(sid), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "Drums"
        assert "id" in data[0]
        assert "name_norm" in data[0]

    def test_list_tags_invalid_sample(self, cli_runner):
        result = cli_runner.invoke(app, ["tag", "list", "99999"])
        assert result.exit_code != 0
        assert "Sample not found" in result.output


# ---------------------------------------------------------------------------
# sample tag bulk
# ---------------------------------------------------------------------------


class TestTagBulkCLI:
    def test_bulk_add_from_search(self, cli_runner, tag_cli_db):
        result = cli_runner.invoke(
            app, ["tag", "bulk", "--from-search", "kick", "--add", "Drums"]
        )
        assert result.exit_code == 0
        assert "Matched 1 samples" in result.output
        assert "Drums" in result.output

    def test_bulk_add_no_matches(self, cli_runner, tag_cli_db):
        result = cli_runner.invoke(
            app, ["tag", "bulk", "--from-search", "zznotfound", "--add", "Tag"]
        )
        assert result.exit_code == 0
        assert "Matched 0 samples" in result.output

    def test_bulk_remove_from_search(self, cli_runner, tag_cli_db):
        sid = tag_cli_db["samples"]["kick.wav"]["id"]
        # Pre-tag
        cli_runner.invoke(app, ["tag", "add", str(sid), "ToRemove"])
        result = cli_runner.invoke(
            app, ["tag", "bulk", "--from-search", "kick", "--remove", "ToRemove"]
        )
        assert result.exit_code == 0
        assert "Removed" in result.output or "detachment" in result.output.lower()

    def test_bulk_json_output(self, cli_runner, tag_cli_db):
        result = cli_runner.invoke(
            app,
            [
                "tag", "bulk",
                "--from-search", "kick",
                "--add", "BulkTag",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "samples_matched" in data
        assert "tags_added" in data
        assert data["tags_added"] == ["BulkTag"]

    def test_bulk_no_add_or_remove_errors(self, cli_runner, tag_cli_db):
        result = cli_runner.invoke(
            app, ["tag", "bulk", "--from-search", "kick"]
        )
        assert result.exit_code != 0
        assert "at least one" in result.output.lower()


# ---------------------------------------------------------------------------
# sample tag alias add / remove
# ---------------------------------------------------------------------------


class TestTagAliasCLI:
    def test_alias_add(self, cli_runner, tag_cli_db):
        db = tag_cli_db["db"]
        TagRepo(db).create("Hi-Hat")
        result = cli_runner.invoke(app, ["tag", "alias", "add", "Hi-Hat", "HH"])
        assert result.exit_code == 0
        assert "alias" in result.output.lower()

    def test_alias_add_unknown_tag_errors(self, cli_runner, tag_cli_db):
        result = cli_runner.invoke(
            app, ["tag", "alias", "add", "nonexistent", "alias"]
        )
        assert result.exit_code != 0
        assert "Tag not found" in result.output

    def test_alias_add_duplicate_errors(self, cli_runner, tag_cli_db):
        db = tag_cli_db["db"]
        TagRepo(db).create("Bass")
        cli_runner.invoke(app, ["tag", "alias", "add", "Bass", "low"])
        result = cli_runner.invoke(app, ["tag", "alias", "add", "Bass", "LOW"])
        assert result.exit_code != 0
        assert "alias already exists" in result.output.lower() or "unique" in result.output.lower()

    def test_alias_remove(self, cli_runner, tag_cli_db):
        db = tag_cli_db["db"]
        TagRepo(db).create("Snare")
        cli_runner.invoke(app, ["tag", "alias", "add", "Snare", "snr"])
        result = cli_runner.invoke(app, ["tag", "alias", "remove", "snr"])
        assert result.exit_code == 0
        assert "Removed" in result.output


# ---------------------------------------------------------------------------
# sample tag parent add / remove
# ---------------------------------------------------------------------------


class TestTagParentCLI:
    def test_parent_add(self, cli_runner, tag_cli_db):
        db = tag_cli_db["db"]
        TagRepo(db).create("Kick")
        TagRepo(db).create("Drums")
        result = cli_runner.invoke(app, ["tag", "parent", "add", "Kick", "Drums"])
        assert result.exit_code == 0
        assert "parent edge" in result.output.lower()

    def test_parent_add_cycle_rejected(self, cli_runner, tag_cli_db):
        db = tag_cli_db["db"]
        TagRepo(db).create("A")
        TagRepo(db).create("B")
        cli_runner.invoke(app, ["tag", "parent", "add", "B", "A"])
        result = cli_runner.invoke(app, ["tag", "parent", "add", "A", "B"])
        assert result.exit_code != 0
        assert "cycle" in result.output.lower()

    def test_parent_add_unknown_tag_errors(self, cli_runner, tag_cli_db):
        db = tag_cli_db["db"]
        TagRepo(db).create("Kick")
        result = cli_runner.invoke(
            app, ["tag", "parent", "add", "Kick", "nonexistent"]
        )
        assert result.exit_code != 0
        assert "Tag not found" in result.output

    def test_parent_remove(self, cli_runner, tag_cli_db):
        db = tag_cli_db["db"]
        TagRepo(db).create("Kick")
        TagRepo(db).create("Drums")
        cli_runner.invoke(app, ["tag", "parent", "add", "Kick", "Drums"])
        result = cli_runner.invoke(app, ["tag", "parent", "remove", "Kick", "Drums"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_parent_remove_unknown_tag_errors(self, cli_runner, tag_cli_db):
        result = cli_runner.invoke(
            app, ["tag", "parent", "remove", "nonexistent", "also_nonexistent"]
        )
        assert result.exit_code != 0
        assert "Tag not found" in result.output
