"""E2E CLI tests for profile and export-profile commands (Phase 6).

Tests cover:
- sample profile list (empty, populated, --json)
- sample profile show <name> (found, not found, --json)
- sample export-profile list (empty, populated, --json)
- sample export-profile show <name> (found, not found, --json)
- sample init creates profiles directory + example files
"""

import json
import pytest
import yaml
from pathlib import Path

from sample_manager.cli import app
from sample_manager import config as config_module
from sample_manager.profiles import (
    ARRANGEMENT_PROFILES_FILENAME,
    EXPORT_PROFILES_FILENAME,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_arrangement_dict(**overrides) -> dict:
    base = {
        "name": "test-mono",
        "description": "A test monolithic profile",
        "layout_mode": "monolithic",
        "naming_template": "{category}/{name}",
        "collision_policy": "suffix",
        "layout_rules": {"category_map": {"kick": "KICKS"}},
    }
    base.update(overrides)
    return base


def _valid_export_dict(**overrides) -> dict:
    base = {
        "name": "mpc-live",
        "max_depth": 3,
        "max_filename_len": 64,
        "illegal_chars": '<>:"/\\|?*',
        "replace_char": "_",
        "case_policy": "preserve",
        "path_sep_policy": "posix",
        "on_violation": "autofix",
    }
    base.update(overrides)
    return base


def _write_yaml(filepath: Path, data):
    with open(filepath, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


@pytest.fixture
def setup_config(tmp_path, monkeypatch):
    """Set up a temp config dir with profiles_dir pointing to a temp profiles folder.

    Returns (config_path, profiles_dir) for further setup.
    """
    config_dir = tmp_path / ".sample_manager"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()

    config_data = {
        "db_path": str(tmp_path / "test.sqlite3"),
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

    return config_path, profiles_dir


# ---------------------------------------------------------------------------
# sample profile list
# ---------------------------------------------------------------------------


class TestProfileList:
    def test_empty(self, cli_runner, setup_config):
        _, profiles_dir = setup_config
        result = cli_runner.invoke(app, ["profile", "list"])
        assert result.exit_code == 0
        assert "No arrangement profiles found" in result.output

    def test_with_profiles(self, cli_runner, setup_config):
        _, profiles_dir = setup_config
        data = [
            _valid_arrangement_dict(name="mono-1"),
            _valid_arrangement_dict(
                name="hier-1",
                layout_mode="hierarchical",
                description="Hierarchical layout",
            ),
        ]
        _write_yaml(profiles_dir / ARRANGEMENT_PROFILES_FILENAME, data)

        result = cli_runner.invoke(app, ["profile", "list"])
        assert result.exit_code == 0
        assert "Arrangement profiles (2)" in result.output
        assert "mono-1" in result.output
        assert "hier-1" in result.output
        assert "monolithic" in result.output
        assert "hierarchical" in result.output

    def test_json_output(self, cli_runner, setup_config):
        _, profiles_dir = setup_config
        data = [_valid_arrangement_dict(name="json-test")]
        _write_yaml(profiles_dir / ARRANGEMENT_PROFILES_FILENAME, data)

        result = cli_runner.invoke(app, ["profile", "list", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        assert len(payload) == 1
        assert payload[0]["name"] == "json-test"
        assert payload[0]["layout_mode"] == "monolithic"

    def test_json_empty(self, cli_runner, setup_config):
        result = cli_runner.invoke(app, ["profile", "list", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload == []

    def test_no_config(self, cli_runner, monkeypatch, tmp_path):
        fake_path = tmp_path / "nonexistent" / "config.yaml"
        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", fake_path)
        result = cli_runner.invoke(app, ["profile", "list"])
        assert result.exit_code != 0
        assert "Config not found" in result.output


# ---------------------------------------------------------------------------
# sample profile show
# ---------------------------------------------------------------------------


class TestProfileShow:
    def test_found(self, cli_runner, setup_config):
        _, profiles_dir = setup_config
        data = [
            _valid_arrangement_dict(
                name="show-me",
                description="Detailed test",
                layout_rules={"category_map": {"kick": "KICKS"}},
            ),
        ]
        _write_yaml(profiles_dir / ARRANGEMENT_PROFILES_FILENAME, data)

        result = cli_runner.invoke(app, ["profile", "show", "show-me"])
        assert result.exit_code == 0
        assert "show-me" in result.output
        assert "Detailed test" in result.output
        assert "monolithic" in result.output
        assert "suffix" in result.output

    def test_not_found(self, cli_runner, setup_config):
        result = cli_runner.invoke(app, ["profile", "show", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_json_output(self, cli_runner, setup_config):
        _, profiles_dir = setup_config
        data = [_valid_arrangement_dict(name="json-show")]
        _write_yaml(profiles_dir / ARRANGEMENT_PROFILES_FILENAME, data)

        result = cli_runner.invoke(
            app, ["profile", "show", "json-show", "--json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["name"] == "json-show"
        assert payload["layout_mode"] == "monolithic"
        assert payload["collision_policy"] == "suffix"


# ---------------------------------------------------------------------------
# sample export-profile list
# ---------------------------------------------------------------------------


class TestExportProfileList:
    def test_empty(self, cli_runner, setup_config):
        result = cli_runner.invoke(app, ["export-profile", "list"])
        assert result.exit_code == 0
        assert "No export profiles found" in result.output

    def test_with_profiles(self, cli_runner, setup_config):
        _, profiles_dir = setup_config
        data = [
            _valid_export_dict(name="mpc-live"),
            _valid_export_dict(name="sp-404", max_depth=2, case_policy="upper"),
        ]
        _write_yaml(profiles_dir / EXPORT_PROFILES_FILENAME, data)

        result = cli_runner.invoke(app, ["export-profile", "list"])
        assert result.exit_code == 0
        assert "Export profiles (2)" in result.output
        assert "mpc-live" in result.output
        assert "sp-404" in result.output

    def test_json_output(self, cli_runner, setup_config):
        _, profiles_dir = setup_config
        data = [_valid_export_dict(name="json-exp")]
        _write_yaml(profiles_dir / EXPORT_PROFILES_FILENAME, data)

        result = cli_runner.invoke(app, ["export-profile", "list", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        assert len(payload) == 1
        assert payload[0]["name"] == "json-exp"
        assert payload[0]["max_depth"] == 3

    def test_json_empty(self, cli_runner, setup_config):
        result = cli_runner.invoke(app, ["export-profile", "list", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload == []


# ---------------------------------------------------------------------------
# sample export-profile show
# ---------------------------------------------------------------------------


class TestExportProfileShow:
    def test_found(self, cli_runner, setup_config):
        _, profiles_dir = setup_config
        data = [_valid_export_dict(name="show-exp")]
        _write_yaml(profiles_dir / EXPORT_PROFILES_FILENAME, data)

        result = cli_runner.invoke(
            app, ["export-profile", "show", "show-exp"]
        )
        assert result.exit_code == 0
        assert "show-exp" in result.output
        assert "Max depth:" in result.output
        assert "3" in result.output
        assert "64" in result.output
        assert "preserve" in result.output

    def test_not_found(self, cli_runner, setup_config):
        result = cli_runner.invoke(
            app, ["export-profile", "show", "nonexistent"]
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_json_output(self, cli_runner, setup_config):
        _, profiles_dir = setup_config
        data = [
            _valid_export_dict(
                name="json-show-exp",
                case_policy="upper",
                on_violation="fail",
            ),
        ]
        _write_yaml(profiles_dir / EXPORT_PROFILES_FILENAME, data)

        result = cli_runner.invoke(
            app, ["export-profile", "show", "json-show-exp", "--json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["name"] == "json-show-exp"
        assert payload["max_depth"] == 3
        assert payload["case_policy"] == "upper"
        assert payload["on_violation"] == "fail"


# ---------------------------------------------------------------------------
# sample init — profiles directory creation
# ---------------------------------------------------------------------------


class TestInitCreatesProfiles:
    def test_init_creates_profiles_dir(self, cli_runner, monkeypatch, tmp_path):
        """sample init should create the profiles directory and example files."""
        config_dir = tmp_path / ".sample_manager"
        config_path = config_dir / "config.yaml"

        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_DIR", config_dir)
        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

        result = cli_runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Profiles directory ready" in result.output

        # Config should have profiles_dir
        cfg = config_module.load_config(config_path)
        profiles_dir = Path(
            config_module.normalize_path(cfg["profiles_dir"])
        )
        assert profiles_dir.is_dir()

        # Example files should exist
        assert (profiles_dir / ARRANGEMENT_PROFILES_FILENAME).exists()
        assert (profiles_dir / EXPORT_PROFILES_FILENAME).exists()

    def test_init_idempotent(self, cli_runner, monkeypatch, tmp_path):
        """Running init twice should not fail or overwrite profile files."""
        config_dir = tmp_path / ".sample_manager"
        config_path = config_dir / "config.yaml"

        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_DIR", config_dir)
        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

        result1 = cli_runner.invoke(app, ["init"])
        assert result1.exit_code == 0

        result2 = cli_runner.invoke(app, ["init"])
        assert result2.exit_code == 0
        assert "Profiles directory ready" in result2.output
