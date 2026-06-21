"""E2E CLI tests for arrangement commands."""

import json

import pytest
import yaml

from sample_manager import config as config_module
from sample_manager.cli import app
from sample_manager.db import Db
from sample_manager.migrations import apply_migrations
from sample_manager.repos.arrangement_repo import ArrangementRepo
from sample_manager.repos.library_root_repo import LibraryRootRepo
from sample_manager.repos.sample_repo import SampleRepo
from sample_manager.profiles import ARRANGEMENT_PROFILES_FILENAME
from sample_manager.profiles import EXPORT_PROFILES_FILENAME
from sample_manager.exit_codes import (
    ERROR_CONSTRAINT_VIOLATION,
    ERROR_INVALID_ARGS,
    ERROR_PARTIAL_OPERATION,
    ERROR_SAFETY_REFUSAL,
)


def _write_yaml(filepath, data):
    with open(filepath, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


@pytest.fixture
def setup_config(tmp_path, monkeypatch):
    config_dir = tmp_path / ".sample_manager"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    db_path = tmp_path / "test.sqlite3"

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()

    config_data = {
        "db_path": str(db_path),
        "library_roots": [],
        "default_library_root": None,
        "profiles_dir": str(profiles_dir),
        "defaults": {
            "export_mode": "copy",
            "collision_policy": "suffix",
            "on_violation": "autofix",
            "preview_format": "table",
            "confirmations": True,
        },
    }
    _write_yaml(config_path, config_data)

    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    return db_path, profiles_dir


def _seed_samples(db_path, tmp_path):
    with Db(db_path) as db:
        apply_migrations(db)
        root_dir = tmp_path / "lib"
        root_dir.mkdir(exist_ok=True)
        root = LibraryRootRepo(db).get_or_create(str(root_dir))
        sample_repo = SampleRepo(db)
        s1 = sample_repo.upsert(root["id"], "kick.wav", "kick.wav")
        s2 = sample_repo.upsert(root["id"], "snare.wav", "snare.wav")
        return s1["id"], s2["id"]


def _write_export_profile(profiles_dir):
    _write_yaml(
        profiles_dir / EXPORT_PROFILES_FILENAME,
        [
            {
                "name": "default-export",
                "max_depth": 5,
                "max_filename_len": 128,
                "illegal_chars": '<>:"/\\|?*',
                "replace_char": "_",
                "case_policy": "preserve",
                "path_sep_policy": "posix",
                "on_violation": "autofix",
            }
        ],
    )


class TestArrangementList:
    def test_empty(self, cli_runner, setup_config):
        _, _ = setup_config
        result = cli_runner.invoke(app, ["arrangement", "list"])
        assert result.exit_code == 0
        assert "No arrangements found" in result.output

    def test_human_output(self, cli_runner, setup_config):
        db_path, _ = setup_config
        with Db(db_path) as db:
            apply_migrations(db)
            repo = ArrangementRepo(db)
            repo.create("Studio A", "default-monolithic")
            repo.create("Studio B", "vendor-hierarchy")

        result = cli_runner.invoke(app, ["arrangement", "list"])
        assert result.exit_code == 0
        assert "Arrangements (2)" in result.output
        assert "Studio A" in result.output
        assert "default-monolithic" in result.output
        assert "samples=0" in result.output

    def test_json_output(self, cli_runner, setup_config):
        db_path, _ = setup_config
        with Db(db_path) as db:
            apply_migrations(db)
            repo = ArrangementRepo(db)
            repo.create("Export Pack", "default-monolithic")

        result = cli_runner.invoke(app, ["arrangement", "list", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        assert len(payload) == 1
        assert payload[0]["name"] == "Export Pack"
        assert payload[0]["profile_name"] == "default-monolithic"

    def test_no_config(self, cli_runner, monkeypatch, tmp_path):
        fake_path = tmp_path / "missing" / "config.yaml"
        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", fake_path)
        result = cli_runner.invoke(app, ["arrangement", "list"])
        assert result.exit_code != 0
        assert "Config not found" in result.output


class TestArrangementCreate:
    def test_create_empty_selection(self, cli_runner, setup_config):
        db_path, profiles_dir = setup_config
        _write_yaml(
            profiles_dir / ARRANGEMENT_PROFILES_FILENAME,
            [
                {
                    "name": "default-monolithic",
                    "layout_mode": "monolithic",
                    "naming_template": "{category}/{name}",
                    "collision_policy": "suffix",
                }
            ],
        )

        result = cli_runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "My Set",
                "--profile",
                "default-monolithic",
            ],
        )
        assert result.exit_code == 0
        assert "Created arrangement 'My Set'" in result.output

        with Db(db_path) as db:
            apply_migrations(db)
            rows = db.fetchall("SELECT * FROM arrangement")
            assert len(rows) == 1
            attachments = db.fetchval("SELECT COUNT(*) FROM arrangement_sample")
            assert attachments == 0

    def test_create_with_from_ids_csv(self, cli_runner, setup_config, tmp_path):
        db_path, profiles_dir = setup_config
        _write_yaml(
            profiles_dir / ARRANGEMENT_PROFILES_FILENAME,
            [
                {
                    "name": "default-monolithic",
                    "layout_mode": "monolithic",
                    "naming_template": "{category}/{name}",
                    "collision_policy": "suffix",
                }
            ],
        )
        s1, s2 = _seed_samples(db_path, tmp_path)

        result = cli_runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "Drum Set",
                "--profile",
                "default-monolithic",
                "--from-ids",
                f"{s1},{s2}",
            ],
        )
        assert result.exit_code == 0
        assert "samples=2" in result.output

    def test_create_with_from_search(self, cli_runner, setup_config, tmp_path):
        db_path, profiles_dir = setup_config
        _write_yaml(
            profiles_dir / ARRANGEMENT_PROFILES_FILENAME,
            [
                {
                    "name": "default-monolithic",
                    "layout_mode": "monolithic",
                    "naming_template": "{category}/{name}",
                    "collision_policy": "suffix",
                }
            ],
        )
        _seed_samples(db_path, tmp_path)

        result = cli_runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "Kick Set",
                "--profile",
                "default-monolithic",
                "--from-search",
                "kick",
            ],
        )
        assert result.exit_code == 0
        assert "samples=1" in result.output

    def test_create_json_output(self, cli_runner, setup_config):
        _, profiles_dir = setup_config
        _write_yaml(
            profiles_dir / ARRANGEMENT_PROFILES_FILENAME,
            [
                {
                    "name": "default-monolithic",
                    "layout_mode": "monolithic",
                    "naming_template": "{category}/{name}",
                    "collision_policy": "suffix",
                }
            ],
        )

        result = cli_runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "Json Set",
                "--profile",
                "default-monolithic",
                "--json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["name"] == "Json Set"
        assert payload["profile_name"] == "default-monolithic"
        assert payload["samples_attached"] == 0

    def test_create_fails_if_profile_missing(self, cli_runner, setup_config):
        result = cli_runner.invoke(
            app,
            ["arrangement", "create", "Bad", "--profile", "missing-profile"],
        )
        assert result.exit_code == ERROR_INVALID_ARGS
        assert "profile not found" in result.output

    def test_create_fails_if_sample_id_missing(
        self, cli_runner, setup_config, tmp_path
    ):
        db_path, profiles_dir = setup_config
        _write_yaml(
            profiles_dir / ARRANGEMENT_PROFILES_FILENAME,
            [
                {
                    "name": "default-monolithic",
                    "layout_mode": "monolithic",
                    "naming_template": "{category}/{name}",
                    "collision_policy": "suffix",
                }
            ],
        )
        _seed_samples(db_path, tmp_path)

        result = cli_runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "Bad IDs",
                "--profile",
                "default-monolithic",
                "--from-ids",
                "999999",
            ],
        )
        assert result.exit_code == ERROR_INVALID_ARGS
        assert "sample ids not found" in result.output

    def test_create_fails_on_duplicate_name(self, cli_runner, setup_config):
        _, profiles_dir = setup_config
        _write_yaml(
            profiles_dir / ARRANGEMENT_PROFILES_FILENAME,
            [
                {
                    "name": "default-monolithic",
                    "layout_mode": "monolithic",
                    "naming_template": "{category}/{name}",
                    "collision_policy": "suffix",
                }
            ],
        )
        first = cli_runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "Duplicate",
                "--profile",
                "default-monolithic",
            ],
        )
        assert first.exit_code == 0

        second = cli_runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "duplicate",
                "--profile",
                "default-monolithic",
            ],
        )
        assert second.exit_code == ERROR_CONSTRAINT_VIOLATION

    def test_create_from_selection(self, cli_runner, setup_config, tmp_path):
        db_path, profiles_dir = setup_config
        _write_yaml(
            profiles_dir / ARRANGEMENT_PROFILES_FILENAME,
            [
                {
                    "name": "default-monolithic",
                    "layout_mode": "monolithic",
                    "naming_template": "{name}",
                    "collision_policy": "suffix",
                }
            ],
        )
        s1, _ = _seed_samples(db_path, tmp_path)
        cli_runner.invoke(app, ["selection", "add", "--ids", str(s1)])
        result = cli_runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "From Selection",
                "--profile",
                "default-monolithic",
                "--from-selection",
            ],
        )
        assert result.exit_code == 0
        assert "samples=1" in result.output


class TestArrangementShowAddRemovePreview:
    def _setup(self, setup_config, tmp_path):
        db_path, profiles_dir = setup_config
        _write_yaml(
            profiles_dir / ARRANGEMENT_PROFILES_FILENAME,
            [
                {
                    "name": "default-monolithic",
                    "layout_mode": "monolithic",
                    "naming_template": "{name}",
                    "collision_policy": "suffix",
                }
            ],
        )
        _write_export_profile(profiles_dir)
        s1, s2 = _seed_samples(db_path, tmp_path)
        return db_path, profiles_dir, s1, s2

    def test_show(self, cli_runner, setup_config, tmp_path):
        _, _, s1, _ = self._setup(setup_config, tmp_path)
        cli_runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "Show Me",
                "--profile",
                "default-monolithic",
                "--from-ids",
                str(s1),
            ],
        )
        result = cli_runner.invoke(app, ["arrangement", "show", "Show Me", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["name"] == "Show Me"
        assert payload["sample_count"] == 1

    def test_add_and_remove(self, cli_runner, setup_config, tmp_path):
        _, _, s1, s2 = self._setup(setup_config, tmp_path)
        cli_runner.invoke(
            app,
            ["arrangement", "create", "Edit Me", "--profile", "default-monolithic"],
        )
        add_res = cli_runner.invoke(
            app,
            ["arrangement", "add", "Edit Me", "--ids", f"{s1},{s2}", "--json"],
        )
        assert add_res.exit_code == 0
        add_payload = json.loads(add_res.output)
        assert add_payload["added"] == 2

        rm_res = cli_runner.invoke(
            app,
            ["arrangement", "remove", "Edit Me", "--ids", str(s1), "--json"],
        )
        assert rm_res.exit_code == 0
        rm_payload = json.loads(rm_res.output)
        assert rm_payload["removed"] == 1
        assert rm_payload["sample_count"] == 1

    def test_preview_deterministic_json(self, cli_runner, setup_config, tmp_path):
        _, _, s1, s2 = self._setup(setup_config, tmp_path)
        cli_runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "Preview Me",
                "--profile",
                "default-monolithic",
                "--from-ids",
                f"{s2},{s1}",
            ],
        )
        args = [
            "arrangement",
            "preview",
            "Preview Me",
            "--export-profile",
            "default-export",
            "--format",
            "json",
        ]
        one = cli_runner.invoke(app, args)
        two = cli_runner.invoke(app, args)
        assert one.exit_code == 0
        assert two.exit_code == 0
        assert one.output == two.output


class TestExportAndRevert:
    def _setup(self, setup_config, tmp_path, cli_runner):
        db_path, profiles_dir = setup_config
        _write_yaml(
            profiles_dir / ARRANGEMENT_PROFILES_FILENAME,
            [
                {
                    "name": "default-monolithic",
                    "layout_mode": "monolithic",
                    "naming_template": "{name}",
                    "collision_policy": "suffix",
                }
            ],
        )
        _write_export_profile(profiles_dir)
        s1, _ = _seed_samples(db_path, tmp_path)
        cli_runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "Export Me",
                "--profile",
                "default-monolithic",
                "--from-ids",
                str(s1),
            ],
        )

    def test_export_requires_confirm(self, cli_runner, setup_config, tmp_path):
        self._setup(setup_config, tmp_path, cli_runner)
        out_dir = tmp_path / "exports"
        result = cli_runner.invoke(
            app,
            ["export", "Export Me", "--to", str(out_dir)],
        )
        assert result.exit_code == ERROR_SAFETY_REFUSAL

    def test_export_dry_run_and_revert_dry_run(self, cli_runner, setup_config, tmp_path):
        self._setup(setup_config, tmp_path, cli_runner)
        out_dir = tmp_path / "exports"
        export_res = cli_runner.invoke(
            app,
            [
                "export",
                "Export Me",
                "--to",
                str(out_dir),
                "--dry-run",
                "--json",
            ],
        )
        assert export_res.exit_code == 0
        export_payload = json.loads(export_res.output)
        export_id = export_payload["export_id"]
        assert export_payload["dry_run"] is True

        revert_res = cli_runner.invoke(
            app,
            ["revert", "--export-id", str(export_id), "--dry-run", "--json"],
        )
        assert revert_res.exit_code == 0
        rev_payload = json.loads(revert_res.output)
        assert rev_payload["result"]["export_id"] == export_id

    def test_export_and_revert_real(self, cli_runner, setup_config, tmp_path):
        self._setup(setup_config, tmp_path, cli_runner)
        out_dir = tmp_path / "exports2"
        export_res = cli_runner.invoke(
            app,
            [
                "export",
                "Export Me",
                "--to",
                str(out_dir),
                "--confirm",
                "--json",
            ],
        )
        assert export_res.exit_code in (0, ERROR_PARTIAL_OPERATION)
        payload = json.loads(export_res.output)
        export_id = payload["export_id"]

        revert_res = cli_runner.invoke(
            app,
            [
                "revert",
                "--export-id",
                str(export_id),
                "--confirm",
                "--json",
            ],
        )
        assert revert_res.exit_code in (0, ERROR_PARTIAL_OPERATION)
