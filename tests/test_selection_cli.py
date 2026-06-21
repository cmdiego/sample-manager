"""E2E CLI tests for selection buffer commands."""

import json

import pytest

from sample_manager import config as config_module
from sample_manager.cli import app
from sample_manager.db import Db
from sample_manager.migrations import apply_migrations
from sample_manager.repos.library_root_repo import LibraryRootRepo
from sample_manager.repos.sample_repo import SampleRepo
from sample_manager.exit_codes import ERROR_INVALID_ARGS


@pytest.fixture
def selection_cli_db(tmp_path):
    db_path = tmp_path / "selection_cli_test.sqlite3"
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

    yield {"db": db, "db_path": db_path, "samples": samples}
    db.close()


@pytest.fixture(autouse=True)
def _setup_cli_config(tmp_path, monkeypatch, selection_cli_db):
    config_dir = tmp_path / "cli_home" / ".sample_manager"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"

    db_path = selection_cli_db["db_path"]
    config_path.write_text(
        f"db_path: {db_path}\n"
        f"library_roots: []\n"
        f"default_library_root: null\n"
        f"profiles_dir: {tmp_path / 'profiles'}\n"
        f"defaults:\n"
        f"  export_mode: copy\n"
    )

    monkeypatch.setattr(config_module, "get_config_path", lambda: config_path)


class TestSelectionAdd:
    def test_add_by_ids(self, cli_runner, selection_cli_db):
        sid = selection_cli_db["samples"]["kick.wav"]["id"]
        result = cli_runner.invoke(app, ["selection", "add", "--ids", str(sid)])
        assert result.exit_code == 0
        assert "added 1" in result.output

    def test_add_by_search(self, cli_runner, selection_cli_db):
        result = cli_runner.invoke(
            app, ["selection", "add", "--from-search", "kick"]
        )
        assert result.exit_code == 0
        assert "added 1" in result.output

    def test_add_requires_source(self, cli_runner):
        result = cli_runner.invoke(app, ["selection", "add"])
        assert result.exit_code == ERROR_INVALID_ARGS
        assert "provide at least one" in result.output

    def test_add_json(self, cli_runner, selection_cli_db):
        sid = selection_cli_db["samples"]["snare.wav"]["id"]
        result = cli_runner.invoke(
            app, ["selection", "add", "--ids", str(sid), "--json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["added"] == 1
        assert payload["selected_count"] == 1


class TestSelectionRemove:
    def test_remove_by_ids(self, cli_runner, selection_cli_db):
        sid = selection_cli_db["samples"]["kick.wav"]["id"]
        cli_runner.invoke(app, ["selection", "add", "--ids", str(sid)])
        result = cli_runner.invoke(
            app, ["selection", "remove", "--ids", str(sid)]
        )
        assert result.exit_code == 0
        assert "removed 1" in result.output

    def test_remove_by_search(self, cli_runner, selection_cli_db):
        cli_runner.invoke(app, ["selection", "add", "--from-search", "snare"])
        result = cli_runner.invoke(
            app, ["selection", "remove", "--from-search", "snare"]
        )
        assert result.exit_code == 0
        assert "removed 1" in result.output


class TestSelectionListAndClear:
    def test_list_empty(self, cli_runner):
        result = cli_runner.invoke(app, ["selection", "list"])
        assert result.exit_code == 0
        assert "Selection is empty" in result.output

    def test_list_json(self, cli_runner, selection_cli_db):
        sid = selection_cli_db["samples"]["hihat.wav"]["id"]
        cli_runner.invoke(app, ["selection", "add", "--ids", str(sid)])
        result = cli_runner.invoke(app, ["selection", "list", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["total"] == 1
        assert payload["items"][0]["filename"] == "hihat.wav"

    def test_clear(self, cli_runner, selection_cli_db):
        sid = selection_cli_db["samples"]["hihat.wav"]["id"]
        cli_runner.invoke(app, ["selection", "add", "--ids", str(sid)])
        result = cli_runner.invoke(app, ["selection", "clear"])
        assert result.exit_code == 0
        assert "Selection cleared (1 removed)" in result.output
