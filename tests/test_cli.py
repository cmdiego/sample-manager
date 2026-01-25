"""Tests for CLI commands end-to-end."""

import pytest
import json
from pathlib import Path
from typer.testing import CliRunner
from sample_manager.cli import app
from sample_manager import config as config_module
from sample_manager.exit_codes import ERROR_CONFIG_VALIDATION, ERROR_INVALID_ARGS


@pytest.fixture
def runner():
    return CliRunner()


def test_init_creates_config(tmp_home, monkeypatch, runner):
    """Test sample init command creates config."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    result = runner.invoke(app, ["init"])
    
    assert result.exit_code == 0
    assert config_path.exists()
    assert "Created config" in result.stdout


def test_init_idempotent(tmp_home, monkeypatch, runner):
    """Test sample init is idempotent."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    # First run
    result1 = runner.invoke(app, ["init"])
    assert result1.exit_code == 0
    
    # Second run
    result2 = runner.invoke(app, ["init"])
    assert result2.exit_code == 0
    assert "already exists" in result2.stdout


def test_config_show_human_output(tmp_home, monkeypatch, runner):
    """Test config show command (human output)."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["config", "show"])
    
    assert result.exit_code == 0
    assert "db_path:" in result.stdout
    assert "library_roots:" in result.stdout


def test_config_show_json_output(tmp_home, monkeypatch, runner):
    """Test config show --json produces valid JSON."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["config", "show", "--json"])
    
    assert result.exit_code == 0
    
    # Parse JSON
    data = json.loads(result.stdout)
    assert "db_path" in data
    assert "library_roots" in data
    assert "defaults" in data


def test_config_show_without_init(tmp_home, monkeypatch, runner):
    """Test config show fails gracefully without init."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    result = runner.invoke(app, ["config", "show"])
    
    assert result.exit_code == ERROR_INVALID_ARGS
    assert "Config not found" in result.output


def test_config_validate_success(tmp_home, monkeypatch, runner, sample_library_root):
    """Test config validate with valid config."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    runner.invoke(app, ["init"])
    runner.invoke(app, ["config", "add-root", str(sample_library_root)])
    
    result = runner.invoke(app, ["config", "validate"])
    
    assert result.exit_code == 0
    assert "valid" in result.stdout.lower()


def test_config_validate_strict_mode(tmp_home, monkeypatch, runner):
    """Test config validate --strict returns correct exit code."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    runner.invoke(app, ["init"])
    
    # Add invalid library root to cause validation warnings
    cfg = config_module.load_config(config_path)
    cfg["library_roots"] = ["/does/not/exist/path"]
    config_module.save_config(cfg, config_path)
    
    # Should have errors for invalid library root
    result = runner.invoke(app, ["config", "validate", "--strict"])
    
    # Exit code should be 6 on validation failure in strict mode
    assert result.exit_code == ERROR_CONFIG_VALIDATION


def test_config_validate_json(tmp_home, monkeypatch, runner):
    """Test config validate --json produces structured output."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["config", "validate", "--json"])
    
    data = json.loads(result.stdout)
    
    assert "ok" in data
    assert "exit_code" in data
    assert "errors" in data
    assert "warnings" in data
    assert "checked" in data
    assert "effective_config" in data


def test_config_set(tmp_home, monkeypatch, runner):
    """Test config set command."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["config", "set", "defaults.export_mode", "symlink"])
    
    assert result.exit_code == 0
    
    # Verify it was set
    cfg = config_module.load_config(config_path)
    assert cfg["defaults"]["export_mode"] == "symlink"


def test_config_set_bool(tmp_home, monkeypatch, runner):
    """Test config set with boolean value."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["config", "set", "defaults.confirmations", "false"])
    
    assert result.exit_code == 0
    
    cfg = config_module.load_config(config_path)
    assert cfg["defaults"]["confirmations"] is False


def test_config_add_root(tmp_home, monkeypatch, runner, sample_library_root):
    """Test config add-root command."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["config", "add-root", str(sample_library_root)])
    
    assert result.exit_code == 0
    assert "Added" in result.stdout
    
    # Verify it was added
    cfg = config_module.load_config(config_path)
    assert len(cfg["library_roots"]) == 1


def test_config_add_root_with_default(tmp_home, monkeypatch, runner, sample_library_root):
    """Test config add-root --set-default."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    runner.invoke(app, ["init"])
    result = runner.invoke(app, [
        "config", "add-root", str(sample_library_root), "--set-default"
    ])
    
    assert result.exit_code == 0
    
    cfg = config_module.load_config(config_path)
    assert cfg["default_library_root"] is not None


def test_config_add_root_invalid(tmp_home, monkeypatch, runner):
    """Test config add-root with invalid path."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["config", "add-root", "/does/not/exist"])
    
    assert result.exit_code == ERROR_INVALID_ARGS
    assert "does not exist" in result.output


def test_config_remove_root(tmp_home, monkeypatch, runner, sample_library_root):
    """Test config remove-root command."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    runner.invoke(app, ["init"])
    runner.invoke(app, ["config", "add-root", str(sample_library_root)])
    
    result = runner.invoke(app, ["config", "remove-root", str(sample_library_root)])
    
    assert result.exit_code == 0
    assert "Removed" in result.stdout
    
    cfg = config_module.load_config(config_path)
    assert len(cfg["library_roots"]) == 0


def test_config_set_default(tmp_home, monkeypatch, runner, sample_library_root):
    """Test config set-default command."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    runner.invoke(app, ["init"])
    runner.invoke(app, ["config", "add-root", str(sample_library_root)])
    
    result = runner.invoke(app, ["config", "set-default", str(sample_library_root)])
    
    assert result.exit_code == 0
    
    cfg = config_module.load_config(config_path)
    assert cfg["default_library_root"] is not None


def test_config_set_default_not_in_roots(tmp_home, monkeypatch, runner, sample_library_root):
    """Test config set-default fails if path not in roots."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    runner.invoke(app, ["init"])
    
    result = runner.invoke(app, ["config", "set-default", str(sample_library_root)])
    
    assert result.exit_code == ERROR_INVALID_ARGS
    assert "not in library_roots" in result.output
